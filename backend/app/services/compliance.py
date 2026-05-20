"""
本地合规审查双层架构:第一层正则黑名单 + 第二层 LLM 复审兜底。

Agent prompt 那条 LLM 复审已经在 orchestrator 里跑(COMPLIANCE_PROMPT step),
本模块负责【确定性 + 可解释】的第一层 — 任何敏感字段命中正则就直接脱敏,
LLM 只做"我可能漏了什么语义级风险"的兜底。

汽车行业典型敏感项 (按 PPTX 培训说明):
- 用户隐私: 身份证号 / 手机号 / 邮箱 / 银行卡 / 车牌号 / VIN / 客户姓名
- 商业敏感: 精确金额(可选打码到万位) / 内部车型代号 / 供应商单价
- 涉密关键词: 由 .env / 自定义词表加载

API:
    scan(text)        → ComplianceReport(原文/脱敏文/命中清单/统计)
    sanitize(text)    → 脱敏后文本(快捷调用)
    sanitize_dict(d)  → 递归脱敏 dict(用于简报 JSON sections)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple


# ============================================================
# 1. 正则规则定义
# ============================================================
# 每条规则: (rule_id, label, pattern, mask_fn)
# mask_fn(match) 返回脱敏后的字符串

def _mask_id_card(m: re.Match) -> str:
    """身份证 18 位:保留前 6 位籍贯 + ****"""
    s = m.group(0)
    if len(s) == 18:
        return s[:6] + "********" + s[-4:]
    return "***"


def _mask_phone(m: re.Match) -> str:
    """手机号 138-****-1234"""
    s = m.group(0)
    return s[:3] + "****" + s[-4:]


def _mask_bank_card(m: re.Match) -> str:
    """银行卡 16-19 位:保留前 6 + 后 4"""
    s = m.group(0)
    return s[:6] + "*" * (len(s) - 10) + s[-4:]


def _mask_email(m: re.Match) -> str:
    """邮箱 a***@b.com"""
    s = m.group(0)
    name, _, domain = s.partition("@")
    if len(name) <= 2:
        return "***@" + domain
    return name[0] + "*" * (len(name) - 2) + name[-1] + "@" + domain


def _mask_vin(m: re.Match) -> str:
    """VIN 17 位:保留前 8(WMI+VDS)+ ******* + 后 2"""
    s = m.group(0)
    return s[:8] + "*******" + s[-2:]


def _mask_plate(m: re.Match) -> str:
    """中国车牌:首字母 + ***** + 末位"""
    s = m.group(0)
    return s[0] + "*" * (len(s) - 2) + s[-1]


def _mask_money(m: re.Match) -> str:
    """精确金额(>= 10 万)模糊到"约 X 万元/亿元",< 10 万不打码"""
    raw = m.group(0)
    digits = re.sub(r"[^\d.]", "", raw)
    try:
        v = float(digits)
    except ValueError:
        return raw
    if v < 100000:
        return raw  # 小金额不脱敏
    if v >= 1e8:
        return f"约 {v/1e8:.1f} 亿元"
    if v >= 1e4:
        return f"约 {v/1e4:.0f} 万元"
    return raw


def _mask_full(_m: re.Match) -> str:
    return "***"


# 主规则表
RULES: List[Tuple[str, str, re.Pattern, Any]] = [
    # 用户隐私(高风险)
    ("id_card",   "身份证号",   re.compile(r"\b\d{17}[\dXx]\b"),                        _mask_id_card),
    ("phone",     "手机号",     re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),                _mask_phone),
    ("bank_card", "银行卡号",   re.compile(r"(?<!\d)\d{16,19}(?!\d)"),                  _mask_bank_card),
    ("email",     "邮箱",       re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), _mask_email),
    # 车辆识别码(汽车行业专属)
    ("vin",       "VIN 码",     re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),                _mask_vin),
    ("plate",     "中国车牌",
        re.compile(r"[一-龥][A-Z][A-Z0-9·•\-]{4,7}", re.UNICODE),
        _mask_plate),
    # 商业敏感:精确金额(>= 10 万元才脱敏,小额保留)
    # 必须有货币标志(前缀 ¥/RMB 或后缀 元/人民币)防止误吃身份证/银行卡的裸数字尾巴
    ("big_money", "精确金额",
        re.compile(r"(?:(?:¥|￥|RMB\s*)\d{6,}(?:\.\d+)?(?:\s*(?:元|人民币))?|\d{6,}(?:\.\d+)?\s*(?:元|人民币))"),
        _mask_money),
]


# ============================================================
# 2. 敏感关键词词表(可扩展)
# ============================================================
# 默认词表;实际项目可通过 .env COMPLIANCE_KEYWORDS=代号A,代号B 注入
DEFAULT_SENSITIVE_KEYWORDS: List[str] = [
    # 内部代号占位(实际项目按需扩展)
    # "项目代号X", "工程代号Y",
]


def _load_extra_keywords() -> List[str]:
    """从 .env 加载额外关键词"""
    import os
    raw = os.environ.get("COMPLIANCE_KEYWORDS", "")
    return [w.strip() for w in raw.split(",") if w.strip()]


# ============================================================
# 3. 数据契约
# ============================================================

@dataclass
class Finding:
    rule_id:    str
    label:      str
    matched:    str       # 命中原文(用于审计)
    masked:     str       # 脱敏后
    position:   int       # 在原文中的字符偏移


@dataclass
class ComplianceReport:
    original_length:  int
    sanitized_text:   str
    findings:         List[Finding] = field(default_factory=list)
    rule_hit_counts:  Dict[str, int] = field(default_factory=dict)

    @property
    def masked_field_count(self) -> int:
        return len(self.findings)

    @property
    def total_field_count(self) -> int:
        # "总检查字段数"用文本长度的粗估(每 100 字符按 1 字段),用于面板友好显示
        return max(self.masked_field_count, max(self.original_length // 100, 1))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_length":    self.original_length,
            "sanitized_text":     self.sanitized_text,
            "findings":           [asdict(f) for f in self.findings],
            "rule_hit_counts":    self.rule_hit_counts,
            "masked_field_count": self.masked_field_count,
            "total_field_count":  self.total_field_count,
        }


# ============================================================
# 4. 扫描 + 脱敏
# ============================================================

def scan(text: str, extra_keywords: List[str] | None = None) -> ComplianceReport:
    """
    扫描原文,执行所有正则规则 + 关键词命中,产出脱敏文本与命中清单。

    应用规则的顺序很重要:VIN 必须在 bank_card / id_card 之前,因为 VIN 都是
    字母+数字,不会和纯数字误判;精确金额放在最后,避免吃掉前面已脱敏的位掩码。
    """
    if not text:
        return ComplianceReport(original_length=0, sanitized_text="")

    findings: List[Finding] = []
    counts: Dict[str, int] = {}
    sanitized = text

    # 4.1 应用正则规则
    for rule_id, label, pattern, mask_fn in RULES:
        # 找完所有命中再 sub 是为了保留原文位置
        for m in pattern.finditer(sanitized):
            matched_text = m.group(0)
            # _mask_money 对小金额返回原文 → 不计为 finding
            masked_text = mask_fn(m)
            if masked_text == matched_text:
                continue
            findings.append(Finding(
                rule_id=rule_id,
                label=label,
                matched=matched_text,
                masked=masked_text,
                position=m.start(),
            ))
        # 真正替换:用同一 mask_fn 跑一遍 sub
        sanitized = pattern.sub(mask_fn, sanitized)
        # 重新计数(以 sub 后真正发生变化为准)
        hits = sum(1 for f in findings if f.rule_id == rule_id)
        if hits:
            counts[rule_id] = hits

    # 4.2 敏感关键词命中(逐字匹配,大小写敏感保留实词意图)
    keywords = (extra_keywords or []) + DEFAULT_SENSITIVE_KEYWORDS + _load_extra_keywords()
    for kw in dict.fromkeys(keywords):  # 去重保序
        if not kw:
            continue
        idx = 0
        while True:
            pos = sanitized.find(kw, idx)
            if pos < 0:
                break
            findings.append(Finding(
                rule_id="keyword",
                label=f"敏感词「{kw}」",
                matched=kw,
                masked="*" * len(kw),
                position=pos,
            ))
            idx = pos + len(kw)
        if any(f.rule_id == "keyword" and f.matched == kw for f in findings):
            sanitized = sanitized.replace(kw, "*" * len(kw))
            counts["keyword"] = counts.get("keyword", 0) + sum(
                1 for f in findings if f.rule_id == "keyword" and f.matched == kw
            )

    findings.sort(key=lambda f: f.position)

    return ComplianceReport(
        original_length=len(text),
        sanitized_text=sanitized,
        findings=findings,
        rule_hit_counts=counts,
    )


def sanitize(text: str, extra_keywords: List[str] | None = None) -> str:
    """快捷接口:只要脱敏后的文本"""
    return scan(text, extra_keywords=extra_keywords).sanitized_text


def sanitize_dict(obj: Any, extra_keywords: List[str] | None = None) -> Any:
    """
    递归脱敏 dict / list / str。用于在简报装配前清洗 sections 里的所有文本字段。
    数字/布尔/None 不动。
    """
    if isinstance(obj, str):
        return sanitize(obj, extra_keywords=extra_keywords)
    if isinstance(obj, list):
        return [sanitize_dict(x, extra_keywords=extra_keywords) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize_dict(v, extra_keywords=extra_keywords) for k, v in obj.items()}
    return obj


# ============================================================
# Dry-run 模式(演示场景):仅扫描识别风险,不修改原文
# ============================================================

def is_dry_run() -> bool:
    """
    判断当前是否启用合规 dry-run 模式。

    设计意图(2026-05-08 用户决议):
    - 数据方提供的数据本身已经脱敏,如果继续真改文本,反而把"443.37 万元"
      改成"约 443 万元"这种已脱敏的数据再做一次假脱敏,语义重复
    - 但合规审查环节仍然要展示给用户看(产品化必备)
    - dry-run=true 时:扫描照跑(识别 + 计数 + LLM 复审都正常),但**不改原文**
    - 真实上生产时,切 COMPLIANCE_DRY_RUN=false 即触发真实脱敏

    默认 true(演示场景)。
    """
    val = os.getenv("COMPLIANCE_DRY_RUN", "true").strip().lower()
    return val in ("1", "true", "yes", "on")


def sanitize_dict_or_skip(obj: Any, extra_keywords: List[str] | None = None) -> Any:
    """
    根据 COMPLIANCE_DRY_RUN 决定是否真改文本:
    - dry_run=true(默认):返回原对象,**不改文本**(演示场景)
    - dry_run=false:走完整 sanitize_dict(生产场景)

    注意:scan() 仍然要在外面单独跑一次,获取 findings 与命中数。
    本函数只控制"是否真改文本"。
    """
    if is_dry_run():
        return obj
    return sanitize_dict(obj, extra_keywords=extra_keywords)


# ============================================================
# 5. 与现有 Compliance schema 对齐(给 orchestrator 用)
# ============================================================

def report_to_briefing_compliance(report: ComplianceReport) -> Dict[str, Any]:
    """
    把 ComplianceReport 投影成 BriefingDoc.compliance 字段需要的形态:
    {masked_field_count, total_field_count, findings: list[str]}
    """
    finding_lines: List[str] = []
    for f in report.findings[:20]:  # 限制 20 条避免简报变冗长
        finding_lines.append(f"{f.label}: {f.matched} → {f.masked}")
    return {
        "masked_field_count": report.masked_field_count,
        "total_field_count":  report.total_field_count,
        "findings":           finding_lines,
    }


def render_text_summary(report: ComplianceReport) -> str:
    """给 LLM compliance step 用的简短摘要 - 让 LLM 知道'本地已脱敏 N 项,你只做语义复审'"""
    if report.masked_field_count == 0:
        return f"【本地正则扫描】未发现敏感信息(共 {report.original_length} 字)"
    breakdown = "、".join(f"{rid} ×{c}" for rid, c in report.rule_hit_counts.items())
    return (
        f"【本地正则已脱敏】{report.masked_field_count} 项("
        f"{breakdown})。请只检查语义级敏感信息(竞品负面表述、未公开商业策略等),"
        f"不要重复检测身份证/手机号/VIN/车牌/邮箱/精确金额,本地正则已处理。"
    )
