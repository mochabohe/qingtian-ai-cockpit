# -*- coding: utf-8 -*-
"""
阶段 4.6+4.7 冒烟: doc_to_pptx + doc_to_html 端到端验证。
不起 server,直接调函数,用最近一份 *.json 简报当输入。

校验项:
1. PPTX 生成成功,能被 python-pptx 重新加载,含合理页数
2. HTML 含关键 CSS / 卡片标签 / KPI / 合规水印
3. 字符长度 / 文件大小合理
4. matplotlib 图表(若有数据)能渲染
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # type: ignore
load_dotenv(ROOT / ".env")

from app.core.config import settings  # noqa: E402
from app.services.briefing_schema import parse_briefing  # noqa: E402
from app.services.report_exporter import (  # noqa: E402
    doc_to_pptx, doc_to_html,
    render_trend_png, render_distribution_png,
    _setup_matplotlib_font,
)


def main() -> int:
    print("=" * 60)
    print("阶段 4.6+4.7 · doc_to_pptx + doc_to_html 冒烟")
    print("=" * 60)

    report_dir = Path(settings.report_dir)
    json_files = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not json_files:
        print("[FAIL] data/reports/ 下没有 *.json 简报,先跑一次 spike_orchestrator_smoke")
        return 1

    json_path = json_files[-1]
    print(f"\n输入: {json_path.name} ({json_path.stat().st_size} bytes)")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    doc = parse_briefing(payload)
    print(f"  meta.title:        {doc.meta.title}")
    print(f"  cover.headline:    {doc.cover.headline}")
    print(f"  kpi count:         {len(doc.cover.kpi_strip)}")
    section_types = [s.type for s in doc.sections]
    print(f"  section types:     {section_types}")
    print(f"  actions count:     {len(doc.actions)}")

    issues = []

    # ---- 1) matplotlib 字体 ----
    print("\n--- matplotlib 字体 ---")
    font = _setup_matplotlib_font()
    if font:
        print(f"  使用: {font}")
    else:
        issues.append("matplotlib 中文字体缺失,图表会降级为空白占位")

    # ---- 2) 单 section 渲染 ----
    print("\n--- 单 section 图表渲染 ---")
    from app.services.briefing_schema import TrendSection, DistributionSection
    for sec in doc.sections:
        if isinstance(sec, TrendSection):
            png = render_trend_png(sec)
            print(f"  trend({sec.title}): {'OK ' + str(len(png)) + ' bytes' if png else '空(可能 data 为空)'}")
        elif isinstance(sec, DistributionSection):
            png = render_distribution_png(sec)
            print(f"  distribution({sec.title}): {'OK ' + str(len(png)) + ' bytes' if png else '空(可能 data 为空)'}")

    # ---- 3) doc_to_pptx ----
    print("\n--- doc_to_pptx ---")
    pptx_out = report_dir / (json_path.stem + ".pptx")
    if pptx_out.exists():
        pptx_out.unlink()
    try:
        doc_to_pptx(doc, pptx_out)
        size = pptx_out.stat().st_size
        print(f"  生成: {pptx_out.name} ({size} bytes)")
        if size < 10000:
            issues.append(f"PPTX 体积过小: {size}")
        # 重新加载
        from pptx import Presentation
        p = Presentation(pptx_out)
        n_slides = len(p.slides)
        print(f"  页数: {n_slides}")
        # 期望: 封面 + 摘要 + N section + 行动项 + 合规 + 末页
        expected_min = 1 + 1 + len(doc.sections) + (1 if doc.actions else 0) + 1 + 1
        if n_slides < expected_min:
            issues.append(f"PPTX 页数 {n_slides} 少于预期 {expected_min}")
    except Exception as e:
        issues.append(f"doc_to_pptx 报错: {e}")
        print(f"  [FAIL] {e}")

    # ---- 4) doc_to_html ----
    print("\n--- doc_to_html ---")
    try:
        html = doc_to_html(doc)
        size = len(html)
        print(f"  HTML 长度: {size}")
        # 关键标签
        markers = [
            '<section class="cover">',
            'class="kpi-strip"',
            '<section class="summary">',
            'class="actions"',
            'class="compliance"',
            '@page',
            'size: A4',
            '@media print',
        ]
        for m in markers:
            ok = m in html
            print(f"  [{'OK' if ok else 'XX'}] {m}")
            if not ok:
                issues.append(f"HTML 缺关键标签: {m}")
        # 写到文件让用户能浏览器打开
        html_out = report_dir / (json_path.stem + "_doc.html")
        html_out.write_text(html, encoding="utf-8")
        print(f"  HTML 已写到: {html_out.name} ({html_out.stat().st_size} bytes)")
    except Exception as e:
        issues.append(f"doc_to_html 报错: {e}")
        print(f"  [FAIL] {e}")

    # ---- 5) markdown fallback 路径(模拟 *.json 缺失) ----
    print("\n--- 降级路径:md_to_pptx (备援验证) ---")
    md_path = json_path.with_suffix(".md")
    if md_path.exists():
        from app.services.report_exporter import md_to_pptx, md_to_html
        try:
            md_pptx = report_dir / (json_path.stem + "_md.pptx")
            md_to_pptx(md_path.read_text(encoding="utf-8"), md_pptx)
            print(f"  md_to_pptx: {md_pptx.name} ({md_pptx.stat().st_size} bytes)")
            md_html = md_to_html(md_path.read_text(encoding="utf-8"))
            print(f"  md_to_html: {len(md_html)} chars")
            # 清理
            md_pptx.unlink(missing_ok=True)
        except Exception as e:
            issues.append(f"markdown fallback 报错: {e}")

    # ---- 汇总 ----
    print("\n" + "=" * 60)
    if not issues:
        print("[PASS] doc_to_pptx + doc_to_html 冒烟全部通过")
        return 0
    print("[FAIL] 发现问题:")
    for i in issues:
        print(f"  - {i}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
