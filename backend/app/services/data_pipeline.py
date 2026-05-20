"""
数据分析引擎 - 5 类分析方法

公开 API:
  load_data(filepath)              加载 CSV/Excel/JSON/Parquet
  profile_data(df)                 字段类型/缺失/唯一值
  describe_numeric(df)             描述统计
  cluster_kmeans(df, k=3)          KMeans 聚类
  trend_analysis(df)               时序趋势 + 月度增长率
  correlation(df)                  相关性矩阵
  detect_anomalies(df)             3σ 异常检测
  run_full_analysis(filepath)      跑全套 5 类分析
  format_for_llm(result)           格式化为 LLM 可读文本
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# =============================================================================
# 加载
# =============================================================================
def load_data(filepath: str | Path) -> pd.DataFrame:
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")

    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix == ".tsv":
        return pd.read_csv(p, sep="\t")
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if suffix == ".json":
        return pd.read_json(p)
    if suffix == ".parquet":
        return pd.read_parquet(p)
    raise ValueError(f"不支持的格式: {suffix}")


# =============================================================================
# 1. 数据 profile（字段、类型、缺失）
# =============================================================================
def profile_data(df: pd.DataFrame) -> Dict[str, Any]:
    cols: List[Dict[str, Any]] = []
    for c in df.columns:
        cols.append({
            "name":   c,
            "dtype":  str(df[c].dtype),
            "nulls":  int(df[c].isnull().sum()),
            "unique": int(df[c].nunique()),
            "sample": _safe_sample(df[c]),
        })
    return {
        "n_rows":  len(df),
        "n_cols":  len(df.columns),
        "columns": cols,
    }


def _safe_sample(series: pd.Series, n: int = 3):
    try:
        vals = series.dropna().head(n).tolist()
        return [_to_native(v) for v in vals]
    except Exception:
        return []


def _to_native(v):
    """numpy 类型 → Python 原生（便于 JSON 序列化）"""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return v


# =============================================================================
# 2. 描述统计
# =============================================================================
def describe_numeric(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    nums = df.select_dtypes(include="number")
    if nums.empty:
        return {}
    desc = nums.describe().round(2)
    return {col: {k: float(v) for k, v in desc[col].items()} for col in desc.columns}


# =============================================================================
# 3. KMeans 聚类
# =============================================================================
def cluster_kmeans(df: pd.DataFrame, n_clusters: int = 3) -> Dict[str, Any]:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    nums = df.select_dtypes(include="number").dropna()
    if nums.shape[0] < n_clusters or nums.empty:
        return {"error": "数据量不足以聚类"}

    X = StandardScaler().fit_transform(nums)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    sizes = pd.Series(labels).value_counts().sort_index().to_dict()
    centers = pd.DataFrame(km.cluster_centers_, columns=nums.columns).round(2)

    # 如果原 df 有分类列（如 department），统计每个簇的主要类别
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    by_cat: Dict[str, Any] = {}
    if cat_cols:
        df_aligned = df.loc[nums.index].copy()
        df_aligned["_cluster"] = labels
        for c in cat_cols[:1]:  # 只看第一个分类列
            cnt = df_aligned.groupby(["_cluster", c]).size().unstack(fill_value=0)
            by_cat[c] = cnt.to_dict()

    return {
        "n_clusters":           n_clusters,
        "cluster_sizes":        {f"簇{int(k)}": int(v) for k, v in sizes.items()},
        "centers_normalized":   centers.to_dict(orient="index"),
        "by_category":          by_cat,
    }


# =============================================================================
# 4. 时序趋势
# =============================================================================
def trend_analysis(
    df: pd.DataFrame, time_col: Optional[str] = None
) -> Dict[str, Any]:
    if time_col is None:
        time_col = _detect_time_col(df)
    if time_col is None:
        return {"error": "未找到时间列"}

    df_t = df.copy()
    df_t[time_col] = pd.to_datetime(df_t[time_col], errors="coerce")
    df_t = df_t.dropna(subset=[time_col])
    if df_t.empty:
        return {"error": "时间列解析后为空"}

    df_t["_month"] = df_t[time_col].dt.to_period("M").astype(str)
    nums = df_t.select_dtypes(include="number").columns.tolist()
    if not nums:
        return {"error": "无数值列可做时序"}

    by_month = df_t.groupby("_month")[nums].sum().round(2)
    growth = by_month.pct_change().fillna(0).round(4) * 100  # 百分比

    return {
        "time_col":   time_col,
        "by_month":   by_month.to_dict(orient="index"),
        "growth_pct": growth.to_dict(orient="index"),
    }


def _detect_time_col(df: pd.DataFrame) -> Optional[str]:
    for c in df.columns:
        cl = c.lower()
        if any(kw in cl for kw in ("date", "time", "day", "日期", "时间")):
            return c
    # 尝试看哪一列能成功 to_datetime
    for c in df.columns:
        if df[c].dtype == "object":
            try:
                pd.to_datetime(df[c].head(10), errors="raise")
                return c
            except Exception:
                continue
    return None


# =============================================================================
# 5. 相关性矩阵
# =============================================================================
def correlation(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    nums = df.select_dtypes(include="number")
    if nums.shape[1] < 2:
        return {}
    corr = nums.corr().round(3)
    return {col: {k: float(v) for k, v in corr[col].items()} for col in corr.columns}


# =============================================================================
# 6. 异常检测（3σ 法则）
# =============================================================================
def detect_anomalies(df: pd.DataFrame) -> Dict[str, Any]:
    nums = df.select_dtypes(include="number")
    out: Dict[str, Any] = {}
    for col in nums.columns:
        s = nums[col].dropna()
        if s.empty:
            continue
        mean, std = s.mean(), s.std()
        if std == 0 or pd.isna(std):
            out[col] = {"n_outliers": 0, "examples": []}
            continue
        mask = (s > mean + 3 * std) | (s < mean - 3 * std)
        outliers = s[mask]
        out[col] = {
            "n_outliers": int(mask.sum()),
            "mean":       round(float(mean), 2),
            "std":        round(float(std), 2),
            "examples":   [float(v) for v in outliers.head(3).tolist()],
        }
    return out


# =============================================================================
# 主入口
# =============================================================================
def run_full_analysis(filepath: str | Path) -> Dict[str, Any]:
    df = load_data(filepath)
    return {
        "profile":     profile_data(df),
        "describe":    describe_numeric(df),
        "cluster":     cluster_kmeans(df),
        "trend":       trend_analysis(df),
        "correlation": correlation(df),
        "anomalies":   detect_anomalies(df),
    }


# =============================================================================
# 输出格式化（给 LLM 阅读）
# =============================================================================
def format_for_llm(result: Dict[str, Any], max_chars: int = 2200) -> str:
    """把分析结果浓缩为简洁文本，供 LLM analyzer Agent 阅读"""
    parts: List[str] = []

    p = result.get("profile") or {}
    parts.append(f"【数据规模】{p.get('n_rows', 0)} 行 × {p.get('n_cols', 0)} 列")
    cols = [c["name"] for c in p.get("columns", [])]
    if cols:
        parts.append(f"【字段】{', '.join(cols)}")

    desc = result.get("describe") or {}
    if desc:
        parts.append("\n【描述统计】（部分指标）")
        for col, stats in list(desc.items())[:6]:
            mean = stats.get("mean")
            mx = stats.get("max")
            mn = stats.get("min")
            if mean is not None:
                parts.append(f"  {col}: mean={mean}, min={mn}, max={mx}")

    cluster = result.get("cluster") or {}
    if "cluster_sizes" in cluster:
        parts.append(
            f"\n【KMeans 聚类】{cluster.get('n_clusters')} 簇，"
            f"分布: {cluster['cluster_sizes']}"
        )
        if cluster.get("by_category"):
            for cat, dist in cluster["by_category"].items():
                parts.append(f"  各簇 {cat} 分布: {dist}")

    trend = result.get("trend") or {}
    if "growth_pct" in trend:
        parts.append(f"\n【月度趋势】时间列={trend.get('time_col')}")
        for month, gs in list(trend["growth_pct"].items())[:6]:
            top = sorted(gs.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            top_str = ", ".join(f"{k}{v:+.1f}%" for k, v in top)
            parts.append(f"  {month}: {top_str}")

    anomalies = result.get("anomalies") or {}
    flagged = {k: v for k, v in anomalies.items() if v.get("n_outliers", 0) > 0}
    if flagged:
        parts.append("\n【异常点（3σ）】")
        for col, info in list(flagged.items())[:5]:
            parts.append(
                f"  {col}: {info['n_outliers']} 个异常, "
                f"mean={info.get('mean')}, std={info.get('std')}, "
                f"例={info.get('examples')}"
            )

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(已截断)"
    return text
