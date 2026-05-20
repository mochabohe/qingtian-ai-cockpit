"""演示兜底播放器(P0 演示兜底机制)

设计目的:
演示现场风险三连——断网 / LLM 限速 429 / Seedance 服务挂。
绝不允许在用户面前现场调外网 LLM。

启用方式:
    OFFLINE_MODE=true (环境变量) 或 settings.offline_mode

工作原理:
    AgentOrchestrator.run() 入口检测 offline_mode,直接走 FallbackPlayer.replay():
    1. 根据 topic 关键词匹配 _fallback/<stem>.* 三件套(md / json / trace.json)
    2. 按 SSE 协议节奏化回放每步事件:start → step_start → token chunks → step_done → end
    3. 节奏由 trace.json 里每步的 duration_s 决定(整体压缩到 ~12 秒,演示节奏更紧凑)

不假装在线:
    回放时往 state 注入 _is_fallback=true,前端 SSE 收到 'start' 事件 data 中
    含 source='fallback',MissionBar 显示"演示模式 · 使用预热案例"角标。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 兜底文件按主题命中规则:命中关键词 → 用对应 stem
TOPIC_RULES: List[tuple[str, str]] = [
    # (关键词, fallback stem)。匹配顺序从特殊到通用,先匹配中先返回
    ("对标",       "benchmark"),
    ("vs ",        "benchmark"),
    ("vs",         "benchmark"),
    ("Model Y",    "benchmark"),
    ("竞品",       "benchmark"),
    ("比较",       "benchmark"),
    ("售后",       "aftersale_recovery"),
    ("服务网络",   "aftersale_recovery"),
    ("断层",       "aftersale_recovery"),
    ("应急",       "aftersale_recovery"),
    ("复盘",       "aftersale_recovery"),
]
DEFAULT_FALLBACK_STEM = "comprehensive"

# 整体回放压缩到 ~12 秒(单步约 2-3 秒),够看清"流式"过程又不拖
TARGET_TOTAL_SECONDS = 12.0
# 单步最少 1 秒,避免 trace 里某步 duration_s 接近 0 时回放瞬完
MIN_STEP_SECONDS = 1.0


# Runtime override:允许通过 POST /api/system/mode 在运行时切换,无需重启 backend。
# None = 跟随环境变量;True/False = 显式 override。
# 优先级:runtime override > 环境变量 OFFLINE_MODE
_runtime_offline_override: Optional[bool] = None


def is_offline_mode() -> bool:
    """判断当前是否启用演示兜底模式(runtime override > env var)"""
    if _runtime_offline_override is not None:
        return _runtime_offline_override
    val = os.getenv("OFFLINE_MODE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def set_offline_mode(enabled: Optional[bool]) -> None:
    """运行时切换 offline 模式;传 None 恢复跟随环境变量。"""
    global _runtime_offline_override
    _runtime_offline_override = enabled
    logger.info("OFFLINE_MODE runtime override 切换为 %s", _runtime_offline_override)


def _fallback_dir() -> Path:
    from ..core.config import settings
    return Path(settings.report_dir) / "_fallback"


def select_fallback_stem(topic: str) -> str:
    """根据 topic 命中关键词,返回兜底 stem"""
    if not topic:
        return DEFAULT_FALLBACK_STEM
    t = topic.lower()
    for kw, stem in TOPIC_RULES:
        if kw.lower() in t:
            # 检查文件是否存在(避免规则配错指向不存在的 stem)
            if (_fallback_dir() / f"{stem}.md").exists():
                return stem
    return DEFAULT_FALLBACK_STEM


def load_fallback(stem: str) -> Optional[Dict[str, Any]]:
    """加载 _fallback/<stem>.{md,json,trace.json} 三件套"""
    base = _fallback_dir()
    md_path    = base / f"{stem}.md"
    json_path  = base / f"{stem}.json"
    trace_path = base / f"{stem}.trace.json"
    if not md_path.exists() or not trace_path.exists():
        logger.warning("fallback stem %s 不完整: md=%s trace=%s",
                       stem, md_path.exists(), trace_path.exists())
        return None
    try:
        md_text = md_path.read_text(encoding="utf-8")
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        doc_payload = None
        if json_path.exists():
            try:
                doc_payload = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                doc_payload = None
        return {
            "stem": stem,
            "md":   md_text,
            "doc":  doc_payload,
            "trace": trace,
        }
    except Exception:
        logger.exception("加载 fallback %s 失败", stem)
        return None


class FallbackPlayer:
    """兜底播放器:把已有简报按 SSE 协议节奏化回放给前端"""

    def __init__(self, topic: str, queue: asyncio.Queue):
        self.topic = topic
        self._queue = queue
        self.stem = select_fallback_stem(topic)
        self.payload = load_fallback(self.stem)

    @property
    def available(self) -> bool:
        return self.payload is not None

    async def _emit(self, event: str, data: Any) -> None:
        await self._queue.put((event, data))

    def _calc_step_durations(self, steps: List[Dict[str, Any]]) -> List[float]:
        """根据原始 trace 的 duration_s 等比缩放到目标总时长"""
        raw = [max(s.get("duration_s") or 0, MIN_STEP_SECONDS) for s in steps]
        total = sum(raw) or 1.0
        scale = TARGET_TOTAL_SECONDS / total
        return [max(d * scale, MIN_STEP_SECONDS) for d in raw]

    async def replay(self) -> None:
        """主入口:按 SSE 事件流节奏化回放兜底简报"""
        if not self.available:
            await self._emit("error", {"message": "演示兜底案例缺失,请检查 data/reports/_fallback/"})
            await self._queue.put(None)
            return

        try:
            payload = self.payload
            assert payload is not None
            trace = payload["trace"]
            steps: List[Dict[str, Any]] = trace.get("steps") or []
            md_text = payload["md"]

            # 1) start 事件:主动声明 source=fallback 让前端打"演示模式"角标
            await self._emit("start", {
                "topic":       self.topic,
                "total_steps": len(steps),
                "data_file":   None,
                "source":      "fallback",       # 关键标志位
                "fallback_case": self.stem,
            })

            # 2) data_loaded 事件(回放兜底数据描述)
            n_voc = (trace.get("totals") or {}).get("n_voc_total") or 1000
            await self._emit("data_loaded", {
                "file": "(预热案例:主线四份数据集)",
                "rows": (trace.get("totals") or {}).get("n_records_total") or 51000,
                "cols": n_voc,
                "summary": f"使用预热案例「{self.stem}」回放,确保现场零外网依赖",
            })

            # 3) 逐步回放
            durations = self._calc_step_durations(steps)
            for i, (step, dur) in enumerate(zip(steps, durations), 1):
                step_name = step.get("name") or f"step{i}"
                await self._emit("step_start", {
                    "index": i,
                    "name":  step_name,
                    "title": step.get("title") or step_name,
                    "desc":  step.get("desc") or "",
                })

                # 把 step.output 切成 ~30 个 chunk 节奏化吐出
                output = step.get("output") or ""
                if output:
                    n_chunks = max(8, min(40, len(output) // 50))
                    chunk_size = max(1, len(output) // n_chunks)
                    chunk_delay = dur / max(n_chunks, 1)
                    for c_start in range(0, len(output), chunk_size):
                        chunk = output[c_start:c_start + chunk_size]
                        await self._emit("agent_token", {
                            "index": i,
                            "name":  step_name,
                            "text":  chunk,
                        })
                        await asyncio.sleep(chunk_delay)
                else:
                    await asyncio.sleep(dur)

                await self._emit("step_done", {
                    "index":  i,
                    "name":   step_name,
                    "output": output,
                })

            # 4) end 事件:回放原始 markdown
            await self._emit("end", {
                "final":    "已完成(演示模式)",
                "report":   md_text,
                "saved_as": None,                # 演示模式不写盘,避免污染列表
                "source":   "fallback",
                "fallback_case": self.stem,
            })
        except Exception as e:
            logger.exception("fallback replay 失败")
            await self._emit("error", {"message": f"演示模式回放失败: {e}"})
        finally:
            await self._queue.put(None)
