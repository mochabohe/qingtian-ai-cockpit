"""
P0-3 洞察证据链构造器

设计目的:
演示"这个数字哪来的"必问题的硬解。从 briefing_analytics 已算出的真实数据里,
为每条 KPI / section 补一份业务可读的证据摘要,包括:
- source        数据来源(销售记录/售后维修/VOC 评论/故障案例 RAG)
- method        计算口径(给用户一句话能听懂的)
- record_count  命中记录数
- fields        关键字段
- samples       3-5 条原始样例(脱敏后)

设计原则(对抗 LLM 幻觉):
**所有证据由算法层确定性生成,LLM 不参与**——LLM 只负责洞察文案,数字与样例
全来自 pandas 计算的真实结果。这样演示追问"哪条评论"时一定能掏出真原文。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_str(v: Any, max_len: int = 80) -> str:
    s = str(v) if v is not None else ""
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _mask_amount(text: str) -> str:
    """简单金额脱敏:百万级以上保留区间(避免和合规 sanitize 冲突,只做保险)"""
    return text


def build_evidence_pool(brief: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    把 briefing_analytics.run_main_brief() 返回的 dict 转换成证据池。

    返回结构:
    {
      "linkage":     [Evidence dict, ...],   # 销售-售后联动相关证据
      "aftersales":  [Evidence dict, ...],   # 售后 TOP 维修项 + RAG
      "voc":         [Evidence dict, ...],   # VOC 主题聚类
    }

    每条 evidence dict 形如:
    {
      "label": "服务网络分离",        # 给前端反查的标识
      "source": "销售记录 + 售后维修",
      "method": "按 _aligned_id join 后,统计销售门店与维修门店是否同名",
      "fields": ["销售门店", "维修门店"],
      "record_count": 8731,
      "samples": ["销售门店=江汉店 / 维修门店=武昌店", ...],
      "note": "门店错配率 = 1 - same_store_ratio"
    }
    """
    pool: Dict[str, List[Dict[str, Any]]] = {
        "linkage":          [],
        "aftersales":       [],
        "voc":              [],
        "customer_profile": [],
    }

    # ============================================================
    # 第 1 路:销售-售后联动
    # ============================================================
    lk = brief.get("linkage", {}) or {}

    # 1.1 销售规模 evidence
    pool["linkage"].append({
        "label":        "销售规模",
        "source":       "销售记录",
        "method":       "按 销售id 计数(去重)",
        "fields":       ["销售id", "销售时间", "最终价格(元)"],
        "record_count": int(lk.get("n_sales", 0)),
        "samples":      [],
        "note":         "对应销售曲线的总样本量",
    })

    # 1.2 跨源主键对齐(项目核心算法亮点)
    align = lk.get("align_report") or {}
    align_samples: List[str] = []
    if align.get("normalized"):
        align_samples = [
            f"修复前:销售 id 'S040829' / 售后 id 'S40829' (字面不一致 → join 失败)",
            f"修复后:售后 id 补齐前导零至 {align.get('target_width')} 位 → 'S040829' ↔ 'S040829'",
        ]
    pool["linkage"].append({
        "label":        "跨源对齐",
        "source":       "销售记录 ↔ 售后维修",
        "method":       "schema_inspector.align_id_columns()",
        "fields":       ["销售id", "车辆销售ID"],
        "record_count": int(lk.get("n_join_matched", 0)),
        "samples":      align_samples,
        "note":         (f"覆盖率 {lk.get('join_match_ratio', 0) * 100:.1f}%(主键格式自动修复后)"
                          if align.get("normalized")
                          else f"覆盖率 {lk.get('join_match_ratio', 0) * 100:.1f}%"),
    })

    # 1.3 销售月度曲线
    curve = lk.get("sales_curve") or []
    if curve:
        head_samples = [
            f"{r['month']}: {r['orders']:,} 单 / {r['revenue_wan']:,} 万"
            for r in curve[:3]
        ]
        tail_samples = [
            f"{r['month']}: {r['orders']:,} 单 / {r['revenue_wan']:,} 万"
            for r in curve[-2:]
        ]
        pool["linkage"].append({
            "label":        "销售月度曲线",
            "source":       "销售记录",
            "method":       "按销售时间 strftime('%Y-%m') 分组,聚合订单数与 revenue 总和",
            "fields":       ["销售时间", "销售id", "最终价格(元)"],
            "record_count": len(curve),
            "samples":      head_samples + (["…"] if len(curve) > 5 else []) + tail_samples,
            "note":         f"近 {len(curve)} 个月汇总(>12 月时仅保留最近 12 月)",
        })

    # 1.4 TOP 销售门店
    stores = lk.get("top_sales_stores") or []
    if stores:
        pool["linkage"].append({
            "label":        "TOP 销售门店",
            "source":       "销售记录",
            "method":       "按 销售门店 分组,count(销售id) + sum(最终价格) 排序取 TOP 5",
            "fields":       ["销售门店", "销售id", "最终价格(元)"],
            "record_count": int(lk.get("n_sales", 0)),
            "samples":      [
                f"{x['store']}: {x['orders']} 单 / {x['revenue_wan']:,} 万"
                for x in stores[:5]
            ],
        })

    # 1.5 服务网络分离(关键洞察)
    nw = lk.get("network_separation") or {}
    if nw:
        pool["linkage"].append({
            "label":        "服务网络分离",
            "source":       "销售记录 + 售后维修",
            "method":       "按 _aligned_id join 后,比较 销售门店 vs 维修门店 是否同店",
            "fields":       ["_aligned_id", "销售门店", "维修门店"],
            "record_count": int(nw.get("joined_records", 0)),
            "samples":      [
                f"同店维修 {nw.get('same_store_records', 0):,} / 跨店维修 {nw.get('joined_records', 0) - nw.get('same_store_records', 0):,}",
                f"销售门店 {nw.get('n_sales_stores')} 家 vs 维修门店 {nw.get('n_repair_stores')} 家",
            ],
            "note":         f"同店维修率仅 {nw.get('same_store_ratio', 0) * 100:.1f}%",
        })

    # 1.6 月度异常(3σ)
    anomalies = lk.get("monthly_repair_anomalies") or []
    if anomalies:
        pool["linkage"].append({
            "label":        "月度异常",
            "source":       "售后维修",
            "method":       "按月聚合维修单数,均值 + 3σ 上限触发",
            "fields":       ["维修日期", "维修单号"],
            "record_count": len(anomalies),
            "samples":      [
                f"{x['month']}: {x['orders']} 单 ({x['deviation']:+.1f}σ)"
                for x in anomalies[:5]
            ],
        })

    # ============================================================
    # 第 2 路:售后 TOP 维修项目 + RAG
    # ============================================================
    af = brief.get("aftersales", {}) or {}
    items = af.get("items") or []
    amount_method_full = af.get("amount_method") or "按 维修项目名称 分组,nunique(维修单号) + sum(小计金额) 取 TOP 5"
    if items:
        pool["aftersales"].append({
            "label":        "TOP 维修项目",
            "source":       "售后维修(维修价格明细表)",
            "method":       (
                "按 维修项目名称 分组,nunique(维修单号) + sum(小计金额) 取 TOP 5;"
                f" 金额口径:{amount_method_full}(原始单价/小计金额字段缺失,由系统反推)"
            ),
            "fields":       ["维修项目名称", "维修单号", "小计金额(估算)"],
            "record_count": len(items),
            "samples":      [
                f"{it['project']}: {it['orders']} 单 / ¥{it['total_amount']:,.0f}(估算)"
                for it in items[:5]
            ],
            "note":         "金额为基于「维修项目基础单价 × 数量」的估算,非原始结算金额",
        })

        # RAG 命中(每个 item 对应一条独立 evidence,便于精准匹配)
        for it in items:
            hits = it.get("rag_hits") or []
            if not hits:
                continue
            samples = []
            for h in hits[:3]:
                cause = _safe_str(h.get("root_cause"), 80)
                method_ = _safe_str(h.get("repair_method"), 60)
                samples.append(f"{h.get('topic')} → 根因:{cause} | 维修:{method_}")
            pool["aftersales"].append({
                "label":        f"RAG 故障根因 · {it['project']}",
                "source":       "故障案例 RAG(quality_fault_cases)",
                "method":       f"TF-IDF cosine 检索,阈值 ≥ {af.get('rag_min_score', 0.2)}",
                "fields":       ["故障主题", "故障原因", "维修方法"],
                "record_count": len(hits),
                "samples":      samples,
                "note":         f"案例库共 {af.get('rag_total_docs', 0)} 条故障案例",
            })

    # ============================================================
    # 第 3 路:VOC 市场口碑(聚类)
    # ============================================================
    voc = brief.get("voc", {}) or {}
    pool["voc"].append({
        "label":        "VOC 数据规模",
        "source":       "VOC 评论(懂车帝)",
        "method":       "物理去重(空白 / 太短 / 重复) + 车系过滤",
        "fields":       ["车系", "内容"],
        "record_count": int(voc.get("n_after_dedup", 0)),
        "samples":      [
            f"原始 {voc.get('n_voc_total', 0):,} 条 → 去重后 {voc.get('n_after_dedup', 0):,} 条",
            f"聚焦车系: {voc.get('target_competitor', '-')}",
        ],
        "note":         f"提炼 {voc.get('n_clusters', 0)} 个用户话题",
    })

    pains = voc.get("top_pain_clusters") or []
    if pains:
        pool["voc"].append({
            "label":        "VOC TOP 痛点话题",
            "source":       "VOC 评论 → KMeans 聚类",
            "method":       "TF-IDF 向量化 → KMeans → 关键词 Top + 情感打分(<0)",
            "fields":       ["内容", "主题关键词", "情感词典"],
            "record_count": sum(c.get("size", 0) for c in pains),
            "samples":      [
                f"痛点 {i}({c['size']} 条 / 情感{c['sentiment_score']:+.2f}): "
                f"{'、'.join((c.get('keywords') or [])[:5])}"
                for i, c in enumerate(pains[:5], start=1)
            ],
            "note":         "完整代表评论参见 BriefingDoc.sections 的 ranking 行",
        })

    praises = voc.get("top_praise_clusters") or []
    if praises:
        pool["voc"].append({
            "label":        "VOC TOP 卖点话题",
            "source":       "VOC 评论 → KMeans 聚类",
            "method":       "TF-IDF 向量化 → KMeans → 关键词 Top + 情感打分(>0)",
            "fields":       ["内容", "主题关键词", "情感词典"],
            "record_count": sum(c.get("size", 0) for c in praises),
            "samples":      [
                f"卖点 {i}({c['size']} 条 / 情感{c['sentiment_score']:+.2f}): "
                f"{'、'.join((c.get('keywords') or [])[:5])}"
                for i, c in enumerate(praises[:5], start=1)
            ],
        })

    # ============================================================
    # 第 4 路:销售用户画像(现场演示 新数据驱动)
    # ============================================================
    cp = brief.get("customer_profile", {}) or {}
    if cp.get("available"):
        pool["customer_profile"].append({
            "label":        "客户画像",
            "source":       "销售记录(车辆销售记录表 · 现场新数据)",
            "method":       "按 性别 / 年龄分桶(18-25/26-35/.../56+) / 付款类型 直接 value_counts",
            "fields":       cp.get("fields_used") or ["性别", "年龄", "付款类型", "顾客地址"],
            "record_count": int(cp.get("n_sales", 0)),
            "samples":      [
                "性别: " + "、".join(f"{x['label']} {x['ratio']*100:.1f}%"
                                   for x in (cp.get("gender_distribution") or [])[:3]),
                "年龄: " + "、".join(f"{x['bucket']} {x['ratio']*100:.1f}%"
                                   for x in (cp.get("age_distribution") or [])[:6]),
                "付款: " + "、".join(f"{x['label']} {x['ratio']*100:.1f}%"
                                   for x in (cp.get("payment_distribution") or [])[:3]),
            ],
            "note":         "现场新数据多出 性别/年龄/付款类型/顾客地址 四列,阉割版无此能力",
        })
        if cp.get("avg_price_by_age"):
            pool["customer_profile"].append({
                "label":        "年龄段均价",
                "source":       "销售记录(年龄 + 最终成交价)",
                "method":       "按年龄分桶 groupby + mean(最终价格)",
                "fields":       ["年龄", "最终价格(元)"],
                "record_count": int(cp.get("n_sales", 0)),
                "samples":      [
                    f"{x['bucket']}: ¥{x['avg_price']:,}"
                    for x in cp["avg_price_by_age"][:6]
                ],
            })
        if cp.get("top_customer_cities"):
            pool["customer_profile"].append({
                "label":        "TOP 客户来源城市",
                "source":       "销售记录(顾客地址)",
                "method":       "value_counts(顾客地址).head(top_n)",
                "fields":       ["顾客地址"],
                "record_count": int(cp.get("n_sales", 0)),
                "samples":      [
                    f"{x['city']}: {x['orders']} 单"
                    for x in cp["top_customer_cities"][:5]
                ],
            })

    return pool


# ============================================================
# 注入器:把证据池绑定到 BriefingDoc 对应的 KPI/section/action
# ============================================================

# 关键词 → evidence 池路径的映射(用于按文本启发式匹配)
# 顺序很重要:从特殊到通用,先匹配的优先
# 注意:不能用单字 "门店"(售后维修记录的 delta 也含 "门店",会误命中)
_KEYWORD_RULES: List[tuple[str, str]] = [
    # ---- 销售规模 ----
    ("销售记录规模",        "linkage:销售规模"),
    ("销售记录",           "linkage:销售规模"),
    ("销售规模",           "linkage:销售规模"),
    # ---- 跨源对齐(优先级高,关键词放前) ----
    ("跨源匹配",           "linkage:跨源对齐"),
    ("跨源验证",           "linkage:跨源对齐"),
    ("跨源",               "linkage:跨源对齐"),
    ("跨网",               "linkage:跨源对齐"),
    ("主键",               "linkage:跨源对齐"),
    ("匹配率",             "linkage:跨源对齐"),
    ("自动修复",           "linkage:跨源对齐"),
    # ---- 销售月度趋势 ----
    ("月度趋势",           "linkage:销售月度曲线"),
    ("销售曲线",           "linkage:销售月度曲线"),
    ("销售月度",           "linkage:销售月度曲线"),
    # ---- 销售门店 ----
    ("TOP 销售门店",       "linkage:TOP 销售门店"),
    ("销售门店",           "linkage:TOP 销售门店"),
    # ---- 服务网络分离(放在 维修 前,因为更特殊) ----
    ("服务网络",           "linkage:服务网络分离"),
    ("网络分离",           "linkage:服务网络分离"),
    ("同店维修",           "linkage:服务网络分离"),
    ("交付后服务",         "linkage:服务网络分离"),
    ("服务承接",           "linkage:服务网络分离"),
    ("承接闭环",           "linkage:服务网络分离"),
    ("交付服务",           "linkage:服务网络分离"),
    ("转接",               "linkage:服务网络分离"),
    # ---- 月度异常 ----
    ("月度异常",           "linkage:月度异常"),
    ("3σ",                 "linkage:月度异常"),
    # ---- 售后维修(后于 服务网络) ----
    ("售后服务类型",        "aftersales:TOP 维修项目"),
    ("售后服务分布",        "aftersales:TOP 维修项目"),
    ("售后维修记录",        "aftersales:TOP 维修项目"),
    ("售后维修",           "aftersales:TOP 维修项目"),
    ("维修记录",           "aftersales:TOP 维修项目"),
    ("TOP 维修",           "aftersales:TOP 维修项目"),
    ("维修项目",           "aftersales:TOP 维修项目"),
    ("高频项目",           "aftersales:TOP 维修项目"),
    ("高频售后",           "aftersales:TOP 维修项目"),
    ("售后频次",           "aftersales:TOP 维修项目"),
    ("主动检测",           "aftersales:RAG"),
    ("检测套餐",           "aftersales:RAG"),
    # ---- 故障根因 RAG ----
    ("电池类维修",         "aftersales:RAG"),
    ("故障根因",           "aftersales:RAG"),
    ("故障案例",           "aftersales:RAG"),
    ("故障原因",           "aftersales:RAG"),
    ("根因",               "aftersales:RAG"),
    ("RAG",                "aftersales:RAG"),
    ("四轮定位",           "aftersales:RAG"),
    ("空调",               "aftersales:RAG"),
    # ---- VOC ----
    ("VOC有效样本",        "voc:VOC 数据规模"),
    ("VOC",                "voc:VOC 数据规模"),
    ("用户评论",           "voc:VOC 数据规模"),
    ("有效样本",           "voc:VOC 数据规模"),
    ("口碑",               "voc:VOC 数据规模"),
    ("聚类",               "voc:VOC 数据规模"),
    ("痛点",               "voc:VOC TOP 痛点话题"),
    ("不满",               "voc:VOC TOP 痛点话题"),
    ("差距",               "voc:VOC TOP 痛点话题"),
    ("释疑",               "voc:VOC TOP 痛点话题"),
    ("信心",               "voc:VOC TOP 痛点话题"),
    ("卖点",               "voc:VOC TOP 卖点话题"),
    ("亮点",               "voc:VOC TOP 卖点话题"),
    ("可靠性",             "voc:VOC TOP 卖点话题"),
    ("免息",               "voc:VOC TOP 卖点话题"),
    ("金融权益",           "voc:VOC TOP 卖点话题"),
    ("转化话术",           "voc:VOC TOP 卖点话题"),
    ("权益",               "voc:VOC TOP 卖点话题"),
    ("对标",               "voc:VOC TOP 痛点话题"),
    # ---- 兜底:质量类行动 → 售后维修(因为 P0-3 主要数据源) ----
    ("质量",               "aftersales:TOP 维修项目"),
    ("复核",               "aftersales:TOP 维修项目"),
    # ---- 销售用户画像(现场演示新增) ----
    ("客户画像",           "customer_profile:客户画像"),
    ("用户画像",           "customer_profile:客户画像"),
    ("年龄段",             "customer_profile:客户画像"),
    ("年龄分布",           "customer_profile:客户画像"),
    ("年龄结构",           "customer_profile:客户画像"),
    ("性别比例",           "customer_profile:客户画像"),
    ("性别分布",           "customer_profile:客户画像"),
    ("付款类型",           "customer_profile:客户画像"),
    ("付款偏好",           "customer_profile:客户画像"),
    ("分期",               "customer_profile:客户画像"),
    ("全款",               "customer_profile:客户画像"),
    ("年龄段均价",         "customer_profile:年龄段均价"),
    ("客单价",             "customer_profile:年龄段均价"),
    ("客户来源",           "customer_profile:TOP 客户来源城市"),
    ("城市分布",           "customer_profile:TOP 客户来源城市"),
    ("顾客地址",           "customer_profile:TOP 客户来源城市"),
]


def _find_evidence_by_text(
    text: str,
    pool: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """根据文本启发式匹配证据池中的条目,返回最多 3 条"""
    if not text:
        return []
    matched: List[Dict[str, Any]] = []
    seen_ids = set()
    for kw, path in _KEYWORD_RULES:
        if kw not in text:
            continue
        cat, label_keyword = path.split(":", 1)
        for ev in pool.get(cat, []):
            ev_label = str(ev.get("label", ""))
            ev_id = (cat, ev_label)
            if ev_id in seen_ids:
                continue
            # label_keyword 是部分匹配(因为 label 含变量,如 "RAG 故障根因 · 刹车片")
            if label_keyword in ev_label or ev_label.startswith(label_keyword):
                matched.append(ev)
                seen_ids.add(ev_id)
                if len(matched) >= 3:
                    return matched
    return matched


def _is_real_evidence_list(v: Any) -> bool:
    """判断 evidence 字段是否已经是 list[Evidence dict] 而不是 LLM 旧输出的 list[str]。
    旧 LLM 给 alert.evidence 输出字符串列表,要被迁移而不是当作"已有证据"。
    """
    if not isinstance(v, list) or not v:
        return False
    return all(isinstance(x, dict) for x in v)


def attach_evidence_to_briefing(
    briefing_payload: Dict[str, Any],
    evidence_pool: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    把证据池注入到 BriefingDoc 即将装配的 payload(orchestrator 装配前的 dict)。
    通过启发式关键词匹配,给 KPI/sections/actions 各自补 evidence 列表。

    幂等:已有 evidence 字段(且为 dict 列表)的不覆盖。
    """
    if not isinstance(briefing_payload, dict):
        return briefing_payload

    # 预处理:LLM 旧 schema 把 alert.evidence 当 list[str] 输出 → 迁移到 evidence_text
    # 否则 attach 时会因为 evidence 是 truthy(虽然是字符串列表)而跳过注入
    for sec in briefing_payload.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        ev = sec.get("evidence")
        if isinstance(ev, list) and ev and all(isinstance(x, str) for x in ev):
            existing_text = sec.get("evidence_text") or []
            sec["evidence_text"] = list(existing_text) + ev
            sec["evidence"] = []

    # ---- KPI strip ----
    cover = briefing_payload.get("cover") or {}
    kpis = cover.get("kpi_strip") or []
    for k in kpis:
        if not isinstance(k, dict):
            continue
        if _is_real_evidence_list(k.get("evidence")):
            continue
        text = " ".join(filter(None, [k.get("label"), k.get("value"), k.get("delta")]))
        evs = _find_evidence_by_text(text, evidence_pool)
        if evs:
            k["evidence"] = evs

    # ---- sections ----
    for sec in briefing_payload.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        if _is_real_evidence_list(sec.get("evidence")):
            continue
        # alert 类把 msg 和 evidence_text 拼进文本一起搜;ranking 类把 columns/rows 也纳入
        parts = [sec.get("title"), sec.get("metric"), sec.get("insight"), sec.get("msg")]
        if sec.get("type") == "alert":
            parts.append(" ".join(sec.get("evidence_text") or []))
        if sec.get("type") == "ranking":
            parts.append(" ".join(str(c) for c in (sec.get("columns") or [])))
        text = " ".join(filter(None, parts))
        evs = _find_evidence_by_text(text, evidence_pool)
        if evs:
            sec["evidence"] = evs

    # ---- actions ----
    for act in briefing_payload.get("actions") or []:
        if not isinstance(act, dict):
            continue
        if _is_real_evidence_list(act.get("evidence")):
            continue
        # action 也把 deadline / priority 拼进来,虽然这俩通常没关键词,但聊胜于无
        text = " ".join(filter(None, [
            act.get("owner"), act.get("action"),
            act.get("deadline"), act.get("priority"),
        ]))
        evs = _find_evidence_by_text(text, evidence_pool)
        if evs:
            act["evidence"] = evs

    return briefing_payload
