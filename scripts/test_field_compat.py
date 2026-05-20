"""
字段名变形兼容性测试 ─ 验证"换数据集 manifest 即可,代码零改动"承诺。

测试套路:
    1. 加载内置 4 份数据
    2. 对每份做"中文字段名变形" + 同步把 manifest.key_fields 改成新名
    3. 跑 briefing_analytics.run_main_brief()
    4. 验证 KPI 数字与原版一致(销售记录数 / 售后记录数 / 跨源匹配数 / VOC 聚类簇数等)

3 套变形场景(按设计文档):
    A. 中文同义词    销售id → 销售编号 / 维修单号 → 维修编号 / 内容 → 评论内容
    B. 中英混合      销售id → SaleID  / 维修单号 → RepairID / 内容 → Content
    C. 语义相近      销售id → 订单ID  / 维修单号 → 工单号  / 内容 → 评论文本

不调 LLM,纯本地分析,运行 < 60s。
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

# Windows 控制台 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

# 必须在 import 前定位 manifest 路径(后面会临时改写)
ORIGINAL_MANIFEST = REPO_ROOT / "data" / "datasets" / "manifest.json"
RAW_DIR = REPO_ROOT / "data" / "datasets" / "raw"


# ============================================================
# 变形规则(alias → 中文新列名)
# ============================================================
# 这些规则同时作用在两层:
#   1) 物理数据文件(把对应中文列重命名成新名)
#   2) manifest.key_fields(把 alias→ 旧中文名 改写为 alias→ 新中文名)
# 这样代码只读 manifest,哪怕物理列名变了也能跑通。

VARIANT_RULES: Dict[str, Dict[Tuple[str, str], Dict[str, str]]] = {
    # 变形 A:中文同义词
    "A_synonym": {
        ("sales_records", "车辆销售记录表"): {
            "sale_id": "销售编号",
            "time": "下单时间",
            "price_final": "成交价(元)",
            "store": "销售网点",
        },
        ("aftersales_records", "维修记录表"): {
            "repair_id": "维修编号",
            "sale_id": "销售编号外键",
            "time": "维修时间",
            "store": "维修网点",
            "service_type": "服务种类",
        },
        ("aftersales_records", "维修价格明细表"): {
            "repair_id": "维修编号",
            "project_name": "维修项目",
            "subtotal": "小计(元)",
        },
        ("voc_dongchedi", None): {
            "vehicle": "车型",
            "content": "评论内容",
        },
    },
    # 变形 B:中英混合
    "B_mixed": {
        ("sales_records", "车辆销售记录表"): {
            "sale_id": "SaleID",
            "time": "SaleTime",
            "price_final": "FinalPrice",
            "store": "SaleStore",
        },
        ("aftersales_records", "维修记录表"): {
            "repair_id": "RepairID",
            "sale_id": "SaleIDFK",
            "time": "RepairDate",
            "store": "RepairStore",
            "service_type": "ServiceType",
        },
        ("aftersales_records", "维修价格明细表"): {
            "repair_id": "RepairID",
            "project_name": "ProjectName",
            "subtotal": "Subtotal",
        },
        ("voc_dongchedi", None): {
            "vehicle": "VehicleSeries",
            "content": "Content",
        },
    },
    # 变形 C:语义相近
    "C_semantic": {
        ("sales_records", "车辆销售记录表"): {
            "sale_id": "订单ID",
            "time": "订单日期",
            "price_final": "实付金额",
            "store": "经销商",
        },
        ("aftersales_records", "维修记录表"): {
            "repair_id": "工单号",
            "sale_id": "关联订单ID",
            "time": "进店日期",
            "store": "服务商",
            "service_type": "工单类型",
        },
        ("aftersales_records", "维修价格明细表"): {
            "repair_id": "工单号",
            "project_name": "工时项目",
            "subtotal": "费用",
        },
        ("voc_dongchedi", None): {
            "vehicle": "车款",
            "content": "正文",
        },
    },
}


def _apply_rename_to_xlsx(src: Path, dst: Path,
                          per_sheet_rename: Dict[str, Dict[str, str]]) -> None:
    """把 src.xlsx 复制到 dst,逐 sheet 应用列重命名。

    per_sheet_rename: {sheet_name: {old_chinese: new_chinese}}
    """
    xl = pd.ExcelFile(src)
    with pd.ExcelWriter(dst, engine="openpyxl") as writer:
        for sn in xl.sheet_names:
            df = xl.parse(sn)
            mapping = per_sheet_rename.get(sn.strip(), {})
            if mapping:
                # 仅重命名实际存在的列(防止 mapping 写错列名)
                actual = {k: v for k, v in mapping.items() if k in df.columns}
                df = df.rename(columns=actual)
            df.to_excel(writer, sheet_name=sn, index=False)


def _apply_rename_to_csv(src: Path, dst: Path, rename: Dict[str, str]) -> None:
    df = pd.read_csv(src)
    actual = {k: v for k, v in rename.items() if k in df.columns}
    if actual:
        df = df.rename(columns=actual)
    df.to_csv(dst, index=False, encoding="utf-8")


def _build_variant_workspace(variant_name: str) -> Path:
    """
    在临时目录里搭一份"被变形过的数据集 + 对应 manifest"。

    返回临时目录路径(其下 datasets/{manifest.json + raw/...})。
    """
    rules = VARIANT_RULES[variant_name]
    tmp = Path(tempfile.mkdtemp(prefix=f"compat-{variant_name}-"))
    ds_dir = tmp / "datasets"
    raw_dir = ds_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. 拷贝 + 重命名物理数据
    for fname in ["sales_records.xlsx", "aftersales_records.xlsx"]:
        src = RAW_DIR / fname
        dst = raw_dir / fname
        if not src.exists():
            shutil.copy(src, dst)
            continue
        # 准备 per_sheet 改名表(alias → newname,我们要先把 alias 转成 老中文名,再映射到新中文名)
        per_sheet = _per_sheet_rename(variant_name, fname.replace(".xlsx", ""))
        _apply_rename_to_xlsx(src, dst, per_sheet)

    # voc_dongchedi.csv
    src_csv = RAW_DIR / "voc_dongchedi.csv"
    dst_csv = raw_dir / "voc_dongchedi.csv"
    voc_rename = _csv_rename(variant_name, "voc_dongchedi")
    _apply_rename_to_csv(src_csv, dst_csv, voc_rename)

    # 质量故障案例不在主线 KPI 验证范围,直接复制,避免 manifest 报丢失
    fault = RAW_DIR / "quality_fault_cases.xlsx"
    if fault.exists():
        shutil.copy(fault, raw_dir / "quality_fault_cases.xlsx")

    # 2. 写新 manifest
    new_manifest = _build_variant_manifest(variant_name)
    (ds_dir / "manifest.json").write_text(
        json.dumps(new_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp


def _per_sheet_rename(variant_name: str, key: str) -> Dict[str, Dict[str, str]]:
    """构建某个 xlsx 数据集的"sheet → {老中文 → 新中文}"映射"""
    rules = VARIANT_RULES[variant_name]
    out: Dict[str, Dict[str, str]] = {}
    # 从原 manifest 读取每个 sheet 的 alias→ 老中文名
    with ORIGINAL_MANIFEST.open(encoding="utf-8") as f:
        original = json.load(f)
    ds = next(d for d in original["datasets"] if d["key"] == key)
    for sheet in ds.get("sheets", []):
        sheet_name = sheet["name"]
        alias_map = sheet.get("key_fields", {})
        new_for_sheet = rules.get((key, sheet_name), {})
        # alias → new_chinese ⇒ old_chinese → new_chinese
        old_to_new: Dict[str, str] = {}
        for alias, new_chinese in new_for_sheet.items():
            old_chinese = alias_map.get(alias)
            if old_chinese:
                old_to_new[old_chinese] = new_chinese
        if old_to_new:
            out[sheet_name] = old_to_new
    return out


def _csv_rename(variant_name: str, key: str) -> Dict[str, str]:
    rules = VARIANT_RULES[variant_name]
    with ORIGINAL_MANIFEST.open(encoding="utf-8") as f:
        original = json.load(f)
    ds = next(d for d in original["datasets"] if d["key"] == key)
    alias_map = ds.get("key_fields", {})
    new_for = rules.get((key, None), {})
    return {
        alias_map[alias]: new_chinese
        for alias, new_chinese in new_for.items()
        if alias in alias_map
    }


def _build_variant_manifest(variant_name: str) -> Dict[str, Any]:
    """
    构造变形版 manifest:把改名涉及的 alias→ 老中文名 替换为 alias→ 新中文名,
    其余 alias 保持原样。
    """
    rules = VARIANT_RULES[variant_name]
    with ORIGINAL_MANIFEST.open(encoding="utf-8") as f:
        manifest = json.load(f)

    new_manifest = copy.deepcopy(manifest)
    for ds in new_manifest["datasets"]:
        key = ds["key"]
        # csv 顶层 key_fields
        if ds["format"] == "csv":
            new_for = rules.get((key, None), {})
            kf = ds.get("key_fields", {})
            for alias, new_chinese in new_for.items():
                if alias in kf:
                    kf[alias] = new_chinese
            continue
        # xlsx sheet 内 key_fields
        for sheet in ds.get("sheets", []):
            sn = sheet["name"]
            new_for = rules.get((key, sn), {})
            kf = sheet.get("key_fields", {})
            for alias, new_chinese in new_for.items():
                if alias in kf:
                    kf[alias] = new_chinese
    return new_manifest


# ============================================================
# 简报跑测 + KPI 比较
# ============================================================

def _kpi_signature(brief: Dict[str, Any]) -> Dict[str, Any]:
    """从 brief 中抽取一组结构性 KPI,用于比较;只看数字与计数,不比较文案。"""
    lk = brief.get("linkage", {}) or {}
    af = brief.get("aftersales", {}) or {}
    voc = brief.get("voc", {}) or {}
    return {
        "n_sales":              lk.get("n_sales"),
        "n_aftersales":         lk.get("n_aftersales"),
        "n_join_matched":       lk.get("n_join_matched"),
        "n_sales_curve_points": len(lk.get("sales_curve") or []),
        "n_top_sales_stores":   len(lk.get("top_sales_stores") or []),
        "n_top_after_vehicles": len(lk.get("top_aftersales_vehicles") or []),
        "n_anomalies":          len(lk.get("monthly_repair_anomalies") or []),
        "n_after_top_items":    len(af.get("items") or []),
        "n_voc_total":          voc.get("n_voc_total"),
        "n_after_dedup":        voc.get("n_after_dedup"),
        "n_clusters":           voc.get("n_clusters"),
    }


def _run_brief_in_workspace(workspace: Path) -> Dict[str, Any]:
    """切换 dataset_loader 的 manifest/raw 路径到 workspace,跑一次主线分析。

    通过 monkeypatch 模块全局变量 + 清缓存实现,不影响真实代码。
    """
    # 必须在 import 前 reset 缓存,因为 lru_cache 会锁住第一次的 manifest
    from app.services import dataset_loader

    # 备份原值
    orig_dir = dataset_loader.DATASETS_DIR
    orig_manifest = dataset_loader.MANIFEST_PATH
    try:
        new_dir = workspace / "datasets"
        dataset_loader.DATASETS_DIR = new_dir
        dataset_loader.MANIFEST_PATH = new_dir / "manifest.json"
        dataset_loader.load_manifest.cache_clear()  # type: ignore[attr-defined]

        # 延迟导入,确保 dataset_loader 切换路径后再载入
        from app.services import briefing_analytics
        return briefing_analytics.run_main_brief()
    finally:
        dataset_loader.DATASETS_DIR = orig_dir
        dataset_loader.MANIFEST_PATH = orig_manifest
        dataset_loader.load_manifest.cache_clear()  # type: ignore[attr-defined]


def main() -> int:
    print(f"=== 字段变形兼容性测试 ({len(VARIANT_RULES)} 套变形) ===\n")

    # 1) 跑原版,作为 baseline
    from app.services import briefing_analytics
    print("[BASELINE] 用原始 manifest + 原始数据跑主线分析...")
    t0 = time.perf_counter()
    base_brief = briefing_analytics.run_main_brief()
    base_kpi = _kpi_signature(base_brief)
    print(f"  baseline KPI: {json.dumps(base_kpi, ensure_ascii=False)}  耗时 {time.perf_counter()-t0:.1f}s\n")

    overall_pass = True
    for variant in VARIANT_RULES:
        print(f"[VARIANT {variant}] 构造变形数据 + manifest...")
        ws = _build_variant_workspace(variant)
        try:
            t0 = time.perf_counter()
            brief = _run_brief_in_workspace(ws)
            kpi = _kpi_signature(brief)
            elapsed = time.perf_counter() - t0
            diff = {k: (base_kpi[k], kpi[k]) for k in base_kpi if base_kpi[k] != kpi[k]}
            if diff:
                overall_pass = False
                print(f"  ❌ KPI 偏差 {len(diff)} 处(耗时 {elapsed:.1f}s):")
                for k, (b, v) in diff.items():
                    print(f"     · {k}: baseline={b}  variant={v}")
            else:
                print(f"  ✅ KPI 全等 (耗时 {elapsed:.1f}s)")
        except Exception as e:
            overall_pass = False
            print(f"  ❌ 变形 {variant} 抛异常: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        print()

    # 4) 缺失字段降级测试:故意删掉一个 alias,确认抛 FieldNotFoundError 而不是 KeyError
    print("[NEGATIVE] 故意删掉 sales_records.车辆销售记录表.key_fields.sale_id,期望 FieldNotFoundError...")
    ws = _build_variant_workspace("A_synonym")  # 复用一份 workspace
    try:
        manifest_path = ws / "datasets" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for ds in manifest["datasets"]:
            if ds["key"] == "sales_records":
                for sh in ds["sheets"]:
                    if sh["name"] == "车辆销售记录表":
                        sh["key_fields"].pop("sale_id", None)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            _run_brief_in_workspace(ws)
            # 走到这里说明启发式兜底成功识别了主键 → 也算通过(更稳)
            print("  ✅ alias 缺失但启发式兜底成功跑通(detect_primary_id_column 有效)")
        except Exception as e:
            from app.services.dataset_loader import FieldNotFoundError
            if isinstance(e, FieldNotFoundError):
                print(f"  ✅ 抛 FieldNotFoundError(suggestions={e.suggestions[:3]})")
            else:
                overall_pass = False
                print(f"  ❌ 抛了非 FieldNotFoundError: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(ws, ignore_errors=True)

    print()
    if overall_pass:
        print("=== ✅ 全部通过 ===")
        return 0
    print("=== ❌ 存在失败用例 ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
