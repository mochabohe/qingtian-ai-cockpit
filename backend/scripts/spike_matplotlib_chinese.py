# -*- coding: utf-8 -*-
"""
阶段 0.2 spike: matplotlib 中文字体可用性验证。

验证项：
1. 当前环境 matplotlib 默认是否能正确显示中文（不出豆腐块）
2. 备选字体链 ['Microsoft YaHei','SimHei','Noto Sans CJK SC'] 哪些可用
3. 用候选字体渲染折线 + 饼图，输出 png
4. 字体缺失时的降级路径是否清晰

输出：
- spike_out/trend.png
- spike_out/pie.png
- 控制台打印：可用字体列表 / 渲染状态 / 建议
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无 GUI 环境
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

OUT_DIR = Path(__file__).parent / "spike_out"
OUT_DIR.mkdir(exist_ok=True)

# 候选中文字体链（按优先级）
CANDIDATE_FONTS = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "PingFang SC",
    "WenQuanYi Zen Hei",
]

THEME_PRIMARY = "#2563eb"
THEME_ACCENT = "#10b981"


def detect_available_fonts() -> list[str]:
    available = set()
    for f in fm.fontManager.ttflist:
        if f.name in CANDIDATE_FONTS:
            available.add(f.name)
    return [f for f in CANDIDATE_FONTS if f in available]


def render_trend(font: str, out_path: Path) -> None:
    plt.rcParams["font.sans-serif"] = [font]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)
    x = ["1月", "2月", "3月", "4月", "5月"]
    y = [9.8, 10.2, 11.1, 12.4, 11.8]
    ax.plot(x, y, marker="o", linewidth=2.5, color=THEME_PRIMARY)
    ax.fill_between(x, y, alpha=0.15, color=THEME_PRIMARY)
    ax.set_title("东风新能源板块销量趋势（万辆）", fontsize=15, color="#1f2937", pad=12)
    ax.set_xlabel("月份", fontsize=11, color="#6b7280")
    ax.set_ylabel("销量（万辆）", fontsize=11, color="#6b7280")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for sx, sy in zip(x, y):
        ax.annotate(f"{sy}", (sx, sy), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=10, color=THEME_PRIMARY)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_pie(font: str, out_path: Path) -> None:
    plt.rcParams["font.sans-serif"] = [font]
    plt.rcParams["axes.unicode_minus"] = False

    labels = ["华东", "华南", "华北", "西南", "其他"]
    sizes = [32, 28, 18, 12, 10]
    colors = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#94a3b8"]

    fig, ax = plt.subplots(figsize=(7, 5), dpi=120)
    ax.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%",
           startangle=90, pctdistance=0.78, textprops={"fontsize": 11})
    centre_circle = plt.Circle((0, 0), 0.55, fc="white")
    ax.add_artist(centre_circle)
    ax.set_title("4 月销量区域分布", fontsize=15, color="#1f2937", pad=12)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    print("=" * 60)
    print("阶段 0.2 · matplotlib 中文字体 spike")
    print("=" * 60)

    available = detect_available_fonts()
    print(f"\n候选字体（按优先级）：{CANDIDATE_FONTS}")
    print(f"实际可用：{available if available else '【无】'}")

    if not available:
        print("\n[FAIL] 当前环境无可用中文字体。")
        print("降级方案：图表区域改为数据表格 + 文字提示")
        print("修复建议：安装 微软雅黑 / SimHei / Noto Sans CJK SC 任一")
        return 1

    chosen = available[0]
    print(f"\n选用字体：{chosen}")

    trend_path = OUT_DIR / "trend.png"
    pie_path = OUT_DIR / "pie.png"
    print(f"渲染折线图 → {trend_path}")
    render_trend(chosen, trend_path)
    print(f"渲染饼图 → {pie_path}")
    render_pie(chosen, pie_path)

    # 检查输出文件
    for p in (trend_path, pie_path):
        size = p.stat().st_size
        status = "OK" if size > 5000 else "TOO_SMALL"
        print(f"  - {p.name}: {size} bytes [{status}]")

    print(f"\n[PASS] spike 通过。可用字体链：{available}")
    print("→ 在 report_exporter.py 中配置 plt.rcParams['font.sans-serif'] = " + str(available))
    return 0


if __name__ == "__main__":
    sys.exit(main())
