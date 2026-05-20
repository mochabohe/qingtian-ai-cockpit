"""
把准备好的核心数据集复制并重命名到 data/datasets/raw/。

用法：
  python scripts/seed_real_data.py --source <你存放原始数据集的目录>
  # 或者直接修改下方 SOURCE_ROOT 常量

聚焦原则：只复制主线（销售-售后联动 + VOC 口碑）实际会用到的 4 份数据。

主线数据（3 个 + 1 RAG）：
    1   voc-评论数据.csv          → voc_dongchedi.csv          // 市场口碑 Agent
    6   销售-车辆销售表.xlsx       → sales_records.xlsx         // 销售-售后联动 Agent
    7   售后-车辆售后数据.xlsx     → aftersales_records.xlsx    // 销售-售后联动 Agent
   11   质量-故障案例.xlsx         → quality_fault_cases.xlsx   // 故障根因 RAG

可重复执行（已存在的目标文件会跳过；加 --force 覆盖）。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 默认源目录（请按需修改，或通过 --source 参数传入）
SOURCE_ROOT_DEFAULT = Path(r"C:\Users\<username>\Downloads\汽车经营数据集")

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_ROOT = REPO_ROOT / "data" / "datasets" / "raw"

# 复制清单：(源文件名, 目标文件名, 用途说明)
COPY_LIST = [
    ("1.voc-评论数据.csv", "voc_dongchedi.csv", "市场口碑 Agent · VOC 评论"),
    ("6.销售-车辆销售表.xlsx", "sales_records.xlsx", "销售-售后联动 Agent · 销售记录"),
    ("7.售后-车辆售后数据.xlsx", "aftersales_records.xlsx", "销售-售后联动 Agent · 售后维修"),
    ("11.质量-故障案例.xlsx", "quality_fault_cases.xlsx", "售后质量 RAG · 故障根因"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_ROOT_DEFAULT,
                        help="原始数据集所在目录")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的目标文件")
    args = parser.parse_args()

    source_root: Path = args.source

    if not source_root.exists():
        print(f"[错误] 源目录不存在：{source_root}", file=sys.stderr)
        print("       请用 --source <目录> 指定，或修改 SOURCE_ROOT_DEFAULT 后再跑", file=sys.stderr)
        return 1

    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    copied = skipped = missing = 0
    total_size = 0

    for src_name, dst_name, purpose in COPY_LIST:
        src = source_root / src_name
        dst = TARGET_ROOT / dst_name

        if not src.exists():
            print(f"  [缺失] {src_name}（{purpose}）— 源文件不存在")
            missing += 1
            continue

        if dst.exists() and not args.force:
            size_kb = dst.stat().st_size // 1024
            print(f"  [跳过] {dst_name}  ({size_kb} KB)  已存在，加 --force 可覆盖")
            skipped += 1
            total_size += dst.stat().st_size
            continue

        shutil.copy2(src, dst)
        size_kb = dst.stat().st_size // 1024
        print(f"  [复制] {src_name}")
        print(f"     → {dst_name}  ({size_kb} KB)  // {purpose}")
        copied += 1
        total_size += dst.stat().st_size

    print()
    print(f"汇总：复制 {copied} 个，跳过 {skipped} 个，缺失 {missing} 个，总大小 {total_size / 1024 / 1024:.1f} MB")
    print(f"目标目录：{TARGET_ROOT}")

    if missing > 0:
        print("[警告] 有源文件缺失，请检查源目录路径或文件名", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
