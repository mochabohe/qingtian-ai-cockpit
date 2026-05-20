# -*- coding: utf-8 -*-
"""
BriefingDoc 结构化决策简报数据模型(对应 design.md §2.1)。

包含:
- Pydantic v2 模型定义(Section discriminated union by type)
- parse_briefing(): JSON/dict -> BriefingDoc,带失败兜底(缺字段/未知 type 自动降级)
- render_to_markdown(): BriefingDoc -> markdown 投影,用于向下兼容历史 *.md 视图
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, ValidationError


# ============================================================================
# 基础值对象
# ============================================================================
class Evidence(BaseModel):
    """
    P0-3 洞察证据链:每条 KPI/section/action 关联的数据来源摘要

    设计目标:演示"这个数字哪来的"必问题的硬解。任何展示给用户的结论都能点开
    抽屉看到"源数据集 + 字段 + 计算口径 + 命中记录数 + 3-5 条原始样例(脱敏)",
    用户追问时直接打开对应抽屉,代替"AI 编的吗"质疑。
    """
    label:        str = ""                       # 这条证据指向的结论标识(给前端定位用)
    source:       str = ""                       # "销售记录 / 售后维修 / VOC 评论 / 故障案例 RAG"
    method:       str = ""                       # 计算口径,如"近 12 月按月聚合"
    fields:       list[str] = Field(default_factory=list)   # 涉及的关键字段
    record_count: int = 0                        # 命中记录数
    samples:      list[str] = Field(default_factory=list)   # 3-5 条原始样例(已脱敏)
    note:         str = ""                       # 附加说明(可选)


class KPI(BaseModel):
    label: str
    value: str                              # "12.4 万辆" / "+8.3%"
    delta: str | None = None                # "↑ 同比 +12%"
    tone: Literal["positive", "negative", "neutral"] = "neutral"
    evidence: list[Evidence] = Field(default_factory=list)


class ActionItem(BaseModel):
    owner: str
    action: str
    deadline: str                           # YYYY-MM-DD
    priority: Literal["high", "medium", "low"] = "medium"
    evidence: list[Evidence] = Field(default_factory=list)


# ============================================================================
# Section 各 type
# ============================================================================
class TrendDataPoint(BaseModel):
    x: str
    y: float


class TrendDelta(BaseModel):
    # value 允许 None：LLM 在缺真实数据时常输出 null,避免整个 trend section 被降级为 text
    value: float | None = None
    baseline: str = ""                      # "同比 / 环比 / 去年"


class TrendSection(BaseModel):
    type: Literal["trend"] = "trend"
    title: str
    metric: str
    unit: str | None = None
    data: list[TrendDataPoint] = Field(default_factory=list)
    delta: TrendDelta | None = None
    insight: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class RankingSection(BaseModel):
    type: Literal["ranking"] = "ranking"
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    insight: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class DistributionDataPoint(BaseModel):
    label: str
    value: float


class DistributionSection(BaseModel):
    type: Literal["distribution"] = "distribution"
    title: str
    data: list[DistributionDataPoint] = Field(default_factory=list)
    insight: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class AlertSection(BaseModel):
    type: Literal["alert"] = "alert"
    level: Literal["info", "warning", "high"] = "warning"
    title: str
    msg: str = ""
    evidence_text: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class TextSection(BaseModel):
    """兜底文本卡片,用于 LLM 输出不合 schema / 未知 type / 冗余文本场景"""
    type: Literal["text"] = "text"
    title: str = "补充信息"
    body: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


Section = Annotated[
    Union[TrendSection, RankingSection, DistributionSection, AlertSection, TextSection],
    Field(discriminator="type"),
]


# ============================================================================
# 顶层结构
# ============================================================================
class Meta(BaseModel):
    title: str
    topic: str
    period: str = ""                        # "2026-04" / "2026-Q2"
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    audit_id: str = ""


class Cover(BaseModel):
    headline: str
    kpi_strip: list[KPI] = Field(default_factory=list)


class Compliance(BaseModel):
    masked_field_count: int = 0
    total_field_count: int = 0
    findings: list[str] = Field(default_factory=list)
    # 模式:"dry_run"(默认演示,识别但不改文本) / "production"(真改)
    # 让前端展示"已识别 N 处风险(演示模式·生产环境会自动脱敏)" vs "已脱敏 N 处"
    mode: Literal["dry_run", "production"] = "dry_run"


class BriefingDoc(BaseModel):
    meta: Meta
    cover: Cover
    executive_summary: str = ""
    sections: list[Section] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    compliance: Compliance = Field(default_factory=Compliance)


# ============================================================================
# 兜底解析: dict/json -> Section,未知 type 自动降级为 TextSection
# ============================================================================
KNOWN_SECTION_TYPES = {"trend", "ranking", "distribution", "alert", "text"}


def _coerce_section(d: Any) -> Section:
    """单个 section 兜底解析:type 不识别 / 字段缺失 / 验证失败 -> TextSection"""
    if not isinstance(d, dict):
        return TextSection(title="(无效卡片)", body=str(d))
    t = d.get("type", "text")
    if t not in KNOWN_SECTION_TYPES:
        return TextSection(
            title=str(d.get("title") or "未知卡片"),
            body=json.dumps(d, ensure_ascii=False, indent=2),
        )

    # 向下兼容:旧 LLM 输出 alert.evidence 是 list[str],新 schema 改为 list[Evidence]。
    # 迁移规则:list[str] → 移到 evidence_text;dict 列表正常走 list[Evidence]。
    if t == "alert" and isinstance(d.get("evidence"), list):
        ev = d["evidence"]
        if ev and all(isinstance(x, str) for x in ev):
            d = {**d, "evidence_text": ev, "evidence": []}

    cls_map = {
        "trend": TrendSection,
        "ranking": RankingSection,
        "distribution": DistributionSection,
        "alert": AlertSection,
        "text": TextSection,
    }
    try:
        return cls_map[t].model_validate(d)
    except ValidationError:
        # 验证失败:把原 dict 序列化进 TextSection.body 兜底
        return TextSection(
            title=str(d.get("title") or "(解析失败)"),
            body=json.dumps(d, ensure_ascii=False, indent=2),
        )


def _truncate_insight(text: str, limit: int = 40) -> str:
    """insight 超过限长截断 + …"""
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def parse_briefing(
    payload: str | dict[str, Any],
    *,
    meta: dict[str, Any] | None = None,
    fallback_text: str | None = None,
) -> BriefingDoc:
    """
    把 LLM 输出(已合并 analyzer/writer/compliance 的 dict)转成 BriefingDoc。
    任一环节失败都会兜底为最少含 cover + 1 个 TextSection 的最小文档。

    payload 期望结构:
      {
        "meta": {...} (可空,从外部 meta 参数补),
        "cover": {"headline": "...", "kpi_strip": [...]},
        "executive_summary": "...",
        "sections": [...],
        "actions": [...],
        "compliance": {...},
      }
    """
    # 1) 输入归一化
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return _emergency_doc(meta, body=payload, reason="JSON 解析失败")
    elif isinstance(payload, dict):
        data = payload
    else:
        return _emergency_doc(meta, body=fallback_text or "", reason="输入类型不支持")

    # 2) meta 合并(外部传入的优先)
    raw_meta = {**(data.get("meta") or {}), **(meta or {})}
    if not raw_meta.get("title"):
        raw_meta["title"] = raw_meta.get("topic") or "决策简报"
    if not raw_meta.get("topic"):
        raw_meta["topic"] = raw_meta["title"]
    try:
        meta_obj = Meta.model_validate(raw_meta)
    except ValidationError:
        meta_obj = Meta(title="决策简报", topic="决策简报")

    # 3) cover
    raw_cover = data.get("cover") or {}
    headline = raw_cover.get("headline") or meta_obj.title
    kpi_list: list[KPI] = []
    for k in raw_cover.get("kpi_strip") or []:
        try:
            kpi_list.append(KPI.model_validate(k))
        except ValidationError:
            continue
    cover = Cover(headline=str(headline), kpi_strip=kpi_list)

    # 4) sections (逐个兜底 + insight 截断)
    sections: list[Section] = []
    for s in data.get("sections") or []:
        sec = _coerce_section(s)
        # insight 超长截断
        if hasattr(sec, "insight") and isinstance(sec.insight, str):
            sec.insight = _truncate_insight(sec.insight, 40)
        sections.append(sec)

    # 5) actions (逐个兜底)
    actions: list[ActionItem] = []
    for a in data.get("actions") or []:
        try:
            actions.append(ActionItem.model_validate(a))
        except ValidationError:
            continue

    # 6) compliance
    raw_comp = data.get("compliance") or {}
    try:
        compliance = Compliance.model_validate(raw_comp)
    except ValidationError:
        compliance = Compliance()

    # 7) executive_summary
    summary = data.get("executive_summary") or ""
    if not isinstance(summary, str):
        summary = str(summary)

    # 8) 兜底:如果 sections 为空且有 fallback_text,塞一个 TextSection
    if not sections and fallback_text:
        sections.append(TextSection(title="正文", body=fallback_text))

    return BriefingDoc(
        meta=meta_obj,
        cover=cover,
        executive_summary=summary,
        sections=sections,
        actions=actions,
        compliance=compliance,
    )


def _emergency_doc(meta: dict | None, body: str, reason: str) -> BriefingDoc:
    """JSON 完全无法解析时的最小兜底文档"""
    raw_meta = {**(meta or {})}
    if not raw_meta.get("title"):
        raw_meta["title"] = raw_meta.get("topic") or "决策简报"
    if not raw_meta.get("topic"):
        raw_meta["topic"] = raw_meta["title"]
    try:
        meta_obj = Meta.model_validate(raw_meta)
    except ValidationError:
        meta_obj = Meta(title="决策简报", topic="决策简报")
    return BriefingDoc(
        meta=meta_obj,
        cover=Cover(headline=meta_obj.title),
        executive_summary=f"(自动降级:{reason},以下为原始输出)",
        sections=[TextSection(title="原始输出", body=body[:5000])],
        actions=[],
        compliance=Compliance(),
    )


# ============================================================================
# 投影:BriefingDoc -> markdown(向下兼容历史 *.md 视图)
# ============================================================================
TONE_PREFIX = {"positive": "↑", "negative": "↓", "neutral": "·"}


def render_to_markdown(doc: BriefingDoc) -> str:
    """把 BriefingDoc 还原成 markdown 文本,与原 writer 输出风格保持一致。"""
    lines: list[str] = []
    lines.append(f"# {doc.meta.title}")
    if doc.meta.period:
        lines.append(f"> 周期:{doc.meta.period}  ·  生成于:{doc.meta.generated_at[:10]}")
    if doc.cover.headline:
        lines.append("")
        lines.append(f"**{doc.cover.headline}**")
    if doc.cover.kpi_strip:
        lines.append("")
        kpi_parts = []
        for k in doc.cover.kpi_strip:
            tag = TONE_PREFIX.get(k.tone, "·")
            piece = f"`{k.label}` **{k.value}**"
            if k.delta:
                piece += f" {tag} {k.delta}"
            kpi_parts.append(piece)
        lines.append(" / ".join(kpi_parts))

    lines.append("")
    lines.append("## 一、摘要")
    lines.append(doc.executive_summary or "(无)")

    if doc.sections:
        lines.append("")
        lines.append("## 二、关键洞察")
        for i, sec in enumerate(doc.sections, 1):
            lines.append("")
            lines.append(f"### {i}. {sec.title}")
            lines.extend(_render_section_md(sec))

    if doc.actions:
        lines.append("")
        lines.append("## 三、行动建议")
        for a in doc.actions:
            tag = {"high": "[HIGH]", "medium": "[MID]", "low": "[LOW]"}[a.priority]
            lines.append(f"- {tag} **{a.owner}** · {a.action} · 截止 {a.deadline}")

    lines.append("")
    lines.append("## 四、合规与数据出处")
    lines.append(
        f"- 合规过滤:已脱敏 {doc.compliance.masked_field_count} / "
        f"{doc.compliance.total_field_count} 字段"
    )
    if doc.compliance.findings:
        for f in doc.compliance.findings:
            lines.append(f"  - {f}")
    if doc.meta.audit_id:
        lines.append(f"- 审计 ID:{doc.meta.audit_id}")

    return "\n".join(lines).rstrip() + "\n"


def _render_section_md(sec: Section) -> list[str]:
    out: list[str] = []
    if isinstance(sec, TrendSection):
        head = f"指标:**{sec.metric}**"
        if sec.unit:
            head += f"({sec.unit})"
        if sec.delta and sec.delta.value is not None:
            head += f"  ·  {sec.delta.baseline}: {sec.delta.value:+.1f}"
        elif sec.delta and sec.delta.baseline:
            head += f"  ·  {sec.delta.baseline}: 数据缺失"
        out.append(head)
        if sec.data:
            pairs = [f"{p.x}={p.y}" for p in sec.data]
            out.append("- 数据:" + " / ".join(pairs))
        if sec.insight:
            out.append(f"- 💡 {sec.insight}")
    elif isinstance(sec, RankingSection):
        if sec.columns:
            out.append("| " + " | ".join(sec.columns) + " |")
            out.append("| " + " | ".join("---" for _ in sec.columns) + " |")
            for row in sec.rows:
                out.append("| " + " | ".join(str(c) for c in row) + " |")
        if sec.insight:
            out.append(f"- 💡 {sec.insight}")
    elif isinstance(sec, DistributionSection):
        for p in sec.data:
            out.append(f"- {p.label}: {p.value}")
        if sec.insight:
            out.append(f"- 💡 {sec.insight}")
    elif isinstance(sec, AlertSection):
        emoji = {"high": "🔴", "warning": "🟠", "info": "🔵"}[sec.level]
        out.append(f"{emoji} **{sec.level.upper()}**:{sec.msg}")
        # 旧字段(LLM 直接产的字符串证据列表),保留兼容
        if sec.evidence_text:
            out.append("- 证据:")
            for e in sec.evidence_text:
                out.append(f"  - {e}")
    elif isinstance(sec, TextSection):
        out.append(sec.body or "(空)")
    return out


# ============================================================================
# 合规结果文本 -> Compliance(给 orchestrator 用)
# ============================================================================
_FIELD_PATTERNS = [
    re.compile(r"已?脱敏\s*(\d+)\s*/\s*(\d+)\s*字段"),
    re.compile(r"(\d+)\s*/\s*(\d+)\s*字段"),
]


def parse_compliance_stat(text: str, default_total: int = 0) -> Compliance:
    """
    从 compliance Agent 的 markdown 输出里抽取统计。
    格式按 design.md §3 默认 prompt:
      【合规检查】通过 / 需要脱敏
      【发现问题】<列表 或 "无">
      【建议】...
    抽取策略:
      1) 优先匹配 "脱敏 X / Y 字段" 这种显式格式(若以后 prompt 升级输出该格式)
      2) 否则按 "发现问题" 段下的列表条数推断 masked_field_count
    """
    if not text:
        return Compliance()

    masked = total = 0
    for pat in _FIELD_PATTERNS:
        m = pat.search(text)
        if m:
            masked, total = int(m.group(1)), int(m.group(2))
            break

    findings: list[str] = []
    in_findings = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "【发现问题】" in line:
            in_findings = True
            tail = line.split("】", 1)[1].strip()
            if tail and tail != "无":
                findings.append(tail)
            continue
        if line.startswith("【") and "】" in line:
            in_findings = False
            continue
        if in_findings:
            cleaned = re.sub(r"^[-*\d.\s、]+", "", line).strip()
            if cleaned and cleaned != "无":
                findings.append(cleaned)

    if masked == 0 and findings:
        masked = len(findings)
    if total == 0:
        total = max(default_total, masked, len(findings))

    return Compliance(
        masked_field_count=masked,
        total_field_count=total,
        findings=findings,
    )
