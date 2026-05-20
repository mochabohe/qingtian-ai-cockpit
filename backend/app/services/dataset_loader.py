"""
基于 data/datasets/manifest.json 的主线数据集统一加载层。

设计原则：
- 所有数据集元信息集中在 manifest.json，代码不写死字段名
- 提供统一接口，下游 Agent / 前端只通过 key 引用数据集
- CSV/Excel 直接返回 DataFrame；PDF 返回路径（交给 RAG 模块处理）

主线数据集（4 份）：
    voc_dongchedi          VOC 评论 csv
    sales_records          销售记录 xlsx (5 sheet)
    aftersales_records     售后维修 xlsx (3 sheet)
    quality_fault_cases    故障案例 xlsx (1 sheet, RAG 来源)

性能开关:
- DATASET_SAMPLE_LIMIT=200000 → 单表读取超过该行数则随机采样到该行数
  (现场临场遇到超大数据时的应急开关,先撑场再调优;不设默认全量加载)
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)


def _maybe_sample(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """如果设置了 DATASET_SAMPLE_LIMIT 且数据量超过该值,随机采样。
    用于现场临场超大数据应急,正常情况不触发。"""
    try:
        limit = int(os.getenv("DATASET_SAMPLE_LIMIT", "0"))
    except ValueError:
        return df
    if limit > 0 and len(df) > limit:
        logger.warning(
            "[DATASET_SAMPLE_LIMIT] %s 行数 %d > %d,随机采样到 %d (random_state=42)",
            label, len(df), limit, limit
        )
        return df.sample(n=limit, random_state=42).reset_index(drop=True)
    return df


# 项目根目录：backend/app/services/dataset_loader.py → backend → 项目根
REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = REPO_ROOT / "data" / "datasets"
MANIFEST_PATH = DATASETS_DIR / "manifest.json"

# 非阻塞增强用的"可选"竞品配置文件路径(P0-0)
# 重要:此文件**故意不进 manifest.json**,否则会变成主线依赖。
# 当前文件存在 → 提供对标增强;不存在 → 静默跳过,主线分析照常运行。
COMPETITOR_CONFIGS_PATH = DATASETS_DIR / "raw" / "competitor_configs.xlsx"


class DatasetNotFoundError(KeyError):
    """manifest 中未注册的数据集 key"""


class DatasetFileMissingError(FileNotFoundError):
    """manifest 注册了但磁盘上找不到文件"""


class FieldNotFoundError(KeyError):
    """
    业务别名(sale_id / repair_id / vehicle_system 等)无法解析到任何实际中文字段名。

    比裸 KeyError 多带:
    - alias / key / sheet:出错的别名 + 数据集定位
    - candidates:manifest 已声明的所有别名(便于发现写错的别名)
    - suggestions:数据列名中与 alias 字面最相似的 3 个(便于现场快速对照换数据集)

    设计目的:换数据集时如果 manifest 别名漏配,这条错误能直接告诉
    用户/现场操作人员"该补哪个 alias"。
    """

    def __init__(
        self,
        alias: str,
        key: str,
        sheet: Optional[str],
        candidates: Optional[List[str]] = None,
        suggestions: Optional[List[str]] = None,
    ) -> None:
        self.alias = alias
        self.key = key
        self.sheet = sheet
        self.candidates = list(candidates or [])
        self.suggestions = list(suggestions or [])
        loc = f"{key}" + (f"/{sheet}" if sheet else "")
        msg_parts = [
            f"业务别名 {alias!r} 无法在数据集 {loc} 中解析到实际字段名。"
        ]
        if self.candidates:
            msg_parts.append(
                "manifest 已声明的别名:" + ", ".join(self.candidates)
            )
        if self.suggestions:
            msg_parts.append(
                "数据列名中字面最接近的:" + ", ".join(self.suggestions)
            )
        super().__init__("\n".join(msg_parts))


@lru_cache(maxsize=1)
def load_manifest() -> Dict[str, Any]:
    """加载并缓存 manifest.json"""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"manifest.json 不存在：{MANIFEST_PATH}")
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_datasets() -> List[Dict[str, Any]]:
    """列出所有数据集的元信息（用于前端数据集卡片）"""
    manifest = load_manifest()
    out = []
    for ds in manifest.get("datasets", []):
        path = DATASETS_DIR / ds["file"]
        out.append({
            "key": ds["key"],
            "name": ds["name"],
            "format": ds["format"],
            "domain": ds["domain"],
            "agents": ds.get("agents", []),
            "use_case": ds.get("use_case", ""),
            "size_kb": ds.get("size_kb"),
            # csv 顶层有 rows;xlsx 顶层无 rows,降级到第一个 sheet 的 rows(主表行数)
            "rows": ds.get("rows") or (ds.get("sheets", [{}])[0].get("rows") if ds.get("sheets") else None),
            "sheets": [s["name"] for s in ds.get("sheets", [])] if ds.get("sheets") else None,
            "available": path.exists(),
            "file": ds["file"],
        })
    return out


def get_dataset_meta(key: str) -> Dict[str, Any]:
    """获取单个数据集的完整元信息"""
    manifest = load_manifest()
    for ds in manifest.get("datasets", []):
        if ds["key"] == key:
            return ds
    raise DatasetNotFoundError(f"未注册的数据集 key：{key}")


def get_path(key: str) -> Path:
    """返回数据集的绝对路径（PDF 类专用，CSV/Excel 也可用）"""
    meta = get_dataset_meta(key)
    path = DATASETS_DIR / meta["file"]
    if not path.exists():
        raise DatasetFileMissingError(
            f"数据集文件缺失：{path}\n请先运行 `python scripts/seed_real_data.py` 复制原始数据。"
        )
    return path


def load_csv(key: str, **read_csv_kwargs: Any) -> pd.DataFrame:
    """加载 csv 类数据集(超大数据时按 DATASET_SAMPLE_LIMIT 采样)"""
    meta = get_dataset_meta(key)
    if meta["format"] != "csv":
        raise ValueError(f"{key} 不是 csv 类数据集（实际：{meta['format']}）")
    df = pd.read_csv(get_path(key), **read_csv_kwargs)
    return _maybe_sample(df, label=f"csv:{key}")


def _backfill_aftersales_price_detail(
    df: "pd.DataFrame",
    xl: "pd.ExcelFile",
) -> "pd.DataFrame":
    """
    现场演示适配:售后维修价格明细表的某些版本缺失「单价」「小计金额」两列。
    通过 join 维修项目基础表的「基础单价」× 数量 反推回填,保持下游 manifest/业务代码零改动。

    触发条件:df 已有「数量」列且缺少「小计金额」列,同 xlsx 还存在「维修项目基础表」sheet。
    回填规则:
        单价     = 维修项目基础表.基础单价 (按 项目编号 join)
        小计金额 = 单价 × 数量
    若上述任一前提不成立,直接返回原 df 不动。
    """
    if "小计金额" in df.columns or "数量" not in df.columns or "项目编号" not in df.columns:
        return df
    base_sheet_name = None
    for sn in xl.sheet_names:
        if sn.strip() == "维修项目基础表":
            base_sheet_name = sn
            break
    if base_sheet_name is None:
        return df
    base = xl.parse(base_sheet_name)
    if "项目编号" not in base.columns or "基础单价" not in base.columns:
        return df

    price_lookup = base.set_index("项目编号")["基础单价"].to_dict()
    df = df.copy()
    if "单价" not in df.columns:
        df["单价"] = df["项目编号"].map(price_lookup)
    df["小计金额"] = pd.to_numeric(df["单价"], errors="coerce") * pd.to_numeric(df["数量"], errors="coerce")
    logger.info(
        "[backfill] aftersales 维修价格明细表 缺『小计金额』,已用『基础单价×数量』反推 %d 行",
        len(df),
    )
    return df


def _apply_post_load_patches(
    key: str,
    sheet: str,
    df: "pd.DataFrame",
    xl: "pd.ExcelFile",
) -> "pd.DataFrame":
    """统一的现场演示后处理钩子,集中所有"缺列回填"逻辑,便于审计/回滚"""
    if key == "aftersales_records" and sheet.strip() == "维修价格明细表":
        return _backfill_aftersales_price_detail(df, xl)
    return df


def load_excel(
    key: str,
    sheet: Optional[str] = None,
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    加载 xlsx 类数据集
    - sheet=None：返回 {sheet_name: DataFrame} 全表字典
    - sheet="维修记录表"：返回单个 DataFrame
    """
    meta = get_dataset_meta(key)
    if meta["format"] != "xlsx":
        raise ValueError(f"{key} 不是 xlsx 类数据集（实际：{meta['format']}）")
    path = get_path(key)
    xl = pd.ExcelFile(path)

    if sheet is None:
        out: Dict[str, pd.DataFrame] = {}
        for sn in xl.sheet_names:
            df = xl.parse(sn)
            df = _apply_post_load_patches(key, sn, df, xl)
            out[sn] = _maybe_sample(df, label=f"xlsx:{key}/{sn}")
        return out

    # 容错：支持传入 sheet 名带/不带前后空格
    sheet_names = {sn.strip(): sn for sn in xl.sheet_names}
    actual_sheet = sheet_names.get(sheet.strip())
    if actual_sheet is None:
        raise ValueError(
            f"{key} 不存在 sheet={sheet!r}，可用 sheet：{list(sheet_names)}"
        )
    df = xl.parse(actual_sheet)
    df = _apply_post_load_patches(key, actual_sheet, df, xl)
    return _maybe_sample(df, label=f"xlsx:{key}/{actual_sheet}")


def load_dataset(
    key: str,
    sheet: Optional[str] = None,
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame], Path]:
    """
    统一入口：根据数据集 format 自动选择加载方式
    - csv → DataFrame
    - xlsx → DataFrame（指定 sheet）或 {sheet: DataFrame}
    - pdf → Path（交给 RAG 模块自行解析）
    """
    meta = get_dataset_meta(key)
    fmt = meta["format"]
    if fmt == "csv":
        return load_csv(key)
    if fmt == "xlsx":
        return load_excel(key, sheet=sheet)
    if fmt == "pdf":
        return get_path(key)
    raise ValueError(f"未知 format：{fmt}（key={key}）")


def get_field_aliases(key: str, sheet: Optional[str] = None) -> Dict[str, str]:
    """
    返回该数据集的字段别名映射 {english_alias: chinese_field_name}

    用于让下游代码基于稳定的英文别名工作，而不是直接依赖中文字段名。
    """
    meta = get_dataset_meta(key)
    if meta["format"] == "csv":
        return dict(meta.get("key_fields", {}))
    if meta["format"] == "xlsx":
        sheets = meta.get("sheets", [])
        if not sheets:
            return {}
        if sheet is None:
            # 默认返回第一个 sheet
            return dict(sheets[0].get("key_fields", {}))
        for s in sheets:
            if s["name"].strip() == sheet.strip():
                return dict(s.get("key_fields", {}))
        return {}
    return {}


def resolve_field(key: str, alias: str, sheet: Optional[str] = None) -> Optional[str]:
    """根据英文别名解析出实际的中文字段名（找不到返回 None）"""
    return get_field_aliases(key, sheet).get(alias)


# ============================================================
# Schema 自适应:严格别名解析
# ============================================================
# 设计目标:让 briefing_analytics 等业务代码只依赖业务语义别名(sale_id/repair_id/...),
# 不再硬编码中文字段名。换数据集只改 manifest,代码零改动。
#
# 解析顺序:
#   1) manifest.key_fields[alias] → 取得中文列名,再确认该列在 DataFrame 里存在
#   2) schema_inspector 启发式兜底(detect_primary_id_column / 时间列 / 角色列)
#   3) 失败时抛 FieldNotFoundError(给 suggestions),而不是 KeyError
# ============================================================

# alias → schema_inspector 角色 的兜底映射(manifest 缺失时按角色找)
_ALIAS_FALLBACK_ROLES: Dict[str, str] = {
    # 主键/外键 → 用 detect_primary_id_column 找唯一率最高的 id 列
    "sale_id":     "primary_id",
    "repair_id":   "primary_id",
    "fault_id":    "primary_id",
    "detail_id":   "primary_id",
    "project_id":  "id_any",
    "campaign_id": "id_any",
    "vehicle_id":  "id_any",
    # 时间 → 第一个 time_cols
    "time":        "time",
    "sale_time":   "time",
    "repair_time": "time",
    "post_time":   "time",
}


def _top_similar_cols(columns: Any, alias: str, k: int = 3) -> List[str]:
    """从 columns 里挑出与 alias 字面最相似的 k 个列名,作为报错时的 suggestions"""
    try:
        cols = [str(c) for c in columns]
    except Exception:
        return []
    if not cols:
        return []
    # 用 difflib 兜底,不引入新依赖
    import difflib
    return difflib.get_close_matches(alias, cols, n=k, cutoff=0.0)


def _load_for_resolve(key: str, sheet: Optional[str]) -> "pd.DataFrame":
    """resolve_field_strict 内部用,把 load_dataset 的多种返回归一为单 DataFrame"""
    obj = load_dataset(key, sheet=sheet) if sheet else load_dataset(key)
    if isinstance(obj, dict):
        # xlsx 不指定 sheet → 取第一个(通常是主表)
        if not obj:
            raise DatasetNotFoundError(f"{key} 加载结果为空")
        return next(iter(obj.values()))
    if isinstance(obj, pd.DataFrame):
        return obj
    raise ValueError(f"{key} 不是表格类数据,无法 resolve_field(实际类型 {type(obj).__name__})")


def _heuristic_resolve(
    df: "pd.DataFrame",
    alias: str,
) -> Optional[str]:
    """
    manifest 缺失 alias 时的启发式兜底:
      - alias 属于"primary_id" 类 → 用 schema_inspector 取 unique_ratio 最高的 id 列
      - alias 属于"id_any" 类 → 取任意一个 id 列(优先名字含 alias 词根的)
      - alias 属于"time" 类 → 取第一个时间列
      - 都没命中 → 返回 None
    """
    from . import schema_inspector  # 延迟导入

    role = _ALIAS_FALLBACK_ROLES.get(alias)
    if role is None:
        return None

    if role == "time":
        roles = schema_inspector.infer_field_roles(df)
        return roles.time_cols[0] if roles.time_cols else None

    if role in ("primary_id", "id_any"):
        primary = schema_inspector.detect_primary_id_column(df)
        if primary is None:
            return None
        if role == "primary_id":
            return primary
        # id_any:优先名字里含 alias 词根的(如 vehicle_id 优先匹配"车型/车辆")
        roles = schema_inspector.infer_field_roles(df)
        for col in roles.id_cols:
            col_l = str(col).lower()
            if any(tok in col_l for tok in alias.lower().split("_")):
                return col
        return primary
    return None


def resolve_field_strict(
    key: str,
    alias: str,
    sheet: Optional[str] = None,
    df: Optional["pd.DataFrame"] = None,
) -> str:
    """
    严格解析业务别名 → 实际中文字段名,失败抛 FieldNotFoundError。

    Args:
        key:    数据集 key(如 sales_records)
        alias:  业务语义别名(如 sale_id / time / store)
        sheet:  xlsx 类指定 sheet(可选,缺省取第一个 sheet)
        df:     传入已加载的 DataFrame 可省一次 IO(否则内部 load_dataset)

    Resolve 顺序:
      1. manifest.key_fields[alias] 命中 + 该列在 df 里存在 → 直接返回
      2. _heuristic_resolve(启发式兜底,如取唯一率最高的 id 列)
      3. 抛 FieldNotFoundError(带 candidates + suggestions)
    """
    aliases = get_field_aliases(key, sheet)
    chinese = aliases.get(alias)

    # 没有 df 就懒加载一次(只在需要校验或兜底时加载)
    def _ensure_df() -> "pd.DataFrame":
        return df if df is not None else _load_for_resolve(key, sheet)

    if chinese:
        # manifest 命中:仍要校验该列在数据里真实存在,防止 manifest 落后于真实文件
        active_df = _ensure_df()
        if chinese in active_df.columns:
            return chinese
        logger.warning(
            "[resolve_field_strict] manifest 声明 %s/%s/%s → %r,但数据列里不存在,降级启发式",
            key, sheet, alias, chinese,
        )

    active_df = _ensure_df()
    fallback = _heuristic_resolve(active_df, alias)
    if fallback and fallback in active_df.columns:
        logger.info(
            "[resolve_field_strict] %s/%s/%s 走启发式 → %r",
            key, sheet, alias, fallback,
        )
        return fallback

    raise FieldNotFoundError(
        alias=alias,
        key=key,
        sheet=sheet,
        candidates=list(aliases.keys()),
        suggestions=_top_similar_cols(active_df.columns, alias),
    )


def resolve_fields_strict(
    key: str,
    aliases: List[str],
    sheet: Optional[str] = None,
    df: Optional["pd.DataFrame"] = None,
) -> Dict[str, str]:
    """批量版 resolve_field_strict;一次加载 df 解析多个 alias,失败原样抛"""
    active_df = df if df is not None else _load_for_resolve(key, sheet)
    return {
        a: resolve_field_strict(key, a, sheet=sheet, df=active_df)
        for a in aliases
    }


def primary_case() -> Dict[str, str]:
    """主案例配置（自家车型 / VOC 对照车型）"""
    return load_manifest().get("primary_case", {})


def agent_specs() -> Dict[str, Any]:
    """Agent 规格（用途、关联数据集）"""
    return load_manifest().get("agents", {})


# ==== Schema 自适应便利封装（避免下游 Agent 重复 import） ====

def inspect(key: str, sheet: Optional[str] = None) -> Dict[str, Any]:
    """
    一次性返回某个数据集（或 sheet）的字段画像。
    输出结构：
      {
        "key": ..., "name": ..., "format": ..., "sheet": ...,
        "rows": int, "cols": int,
        "field_roles": {time_cols/id_cols/metric_cols/dim_cols/text_cols/unknown_cols/field_meta},
        "field_aliases": {alias: chinese_field_name},
      }
    PDF 类无法 inspect，会返回 {"format": "pdf", "note": ...}。
    """
    from . import schema_inspector  # 延迟导入，避免循环

    meta = get_dataset_meta(key)
    fmt = meta["format"]

    if fmt == "pdf":
        return {
            "key": key, "name": meta["name"], "format": "pdf",
            "note": "PDF 类需通过 RAG 模块解析，暂不支持 schema 推断",
        }

    if fmt == "csv":
        df = load_csv(key)
        sheet_name = None
    else:
        sheet_name = sheet
        if sheet_name is None:
            sheets = meta.get("sheets", [])
            sheet_name = sheets[0]["name"] if sheets else None
        if sheet_name is None:
            raise ValueError(f"{key} 是 xlsx 但 manifest 未声明 sheet")
        df = load_excel(key, sheet=sheet_name)

    roles = schema_inspector.infer_field_roles(df)
    return {
        "key":           key,
        "name":          meta["name"],
        "format":        fmt,
        "sheet":         sheet_name,
        "rows":          len(df),
        "cols":          len(df.columns),
        "field_roles":   roles.to_dict(),
        "field_aliases": get_field_aliases(key, sheet=sheet_name),
    }


def cross_dataset_join_candidates(
    pairs: Optional[List[Tuple[str, Optional[str]]]] = None,
    min_overlap_ratio: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    跨主线数据集自动发现关联键候选。
    pairs: [(key, sheet), ...]；不传则默认遍历主线所有 csv/xlsx 数据集的"主 sheet"。
    """
    from . import schema_inspector  # 延迟导入

    if pairs is None:
        pairs = []
        for ds in load_manifest().get("datasets", []):
            if ds["format"] == "pdf":
                continue
            sheet = None
            if ds["format"] == "xlsx":
                sheets = ds.get("sheets", [])
                if not sheets:
                    continue
                sheet = sheets[0]["name"]
            pairs.append((ds["key"], sheet))

    dfs: Dict[str, "pd.DataFrame"] = {}
    label_map: Dict[str, Tuple[str, Optional[str]]] = {}
    for key, sheet in pairs:
        label = key if sheet is None else f"{key}.{sheet}"
        if get_dataset_meta(key)["format"] == "csv":
            dfs[label] = load_csv(key)
        else:
            dfs[label] = load_excel(key, sheet=sheet)
        label_map[label] = (key, sheet)

    cands = schema_inspector.detect_join_candidates(dfs, min_overlap_ratio=min_overlap_ratio)

    # 把 label 还原成 (key, sheet)，方便前端调用
    for c in cands:
        l_key, l_sheet = label_map[c["left"]["df"]]
        r_key, r_sheet = label_map[c["right"]["df"]]
        c["left"]  = {"key": l_key, "sheet": l_sheet, "col": c["left"]["col"]}
        c["right"] = {"key": r_key, "sheet": r_sheet, "col": c["right"]["col"]}
    return cands


# 重新导出 schema_inspector 的 ID 工具（让 Agent 工具层只 import dataset_loader 即可）
def normalize_id_series(series, target_width, prefix=None):
    from .schema_inspector import normalize_id_series as _impl
    return _impl(series, target_width, prefix)


def align_id_columns(s_a, s_b):
    from .schema_inspector import align_id_columns as _impl
    return _impl(s_a, s_b)


# ============================================================
# 非阻塞增强:可选竞品配置(P0-0)
# 设计原则:`if file exists then enrich, else skip`
# - 文件存在 → 返回 DataFrame
# - 文件不存在 → 返回 None,只 logger.info 一句,不抛异常,不污染日志
# - **不进 manifest.json**,避免主线分析意外依赖
# ============================================================

def load_competitor_configs() -> Optional[pd.DataFrame]:
    """
    加载可选的竞品配置表(非阻塞增强,P0-0)。

    返回:
        pd.DataFrame:文件存在且加载成功
        None:文件不存在 / 加载失败(均静默,不抛异常)

    主线调用方应该:
        df = load_competitor_configs()
        if df is None:
            # 跳过对标增强,继续主线流程
            ...
    """
    if not COMPETITOR_CONFIGS_PATH.exists():
        logger.info(
            "竞品配置文件不存在,跳过对标增强(预期路径: %s)",
            COMPETITOR_CONFIGS_PATH,
        )
        return None
    try:
        # 默认读第一个 sheet;数据方文件结构未知,这里保守不指定 sheet
        df = pd.read_excel(COMPETITOR_CONFIGS_PATH)
        logger.info(
            "已加载竞品配置文件: %s (rows=%d, cols=%d)",
            COMPETITOR_CONFIGS_PATH.name, len(df), len(df.columns),
        )
        return df
    except Exception as e:
        logger.warning("竞品配置文件加载失败,降级为不增强: %s", e)
        return None
