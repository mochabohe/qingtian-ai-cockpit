"""
现场数据替换探雷脚本 — 不调用 LLM,只跑主线 3 路真实分析。

用途:
    1. 把数据方提供的真实数据放到 data/datasets/raw/ 后,**第一时间**跑这个脚本
    2. 立刻知道:
       - 哪些 sheet 名 / 字段名对不上(KeyError 直接定位)
       - 各路分析耗时(销售-售后聚合 / 售后 RAG / VOC 聚类)
       - 主线 summary 实际生成内容(供肉眼快速校验)
    3. 全跑通后再启 backend → 跑 e2e 简报 → 跑视频

不发 API、不烧钱,纯本地 pandas + sklearn。

应急:
    如果数据量爆炸卡住,设环境变量后重跑:
        $env:DATASET_SAMPLE_LIMIT="200000"   # 单表上限 20 万行
        $env:VOC_MAX_CLUSTER_SAMPLES="3000"  # VOC 聚类样本上限 3000
        $env:VOC_CLUSTER_BACKEND="minibatch" # 强制 MiniBatchKMeans
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

# Windows 控制台 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))


def _stage(name: str):
    print(f"\n{'='*70}\n>>> {name}\n{'='*70}")


def main() -> int:
    from app.services import dataset_loader, briefing_analytics

    failed_stages: list[str] = []

    # ---- Stage 1: dataset_loader 列出注册的 4 个数据集 ----
    _stage("Stage 1 · 数据集元信息")
    try:
        for ds in dataset_loader.list_datasets():
            avail = "✅" if ds["available"] else "❌"
            print(f"  {avail} {ds['key']:25} format={ds['format']:5} rows={ds['rows']}  file={ds['file']}")
            if ds.get("sheets"):
                for sn in ds["sheets"]:
                    print(f"        └─ sheet: {sn}")
    except Exception as e:
        print(f"  💥 失败: {e}")
        traceback.print_exc()
        failed_stages.append("dataset_loader")
        return 1  # 这一步失败后续都跑不了

    # ---- Stage 2: 销售-售后联动 ----
    _stage("Stage 2 · 销售-售后联动 (linkage_brief)")
    t0 = time.time()
    try:
        brief = briefing_analytics.linkage_brief(top_n=5)
        dt = time.time() - t0
        net = brief.get("network_separation") or {}
        print(f"  ✅ 耗时 {dt:.1f}s")
        print(f"  销售 {brief.get('n_sales', 0):,} 行 / 售后 {brief.get('n_aftersales', 0):,} 行")
        print(f"  跨源 join 匹配率: {brief.get('join_match_ratio', 0)*100:.1f}% (匹配 {brief.get('n_join_matched', 0):,} 条)")
        print(f"  销售门店 {net.get('n_sales_stores')} 个 vs 维修门店 {net.get('n_repair_stores')} 个 (同店率 {(net.get('same_store_rate') or 0)*100:.1f}%)")
        print(f"  销售曲线月数: {len(brief.get('sales_curve', []))}")
        print(f"  TOP 销售门店: {len(brief.get('top_sales_stores', []))}")
        print(f"  TOP 售后频次车型: {len(brief.get('top_aftersales_vehicles', []))}")
        print(f"  月度维修异常: {len(brief.get('monthly_repair_anomalies', []))} 个")
    except KeyError as e:
        print(f"  💥 字段不存在: {e}  ← 检查 sales_records / aftersales_records sheet 字段名")
        traceback.print_exc()
        failed_stages.append("linkage_brief")
    except Exception as e:
        print(f"  💥 失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        failed_stages.append("linkage_brief")

    # ---- Stage 3: 售后 TOP + RAG ----
    _stage("Stage 3 · 售后 TOP 维修项目 + RAG (aftersales_top_with_rag)")
    t0 = time.time()
    try:
        rag = briefing_analytics.aftersales_top_with_rag(top_n=5)
        dt = time.time() - t0
        print(f"  ✅ 耗时 {dt:.1f}s / RAG 索引文档数: {rag.get('rag_total_docs')}")
        for it in rag.get("items", []):
            hits = it.get("rag_hits", [])
            hit_str = f"{hits[0].get('topic')} (score={hits[0].get('score')})" if hits else "未命中"
            print(f"  - {it['project']:15} 单数 {it['orders']:>5} 金额 ¥{it['total_amount']:>12,.0f}  RAG: {hit_str}")
    except KeyError as e:
        print(f"  💥 字段不存在: {e}  ← 检查 aftersales_records 维修价格明细表 字段名")
        traceback.print_exc()
        failed_stages.append("aftersales_top_with_rag")
    except Exception as e:
        print(f"  💥 失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        failed_stages.append("aftersales_top_with_rag")

    # ---- Stage 4: VOC 聚类 (耗时大头) ----
    _stage("Stage 4 · VOC 聚类 (cluster_voc) — 大数据时这里最慢")
    t0 = time.time()
    try:
        from app.services import voc_clustering
        result = voc_clustering.cluster_voc(target_vehicle="Model Y")
        dt = time.time() - t0
        print(f"  ✅ 耗时 {dt:.1f}s")
        print(f"  原始 {result.n_input_total} → 有效 {result.n_after_dedup} → 聚类 {result.n_clusters} 簇 (silhouette={result.silhouette:.3f})")
        for c in result.clusters[:3]:
            kws = "、".join(c.keywords[:5])
            print(f"  - 簇{c.cluster_id} {c.size:>4} 条  情感{c.sentiment_score:+.2f}  关键词: {kws}")
    except KeyError as e:
        print(f"  💥 字段不存在: {e}  ← 检查 voc_dongchedi.csv 字段名(应有'内容''车系')")
        traceback.print_exc()
        failed_stages.append("cluster_voc")
    except Exception as e:
        print(f"  💥 失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        failed_stages.append("cluster_voc")

    # ---- Stage 5: 主线 summary 完整生成 ----
    _stage("Stage 5 · 主线 summary 装配 (run_main_brief + format_for_llm)")
    t0 = time.time()
    try:
        brief_dict = briefing_analytics.run_main_brief()
        summary = briefing_analytics.format_for_llm(brief_dict)
        dt = time.time() - t0
        n_chars = len(summary)
        n_lines = summary.count("\n")
        print(f"  ✅ 耗时 {dt:.1f}s / summary {n_chars} 字符 ({n_lines} 行)")
        print(f"  --- summary 前 800 字预览 ---")
        print("  " + summary[:800].replace("\n", "\n  "))
        print(f"  ...")
    except Exception as e:
        print(f"  💥 失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        failed_stages.append("run_main_brief")

    # ---- 汇总 ----
    _stage("汇总")
    if not failed_stages:
        print("  🎉 全部 5 个 stage 通过,可以启动 backend → 跑 e2e 简报 + 视频合成")
        return 0
    else:
        print(f"  ⚠️ 失败 {len(failed_stages)} 个 stage: {failed_stages}")
        print(f"     按上面的 KeyError / 报错定位字段名/sheet 名,改 manifest.json 或 services/*.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
