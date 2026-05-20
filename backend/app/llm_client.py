"""
可插拔 LLM 客户端 —— 一套代码适配 OpenAI / 擎天 / Ollama / 任意 OpenAI 兼容 API

特性:
  - 环境变量驱动的 provider 切换（练习用本地，赛场切擎天，一行命令完成）
  - 自动重试（指数退避）+ 可配置超时
  - 流式与非流式两种调用
  - Token 计数 + 成本统计（含累计/单次）
  - 多 provider 适配（统一基于 OpenAI 兼容协议）

依赖:
  pip install openai>=1.50.0 python-dotenv>=1.0.0

最简用法:
  from llm_client import LLMClient
  client = LLMClient.from_env()
  print(client.chat("你好"))
  print(client.usage_summary())
"""

from __future__ import annotations

import os
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterator, Optional, Union, List, Dict, Any

from openai import OpenAI, APIError, APITimeoutError, RateLimitError, APIConnectionError
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# P0: pydantic Settings 会读取 .env,但不会把 LLM_* 写入 os.environ。
# LLMClient 直接用 os.getenv,所以这里显式加载项目根目录 .env,否则现场会退回
# openai/gpt-4o-mini + dummy key,导致 5 步流程第一步 LLM 调用直接失败。
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH, override=False)


# ============================================================================
# 价格表（USD per 1K tokens，仅作参考；实际请以 provider 官网为准）
# 模型名做小写子串匹配，例如 "DeepSeek-V3.2-Exp" 命中 "deepseek-v3"
# ============================================================================
PRICING: Dict[str, tuple] = {
    # OpenAI 官方
    "gpt-4o-mini":          (0.15,  0.60),
    "gpt-4o":               (2.50, 10.00),
    "gpt-4-turbo":          (10.00, 30.00),
    "gpt-3.5-turbo":        (0.50,  1.50),

    # DeepSeek 官方
    "deepseek-reasoner":    (0.55,  2.19),
    "deepseek-chat":        (0.27,  1.10),
    "deepseek-v3":          (0.27,  1.10),

    # 阿里 Qwen 官方
    "qwen-max":             (2.40,  9.60),
    "qwen-plus":            (0.40,  1.20),
    "qwen-turbo":           (0.30,  0.60),
    "qwen2.5-72b":          (0.40,  1.20),
    "qwen3-235b":           (1.00,  4.00),

    # 智谱 GLM
    "glm-4.5":              (0.50,  2.00),
    "glm-4":                (0.10,  0.10),

    # 字节豆包
    "doubao":               (0.30,  0.60),

    # 本地/未定义
    "_default":             (0.0,   0.0),
}


# ============================================================================
# 用量数据结构
# ============================================================================
@dataclass
class UsageRecord:
    """单次调用的用量记录"""
    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    duration_s: float
    success: bool
    error: Optional[str] = None


@dataclass
class UsageStats:
    """累计用量统计"""
    records: List[UsageRecord] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return len(self.records)

    @property
    def success_calls(self) -> int:
        return sum(1 for r in self.records if r.success)

    @property
    def fail_calls(self) -> int:
        return self.total_calls - self.success_calls

    @property
    def total_prompt_tokens(self) -> int:
        return sum(r.prompt_tokens for r in self.records)

    @property
    def total_completion_tokens(self) -> int:
        return sum(r.completion_tokens for r in self.records)

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.records)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.records)

    @property
    def total_duration_s(self) -> float:
        return sum(r.duration_s for r in self.records)

    def summary(self) -> dict:
        return {
            "total_calls":             self.total_calls,
            "success_calls":           self.success_calls,
            "fail_calls":              self.fail_calls,
            "total_prompt_tokens":     self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens":            self.total_tokens,
            "total_cost_usd":          round(self.total_cost_usd, 4),
            "total_duration_s":        round(self.total_duration_s, 2),
            "avg_duration_s":          round(
                self.total_duration_s / max(self.total_calls, 1), 2
            ),
        }


# ============================================================================
# 主客户端
# ============================================================================
class LLMClient:
    """
    可插拔 LLM 客户端

    支持的 provider:
      openai    — 官方 OpenAI
      qingtian  — 东风擎天 AI 中台（OpenAI 兼容）
      ollama    — 本地 Ollama（OpenAI 兼容端点 /v1）
      deepseek  — DeepSeek 官方
      custom    — 任意 OpenAI 兼容 API
    """

    # 各 provider 的默认 base_url；None 表示必须用户提供
    PROVIDER_DEFAULTS: Dict[str, Dict[str, Optional[str]]] = {
        "openai":   {"base_url": "https://api.openai.com/v1",   "api_key": None},
        "qingtian": {"base_url": None,                          "api_key": None},
        "ollama":   {"base_url": "http://localhost:11434/v1",   "api_key": "ollama"},
        "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": None},
        "custom":   {"base_url": None,                          "api_key": None},
    }

    def __init__(
        self,
        provider: str = "openai",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_delay_base: float = 1.5,
        track_usage: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
        api_type: str = "chat_completions",
    ):
        """
        api_type:
          "chat_completions" — 传统 /v1/chat/completions（OpenAI / Ollama / DeepSeek / 大多数代理）
          "responses"        — /v1/responses（gpt-5 / o1 / o3 / 任何代理强制走 responses 的场景）
        """
        defaults = self.PROVIDER_DEFAULTS.get(provider, {})

        self.provider = provider
        self.base_url = base_url or defaults.get("base_url")
        self.api_key = api_key or defaults.get("api_key") or "dummy"
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.track_usage = track_usage
        self.extra_headers = extra_headers or {}
        self.api_type = api_type
        self.usage_stats = UsageStats() if track_usage else None

        if not self.base_url:
            raise ValueError(
                f"provider={provider!r} 需要显式提供 base_url，"
                f"请通过参数或 LLM_BASE_URL 环境变量配置"
            )

        # OpenAI SDK 自带的重试关掉，由本类统一管理
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            max_retries=0,
            default_headers=self.extra_headers or None,
        )

        logger.info(
            "LLMClient 初始化: provider=%s, base_url=%s, model=%s, timeout=%ss",
            provider, self.base_url, model, timeout,
        )

    # ------------------------------------------------------------------
    # 工厂：从环境变量构建
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "LLMClient":
        """
        从环境变量构建客户端

        优先级:运行时 override(core.llm_runtime.set_profile) > 环境变量
        切换 profile 后只覆盖 provider/base_url/api_key/model/api_type 五个字段,
        timeout / max_retries / extra_headers 仍然走环境变量,保持现场调优口径不变。

        环境变量:
          LLM_PROVIDER       openai / qingtian / ollama / deepseek / custom
          LLM_BASE_URL       覆盖 provider 默认 URL（custom/qingtian 必填）
          LLM_API_KEY        API Key（Ollama 可填任意值）
          LLM_MODEL          模型名，例如 DeepSeek-V3.2-Exp
          LLM_TIMEOUT        超时秒数（默认 60）
          LLM_MAX_RETRIES    重试次数（默认 3）
          LLM_EXTRA_HEADERS  额外请求头，JSON 字符串，例如 {"X-Tenant":"voyah"}
        """
        import json

        extra_headers_str = os.getenv("LLM_EXTRA_HEADERS", "").strip()
        extra_headers = json.loads(extra_headers_str) if extra_headers_str else None

        # 运行时 profile 覆盖(由前端 /system/llm-model POST 切换 OR env LLM_PROFILE 指定)
        # current_profile() 内部已处理三级优先级:运行时 override > env LLM_PROFILE > 默认。
        # 注意:必须无条件调用,否则默认 profile 不会生效,会退回本文件
        # provider=openai/model=gpt-4o-mini/dummy key 的旧默认值。
        provider = os.getenv("LLM_PROVIDER", "openai")
        base_url = os.getenv("LLM_BASE_URL") or None
        api_key = os.getenv("LLM_API_KEY") or None
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        api_type = os.getenv("LLM_API_TYPE", "chat_completions")
        try:
            from .core.llm_runtime import current_profile
            p = current_profile()
            provider = p.provider
            base_url = p.base_url
            api_key = p.api_key
            model = p.model
            api_type = p.api_type
        except Exception:
            pass

        return cls(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=float(os.getenv("LLM_TIMEOUT", "60")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            extra_headers=extra_headers,
            api_type=api_type,
        )

    # ------------------------------------------------------------------
    # 公开 API：非流式
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: Union[str, List[Dict[str, str]]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        非流式对话

        messages 可传字符串（自动包装成 user message）或 OpenAI 标准 messages 数组
        返回助手回复字符串
        """
        params = self._build_params(
            messages=self._normalize_messages(messages),
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )
        if self.api_type == "responses":
            return self._with_retry(self._do_chat_responses, params)
        if self.api_type == "messages":
            return self._with_retry(self._do_chat_messages, params)
        return self._with_retry(self._do_chat, params)

    # ------------------------------------------------------------------
    # 公开 API：JSON 模式（业务层封装）
    # ------------------------------------------------------------------
    def chat_json(
        self,
        messages: Union[str, List[Dict[str, str]]],
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: Optional[int] = 2000,
        retry_low_temp: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        强制 JSON 输出 + 业务层兜底重试。

        - 第一次 temperature=temperature
        - JSON 解析失败时,若 retry_low_temp=True 再跑一次 temperature=0.1
        - 两次都失败则抛 ValueError(原始文本截断 200 字)
        """
        import json as _json

        kwargs.setdefault("response_format", {"type": "json_object"})

        attempts = [(temperature, max_tokens)]
        if retry_low_temp:
            attempts.append((0.1, max_tokens))

        last_raw = ""
        last_err: Optional[Exception] = None
        for i, (temp, max_tok) in enumerate(attempts, 1):
            try:
                raw = self.chat(
                    messages,
                    model=model,
                    temperature=temp,
                    max_tokens=max_tok,
                    **kwargs,
                )
                last_raw = raw
                return _json.loads(raw)
            except _json.JSONDecodeError as je:
                last_err = je
                logger.warning(
                    "[chat_json] 第 %d 次 JSON 解析失败 (%s),raw_head=%r",
                    i, je, raw[:120] if isinstance(raw, str) else raw,
                )
                continue
            except Exception:
                raise  # 非 JSON 解析错误直接抛(走 chat 自身的重试链)

        head = last_raw[:200].replace("\n", "\\n") if isinstance(last_raw, str) else "<no-text>"
        raise ValueError(f"chat_json 多次解析失败({last_err}),raw_head={head!r}")

    # ------------------------------------------------------------------
    # 公开 API：流式
    # ------------------------------------------------------------------
    def stream(
        self,
        messages: Union[str, List[Dict[str, str]]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Iterator[str]:
        """
        流式对话，yield 字符串增量

        注意:
          - 流式重试会在"完全失败时"才发生（已开始 yield 后不能重试，否则会重复输出）
          - usage 信息在最后一个 chunk 返回（依赖 stream_options.include_usage）
        """
        params = self._build_params(
            messages=self._normalize_messages(messages),
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        if self.api_type == "responses":
            return self._do_stream_responses(params)
        if self.api_type == "messages":
            return self._do_stream_messages(params)
        # 请求最终 usage chunk，OpenAI 兼容 API 大多支持；不支持的会被忽略
        params.setdefault("stream_options", {"include_usage": True})

        return self._do_stream(params)

    # ------------------------------------------------------------------
    # 内部：构建请求参数
    # ------------------------------------------------------------------
    @staticmethod
    def _build_params(**kwargs) -> Dict[str, Any]:
        # 去掉值为 None 的字段，避免某些 OpenAI 兼容端不接受 null
        return {k: v for k, v in kwargs.items() if v is not None}

    @staticmethod
    def _normalize_messages(
        messages: Union[str, List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        return messages

    # ------------------------------------------------------------------
    # 内部：非流式执行
    # ------------------------------------------------------------------
    def _do_chat(self, params: Dict[str, Any]) -> str:
        start = time.time()
        model = params["model"]
        try:
            resp = self._client.chat.completions.create(**params)
            content = resp.choices[0].message.content or ""
            usage = resp.usage
            self._record_usage(
                model=model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                duration=time.time() - start,
                success=True,
            )
            return content
        except Exception as e:
            self._record_usage(
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                duration=time.time() - start,
                success=False,
                error=f"{type(e).__name__}: {e}",
            )
            raise

    # ------------------------------------------------------------------
    # 内部：流式执行（带重试）
    # ------------------------------------------------------------------
    def _do_stream(self, params: Dict[str, Any]) -> Iterator[str]:
        model = params["model"]
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            start = time.time()
            try:
                stream_resp = self._client.chat.completions.create(**params)
                prompt_tokens = 0
                completion_tokens = 0

                for chunk in stream_resp:
                    if getattr(chunk, "usage", None):
                        prompt_tokens = chunk.usage.prompt_tokens
                        completion_tokens = chunk.usage.completion_tokens
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

                self._record_usage(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration=time.time() - start,
                    success=True,
                )
                return

            except (APITimeoutError, RateLimitError, APIConnectionError) as e:
                last_err = e
                if attempt < self.max_retries:
                    delay = self.retry_delay_base ** attempt
                    logger.warning(
                        "[stream] 第 %d 次失败 (%s)，%.1fs 后重试",
                        attempt + 1, type(e).__name__, delay,
                    )
                    time.sleep(delay)
                    continue
                break

            except APIError as e:
                # 5xx 重试，4xx 直接失败
                if e.status_code and 500 <= e.status_code < 600:
                    last_err = e
                    if attempt < self.max_retries:
                        delay = self.retry_delay_base ** attempt
                        logger.warning(
                            "[stream] 第 %d 次失败 (HTTP %s)，%.1fs 后重试",
                            attempt + 1, e.status_code, delay,
                        )
                        time.sleep(delay)
                        continue
                self._record_usage(
                    model=model, prompt_tokens=0, completion_tokens=0,
                    duration=time.time() - start, success=False,
                    error=f"{type(e).__name__}: {e}",
                )
                raise

        # 重试耗尽
        self._record_usage(
            model=model, prompt_tokens=0, completion_tokens=0,
            duration=0, success=False,
            error=f"重试 {self.max_retries} 次后失败: {last_err}",
        )
        raise last_err  # type: ignore[misc]

    # ------------------------------------------------------------------
    # 内部：通用重试包装（仅用于非流式）
    # ------------------------------------------------------------------
    def _with_retry(self, fn, params: Dict[str, Any]):
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn(params)
            except (APITimeoutError, RateLimitError, APIConnectionError) as e:
                last_err = e
                if attempt < self.max_retries:
                    delay = self.retry_delay_base ** attempt
                    logger.warning(
                        "第 %d 次失败 (%s): %s，%.1fs 后重试",
                        attempt + 1, type(e).__name__, e, delay,
                    )
                    time.sleep(delay)
                    continue
                raise
            except APIError as e:
                if e.status_code and 500 <= e.status_code < 600:
                    last_err = e
                    if attempt < self.max_retries:
                        delay = self.retry_delay_base ** attempt
                        logger.warning(
                            "第 %d 次失败 (HTTP %s): %s，%.1fs 后重试",
                            attempt + 1, e.status_code, e, delay,
                        )
                        time.sleep(delay)
                        continue
                raise
        raise last_err  # type: ignore[misc]

    # ------------------------------------------------------------------
    # 内部：用量记录与成本计算
    # ------------------------------------------------------------------
    def _record_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration: float,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        if not self.track_usage or self.usage_stats is None:
            return
        cost = self._calc_cost(model, prompt_tokens, completion_tokens)
        self.usage_stats.records.append(UsageRecord(
            timestamp=time.time(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            duration_s=duration,
            success=success,
            error=error,
        ))

    @staticmethod
    def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """根据 PRICING 表计算成本（USD）"""
        model_lower = model.lower()
        for key, (in_price, out_price) in PRICING.items():
            if key.startswith("_"):
                continue
            if key.lower() in model_lower:
                return (prompt_tokens * in_price + completion_tokens * out_price) / 1000
        in_price, out_price = PRICING["_default"]
        return (prompt_tokens * in_price + completion_tokens * out_price) / 1000

    # ==================================================================
    # Responses API 适配（gpt-5 / o1 / o3 / 强制走 responses 的代理）
    # ==================================================================
    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        """是否 reasoning 模型（需要特殊 token 预算 + reasoning effort）"""
        m = model.lower()
        return (
            m.startswith("o1") or m.startswith("o3")
            or m.startswith("gpt-5") or m.startswith("gpt5")
            or "reasoner" in m or "reasoning" in m
        )

    def _build_responses_body(self, params: Dict[str, Any], stream: bool) -> Dict[str, Any]:
        """构造 /v1/responses 请求体"""
        body: Dict[str, Any] = {
            "model": params["model"],
            "input": params["messages"],
            "text": {"format": {"type": "text"}},
            "max_output_tokens": params.get("max_tokens") or (4096 if stream else 2048),
        }
        if stream:
            body["stream"] = True
        if self._is_reasoning_model(params["model"]):
            body["reasoning"] = {"effort": "low"}
        return body

    @staticmethod
    def _extract_responses_text(data: Dict[str, Any]) -> str:
        """从 Responses API 响应提取文本，容错多种代理实现"""
        if not isinstance(data, dict):
            return ""

        # 优先 1：顶层 output_text
        ot = data.get("output_text")
        if isinstance(ot, str) and ot.strip():
            return ot
        if isinstance(ot, dict) and isinstance(ot.get("value"), str):
            return ot["value"]

        # 标准结构：output 数组
        parts: List[str] = []
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                t = item.get("type")
                if t == "message" and isinstance(item.get("content"), list):
                    for c in item["content"]:
                        if not isinstance(c, dict):
                            continue
                        if isinstance(c.get("text"), str):
                            parts.append(c["text"])
                        elif isinstance(c.get("text"), dict) and isinstance(c["text"].get("value"), str):
                            parts.append(c["text"]["value"])
                elif t == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])

        # 兜底：choices（部分代理回退到 chat completions 结构）
        if not parts and isinstance(data.get("choices"), list):
            for choice in data["choices"]:
                if isinstance(choice, dict):
                    content = (choice.get("message") or {}).get("content")
                    if isinstance(content, str):
                        parts.append(content)

        # 终极兜底：reasoning summary（reasoning 模型 token 耗尽场景）
        if not parts:
            r = data.get("reasoning") or {}
            summary = r.get("summary")
            if isinstance(summary, list):
                for s in summary:
                    if isinstance(s, dict) and isinstance(s.get("text"), str):
                        parts.append(f"[仅返回推理] {s['text']}")
            elif isinstance(summary, str) and summary.strip():
                parts.append(f"[仅返回推理] {summary}")

        return "".join(parts).strip()

    def _do_chat_responses(self, params: Dict[str, Any]) -> str:
        """走 /v1/responses 非流式"""
        import httpx
        import json as _json

        start = time.time()
        model = params["model"]
        body = self._build_responses_body(params, stream=False)
        url = f"{self.base_url.rstrip('/')}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
                data = r.json()

            text = self._extract_responses_text(data)
            usage = data.get("usage") or {}
            prompt_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0

            self._record_usage(
                model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                duration=time.time() - start, success=True,
            )
            return text
        except Exception as e:
            self._record_usage(
                model=model, prompt_tokens=0, completion_tokens=0,
                duration=time.time() - start, success=False,
                error=f"{type(e).__name__}: {e}",
            )
            raise

    def _do_stream_responses(self, params: Dict[str, Any]) -> Iterator[str]:
        """走 /v1/responses 流式"""
        import httpx
        import json as _json

        model = params["model"]
        body = self._build_responses_body(params, stream=True)
        url = f"{self.base_url.rstrip('/')}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **self.extra_headers,
        }
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            start = time.time()
            try:
                prompt_tokens = 0
                completion_tokens = 0
                with httpx.Client(timeout=self.timeout) as client:
                    with client.stream("POST", url, json=body, headers=headers) as r:
                        if r.status_code >= 400:
                            err_body = r.read().decode("utf-8", errors="ignore")[:500]
                            raise RuntimeError(f"HTTP {r.status_code}: {err_body}")

                        buffer = ""
                        for chunk in r.iter_text():
                            buffer += chunk
                            events = buffer.split("\n\n")
                            buffer = events.pop()
                            for evt in events:
                                data_line = next(
                                    (l for l in evt.split("\n") if l.startswith("data: ")),
                                    None,
                                )
                                if not data_line:
                                    continue
                                data_str = data_line[6:].strip()
                                if not data_str or data_str == "[DONE]":
                                    continue
                                try:
                                    data = _json.loads(data_str)
                                except _json.JSONDecodeError:
                                    continue
                                t = data.get("type")
                                if t == "response.output_text.delta" and isinstance(data.get("delta"), str):
                                    yield data["delta"]
                                elif t == "response.completed":
                                    resp = data.get("response", {}) or {}
                                    u = resp.get("usage") or {}
                                    prompt_tokens = u.get("input_tokens") or u.get("prompt_tokens") or 0
                                    completion_tokens = u.get("output_tokens") or u.get("completion_tokens") or 0
                                elif t == "error":
                                    err_msg = (data.get("error") or {}).get("message", "stream error")
                                    raise RuntimeError(err_msg)

                self._record_usage(
                    model=model, prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration=time.time() - start, success=True,
                )
                return

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_err = e
                if attempt < self.max_retries:
                    delay = self.retry_delay_base ** attempt
                    logger.warning(
                        "[stream-responses] 第 %d 次失败 (%s)，%.1fs 后重试",
                        attempt + 1, type(e).__name__, delay,
                    )
                    time.sleep(delay)
                    continue
                break

        self._record_usage(
            model=model, prompt_tokens=0, completion_tokens=0,
            duration=0, success=False,
            error=f"重试 {self.max_retries} 次后失败: {last_err}",
        )
        if last_err:
            raise last_err

    # ==================================================================
    # Anthropic Messages API 适配 (/v1/messages)
    # 用于 某些 等代理强制限制 Claude 走原生协议的场景
    # ==================================================================
    def _build_messages_body(self, params: Dict[str, Any], stream: bool) -> Dict[str, Any]:
        """构造 /v1/messages 请求体(Anthropic 原生协议)

        与 OpenAI chat.completions 的差异:
          - messages 不允许 role=system,system 提示要单独抽出到顶层 system 字段
          - 必填 max_tokens
        """
        model = params["model"]
        # 模型名规整:某些 习惯前缀 'openai/',messages 端只认裸模型名
        if model.startswith("openai/"):
            model = model[len("openai/"):]
        if model.startswith("anthropic/"):
            model = model[len("anthropic/"):]

        system_parts: List[str] = []
        messages: List[Dict[str, Any]] = []
        for m in params["messages"]:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                if isinstance(content, str) and content.strip():
                    system_parts.append(content)
                continue
            if role not in ("user", "assistant"):
                role = "user"
            messages.append({"role": role, "content": content})

        body: Dict[str, Any] = {
            "model": model,
            "max_tokens": params.get("max_tokens") or 2048,
            "messages": messages,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if "temperature" in params:
            body["temperature"] = params["temperature"]
        if stream:
            body["stream"] = True
        return body

    def _messages_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            **self.extra_headers,
        }

    def _do_chat_messages(self, params: Dict[str, Any]) -> str:
        """走 /v1/messages 非流式"""
        import httpx

        start = time.time()
        model = params["model"]
        body = self._build_messages_body(params, stream=False)
        url = f"{self.base_url.rstrip('/')}/messages"
        headers = self._messages_headers()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
                data = r.json()

            parts: List[str] = []
            for block in data.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    txt = block.get("text", "")
                    if isinstance(txt, str):
                        parts.append(txt)
            text = "".join(parts).strip()

            usage = data.get("usage") or {}
            prompt_tokens = usage.get("input_tokens") or 0
            completion_tokens = usage.get("output_tokens") or 0

            self._record_usage(
                model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                duration=time.time() - start, success=True,
            )
            return text
        except Exception as e:
            self._record_usage(
                model=model, prompt_tokens=0, completion_tokens=0,
                duration=time.time() - start, success=False,
                error=f"{type(e).__name__}: {e}",
            )
            raise

    def _do_stream_messages(self, params: Dict[str, Any]) -> Iterator[str]:
        """走 /v1/messages 流式 (SSE)"""
        import httpx
        import json as _json

        model = params["model"]
        body = self._build_messages_body(params, stream=True)
        url = f"{self.base_url.rstrip('/')}/messages"
        headers = self._messages_headers()
        headers["Accept"] = "text/event-stream"
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            start = time.time()
            try:
                prompt_tokens = 0
                completion_tokens = 0
                with httpx.Client(timeout=self.timeout) as client:
                    with client.stream("POST", url, json=body, headers=headers) as r:
                        if r.status_code >= 400:
                            err_body = r.read().decode("utf-8", errors="ignore")[:500]
                            raise RuntimeError(f"HTTP {r.status_code}: {err_body}")

                        buffer = ""
                        for chunk in r.iter_text():
                            buffer += chunk
                            events = buffer.split("\n\n")
                            buffer = events.pop()
                            for evt in events:
                                data_line = next(
                                    (l for l in evt.split("\n") if l.startswith("data: ")),
                                    None,
                                )
                                if not data_line:
                                    continue
                                data_str = data_line[6:].strip()
                                if not data_str or data_str == "[DONE]":
                                    continue
                                try:
                                    data = _json.loads(data_str)
                                except _json.JSONDecodeError:
                                    continue
                                t = data.get("type")
                                if t == "content_block_delta":
                                    delta = data.get("delta") or {}
                                    if delta.get("type") == "text_delta":
                                        text = delta.get("text") or ""
                                        if text:
                                            yield text
                                elif t == "message_start":
                                    u = (data.get("message") or {}).get("usage") or {}
                                    prompt_tokens = u.get("input_tokens") or 0
                                elif t == "message_delta":
                                    u = data.get("usage") or {}
                                    if u.get("output_tokens") is not None:
                                        completion_tokens = u.get("output_tokens")
                                elif t == "error":
                                    err_msg = (data.get("error") or {}).get("message", "stream error")
                                    raise RuntimeError(err_msg)

                self._record_usage(
                    model=model, prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration=time.time() - start, success=True,
                )
                return

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_err = e
                if attempt < self.max_retries:
                    delay = self.retry_delay_base ** attempt
                    logger.warning(
                        "[stream-messages] 第 %d 次失败 (%s)，%.1fs 后重试",
                        attempt + 1, type(e).__name__, delay,
                    )
                    time.sleep(delay)
                    continue
                break

        self._record_usage(
            model=model, prompt_tokens=0, completion_tokens=0,
            duration=0, success=False,
            error=f"重试 {self.max_retries} 次后失败: {last_err}",
        )
        if last_err:
            raise last_err

    # ------------------------------------------------------------------
    # 公开 API：用量统计
    # ------------------------------------------------------------------
    def usage_summary(self) -> dict:
        """累计用量摘要"""
        if not self.usage_stats:
            return {}
        return self.usage_stats.summary()

    def last_usage(self) -> Optional[UsageRecord]:
        """最近一次调用的用量"""
        if not self.usage_stats or not self.usage_stats.records:
            return None
        return self.usage_stats.records[-1]

    def reset_usage(self) -> None:
        """清空累计用量"""
        if self.usage_stats:
            self.usage_stats = UsageStats()


# ============================================================================
# 模块级便捷函数（用默认 client）
# ============================================================================
_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    """获取/创建默认 client（懒加载，从环境变量读配置）"""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient.from_env()
    return _default_client


def chat(messages: Union[str, List[Dict[str, str]]], **kwargs) -> str:
    """快捷调用：使用默认 client 进行非流式对话"""
    return get_default_client().chat(messages, **kwargs)


def stream(messages: Union[str, List[Dict[str, str]]], **kwargs) -> Iterator[str]:
    """快捷调用：使用默认 client 进行流式对话"""
    return get_default_client().stream(messages, **kwargs)


def usage_summary() -> dict:
    """快捷调用：默认 client 的用量统计"""
    return get_default_client().usage_summary()
