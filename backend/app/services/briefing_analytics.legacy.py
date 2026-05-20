"""
主线分析三件套 ─ 把 dataset_loader + schema_inspector + rag_store 串成
"销售-售后联动 + 市场口碑" 三路真实数据摘要,供 ANALYZER_PROMPT 喂给 LLM。

核心 API：
    run_main_brief() -> Dict[str, Any]    跑全部三路并返回结构化结果
    format_for_llm(brief) -> str          把 dict 格式化成给 LLM 看的中文 markdown

被 orchestrator._maybe_run_real_analysis 调用,替换通用 5 类分析。
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

import pandas as pd

from . import dataset_loader, rag_store, schema_inspector, voc_clustering

logger = logging.getLogger(__name__)


# ============================================================
# 第 1 路：销售-售后联动
# ============================================================

def linkage_brief(top_n: int = 5) -> Dict[str, Any]:
    """跨源 join 销售↔售后 → 销售曲线 + 售后频次 TOP + 服务网络分离指标"""
    sales = dataset_loader.load_excel("sales_records", sheet="车辆销售记录表")
    after = dataset_loader.load_excel("aftersales_records", sheet="维修记录表")

    # ---- 主键自动对齐(项目核心算法亮点) ----
    aligned_a, aligned_b, align_report = schema_inspector.align_id_columns(
        sales["销售id"], after["车辆销售ID"]
    )
    sales = sales.assign(_aligned_id=aligned_a)
    after = after.assign(_aligned_id=aligned_b)

    # ---- 销售曲线(月度) ----
    # 大数据时只保留近 12 个月,避免 LLM context 超大 + PPT/视频脚本太长
    sales["_dt"] = pd.to_datetime(sales["销售时间"], errors="coerce")
    sales = sales.dropna(subset=["_dt"])
    sales["_month"] = sales["_dt"].dt.strftime("%Y-%m")
    monthly = (
        sales.groupby("_month")
             .agg(orders=("销售id", "count"), revenue=("最终价格(元)", "sum"))
             .reset_index()
             .sort_values("_month")
    )
    # 近 12 月截断:只保留最新 12 个月的数据,既覆盖年度同比又控制长度
    if len(monthly) > 12:
        monthly = monthly.tail(12).reset_index(drop=True)
    sales_curve = [
        {"month": m, "orders": int(o), "revenue_wan": round(float(r) / 10000, 1)}
        for m, o, r in monthly[["_month", "orders", "revenue"]].itertuples(index=False)
    ]

    # ---- TOP N 销售门店 ----
    top_sales_stores = (
        sales.groupby("销售门店")["最终价格(元)"]
             .agg(["count", "sum"])
             .reset_index()
             .sort_values("count", ascending=False)
             .head(top_n)
    )
    sales_stores = [
        {"store": s, "orders": int(c), "revenue_wan": round(float(v) / 10000, 1)}
        for s, c, v in top_sales_stores[["销售门店", "count", "sum"]].itertuples(index=False)
    ]

    # ---- TOP N 售后频次车型 ----
    top_after_vehicles = (
        after.merge(
            sales[["_aligned_id", "车型id"]].drop_duplicates(),
            on="_aligned_id", how="inner",
        )
        .groupby("车型id")
        .size().reset_index(name="repair_orders")
        .sort_values("repair_orders", ascending=False)
        .head(top_n)
    )
    aftersales_top_vehicles = [
        {"vehicle_id": int(v), "repair_orders": int(c)}
        for v, c in top_after_vehicles[["车型id", "repair_orders"]].itertuples(index=False)
    ]

    # ---- 服务网络分离指标(销售门店 vs 维修门店一致率) ----
    joined = sales[["_aligned_id", "销售门店"]].merge(
        after[["_aligned_id", "维修门店"]], on="_aligned_id", how="inner"
    )
    same_store = (joined["销售门店"] == joined["维修门店"]).sum()
    network_separation = {
        "joined_records":     int(len(joined)),
        "same_store_records": int(same_store),
        "same_store_ratio":   round(float(same_store) / max(len(joined), 1), 4),
        "n_sales_stores":     int(sales["销售门店"].nunique()),
        "n_repair_stores":    int(after["维修门店"].nunique()),
    }

    # ---- 售后服务类型分布 ----
    service_type_dist = (
        after["服务类型"]
        .value_counts(normalize=False)
        .head(10)
        .to_dict()
    )

    # ---- 异常检测(售后单数月度 3σ) ----
    after["_dt"] = pd.to_datetime(after["维修日期"], errors="coerce")
    after_m = after.dropna(subset=["_dt"]).copy()
    after_m["_month"] = after_m["_dt"].dt.strftime("%Y-%m")
    repair_monthly = after_m.groupby("_month").size()
    mean = float(repair_monthly.mean())
    std = float(repair_monthly.std() or 0.0)
    threshold_high = mean + 3 * std
    anomalies = [
        {"month": m, "orders": int(c), "deviation": round((c - mean) / max(std, 1e-6), 2)}
        for m, c in repair_monthly.items()
        if c > threshold_high
    ]

    return {
        "align_report":          align_report,
        "n_sales":               int(len(sales)),
        "n_aftersales":          int(len(after)),
        "n_join_matched":        int(len(joined)),
        "join_match_ratio":      round(len(joined) / max(len(after), 1), 4),
        "sales_curve":           sales_curve,
        "top_sales_stores":      sales_stores,
        "top_aftersales_vehicles": aftersales_top_vehicles,
        "network_separation":    network_separation,
        "service_type_dist":     {str(k): int(v) for k, v in service_type_dist.items()},
        "monthly_repair_anomalies": anomalies,
    }


# ============================================================
# 第 2 路：售后 TOP 维修项目 + RAG 根因检索
# ============================================================

def aftersales_top_with_rag(
    top_n: int = 5,
    rag_per_item: int = 1,
    rag_min_score: float = 0.2,
) -> Dict[str, Any]:
    """从维修价格明细表挑 TOP N 维修项目,对每个项目跑 RAG 检索匹配故障根因。

    rag_min_score: TF-IDF cosine 分数阈值,低于该分数视为"未命中"(filter 掉,
    避免出现"刹车片 → 动力电池压差故障 score=0.137"这种业务上不通的低分误命中)。
    """
    detail = dataset_loader.load_excel("aftersales_records", sheet="维修价格明细表")

    item_rank = (
        detail.groupby("维修项目名称")
              .agg(orders=("维修单号", "nunique"), total_amount=("小计金额", "sum"))
              .reset_index()
              .sort_values("orders", ascending=False)
              .head(top_n)
    )

    store = rag_store.get_default_store()
    items = []
    for proj, orders, total in item_rank[["维修项目名称", "orders", "total_amount"]].itertuples(index=False):
        raw_hits = store.search(str(proj), top_k=rag_per_item)
        # 阈值过滤:低分命中视为未命中(防止跨域误命中)
        hits = [h for h in raw_hits if float(h.get("score") or 0) >= rag_min_score]
        items.append({
            "project":       str(proj),
            "orders":        int(orders),
            "total_amount":  round(float(total), 2),
            "rag_hits":      hits,  # 可能为空 → 渲染时显示"未命中"
        })

    return {
        "top_n": top_n,
        "items": items,
        "rag_total_docs": store.n_docs,
        "rag_min_score":  rag_min_score,
    }


# ============================================================
# 第 3 路：VOC 市场口碑(简版,完整聚类留给后续 P1)
# ============================================================

# 简单痛点/卖点关键词种子,用于第一版口碑摘要
_PAIN_KEYWORDS = ["差", "烂", "贵", "卡", "问题", "故障", "失灵", "异响", "漏", "黑屏", "死机",
                  "不好用", "不灵", "不准", "无语", "失望", "投诉", "退订"]
_PRAISE_KEYWORDS = ["好", "棒", "舒服", "省心", "稳", "快", "强", "推荐", "值", "满意", "牛"]


def voc_brief(top_competitor: str = "Model Y", top_pain: int = 3, top_praise: int = 3) -> Dict[str, Any]:
    """
    竞品 VOC 口碑摘要(聚类版):
    - 物理去重 → TF-IDF 向量化 → KMeans 聚类(自动选 K) → 关键词 + 代表评论 + 情感打分
    - 输出 TOP 痛点话题 / TOP 卖点话题,带规模、情感强度、关键词、代表性评论
    """
    df = dataset_loader.load_csv("voc_dongchedi")
    n_total = int(df["内容"].notna().sum())

    vehicle_dist = df["车系"].value_counts().head(8).to_dict()

    cluster_result = voc_clustering.cluster_voc(target_vehicle=top_competitor)
    pains = voc_clustering.top_pain_points(cluster_result, top_n=top_pain)
    praises = voc_clustering.top_praise_points(cluster_result, top_n=top_praise)

    def _cluster_summary(c: voc_clustering.ClusterDoc) -> Dict[str, Any]:
        return {
            "cluster_id":       c.cluster_id,
            "size":             c.size,
            "sentiment_label":  c.sentiment_label,
            "sentiment_score":  c.sentiment_score,
            "keywords":         c.keywords[:6],
            "representative":   c.representative[:2],  # 取前 2 条
        }

    return {
        "n_voc_total":           n_total,
        "vehicle_distribution":  {str(k): int(v) for k, v in vehicle_dist.items()},
        "target_competitor":     top_competitor,
        "n_after_dedup":         cluster_result.n_after_dedup,
        "n_clusters":            cluster_result.n_clusters,
        "silhouette":             cluster_result.silhouette,
        "top_pain_clusters":     [_cluster_summary(c) for c in pains],
        "top_praise_clusters":   [_cluster_summary(c) for c in praises],
    }


# ============================================================
# 顶层入口
# ============================================================

def run_main_brief(self_vehicle_id: Optional[int] = None) -> Dict[str, Any]:
    """三路并跑,返回完整 brief dict"""
    out = {
        "linkage":     linkage_brief(),
        "aftersales":  aftersales_top_with_rag(),
        "voc":         voc_brief(),
    }
    return out


def format_for_llm(brief: Dict[str, Any]) -> str:
    """把 brief dict 格式化成 LLM 能消化的中文 markdown,< 2000 字"""
    lines: List[str] = []

    # ---- 销售-售后联动 ----
    lk = brief.get("linkage", {})
    align = lk.get("align_report", {})
    lines.append("## 第 1 路 · 销售-售后联动")
    lines.append(f"- 销售记录 {lk.get('n_sales', 0):,} 行,售后维修 {lk.get('n_aftersales', 0):,} 行")
    if align.get("normalized"):
        lines.append(
            f"- ⚠️ 主键格式不一致已自动修复:补齐前导零至 {align.get('target_width')} 位,"
            f"对齐后匹配 {lk.get('n_join_matched', 0):,} 条 "
            f"(覆盖率 {lk.get('join_match_ratio', 0)*100:.1f}%)"
        )
    else:
        lines.append(f"- 跨源 join 匹配 {lk.get('n_join_matched', 0):,} 条")

    # 销售曲线
    curve = lk.get("sales_curve", [])
    if curve:
        head = curve[:3]
        tail = curve[-3:]
        lines.append("- 销售月度曲线(节选):")
        for r in head + (["..."] if len(curve) > 6 else []) + tail:
            if isinstance(r, str):
                lines.append(f"    - {r}")
            else:
                lines.append(f"    - {r['month']}: {r['orders']:,} 单 / {r['revenue_wan']:,} 万")

    # TOP 销售门店
    if lk.get("top_sales_stores"):
        s = "、".join(f"{x['store']}({x['orders']}单)" for x in lk["top_sales_stores"][:3])
        lines.append(f"- TOP 销售门店: {s}")

    # TOP 售后频次车型
    if lk.get("top_aftersales_vehicles"):
        s = "、".join(f"车型{x['vehicle_id']}({x['repair_orders']}次)" for x in lk["top_aftersales_vehicles"][:5])
        lines.append(f"- TOP 售后频次车型: {s}")

    # 服务类型分布
    if lk.get("service_type_dist"):
        s = "、".join(f"{k} {v}" for k, v in list(lk["service_type_dist"].items())[:5])
        lines.append(f"- 售后服务类型分布: {s}")

    # 服务网络分离
    nw = lk.get("network_separation", {})
    if nw:
        lines.append(
            f"- 🔥 服务网络分离: {nw.get('n_sales_stores')} 销售门店 vs "
            f"{nw.get('n_repair_stores')} 维修门店,同门店维修率仅 "
            f"{nw.get('same_store_ratio', 0)*100:.1f}%"
        )

    # 月度异常
    if lk.get("monthly_repair_anomalies"):
        ano = lk["monthly_repair_anomalies"][:3]
        s = "、".join(f"{x['month']}({x['orders']}单, {x['deviation']:+.1f}σ)" for x in ano)
        lines.append(f"- 售后月度 3σ 异常: {s}")

    lines.append("")

    # ---- 售后 TOP 维修项目 + RAG ----
    af = brief.get("aftersales", {})
    lines.append("## 第 2 路 · 售后 TOP 维修项目 + 故障根因 RAG")
    for i, it in enumerate(af.get("items", []), 1):
        lines.append(
            f"{i}. {it['project']} — {it['orders']} 单, ¥{it['total_amount']:,.0f}"
        )
        for h in it.get("rag_hits", []):
            cause = (h.get("root_cause") or "")[:80]
            method = (h.get("repair_method") or "")[:60]
            lines.append(f"    · RAG 命中: {h.get('topic')} (score={h.get('score')}); 根因: {cause}; 维修方法: {method}")
    lines.append("")

    # ---- VOC 市场口碑(聚类版) ----
    voc = brief.get("voc", {})
    lines.append("## 第 3 路 · 市场口碑(VOC 聚类) ⭐")
    # 只给 LLM 业务口径数字(原始 / 有效 / 簇数);silhouette 等内部技术指标不外露,
    # 避免 writer 把它写进 KPI strip(对 PPT 受众无意义且容易被解读为"模型差")
    lines.append(
        f"- 原始 {voc.get('n_voc_total', 0)} 条 → 有效样本 {voc.get('n_after_dedup', 0)} 条 "
        f"→ 提炼 {voc.get('n_clusters', 0)} 个用户话题"
    )
    lines.append(f"- 聚焦竞品: {voc.get('target_competitor')}")
    if voc.get("vehicle_distribution"):
        s = "、".join(f"{k}({v})" for k, v in list(voc["vehicle_distribution"].items())[:5])
        lines.append(f"- VOC 车系分布 TOP5: {s}")

    if voc.get("top_pain_clusters"):
        lines.append("- 🔻 TOP 痛点话题(用户负面情感聚集):")
        for i, c in enumerate(voc["top_pain_clusters"], start=1):
            kws = "、".join(c.get("keywords", [])[:5])
            lines.append(
                f"    - 痛点 {i}: {kws} | {c['size']} 条, 情感{c['sentiment_score']:+.2f}"
            )
            for rep in c.get("representative", [])[:1]:
                short = rep[:60] + ("…" if len(rep) > 60 else "")
                lines.append(f"      代表: 「{short}」")

    if voc.get("top_praise_clusters"):
        lines.append("- 🔺 TOP 卖点话题(用户正面情感聚集):")
        for i, c in enumerate(voc["top_praise_clusters"], start=1):
            kws = "、".join(c.get("keywords", [])[:5])
            lines.append(
                f"    - 卖点 {i}: {kws} | {c['size']} 条, 情感{c['sentiment_score']:+.2f}"
            )
            for rep in c.get("representative", [])[:1]:
                short = rep[:60] + ("…" if len(rep) > 60 else "")
                lines.append(f"      代表: 「{short}」")

    return "\n".join(lines)
