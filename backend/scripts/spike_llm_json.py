# -*- coding: utf-8 -*-
"""
阶段 0.1 spike: LLM JSON 输出稳定性验证。

验证项:
  1. response_format={"type":"json_object"} 在当前 LLM provider 上能否生效
  2. ANALYZER_PROMPT 草稿（design.md §3.1）跑 5 次,统计:
     - JSON 解析成功率
     - sections 数量(目标 ≥ 3)
     - sections 类型覆盖(目标至少 1 个 trend + 1 个 ranking 或 distribution)
     - insight 平均字数(目标 ≤ 40)
     - kpi_strip 数量(目标 3-4)
  3. 报告耗时 / token / 成本

策略:
  - 先跑 1 次 smoke test(连通性 + JSON 模式确认),失败立即退出避免浪费配额
  - smoke OK 后跑 5 次正式 spike
  - 所有结果打印 + 落到 spike_out/llm_json_spike_report.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # type: ignore

load_dotenv(ROOT / ".env")

from app.llm_client import LLMClient  # noqa: E402

OUT_DIR = Path(__file__).parent / "spike_out"
OUT_DIR.mkdir(exist_ok=True)
REPORT_PATH = OUT_DIR / "llm_json_spike_report.json"

ANALYZER_PROMPT = """你是数据分析 Agent,职责:把已计算好的数据结果整理成结构化 JSON。

主题:东风新能源板块 4 月经营分析
已采集数据源摘要:销售订单库 / 区域分布数据 / 客户画像表 / 售后工单库 / 财务台账

【真实数据分析结果(来自 pandas/sklearn 计算,禁止编造)】
- 月度销量(万辆): 1月 9.8 / 2月 10.2 / 3月 11.1 / 4月 12.4 / 5月 11.8
- 同比去年: +8.3%
- 区域 TOP5: 华东 3.2万辆(↑12%) / 华南 2.8万辆(↑9%) / 华北 1.8万辆(↓8%) / 西南 1.2万辆(↑5%) / 其他 1.0万辆(↑3%)
- 区域销量分布(占比): 华东 32% / 华南 28% / 华北 18% / 西南 12% / 其他 10%
- 客户分群: 家庭用户 45% / 商用车队 30% / 政府/企事业 15% / 其他 10%
- 异常:华北区销量环比 -8%,连续 2 月下行;北京 -12%、河北 -7%、天津 -5%
- 达标率: 全国均值 92.6%

请输出严格的 JSON,不要任何 markdown 代码块包裹,直接以 { 开头,以 } 结尾:

{
  "sections": [
    {
      "type": "trend" | "ranking" | "distribution" | "alert",
      "title": "...",
      "metric": "销量(万辆)",
      "data": [...],
      "insight": "一句话洞察(<=40 字)"
    }
  ],
  "kpi_strip": [
    { "label": "总销量", "value": "12.4 万辆", "delta": "↑ 同比 +8.3%", "tone": "positive" }
  ]
}

要求:
1. 每个 section 的 data 必须直接引用上面的真实数值,不能新编
2. insight 必须能在 data 里找到证据,不能凭空联想
3. 至少输出 3 个 section,其中至少 1 个 trend、1 个 ranking 或 distribution
4. 异常数据用 type=alert 单独输出一条
5. kpi_strip 输出 3-4 条核心指标
"""


def smoke_test(client: LLMClient) -> bool:
    """连通性 + JSON 模式 smoke (省钱,只问一个最简短问题)"""
    print("\n[smoke] 测试连通性 + JSON 模式…")
    try:
        out = client.chat(
            '只回复严格 JSON: {"ok": true}',
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=20,
        )
        print(f"[smoke] 返回: {out!r}")
        parsed = json.loads(out)
        if parsed.get("ok") is True:
            print("[smoke] PASS")
            return True
        print("[smoke] JSON 解析了但字段不对")
        return False
    except Exception as e:
        print(f"[smoke] FAIL: {type(e).__name__}: {e}")
        return False


def validate_analyzer_output(parsed: dict) -> dict:
    """校验单次 analyzer 输出是否符合 schema"""
    issues = []
    sections = parsed.get("sections", [])
    kpi_strip = parsed.get("kpi_strip", [])

    if not isinstance(sections, list):
        issues.append("sections 不是数组")
        return {"valid": False, "issues": issues}

    types_seen = set()
    insight_lens = []
    for i, s in enumerate(sections):
        if not isinstance(s, dict):
            issues.append(f"section[{i}] 不是对象")
            continue
        t = s.get("type")
        if t not in {"trend", "ranking", "distribution", "alert", "text"}:
            issues.append(f"section[{i}].type={t!r} 不合法")
        else:
            types_seen.add(t)
        if not s.get("title"):
            issues.append(f"section[{i}] 缺 title")
        ins = s.get("insight", "")
        if isinstance(ins, str):
            insight_lens.append(len(ins))
            if len(ins) > 40:
                issues.append(f"section[{i}].insight 超 40 字: {len(ins)}")

    if len(sections) < 3:
        issues.append(f"sections 数量 {len(sections)} < 3")
    if not (types_seen & {"trend"}):
        issues.append("缺少 trend 类型")
    if not (types_seen & {"ranking", "distribution"}):
        issues.append("缺少 ranking 或 distribution 类型")

    if not isinstance(kpi_strip, list) or not (3 <= len(kpi_strip) <= 4):
        issues.append(f"kpi_strip 数量={len(kpi_strip) if isinstance(kpi_strip, list) else 'N/A'} 不在 [3,4]")

    return {
        "valid": not issues,
        "issues": issues,
        "section_count": len(sections),
        "section_types": sorted(types_seen),
        "kpi_count": len(kpi_strip) if isinstance(kpi_strip, list) else 0,
        "insight_max_len": max(insight_lens) if insight_lens else 0,
        "insight_avg_len": round(sum(insight_lens) / max(len(insight_lens), 1), 1),
    }


def run_one(client: LLMClient, idx: int) -> dict:
    print(f"\n[run {idx}] 调用 LLM…")
    t0 = time.time()
    try:
        raw = client.chat(
            ANALYZER_PROMPT,
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=2000,
        )
        dt = time.time() - t0
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as je:
            return {
                "idx": idx,
                "ok": False,
                "stage": "json_parse",
                "error": str(je),
                "duration_s": round(dt, 2),
                "raw_head": raw[:200],
            }
        v = validate_analyzer_output(parsed)
        print(f"[run {idx}] {dt:.1f}s | sections={v['section_count']}/{v['section_types']} | "
              f"kpi={v['kpi_count']} | insight_max={v['insight_max_len']} | valid={v['valid']}")
        if v["issues"]:
            for it in v["issues"]:
                print(f"          - {it}")
        return {"idx": idx, "ok": True, "duration_s": round(dt, 2), **v}
    except Exception as e:
        return {
            "idx": idx,
            "ok": False,
            "stage": "api_call",
            "error": f"{type(e).__name__}: {e}",
            "duration_s": round(time.time() - t0, 2),
        }


def main() -> int:
    print("=" * 60)
    print("阶段 0.1 · LLM JSON 输出稳定性 spike")
    print("=" * 60)
    print(f"provider = {os.getenv('LLM_PROVIDER', 'openai')}")
    print(f"model    = {os.getenv('LLM_MODEL', 'gpt-4o-mini')}")
    print(f"base_url = {os.getenv('LLM_BASE_URL', '<default>')}")

    client = LLMClient.from_env()

    if not smoke_test(client):
        print("\n[FAIL] smoke 不通,提前退出避免浪费正式配额。")
        return 2

    runs = []
    for i in range(1, 6):
        runs.append(run_one(client, i))

    # 统计
    ok = [r for r in runs if r.get("ok")]
    fully_valid = [r for r in ok if r.get("valid")]
    success_rate = len(ok) / len(runs)
    valid_rate = len(fully_valid) / len(runs)

    print("\n" + "=" * 60)
    print(f"汇总: 5 次调用")
    print(f"  - JSON 可解析: {len(ok)}/5  ({success_rate:.0%})")
    print(f"  - schema 全合法: {len(fully_valid)}/5  ({valid_rate:.0%})")
    print(f"  - 平均耗时: {sum(r['duration_s'] for r in runs)/len(runs):.1f}s")
    summary = client.usage_summary()
    print(f"  - 总 token: {summary.get('total_tokens')} | 总成本(USD): {summary.get('total_cost_usd')}")

    report = {
        "provider": os.getenv("LLM_PROVIDER"),
        "model": os.getenv("LLM_MODEL"),
        "json_parse_rate": success_rate,
        "schema_valid_rate": valid_rate,
        "runs": runs,
        "usage": summary,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已落: {REPORT_PATH}")

    # 验收: 至少 4/5 解析成功 + 至少 3/5 schema 完全合法
    if success_rate >= 0.8 and valid_rate >= 0.6:
        print("\n[PASS] LLM JSON 输出稳定性 spike 通过。")
        return 0
    print(f"\n[FAIL] 不达标 (需 success≥80% & valid≥60%)。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
