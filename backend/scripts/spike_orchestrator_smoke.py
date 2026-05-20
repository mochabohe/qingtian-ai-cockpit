# -*- coding: utf-8 -*-
"""
阶段 1.7 端到端冒烟: 跑一次完整 orchestrator,验证落出 *.json + *.md。

校验项:
1. start / data_loaded / step_start*5 / step_done*5 / end 事件序列完整
2. data/reports/ 下生成新的 *.json 和 *.md(同名 stem)
3. *.json 能被 parse_briefing 重新解析为合法 BriefingDoc
4. doc.sections 数量 >= 3,至少包含 trend
5. doc.cover.kpi_strip 数量 >= 1
6. doc.actions 数量 >= 1
7. *.md 含关键章节标题
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # type: ignore

load_dotenv(ROOT / ".env")

from app.core.config import settings  # noqa: E402
from app.llm_client import LLMClient  # noqa: E402
from app.services.briefing_schema import BriefingDoc, parse_briefing  # noqa: E402
from app.services.orchestrator import AgentOrchestrator  # noqa: E402


TOPIC = "东风新能源板块 4 月经营分析"


async def consume_events(orch: AgentOrchestrator) -> dict:
    """把事件流消费完,返回事件统计"""
    counts: dict = {}
    saved_as = None
    async for event, data in orch.stream_events():
        counts[event] = counts.get(event, 0) + 1
        if event == "step_start":
            print(f"  [step_start] {data['index']}/{data.get('name')} - {data.get('title')}")
        elif event == "step_done":
            out = (data.get("output") or "")[:80].replace("\n", " ")
            print(f"  [step_done ] {data['index']}/{data.get('name')} | head: {out!r}")
        elif event == "end":
            saved_as = data.get("saved_as")
            print(f"  [end] saved_as={saved_as}")
        elif event == "error":
            print(f"  [ERROR] {data}")
    counts["_saved_as"] = saved_as
    return counts


async def amain() -> int:
    print("=" * 60)
    print("阶段 1.7 · orchestrator 端到端冒烟")
    print("=" * 60)

    llm = LLMClient.from_env()
    orch = AgentOrchestrator(llm, data_file=None)

    consumer = asyncio.create_task(consume_events(orch))
    await orch.run(TOPIC)
    counts = await consumer

    print("\n--- 事件统计 ---")
    for ev in ["start", "data_loaded", "step_start", "step_done", "end", "error", "step_error"]:
        print(f"  {ev:14s} {counts.get(ev, 0)}")

    # 校验事件序列
    issues = []
    if counts.get("start", 0) != 1:
        issues.append("start 事件缺失")
    if counts.get("step_start", 0) != 5:
        issues.append(f"step_start 期望 5,实际 {counts.get('step_start')}")
    if counts.get("step_done", 0) != 5:
        issues.append(f"step_done 期望 5,实际 {counts.get('step_done')}")
    if counts.get("end", 0) != 1:
        issues.append("end 事件缺失")
    if counts.get("error", 0) > 0 or counts.get("step_error", 0) > 0:
        issues.append("有 error / step_error 事件")

    saved_as = counts.get("_saved_as")
    if not saved_as:
        issues.append("end.saved_as 为空")

    # 校验文件
    report_dir = Path(settings.report_dir)
    if saved_as:
        stem = saved_as.rsplit(".", 1)[0]
        json_path = report_dir / f"{stem}.json"
        md_path = report_dir / f"{stem}.md"
        print(f"\n--- 文件检查 ---")
        print(f"  json: {json_path} | exists={json_path.exists()} | size={json_path.stat().st_size if json_path.exists() else 0}")
        print(f"  md  : {md_path} | exists={md_path.exists()} | size={md_path.stat().st_size if md_path.exists() else 0}")
        if not json_path.exists():
            issues.append(f"{json_path.name} 不存在")
        if not md_path.exists():
            issues.append(f"{md_path.name} 不存在")

        # 校验 JSON 结构
        if json_path.exists():
            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
                doc = parse_briefing(raw)
                print(f"\n--- BriefingDoc 校验 ---")
                print(f"  meta.title:        {doc.meta.title}")
                print(f"  meta.period:       {doc.meta.period}")
                print(f"  meta.audit_id:     {doc.meta.audit_id}")
                print(f"  cover.headline:    {doc.cover.headline}")
                print(f"  kpi_strip count:   {len(doc.cover.kpi_strip)}")
                print(f"  sections count:    {len(doc.sections)}")
                section_types = [s.type for s in doc.sections]
                print(f"  section types:     {section_types}")
                print(f"  actions count:     {len(doc.actions)}")
                print(f"  exec_summary len:  {len(doc.executive_summary)}")
                print(f"  compliance:        {doc.compliance.masked_field_count}/{doc.compliance.total_field_count}")
                if len(doc.sections) < 3:
                    issues.append(f"sections 数量 {len(doc.sections)} < 3")
                if "trend" not in section_types:
                    issues.append("sections 缺 trend 类型")
                if len(doc.cover.kpi_strip) < 1:
                    issues.append("kpi_strip 为空")
                if len(doc.actions) < 1:
                    issues.append("actions 为空")
            except Exception as e:
                issues.append(f"JSON 解析为 BriefingDoc 失败: {e}")

        # 校验 md 关键标题
        if md_path.exists():
            md = md_path.read_text(encoding="utf-8")
            for marker in ["## 一、摘要", "## 二、关键洞察", "## 三、行动建议", "## 四、合规与数据出处"]:
                if marker not in md:
                    issues.append(f"md 缺关键章节: {marker}")

    print("\n" + "=" * 60)
    if not issues:
        print("[PASS] 端到端冒烟全部通过")
        usage = llm.usage_summary()
        print(f"  本次总 token: {usage.get('total_tokens')} | 调用次数: {usage.get('total_calls')} | 总耗时: {usage.get('total_duration_s')}s")
        return 0
    print("[FAIL] 发现以下问题:")
    for it in issues:
        print(f"  - {it}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
