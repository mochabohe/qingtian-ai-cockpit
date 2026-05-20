"""
主线分析三件套 ─ 把 dataset_loader + schema_inspector + rag_store 串成
"销售-售后联动 + 市场口碑" 三路真实数据摘要,供 ANALYZER_PROMPT 喂给 LLM。

核心 API：
    run_main_brief() -> Dict[str, Any]    跑全部三路并返回结构化结果
    format_for_llm(brief) -> str          把 dict 格式化成给 LLM 看的中文 markdown

被 orchestrator._maybe_run_real_analysis 调用,替换通用 5 类分析。

★ Schema 自适应说明(2026-05-08 通用化改造):
   本模块不直接出现中文字段名(销售id/维修单号/最终价格(元) 等),全部通过
   dataset_loader.resolve_field_strict 由 manifest.json 的 key_fields 别名机制解析。
   换 4S 店数据集只改 manifest 即可,代码零改动。
   (manifest 缺失别名时,schema_inspector 启发式兜底;再失败抛 FieldNotFoundError)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from . import dataset_loader, rag_store, schema_inspector, voc_clustering

logger = logging.getLogger(__name__)


# ============================================================
# 第 1 路：销售-售后联动
# ============================================================

# 销售记录表:linkage_brief 用到的所有别名
_SALES_ALIASES = ["sale_id", "vehicle_id", "time", "price_final", "store"]
# 售后维修记录表:linkage_brief 用到的所有别名(sale_id 是外键,store/time/service_type)
_AFTER_ALIASES = ["sale_id", "time", "store", "service_type"]


def _build_vehicle_id_name_map() -> Dict[Any, str]:
    """从车辆配置表构建 车型id → 车型名称 映射。
    现场演示新数据把"车辆价格表"替换成了"车辆配置表",
    新表带"车型名称"字段,可以把 TOP 售后/销售车型从代号(车型11)翻译为可读名称。
    找不到表/字段时返回空 dict,不阻塞主线。"""
    try:
        cfg = dataset_loader.load_excel("sales_records", sheet="车辆配置表")
    except Exception as e:
        logger.info("[vehicle_name_map] 车辆配置表不可用,跳过翻译: %s", e)
        return {}
    if "车型id" not in cfg.columns or "车型名称" not in cfg.columns:
        logger.info("[vehicle_name_map] 缺『车型id』或『车型名称』列,跳过翻译")
        return {}
    mapping: Dict[Any, str] = {}
    for vid, vname in zip(cfg["车型id"], cfg["车型名称"]):
        if pd.isna(vid) or pd.isna(vname):
            continue
        # 同时存 int / str 两种 key,兼容下游 dict.get 时 dtype 不一致
        try:
            mapping[int(vid)] = str(vname).strip()
        except (TypeError, ValueError):
            pass
        mapping[str(vid).strip()] = str(vname).strip()
    return mapping


def linkage_brief(top_n: int = 5) -> Dict[str, Any]:
    """跨源 join 销售↔售后 → 销售曲线 + 售后频次 TOP + 服务网络分离指标

    所有字段名通过 manifest.json 的 key_fields 别名解析,
    换数据集只需更新 manifest,代码无需改动。
    """
    sales = dataset_loader.load_excel("sales_records", sheet="车辆销售记录表")
    after = dataset_loader.load_excel("aftersales_records", sheet="维修记录表")
    vehicle_name_map = _build_vehicle_id_name_map()

    # ---- 别名 → 实际字段名(单一真理源:manifest.key_fields) ----
    s_cols = dataset_loader.resolve_fields_strict(
        "sales_records", _SALES_ALIASES, sheet="车辆销售记录表", df=sales,
    )
    a_cols = dataset_loader.resolve_fields_strict(
        "aftersales_records", _AFTER_ALIASES, sheet="维修记录表", df=after,
    )

    sale_id_col       = s_cols["sale_id"]        # e.g. 销售id
    s_vehicle_col     = s_cols["vehicle_id"]     # e.g. 车型id
    s_time_col        = s_cols["time"]           # e.g. 销售时间
    s_price_col       = s_cols["price_final"]    # e.g. 最终价格(元)
    s_store_col       = s_cols["store"]          # e.g. 销售门店

    a_sale_fk_col     = a_cols["sale_id"]        # e.g. 车辆销售ID(售后表里的销售外键)
    a_time_col        = a_cols["time"]           # e.g. 维修日期
    a_store_col       = a_cols["store"]          # e.g. 维修门店
    a_service_col     = a_cols["service_type"]   # e.g. 服务类型

    # ---- 主键自动对齐(项目核心算法亮点) ----
    aligned_a, aligned_b, align_report = schema_inspector.align_id_columns(
        sales[sale_id_col], after[a_sale_fk_col]
    )
    sales = sales.assign(_aligned_id=aligned_a)
    after = after.assign(_aligned_id=aligned_b)

    # ---- 销售曲线(月度) ----
    sales["_dt"] = pd.to_datetime(sales[s_time_col], errors="coerce")
    sales = sales.dropna(subset=["_dt"])
    sales["_month"] = sales["_dt"].dt.strftime("%Y-%m")
    monthly = (
        sales.groupby("_month")
             .agg(orders=(sale_id_col, "count"), revenue=(s_price_col, "sum"))
             .reset_index()
             .sort_values("_month")
    )

    # ---- 计算销售环比 (MoM) 和 同比 (YoY) ----
    sales_trend_deltas = {}
    if len(monthly) >= 2:
        cur_orders = float(monthly.iloc[-1]["orders"])
        prev_orders = float(monthly.iloc[-2]["orders"])
        if prev_orders > 0:
            sales_trend_deltas["orders_mom"] = round((cur_orders - prev_orders) / prev_orders * 100, 1)
            
        cur_rev = float(monthly.iloc[-1]["revenue"])
        prev_rev = float(monthly.iloc[-2]["revenue"])
        if prev_rev > 0:
            sales_trend_deltas["revenue_mom"] = round((cur_rev - prev_rev) / prev_rev * 100, 1)

    if len(monthly) >= 13:
        cur_orders = float(monthly.iloc[-1]["orders"])
        yoy_orders = float(monthly.iloc[-13]["orders"])
        if yoy_orders > 0:
            sales_trend_deltas["orders_yoy"] = round((cur_orders - yoy_orders) / yoy_orders * 100, 1)
            
        cur_rev = float(monthly.iloc[-1]["revenue"])
        yoy_rev = float(monthly.iloc[-13]["revenue"])
        if yoy_rev > 0:
            sales_trend_deltas["revenue_yoy"] = round((cur_rev - yoy_rev) / yoy_rev * 100, 1)

    # 近 12 月截断:只保留最新 12 个月的数据,既覆盖年度同比又控制长度
    if len(monthly) > 12:
        monthly = monthly.tail(12).reset_index(drop=True)
    sales_curve = [
        {"month": m, "orders": int(o), "revenue_wan": round(float(r) / 10000, 1)}
        for m, o, r in monthly[["_month", "orders", "revenue"]].itertuples(index=False)
    ]

    # ---- TOP N 销售门店 ----
    top_sales_stores = (
        sales.groupby(s_store_col)[s_price_col]
             .agg(["count", "sum"])
             .reset_index()
             .sort_values("count", ascending=False)
             .head(top_n)
    )
    sales_stores = [
        {"store": s, "orders": int(c), "revenue_wan": round(float(v) / 10000, 1)}
        for s, c, v in top_sales_stores[[s_store_col, "count", "sum"]].itertuples(index=False)
    ]

    # ---- TOP N 售后频次车型 ----
    top_after_vehicles = (
        after.merge(
            sales[["_aligned_id", s_vehicle_col]].drop_duplicates(),
            on="_aligned_id", how="inner",
        )
        .groupby(s_vehicle_col)
        .size().reset_index(name="repair_orders")
        .sort_values("repair_orders", ascending=False)
        .head(top_n)
    )
    aftersales_top_vehicles = [
        {
            "vehicle_id":     _safe_int(v),
            "vehicle_name":   vehicle_name_map.get(v) or vehicle_name_map.get(_safe_int(v)) or "",
            "repair_orders":  int(c),
        }
        for v, c in top_after_vehicles[[s_vehicle_col, "repair_orders"]].itertuples(index=False)
    ]

    # ---- 服务网络分离指标(销售门店 vs 维修门店一致率) ----
    joined = sales[["_aligned_id", s_store_col]].merge(
        after[["_aligned_id", a_store_col]], on="_aligned_id", how="inner"
    )
    same_store = (joined[s_store_col] == joined[a_store_col]).sum()
    network_separation = {
        "joined_records":     int(len(joined)),
        "same_store_records": int(same_store),
        "same_store_ratio":   round(float(same_store) / max(len(joined), 1), 4),
        "n_sales_stores":     int(sales[s_store_col].nunique()),
        "n_repair_stores":    int(after[a_store_col].nunique()),
    }

    # ---- 售后服务类型分布 ----
    service_type_dist = (
        after[a_service_col]
        .value_counts(normalize=False)
        .head(10)
        .to_dict()
    )

    # ---- 异常检测(售后单数月度 3σ) 与月度趋势 ----
    after["_dt"] = pd.to_datetime(after[a_time_col], errors="coerce")
    after_m = after.dropna(subset=["_dt"]).copy()
    after_m["_month"] = after_m["_dt"].dt.strftime("%Y-%m")
    
    repair_monthly_df = after_m.groupby("_month").size().reset_index(name="orders").sort_values("_month")
    
    aftersales_trend_deltas = {}
    if len(repair_monthly_df) >= 2:
        cur_orders = float(repair_monthly_df.iloc[-1]["orders"])
        prev_orders = float(repair_monthly_df.iloc[-2]["orders"])
        if prev_orders > 0:
            aftersales_trend_deltas["orders_mom"] = round((cur_orders - prev_orders) / prev_orders * 100, 1)

    if len(repair_monthly_df) >= 13:
        cur_orders = float(repair_monthly_df.iloc[-1]["orders"])
        yoy_orders = float(repair_monthly_df.iloc[-13]["orders"])
        if yoy_orders > 0:
            aftersales_trend_deltas["orders_yoy"] = round((cur_orders - yoy_orders) / yoy_orders * 100, 1)

    rm_display = repair_monthly_df.tail(12).reset_index(drop=True)
    aftersales_curve = [
        {"month": m, "orders": int(o)}
        for m, o in rm_display.itertuples(index=False)
    ]
    
    repair_monthly_series = after_m.groupby("_month").size()
    mean = float(repair_monthly_series.mean())
    std = float(repair_monthly_series.std() or 0.0)
    threshold_high = mean + 3 * std
    anomalies = [
        {"month": m, "orders": int(c), "deviation": round((c - mean) / max(std, 1e-6), 2)}
        for m, c in repair_monthly_series.items()
        if c > threshold_high
    ]

    return {
        "align_report":          align_report,
        "n_sales":               int(len(sales)),
        "n_aftersales":          int(len(after)),
        "n_join_matched":        int(len(joined)),
        "join_match_ratio":      round(len(joined) / max(len(after), 1), 4),
        "sales_curve":           sales_curve,
        "sales_trend_deltas":    sales_trend_deltas,
        "top_sales_stores":      sales_stores,
        "top_aftersales_vehicles": aftersales_top_vehicles,
        "network_separation":    network_separation,
        "service_type_dist":     {str(k): int(v) for k, v in service_type_dist.items()},
        "aftersales_curve":      aftersales_curve,
        "aftersales_trend_deltas": aftersales_trend_deltas,
        "monthly_repair_anomalies": anomalies,
        "resolved_fields": {
            "sales": s_cols, "aftersales": a_cols,
        },
    }


def _safe_int(v: Any) -> Any:
    """vehicle_id 字段在自适应数据集里可能是 int / str(取决于实际数据);
    int 转换失败时原样返回字符串,保证 JSON 序列化稳。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return str(v)


# ============================================================
# 第 2 路：售后 TOP 维修项目 + RAG 根因检索
# ============================================================

def aftersales_top_with_rag(
    top_n: int = 5,
    rag_per_item: int = 1,
    rag_min_score: float = 0.3,
) -> Dict[str, Any]:
    """从维修价格明细表挑 TOP N 维修项目,对每个项目跑 RAG 检索匹配故障根因。

    rag_min_score: TF-IDF cosine 分数阈值,低于该分数视为"未命中"(filter 掉,
    避免出现"刹车片 → 动力电池压差故障 score=0.137"这种业务上不通的低分误命中)。
    现场演示 阈值由 0.2 → 0.3:RAG 知识库扩到 384 案例后,低分跨域命中
    概率上升(典型:前保险杠喷漆 score=0.257 误命中"无法熄火"),提阈值更稳。

    现场演示适配:
    新数据维修价格明细表缺『单价』『小计金额』,dataset_loader 已用『基础单价×数量』
    回填,因此 total_amount 严格意义上是"估算金额",演示需明示该口径。
    返回里带 amount_method 字段说明口径,供 format_for_llm / evidence_builder 标注。
    """
    detail = dataset_loader.load_excel("aftersales_records", sheet="维修价格明细表")

    # 别名解析:project_name / repair_id / subtotal 全走 manifest
    d_cols = dataset_loader.resolve_fields_strict(
        "aftersales_records",
        ["project_name", "repair_id", "subtotal"],
        sheet="维修价格明细表",
        df=detail,
    )
    project_name_col = d_cols["project_name"]
    repair_id_col    = d_cols["repair_id"]
    subtotal_col     = d_cols["subtotal"]

    item_rank = (
        detail.groupby(project_name_col)
              .agg(orders=(repair_id_col, "nunique"), total_amount=(subtotal_col, "sum"))
              .reset_index()
              .sort_values("orders", ascending=False)
              .head(top_n)
    )

    store = rag_store.get_default_store()
    items = []
    for proj, orders, total in item_rank[[project_name_col, "orders", "total_amount"]].itertuples(index=False):
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
        "amount_method":  "估算: 基础单价 × 维修项目数量",
        "amount_method_short": "估算",
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

    # 别名解析:vehicle / content 全走 manifest
    v_cols = dataset_loader.resolve_fields_strict(
        "voc_dongchedi", ["vehicle", "content"], df=df,
    )
    vehicle_col = v_cols["vehicle"]
    content_col = v_cols["content"]

    n_total = int(df[content_col].notna().sum())

    vehicle_dist = df[vehicle_col].value_counts().head(8).to_dict()

    cluster_result = voc_clustering.cluster_voc(target_vehicle=top_competitor)
    pains = voc_clustering.top_pain_points(cluster_result, top_n=top_pain)
    # 强不重叠:把痛点已选的 cluster_id 排除,卖点从剩下里选
    # 现场演示修复:中文 VOC 情感词典命中偏正面,所有簇 sentiment > 0,
    # 老逻辑兜底按 size 排会让 pain/praise 退化成同一组,展示完全相同
    pain_ids = {c.cluster_id for c in pains}
    praises = voc_clustering.top_praise_points(
        cluster_result, top_n=top_praise, exclude_cluster_ids=pain_ids,
    )

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
# 第 4 路:销售用户画像(性别/年龄/付款类型) — 现场演示 新增
# ============================================================

# 现场新数据多出来的客户字段(老阉割版没有,所以这一路是新数据驱动的差异化亮点)
_CUSTOMER_PROFILE_FIELDS = ["性别", "年龄", "付款类型", "顾客地址"]


def _bucket_age(age: Any) -> str:
    """把年龄归到业务可读的分桶,< 18 / NaN 视为'未知'"""
    try:
        a = int(float(age))
    except (TypeError, ValueError):
        return "未知"
    if a < 18:
        return "未知"
    if a <= 25:
        return "18-25"
    if a <= 35:
        return "26-35"
    if a <= 45:
        return "36-45"
    if a <= 55:
        return "46-55"
    return "56+"


def customer_profile_brief(top_n: int = 5) -> Dict[str, Any]:
    """销售用户画像:
    - 性别 / 年龄分桶 / 付款类型 三个分布
    - TOP N 顾客来源城市
    - 不同年龄段的均价对比(看哪一类客户购买力高)

    现场演示适配:阉割版数据没有这些字段,该函数会自动跳过并返回空 dict;
    只有现场新数据(车辆销售记录表多出 性别 / 年龄 / 付款类型 / 顾客地址 等列)才有结果。
    """
    try:
        sales = dataset_loader.load_excel("sales_records", sheet="车辆销售记录表")
    except Exception as e:
        logger.warning("[customer_profile] 销售记录表加载失败,跳过: %s", e)
        return {"available": False, "reason": "数据集不可用"}

    available_fields = [c for c in _CUSTOMER_PROFILE_FIELDS if c in sales.columns]
    if not available_fields:
        return {"available": False, "reason": "现场数据不含画像字段(性别/年龄/付款类型/顾客地址)"}

    # 价格列尽量解析,失败则用 0(只影响"年龄段均价",不阻塞主流程)
    try:
        s_cols = dataset_loader.resolve_fields_strict(
            "sales_records", ["price_final"], sheet="车辆销售记录表", df=sales,
        )
        price_col: Optional[str] = s_cols["price_final"]
    except Exception:
        price_col = None

    n_sales = int(len(sales))
    out: Dict[str, Any] = {
        "available":        True,
        "n_sales":          n_sales,
        "fields_used":      available_fields,
    }

    # 性别分布
    if "性别" in available_fields:
        gender_counts = sales["性别"].fillna("未知").astype(str).value_counts()
        out["gender_distribution"] = [
            {"label": str(k), "count": int(v), "ratio": round(float(v) / max(n_sales, 1), 4)}
            for k, v in gender_counts.head(5).items()
        ]

    # 年龄段分布
    if "年龄" in available_fields:
        age_buckets = sales["年龄"].map(_bucket_age)
        age_counts = age_buckets.value_counts()
        # 按业务逻辑顺序排序(不是 count 大小)
        order = ["18-25", "26-35", "36-45", "46-55", "56+", "未知"]
        out["age_distribution"] = [
            {"bucket": b, "count": int(age_counts.get(b, 0)),
             "ratio": round(float(age_counts.get(b, 0)) / max(n_sales, 1), 4)}
            for b in order if int(age_counts.get(b, 0)) > 0
        ]

        # 年龄段平均成交价(只在 price 可解析时计算)
        if price_col and price_col in sales.columns:
            tmp = sales.assign(_age_bucket=age_buckets, _price=pd.to_numeric(sales[price_col], errors="coerce"))
            avg_by_age = (
                tmp.dropna(subset=["_price"])
                   .groupby("_age_bucket")["_price"].mean()
                   .round(0)
                   .to_dict()
            )
            out["avg_price_by_age"] = [
                {"bucket": b, "avg_price": int(avg_by_age.get(b, 0))}
                for b in order if avg_by_age.get(b)
            ]

    # 付款类型分布
    if "付款类型" in available_fields:
        pay_counts = sales["付款类型"].fillna("未知").astype(str).value_counts()
        out["payment_distribution"] = [
            {"label": str(k), "count": int(v), "ratio": round(float(v) / max(n_sales, 1), 4)}
            for k, v in pay_counts.head(5).items()
        ]

    # TOP N 顾客来源城市
    if "顾客地址" in available_fields:
        city_counts = sales["顾客地址"].fillna("未知").astype(str).value_counts()
        out["top_customer_cities"] = [
            {"city": str(k), "orders": int(v)}
            for k, v in city_counts.head(top_n).items()
        ]

    return out


# ============================================================
# 顶层入口
# ============================================================

def run_main_brief(self_vehicle_id: Optional[int] = None) -> Dict[str, Any]:
    """三路并跑,返回完整 brief dict;现场演示额外加销售用户画像第 4 路(条件可用才纳入)"""
    out = {
        "linkage":            linkage_brief(),
        "aftersales":         aftersales_top_with_rag(),
        "voc":                voc_brief(),
        "customer_profile":   customer_profile_brief(),
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
    sdeltas = lk.get("sales_trend_deltas", {})
    if curve:
        lines.append("- 销售月度曲线(最近12个月):")
        for r in curve:
            lines.append(f"    - {r['month']}: {r['orders']:,} 单 / {r['revenue_wan']:,} 万")
            
        if sdeltas:
            delta_strs = []
            if "revenue_mom" in sdeltas:
                delta_strs.append(f"营收环比 {sdeltas['revenue_mom']:+.1f}%")
            if "revenue_yoy" in sdeltas:
                delta_strs.append(f"营收同比 {sdeltas['revenue_yoy']:+.1f}%")
            if "orders_mom" in sdeltas:
                delta_strs.append(f"单数环比 {sdeltas['orders_mom']:+.1f}%")
            if "orders_yoy" in sdeltas:
                delta_strs.append(f"单数同比 {sdeltas['orders_yoy']:+.1f}%")
            if delta_strs:
                lines.append(f"    - 📊 最新月趋势对比: " + "，".join(delta_strs))

    # 售后曲线
    acurve = lk.get("aftersales_curve", [])
    adeltas = lk.get("aftersales_trend_deltas", {})
    if acurve:
        lines.append("- 售后维修频次月度曲线(最近12个月):")
        for r in acurve:
            lines.append(f"    - {r['month']}: {r['orders']:,} 单")
        
        if adeltas:
            delta_strs = []
            if "orders_mom" in adeltas:
                delta_strs.append(f"维修单数环比 {adeltas['orders_mom']:+.1f}%")
            if "orders_yoy" in adeltas:
                delta_strs.append(f"维修单数同比 {adeltas['orders_yoy']:+.1f}%")
            if delta_strs:
                lines.append(f"    - 📊 最新月维修趋势对比: " + "，".join(delta_strs))

    # TOP 销售门店
    if lk.get("top_sales_stores"):
        s = "、".join(f"{x['store']}({x['orders']}单)" for x in lk["top_sales_stores"][:3])
        lines.append(f"- TOP 销售门店: {s}")

    # TOP 售后频次车型(若车辆配置表能解析则展示车型名称,否则回退到代号)
    if lk.get("top_aftersales_vehicles"):
        def _vehicle_label(x: Dict[str, Any]) -> str:
            name = x.get("vehicle_name")
            if name:
                return f"{name}({x['repair_orders']}次)"
            return f"车型{x['vehicle_id']}({x['repair_orders']}次)"
        s = "、".join(_vehicle_label(x) for x in lk["top_aftersales_vehicles"][:5])
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
    amt_short = af.get("amount_method_short") or "估算"
    if af.get("items"):
        lines.append(f"- 💡 金额口径:{af.get('amount_method', '估算: 基础单价 × 数量')}")
    for i, it in enumerate(af.get("items", []), 1):
        lines.append(
            f"{i}. {it['project']} — {it['orders']} 单, ¥{it['total_amount']:,.0f} ({amt_short})"
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

    # ---- 销售用户画像(现场演示 新数据驱动的差异化亮点) ----
    cp = brief.get("customer_profile", {})
    if cp.get("available"):
        lines.append("")
        lines.append("## 第 4 路 · 销售用户画像 ⭐ (现场新数据)")
        lines.append(f"- 样本量: {cp.get('n_sales', 0):,} 笔成交,字段: {'、'.join(cp.get('fields_used', []))}")
        if cp.get("gender_distribution"):
            s = "、".join(f"{x['label']} {x['ratio']*100:.1f}%" for x in cp["gender_distribution"][:3])
            lines.append(f"- 性别画像: {s}")
        if cp.get("age_distribution"):
            s = "、".join(f"{x['bucket']} {x['ratio']*100:.1f}%" for x in cp["age_distribution"][:6])
            lines.append(f"- 年龄分布: {s}")
            if cp.get("avg_price_by_age"):
                # 按均价从高到低排,看哪个年龄段是高端客群
                sorted_avg = sorted(cp["avg_price_by_age"], key=lambda x: x["avg_price"], reverse=True)
                s = "、".join(f"{x['bucket']} ¥{x['avg_price']:,}" for x in sorted_avg[:3])
                lines.append(f"- 年龄段均价 TOP3: {s}")
        if cp.get("payment_distribution"):
            s = "、".join(f"{x['label']} {x['ratio']*100:.1f}%" for x in cp["payment_distribution"][:3])
            lines.append(f"- 付款偏好: {s}")
        if cp.get("top_customer_cities"):
            s = "、".join(f"{x['city']}({x['orders']}单)" for x in cp["top_customer_cities"][:5])
            lines.append(f"- TOP 客户来源城市: {s}")

    return "\n".join(lines)
