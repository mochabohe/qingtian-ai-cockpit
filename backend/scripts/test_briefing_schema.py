# -*- coding: utf-8 -*-
"""
阶段 1.6 standalone 单测 (不依赖 pytest)。

覆盖场景:
- 正常 JSON -> BriefingDoc 解析
- 缺字段兜底 (cover/sections/actions 缺失)
- 未知 section type -> 自动降级 TextSection
- insight 超过 40 字 -> 自动截断
- ValidationError 场景 -> 字段类型错也能兜底
- render_to_markdown 输出非空 + 含关键 section 标题
- parse_compliance_stat 各种格式抽取
- 空 payload -> _emergency_doc 最小文档

跑法:
    python backend/scripts/test_briefing_schema.py
退出码:
    0 = 全部 PASS
    1 = 有 FAIL
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.briefing_schema import (  # noqa: E402
    AlertSection,
    BriefingDoc,
    Compliance,
    DistributionSection,
    KPI,
    RankingSection,
    TextSection,
    TrendSection,
    parse_briefing,
    parse_compliance_stat,
    render_to_markdown,
)


PASSED, FAILED = 0, 0


def case(name: str):
    def deco(fn):
        global PASSED, FAILED
        try:
            fn()
            PASSED += 1
            print(f"  [PASS] {name}")
        except AssertionError as e:
            FAILED += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            FAILED += 1
            print(f"  [ERR ] {name}: {type(e).__name__}: {e}")
        return fn
    return deco


# ============================================================================
# Sample payload
# ============================================================================
SAMPLE_PAYLOAD = {
    "meta": {"title": "4月经营简报", "topic": "新能源销量"},
    "cover": {
        "headline": "4月销量同比+8.3%",
        "kpi_strip": [
            {"label": "总销量", "value": "12.4 万辆", "delta": "↑ 同比 +8.3%", "tone": "positive"},
            {"label": "区域覆盖", "value": "23 省"},
        ],
    },
    "executive_summary": "现状。归因。行动方向。",
    "sections": [
        {
            "type": "trend",
            "title": "销量趋势",
            "metric": "销量",
            "unit": "万辆",
            "data": [{"x": "1月", "y": 9.8}, {"x": "2月", "y": 10.2}],
            "delta": {"value": 8.3, "baseline": "同比"},
            "insight": "短洞察",
        },
        {
            "type": "ranking",
            "title": "区域 TOP",
            "columns": ["区域", "销量"],
            "rows": [["华东", "3.2万辆"], ["华南", "2.8万辆"]],
            "insight": "前两区贡献 60%",
        },
        {
            "type": "distribution",
            "title": "区域分布",
            "data": [{"label": "华东", "value": 32}, {"label": "华南", "value": 28}],
            "insight": "集中度上升",
        },
        {
            "type": "alert",
            "level": "high",
            "title": "华北预警",
            "msg": "环比 -8%",
            "evidence": ["北京 -12%", "河北 -7%"],
        },
    ],
    "actions": [
        {"owner": "销售运营组", "action": "完成华北补强", "deadline": "2026-08-15", "priority": "high"},
    ],
    "compliance": {"masked_field_count": 12, "total_field_count": 156, "findings": ["手机号 3 条"]},
}


# ============================================================================
# Test cases
# ============================================================================
@case("正常 dict -> BriefingDoc")
def t_normal():
    doc = parse_briefing(SAMPLE_PAYLOAD)
    assert isinstance(doc, BriefingDoc)
    assert doc.meta.title == "4月经营简报"
    assert doc.cover.headline == "4月销量同比+8.3%"
    assert len(doc.cover.kpi_strip) == 2
    assert doc.cover.kpi_strip[0].tone == "positive"
    assert len(doc.sections) == 4
    types = [s.type for s in doc.sections]
    assert types == ["trend", "ranking", "distribution", "alert"], f"types={types}"
    assert doc.compliance.masked_field_count == 12
    assert doc.actions[0].priority == "high"


@case("正常 JSON 字符串 -> BriefingDoc")
def t_json_string():
    payload = json.dumps(SAMPLE_PAYLOAD, ensure_ascii=False)
    doc = parse_briefing(payload)
    assert doc.meta.topic == "新能源销量"
    assert len(doc.sections) == 4


@case("空 dict -> 兜底为最小文档")
def t_empty_dict():
    doc = parse_briefing({})
    assert isinstance(doc, BriefingDoc)
    assert doc.meta.title  # 不为空(默认值)
    assert isinstance(doc.cover.headline, str)
    assert doc.executive_summary == ""
    assert doc.sections == []


@case("缺 cover 字段 -> 用 meta.title 当 headline 兜底")
def t_missing_cover():
    payload = {**SAMPLE_PAYLOAD}
    payload.pop("cover")
    doc = parse_briefing(payload)
    assert doc.cover.headline  # 不为空


@case("未知 section type -> 自动降级 TextSection")
def t_unknown_type():
    payload = {
        **SAMPLE_PAYLOAD,
        "sections": [
            {"type": "trend", "title": "正常", "metric": "X", "data": [], "insight": "ok"},
            {"type": "supernova", "title": "魔法卡", "anything": 123},
        ],
    }
    doc = parse_briefing(payload)
    assert len(doc.sections) == 2
    assert doc.sections[0].type == "trend"
    assert doc.sections[1].type == "text"
    assert isinstance(doc.sections[1], TextSection)


@case("section 字段类型错误 -> 自动降级 TextSection")
def t_invalid_section():
    payload = {
        **SAMPLE_PAYLOAD,
        "sections": [
            {"type": "trend", "title": "坏的", "metric": "X", "data": "not-a-list"},
        ],
    }
    doc = parse_briefing(payload)
    assert isinstance(doc.sections[0], TextSection)
    assert "trend" in doc.sections[0].body


@case("insight 超 40 字 -> 自动截断 + …")
def t_insight_truncate():
    long_text = "这" * 50
    payload = {
        **SAMPLE_PAYLOAD,
        "sections": [
            {"type": "trend", "title": "X", "metric": "Y", "data": [], "insight": long_text},
        ],
    }
    doc = parse_briefing(payload)
    sec = doc.sections[0]
    assert isinstance(sec, TrendSection)
    assert len(sec.insight) <= 40
    assert sec.insight.endswith("…")


@case("非 JSON 字符串 -> _emergency_doc")
def t_non_json():
    raw = "这不是 JSON,只是一段普通文本。"
    doc = parse_briefing(raw)
    assert isinstance(doc, BriefingDoc)
    assert "降级" in doc.executive_summary
    assert any(isinstance(s, TextSection) and raw in s.body for s in doc.sections)


@case("render_to_markdown 含关键章节")
def t_render_md():
    doc = parse_briefing(SAMPLE_PAYLOAD)
    md = render_to_markdown(doc)
    assert "# 4月经营简报" in md
    assert "## 一、摘要" in md
    assert "## 二、关键洞察" in md
    assert "## 三、行动建议" in md
    assert "## 四、合规与数据出处" in md
    # 各 section 类型都应出现
    assert "销量趋势" in md
    assert "区域 TOP" in md
    assert "华北预警" in md
    # KPI strip 有渲染
    assert "12.4 万辆" in md
    # 合规统计
    assert "12" in md and "156" in md


@case("render_to_markdown 末尾必含换行,无尾随空白")
def t_render_md_trailing():
    md = render_to_markdown(parse_briefing(SAMPLE_PAYLOAD))
    assert md.endswith("\n")
    assert not md.endswith("\n\n\n")


@case("parse_compliance_stat: 显式 X/Y 格式")
def t_compliance_explicit():
    txt = """【合规检查】需要脱敏
【发现问题】
1. 手机号
2. 身份证号
【建议】统一脱敏后发布
此外脱敏 7 / 100 字段"""
    c = parse_compliance_stat(txt)
    assert c.masked_field_count == 7
    assert c.total_field_count == 100


@case("parse_compliance_stat: 通过 + 无问题")
def t_compliance_pass():
    txt = """【合规检查】通过
【发现问题】无
【建议】可直接发布"""
    c = parse_compliance_stat(txt)
    assert c.masked_field_count == 0
    assert c.findings == []


@case("parse_compliance_stat: 列表条数推断 masked_field_count")
def t_compliance_list_infer():
    txt = """【合规检查】需要脱敏
【发现问题】
- 客户姓名
- 精确金额
- 手机号
【建议】脱敏处理"""
    c = parse_compliance_stat(txt)
    assert c.masked_field_count == 3
    assert len(c.findings) == 3


@case("KPI tone 默认 neutral")
def t_kpi_default_tone():
    k = KPI(label="X", value="Y")
    assert k.tone == "neutral"


@case("ActionItem priority 默认 medium")
def t_action_default_priority():
    from app.services.briefing_schema import ActionItem
    a = ActionItem(owner="A", action="B", deadline="2026-01-01")
    assert a.priority == "medium"


@case("Compliance 默认值")
def t_compliance_default():
    c = Compliance()
    assert c.masked_field_count == 0
    assert c.total_field_count == 0
    assert c.findings == []


def main() -> int:
    print("=" * 60)
    print("阶段 1.6 · briefing_schema 单元测试")
    print("=" * 60)
    print(f"\n{'通过' if FAILED == 0 else '失败'}: {PASSED} pass / {FAILED} fail")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
