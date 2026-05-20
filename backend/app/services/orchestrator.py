"""5 子 Agent 编排器（线性状态机，模拟 LangGraph 风格，流式 SSE 输出）"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from ..core.config import settings
from ..llm_client import LLMClient
from .agents import AGENT_DEFS
from .briefing_schema import (
    BriefingDoc,
    parse_briefing,
    parse_compliance_stat,
    render_to_markdown,
)

logger = logging.getLogger(__name__)


# 内部技术字段脱敏:trace 里 step.output 含 silhouette / RAG score / TF-IDF 等
# 这些是工程实现细节,对外展示时易被用户追问"模型为什么这么差"
# 用业务可读口径替换数字
_TECH_PATTERNS = [
    # silhouette=0.019 / silhouette score 0.014 等
    (re.compile(r"silhouette[^\d\-]*[-+]?\d*\.?\d+", re.IGNORECASE), "聚类质量评估"),
    (re.compile(r"score\s*=\s*[-+]?\d*\.?\d+", re.IGNORECASE), "score=已脱敏"),
    (re.compile(r"\(score=[-+]?\d*\.?\d+\)", re.IGNORECASE), ""),
    (re.compile(r"silhouette\b", re.IGNORECASE), "聚类质量"),
]


def _sanitize_trace_step(step: Dict[str, Any]) -> Dict[str, Any]:
    """对单条 trace step 脱敏:仅处理 output 字符串内的内部技术字段"""
    out = dict(step)
    text = out.get("output") or ""
    if isinstance(text, str) and text:
        for pat, repl in _TECH_PATTERNS:
            text = pat.sub(repl, text)
        out["output"] = text
        out["output_len"] = len(text)
    return out


def _dumps_or_default(value: Any, default: str) -> str:
    """将 dict/list 序列化为 JSON 字符串(ensure_ascii=False),其他类型直接转字符串。"""
    if value in (None, "", "(待生成)"):
        return default
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value)


class AgentOrchestrator:
    """
    线性 5 步编排器：每个 Agent 真实调用 LLM 并流式返回 token
    在 analyzer 步骤前会自动跑 pandas 真实数据分析（如果指定了 data_file）

    事件流（按出现顺序）：
      start         编排开始       {topic, total_steps, data_file?}
      data_loaded   真实数据已加载 {file, rows, cols}（仅 analyzer 前）
      step_start    某步骤开始     {index, name, title, desc}
      agent_token   LLM 流式增量   {index, name, text}
      step_done     步骤完成       {index, name, output}
      publish_pushed 飞书推送结果   {ok, channel, error?}（仅 webhook 已配且非 OFFLINE_MODE）
      end           编排完成       {final, report}
      error         全局异常       {message}
      step_error    单步异常       {index, name, message}
    """

    def __init__(self, llm: LLMClient, data_file: Optional[str] = None):
        self.llm = llm
        self.data_file = data_file
        # Agent 全链路追溯:每步开始/结束时间、产出长度、token 数、调用工具
        self.trace: list[Dict[str, Any]] = []
        # state 内可能混存字符串(SSE 流式聚合)与 dict(JSON 解析后),按 key 区分
        self.state: Dict[str, Any] = {}
        self._queue: asyncio.Queue = asyncio.Queue()

    # ---------- 公开 API ----------
    async def run(self, topic: str) -> None:
        # 演示兜底:OFFLINE_MODE=true 时不调外网 LLM,直接走 FallbackPlayer 回放
        # 这是演示现场翻车的核心防线(断网/限速/Seedance 挂均靠这条兜底)
        from .fallback_player import is_offline_mode, FallbackPlayer
        if is_offline_mode():
            logger.info("OFFLINE_MODE 启用,走 FallbackPlayer 回放,topic=%s", topic)
            self.state["topic"] = topic
            player = FallbackPlayer(topic, self._queue)
            await player.replay()
            return

        try:
            self.state["topic"] = topic
            await self._emit("start", {
                "topic": topic,
                "total_steps": len(AGENT_DEFS),
                "data_file": self.data_file,
            })

            for i, (name, title, desc, prompt_tmpl, out_key) in enumerate(AGENT_DEFS, 1):
                # analyzer 步骤前先跑真实数据分析（如果有数据文件）
                if name == "analyzer":
                    await self._maybe_run_real_analysis()
                await self._run_one(i, name, title, desc, prompt_tmpl, out_key)

            # 自动保存简报到 report_dir
            saved_filename = await self._save_report()

            # 真实推送到飞书群机器人(webhook 未配置或 OFFLINE_MODE 时静默跳过)
            await self._maybe_push_to_feishu(saved_filename)

            await self._emit("end", {
                "final": self.state.get("publish_status", "已完成"),
                "report": self.state.get("report_md", ""),
                "saved_as": saved_filename,
            })
        except Exception as e:
            logger.exception("orchestrator 运行失败")
            await self._emit("error", {"message": str(e)})
        finally:
            await self._queue.put(None)

    async def stream_events(self) -> AsyncGenerator[Tuple[str, Any], None]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    # ---------- 内部 ----------
    async def _emit(self, event: str, data: Any) -> None:
        await self._queue.put((event, data))

    async def _save_report(self) -> Optional[str]:
        """
        编排完成时装配 BriefingDoc + 双写 *.json(源) 与 *.md(投影)。
        返回主文件名(不含扩展名);兼容前端旧逻辑,会同时返回 .md 文件名做向下兼容。
        """
        try:
            report_dir = Path(settings.report_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            topic = str(self.state.get("topic", "report"))
            safe_topic = "".join(c for c in topic if c.isalnum() or c in "_-").strip()[:30] or "report"
            stem = f"{ts}_{safe_topic}"

            doc = self._assemble_briefing_doc()
            # 三写: *.json (结构化源)
            json_path = report_dir / f"{stem}.json"
            json_path.write_text(
                doc.model_dump_json(indent=2, exclude_none=False),
                encoding="utf-8",
            )
            # 三写: *.md (markdown 投影,向下兼容历史列表/复制粘贴)
            md_text = render_to_markdown(doc)
            md_path = report_dir / f"{stem}.md"
            md_path.write_text(md_text, encoding="utf-8")
            # 三写: *.trace.json (Agent 全链路追溯,供 ReportPreview 全链路 tab 展示)
            try:
                trace_path = report_dir / f"{stem}.trace.json"
                # 对 step.output 做脱敏:剔除内部技术指标(silhouette / RAG score 等)
                # 这些值前端展示给用户时容易引导问"模型为什么这么差",对外口径以业务数字为准
                sanitized_steps = [_sanitize_trace_step(s) for s in self.trace]
                trace_payload = {
                    "topic":        str(self.state.get("topic", "")),
                    "data_file":    self.data_file,
                    "audit_id":     doc.meta.audit_id if doc.meta else None,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "steps":        sanitized_steps,
                    "totals": {
                        "n_steps":       len(self.trace),
                        "duration_s":    round(sum(s.get("duration_s") or 0 for s in self.trace), 2),
                        "tokens_prompt":     sum((s.get("tokens") or {}).get("prompt") or 0 for s in self.trace),
                        "tokens_completion": sum((s.get("tokens") or {}).get("completion") or 0 for s in self.trace),
                    },
                }
                trace_path.write_text(
                    json.dumps(trace_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                logger.exception("写 .trace.json 失败,简报本身已落盘")

            # 把投影的 markdown 回写到 state,让 SSE end 事件能拿到结构化产物
            self.state["report_md"] = md_text
            return f"{stem}.md"
        except Exception:
            logger.exception("装配/保存简报失败,降级为单写 markdown")
            return await self._save_markdown_fallback()

    async def _save_markdown_fallback(self) -> Optional[str]:
        """装配失败时的兜底:把 writer 流式输出的原始文本当 markdown 写入 *.md"""
        report_md = str(self.state.get("report_md", "")).strip()
        if not report_md:
            return None
        try:
            report_dir = Path(settings.report_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            topic = str(self.state.get("topic", "report"))
            safe_topic = "".join(c for c in topic if c.isalnum() or c in "_-").strip()[:30] or "report"
            filename = f"{ts}_{safe_topic}.md"
            (report_dir / filename).write_text(report_md, encoding="utf-8")
            return filename
        except Exception:
            logger.exception("兜底保存 markdown 失败")
            return None

    async def _maybe_push_to_feishu(self, saved_filename: Optional[str]) -> None:
        """publisher 步完成 + 简报落盘后, 真实推送到飞书群机器人。

        - webhook 未配 / OFFLINE_MODE → 静默跳过(不 emit, 不报错)
        - 飞书 API 失败 → emit 一个 publish_pushed 事件标记 ok=false, 不让主链路挂
        - 成功 → emit publish_pushed 事件, 前端可显示"已推送至飞书群"
        """
        from . import feishu_bot

        if not feishu_bot.is_enabled():
            return

        # 摘要优先用结构化 BriefingDoc 的 executive_summary, 拿不到时退化为原始 publish_status
        # (publish_status 是 LLM 输出的"模拟发布报告", 内容也能看; 但 executive_summary 更精炼)
        topic = str(self.state.get("topic", "")).strip()
        title = topic or "智擎参谋·经营简报"
        summary = ""
        try:
            doc = self._assemble_briefing_doc()
            if doc.executive_summary:
                summary = doc.executive_summary
            if doc.meta and doc.meta.title:
                title = doc.meta.title
        except Exception:
            logger.exception("装配 BriefingDoc 取摘要失败, 降级到 publish_status")
        if not summary:
            summary = str(self.state.get("publish_status", ""))[:1500]

        # 飞书 SDK 同步阻塞, 用 run_in_executor 避免拖住事件循环(8s 超时已设)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: feishu_bot.send_briefing_card(
                title=title,
                summary=summary,
                topic=topic,
                saved_filename=saved_filename,
            ),
        )
        await self._emit("publish_pushed", {
            "ok":       bool(result.get("ok")),
            "channel":  "feishu",
            "error":    result.get("error"),
        })

    def _assemble_briefing_doc(self) -> BriefingDoc:
        """
        把 analyzer_json_dict + writer_json_dict + compliance 文本装配成 BriefingDoc。
        强制走双层合规:
          第 1 层(本地正则) - sanitize_dict 递归脱敏 analyzer/writer 全部文本
          第 2 层(LLM 复审) - parse_compliance_stat 解析 compliance step 的 LLM 输出
        最终 Compliance 字段用"本地命中数 + LLM 发现项"合并,本地优先(确定性强)。
        """
        from . import compliance as local_compliance

        analyzer_dict_raw = self.state.get("analyzer_json_dict") or {}
        writer_dict_raw = self.state.get("writer_json_dict") or {}
        compliance_text = str(self.state.get("compliance", ""))

        # 第 1 层:本地正则扫描(永远跑,识别风险点 + LLM 复审用)
        local_report = local_compliance.scan(
            json.dumps(
                {"analyzer": analyzer_dict_raw, "writer": writer_dict_raw},
                ensure_ascii=False,
            )
        )
        # 是否真实修改文本由 COMPLIANCE_DRY_RUN 决定:
        # - dry-run=true(默认演示场景):项目数据本就已脱敏,不再做假脱敏
        # - dry-run=false(生产场景):真实改文本(443.37万 → 约443万 等)
        analyzer_dict = local_compliance.sanitize_dict_or_skip(analyzer_dict_raw)
        writer_dict = local_compliance.sanitize_dict_or_skip(writer_dict_raw)

        # 第 2 层:LLM 复审(语义级,如竞品负面/未公开商业策略)
        llm_compliance = parse_compliance_stat(compliance_text)

        # 合并:本地命中数 + LLM 命中数,findings 拼接(本地在前,LLM 在后)
        local_findings = [
            f"{f.label}: {f.matched} → {f.masked}" for f in local_report.findings[:15]
        ]
        merged_findings = local_findings + list(llm_compliance.findings)
        merged_masked = local_report.masked_field_count + llm_compliance.masked_field_count
        merged_total = max(
            local_report.total_field_count,
            llm_compliance.total_field_count,
            merged_masked,
        )
        compliance = type(llm_compliance)(
            masked_field_count=merged_masked,
            total_field_count=merged_total,
            findings=merged_findings,
            mode=("dry_run" if local_compliance.is_dry_run() else "production"),
        )

        topic = str(self.state.get("topic", "决策简报"))
        meta = {
            "title": topic,
            "topic": topic,
            "period": datetime.now().strftime("%Y-%m"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "audit_id": f"AUD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
        }

        payload: Dict[str, Any] = {
            "meta": meta,
            "cover": {
                "headline": (writer_dict.get("cover") or {}).get("headline", topic),
                "kpi_strip": analyzer_dict.get("kpi_strip") or [],
            },
            "executive_summary": writer_dict.get("executive_summary", ""),
            "sections": analyzer_dict.get("sections") or [],
            "actions": writer_dict.get("actions") or [],
            "compliance": compliance.model_dump(),
        }

        # P0-3 洞察证据链:把 briefing_analytics 算出的真实数据转证据池,
        # 启发式注入到 KPI/sections/actions 的 evidence 字段。
        # 注意:evidence 由算法层确定性生成,LLM 不参与,杜绝幻觉。
        try:
            analysis_brief = self.state.get("analysis_brief")
            if isinstance(analysis_brief, dict):
                from . import evidence_builder
                evidence_pool = evidence_builder.build_evidence_pool(analysis_brief)
                payload = evidence_builder.attach_evidence_to_briefing(payload, evidence_pool)
        except Exception as e:
            logger.warning("evidence 注入失败,简报本身不受影响: %s", e)

        # 兜底:若 analyzer/writer 全空,至少能渲染原始 writer 文本为 TextSection
        fallback_text = str(self.state.get("report_md", "")).strip() or None
        # 兜底文本只在生产模式下脱敏(dry-run 模式保持原样)
        if fallback_text and not local_compliance.is_dry_run():
            fallback_text = local_compliance.sanitize(fallback_text)
        return parse_briefing(payload, meta=meta, fallback_text=fallback_text)

    async def _maybe_run_real_analysis(self) -> None:
        """
        analyzer 之前跑真实数据分析,结果塞进 state['analysis_data']。
        新主线策略:总是先跑 briefing_analytics(主线四象限三路真实分析),
        若 data_file 指向用户上传的文件则附加通用 5 类分析作为补充。
        """
        loop = asyncio.get_event_loop()
        sections: list[str] = []
        rows = cols = 0

        # ---- 主线分析(销售-售后联动 + 售后 RAG + VOC 简版口碑) ----
        try:
            from . import briefing_analytics
            brief = await loop.run_in_executor(None, briefing_analytics.run_main_brief)
            main_text = await loop.run_in_executor(None, briefing_analytics.format_for_llm, brief)
            sections.append(main_text)
            # 留给装配阶段:把真实算法结果转证据池注入到 KPI/sections/actions
            # (P0-3 洞察证据链)
            self.state["analysis_brief"] = brief

            lk = brief.get("linkage", {})
            rows = lk.get("n_sales", 0) + lk.get("n_aftersales", 0)
            cols = brief.get("voc", {}).get("n_voc_total", 0)
        except Exception as e:
            logger.exception("主线分析失败")
            sections.append(f"(主线 briefing_analytics 运行失败: {e})")

        # ---- 用户上传文件附加 5 类分析(可选) ----
        if self.data_file:
            filepath = Path(settings.data_dir) / self.data_file
            if filepath.exists():
                try:
                    from .data_pipeline import run_full_analysis, format_for_llm
                    result = await loop.run_in_executor(None, run_full_analysis, str(filepath))
                    sections.append("## 附:用户上传数据通用 5 类分析\n" + format_for_llm(result))
                    rows = result["profile"]["n_rows"]
                    cols = result["profile"]["n_cols"]
                except Exception as e:
                    logger.warning("用户文件附加分析失败: %s", e)
                    sections.append(f"(用户文件附加分析失败: {e})")
            else:
                sections.append(f"(用户文件不存在: {self.data_file},仅使用主线数据)")

        self.state["analysis_data"] = "\n\n".join(sections) if sections else "(无可用真实数据)"

        await self._emit("data_loaded", {
            "file":    self.data_file or "main_brief",
            "rows":    rows,
            "cols":    cols,
            "summary": self.state["analysis_data"][:600],
        })

    def _build_render_state(self) -> Dict[str, str]:
        """统一构造给 prompt 模板用的占位字段(全部为字符串)。"""
        return {
            "topic":          str(self.state.get("topic", "")),
            "data_summary":   str(self.state.get("data_summary", "(待生成)")),
            "analysis":       str(self.state.get("analysis", "(待生成)")),
            "compliance":     str(self.state.get("compliance", "(待生成)")),
            "report_md":      str(self.state.get("report_md", "(待生成)")),
            "publish_status": str(self.state.get("publish_status", "(待生成)")),
            "analysis_data":  str(self.state.get("analysis_data", "")),
            "analyzer_json":  _dumps_or_default(self.state.get("analyzer_json_dict"), "(待生成)"),
        }

    async def _run_one(
        self, index: int, name: str, title: str, desc: str,
        prompt_tmpl: str, out_key: str,
    ) -> None:
        prompt = prompt_tmpl.format(**self._build_render_state())

        await self._emit("step_start", {
            "index": index, "name": name, "title": title, "desc": desc,
        })

        # 收集 trace 信息
        from time import time
        start_ts = time()
        trace_entry: Dict[str, Any] = {
            "index":      index,
            "name":       name,
            "title":      title,
            "desc":       desc,
            "started_at": datetime.fromtimestamp(start_ts).isoformat(timespec="seconds"),
            "status":     "running",
            "duration_s": 0.0,
            "output":     "",
            "output_len": 0,
            "model":      getattr(self.llm, "model", None),
            "error":      None,
        }
        self.trace.append(trace_entry)

        # 某些 LLM 中间网络层对大 prompt 偶发 RST,加单步自动重试 — 最多 2 次,
        # 退避 [3s, 8s]。失败立即把 error 抛出去走外层降级。
        # 重试只针对网络层异常(httpx.ReadError/ConnectError/RemoteProtocolError),
        # 不重试 LLM 业务错误(rate limit / 4xx),避免烧 token。
        loop = asyncio.get_event_loop()
        last_err: Optional[Exception] = None
        full_text = ""
        backoffs = [0, 3, 8]  # 第 1/2/3 次尝试前的睡眠;首次 0 即立即跑
        for attempt, sleep_s in enumerate(backoffs, start=1):
            if sleep_s > 0:
                await self._emit("agent_token", {
                    "index": index, "name": name,
                    "text": f"\n[网络重试 #{attempt-1}, 等待 {sleep_s}s 后重发...]\n",
                })
                await asyncio.sleep(sleep_s)
            stream_iter = self.llm.stream(prompt)
            text_parts: List[str] = []
            try:
                while True:
                    chunk = await loop.run_in_executor(None, lambda: next(stream_iter, None))
                    if chunk is None:
                        break
                    text_parts.append(chunk)
                    await self._emit("agent_token", {
                        "index": index, "name": name, "text": chunk,
                    })
                # 流式 chunk 走完没异常 → 成功
                full_text = "".join(text_parts).strip()
                last_err = None
                break
            except Exception as e:
                last_err = e
                err_repr = f"{type(e).__name__}: {str(e)[:120]}"
                logger.warning("[orchestrator] step %s attempt %d 失败: %s", name, attempt, err_repr)
                # 只重试明确的网络层瞬时异常,其他立即抛
                err_str = str(e).lower()
                is_transient = (
                    "10054" in err_str
                    or "readerror" in type(e).__name__.lower()
                    or "connecterror" in type(e).__name__.lower()
                    or "remoteprotocol" in type(e).__name__.lower()
                    or "timeouterror" in type(e).__name__.lower()
                    or "远程主机" in err_str
                )
                if not is_transient or attempt == len(backoffs):
                    trace_entry["status"] = "error"
                    trace_entry["error"] = err_repr
                    trace_entry["duration_s"] = round(time() - start_ts, 2)
                    await self._emit("step_error", {"index": index, "name": name, "message": str(e)})
                    raise

        if last_err is not None:
            # 兜底:理论上 break 后 last_err = None;否则说明重试用完
            trace_entry["status"] = "error"
            trace_entry["error"] = str(last_err)
            trace_entry["duration_s"] = round(time() - start_ts, 2)
            await self._emit("step_error", {"index": index, "name": name, "message": str(last_err)})
            raise last_err
        self.state[out_key] = full_text
        # analyzer / writer 步骤后追加一次 JSON 解析(用于装配 BriefingDoc)
        self._post_process_step(name, full_text)

        # 完善 trace
        trace_entry["status"] = "done"
        trace_entry["duration_s"] = round(time() - start_ts, 2)
        trace_entry["output"] = full_text
        trace_entry["output_len"] = len(full_text)
        # 从 LLM client 拿最近一次 usage(包含 token 数)
        try:
            last_usage = self.llm.last_usage()
            if last_usage:
                u = last_usage.__dict__ if hasattr(last_usage, "__dict__") else last_usage
                trace_entry["tokens"] = {
                    "prompt":     u.get("prompt_tokens"),
                    "completion": u.get("completion_tokens"),
                    "total":      u.get("total_tokens"),
                }
        except Exception:
            pass

        await self._emit("step_done", {
            "index": index, "name": name, "output": full_text,
        })

    def _post_process_step(self, name: str, full_text: str) -> None:
        """analyzer / writer 步骤后,把流式聚合的文本再 json.loads 一次,失败则记日志兜底。"""
        if name == "analyzer":
            self.state["analyzer_json_dict"] = self._safe_json_loads(full_text, "analyzer")
        elif name == "writer":
            self.state["writer_json_dict"] = self._safe_json_loads(full_text, "writer")

    @staticmethod
    def _safe_json_loads(text: str, label: str) -> Dict[str, Any]:
        """容错 JSON 解析:支持纯 JSON / 含 ``` 围栏的 JSON / 解析失败回退空 dict。"""
        if not text:
            return {}
        # 去掉可能的 ```json ... ``` 围栏
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].lstrip()
            if stripped.endswith("```"):
                stripped = stripped[:-3].rstrip()
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                return data
            logger.warning("[%s] JSON 解析为非 dict 类型: %s", label, type(data).__name__)
            return {}
        except json.JSONDecodeError as e:
            logger.warning("[%s] JSON 解析失败: %s; raw_head=%r", label, e, stripped[:200])
            return {}
