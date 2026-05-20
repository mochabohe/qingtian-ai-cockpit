"""数据上传与管理路由"""
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from ..core.config import settings
from ..services import dataset_loader

router = APIRouter(prefix="/data", tags=["data"])

ALLOWED_EXT = {".csv", ".xlsx", ".xls", ".json", ".tsv", ".parquet", ".txt"}

# 大屏 payload 计算成本高(50k 行 × pivot/groupby/异常检测/相关性 ≈ 数秒),
# 但相同 (key, sheet) 在数据未变更时多次返回同一结果。
# 用进程内 dict 做 TTL 缓存:30 分钟内复用,失效后惰性重算。
# 数据集底层文件由 dataset_loader.@lru_cache 控制,这里只缓存最终 payload。
_DASHBOARD_CACHE: Dict[Tuple[str, Optional[str]], Tuple[float, Dict[str, Any]]] = {}
_DASHBOARD_CACHE_TTL = 30 * 60  # 30 分钟


def _cache_get(key: Tuple[str, Optional[str]]) -> Optional[Dict[str, Any]]:
    item = _DASHBOARD_CACHE.get(key)
    if item is None:
        return None
    ts, payload = item
    if time.time() - ts > _DASHBOARD_CACHE_TTL:
        _DASHBOARD_CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key: Tuple[str, Optional[str]], payload: Dict[str, Any]) -> None:
    _DASHBOARD_CACHE[(key)] = (time.time(), payload)


def invalidate_dashboard_cache() -> None:
    """数据上传/删除时调用,让 dashboard 缓存失效"""
    _DASHBOARD_CACHE.clear()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传数据文件"""
    if not file.filename:
        raise HTTPException(400, "缺少文件名")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的文件类型: {ext}，仅支持 {sorted(ALLOWED_EXT)}")

    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    filepath = data_dir / file.filename
    content = await file.read()
    filepath.write_bytes(content)

    # 文件变更后让 dashboard payload 缓存失效(下次请求会重新计算)
    invalidate_dashboard_cache()

    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "filename": file.filename,
            "size": len(content),
            "path": str(filepath),
        },
    }


@router.get("/list")
async def list_files():
    """列出已上传文件"""
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return {"code": 0, "msg": "ok", "data": []}

    files = []
    for p in sorted(data_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            files.append({
                "name": p.name,
                "size": p.stat().st_size,
                "modified": p.stat().st_mtime,
            })
    return {"code": 0, "msg": "ok", "data": files}


@router.delete("/{filename}")
async def delete_file(filename: str):
    """删除文件"""
    filepath = Path(settings.data_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, "文件不存在")
    filepath.unlink()
    invalidate_dashboard_cache()
    return {"code": 0, "msg": "ok", "data": None}


@router.get("/vehicle-options")
async def vehicle_options():
    """MissionBar 下拉的权威源:焦点车型 / 对标车型 / 分析周期。

    单一来源:manifest.json 的 vehicle_options 节点。
    对标车型在 manifest 未声明时,从 voc_dongchedi 真实评论数据 distinct 兜底,
    保证候选清单和实际能跑的 VOC Agent 对得上。
    primary_case.self_vehicle 自动置顶到 focus 的第一项。
    """
    try:
        meta = dataset_loader.load_manifest()
    except FileNotFoundError as e:
        raise HTTPException(500, f"manifest 缺失:{e}")

    opts = meta.get("vehicle_options") or {}
    focus = list(opts.get("focus") or [])
    benchmark = list(opts.get("benchmark") or [])
    period = list(opts.get("period") or [])

    primary = (meta.get("primary_case") or {}).get("self_vehicle")
    if primary:
        # 始终把主案例车型置顶,且仅出现一次
        focus = [primary] + [v for v in focus if v != primary]

    benchmark_source = "manifest"
    if not benchmark:
        try:
            df = dataset_loader.load_csv("voc_dongchedi")
            if "车系" in df.columns:
                vc = df["车系"].dropna().value_counts()
                benchmark = [v for v in vc.index.tolist() if v != primary]
                benchmark_source = "voc_distinct"
        except dataset_loader.DatasetFileMissingError:
            benchmark_source = "fallback_empty"

    return {
        "code": 0, "msg": "ok",
        "data": {
            "focus": focus,
            "benchmark": benchmark,
            "period": period,
            "primary_focus": primary,
            "benchmark_source": benchmark_source,
        },
    }


@router.get("/kpi-summary")
async def kpi_summary():
    """Home 驾驶舱 KPI 副标题用:返回每个数据集的核心 distinct 业务字段统计,
    用'56 个车型 · 8 家 4S 店'这种细节'佐证'主数字真实性,避免'50000 / 10000 / 1000'
    被误解为 mock。

    所有字段都是从真实数据 distinct 算的,保证现场换新数据后自动刷新。
    """
    import pandas as pd
    out: Dict[str, Any] = {
        "sales":      {"rows": 0, "n_vehicles": 0, "n_stores": 0, "n_salesperson": 0},
        "aftersales": {"rows": 0, "n_repair_stores": 0, "n_service_types": 0},
        "voc":        {"rows": 0, "n_vehicle_systems": 0},
        "quality":    {"rows": 0, "n_systems": 0},
    }

    # 销售
    try:
        df = dataset_loader.load_excel("sales_records", sheet="车辆销售记录表")
        out["sales"] = {
            "rows":           int(len(df)),
            "n_vehicles":     int(df["车型id"].nunique()) if "车型id" in df.columns else 0,
            "n_stores":       int(df["销售门店"].nunique()) if "销售门店" in df.columns else 0,
            "n_salesperson":  int(df["销售顾问"].nunique()) if "销售顾问" in df.columns else 0,
        }
    except Exception:
        pass

    # 售后
    try:
        df = dataset_loader.load_excel("aftersales_records", sheet="维修记录表")
        out["aftersales"] = {
            "rows":            int(len(df)),
            "n_repair_stores": int(df["维修门店"].nunique()) if "维修门店" in df.columns else 0,
            "n_service_types": int(df["服务类型"].nunique()) if "服务类型" in df.columns else 0,
        }
    except Exception:
        pass

    # VOC
    try:
        df = dataset_loader.load_csv("voc_dongchedi")
        top_vehicles: list[Dict[str, Any]] = []
        if "车系" in df.columns:
            for v, c in df["车系"].value_counts().head(3).items():
                top_vehicles.append({"name": str(v), "count": int(c)})
        out["voc"] = {
            "rows":              int(len(df)),
            "n_vehicle_systems": int(df["车系"].nunique()) if "车系" in df.columns else 0,
            "top_vehicles":      top_vehicles,
        }
    except Exception:
        pass

    # 质量案例
    try:
        df = dataset_loader.load_dataset("quality_fault_cases")
        if isinstance(df, dict):
            df = next(iter(df.values()))
        if isinstance(df, pd.DataFrame):
            sys_col = next((c for c in df.columns if "系统" in c or "故障类" in c), None)
            out["quality"] = {
                "rows":      int(len(df)),
                "n_systems": int(df[sys_col].nunique()) if sys_col else 0,
            }
    except Exception:
        pass

    return {"code": 0, "msg": "ok", "data": out}


@router.get("/datasets")
async def list_main_datasets():
    """列出主线数据集元信息（前端「数据集卡片」用）"""
    try:
        items = dataset_loader.list_datasets()
        meta = dataset_loader.load_manifest()
        return {
            "code": 0,
            "msg": "ok",
            "data": {
                "primary_case": meta.get("primary_case", {}),
                "agents": meta.get("agents", {}),
                "datasets": items,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(500, f"manifest 缺失：{e}")


@router.get("/datasets/{key}/preview")
async def preview_dataset(
    key: str,
    sheet: Optional[str] = Query(None, description="xlsx 多 sheet 时指定 sheet 名"),
    n: int = Query(10, ge=1, le=200, description="返回行数"),
):
    """预览主线数据集前 N 行 + 字段信息"""
    try:
        meta = dataset_loader.get_dataset_meta(key)
    except dataset_loader.DatasetNotFoundError:
        raise HTTPException(404, f"未注册的数据集 key：{key}")

    fmt = meta["format"]

    if fmt == "pdf":
        try:
            path = dataset_loader.get_path(key)
        except dataset_loader.DatasetFileMissingError as e:
            raise HTTPException(404, str(e))
        return {
            "code": 0, "msg": "ok",
            "data": {
                "key": key,
                "name": meta["name"],
                "format": "pdf",
                "path": str(path),
                "size_kb": meta.get("size_kb"),
                "use_case": meta.get("use_case"),
                "note": "PDF 预览需通过 RAG 模块解析",
            },
        }

    try:
        if fmt == "csv":
            df = dataset_loader.load_csv(key)
        elif fmt == "xlsx":
            # xlsx 需指定 sheet；未指定时用 manifest 第一个
            target_sheet = sheet
            if target_sheet is None:
                sheets = meta.get("sheets", [])
                target_sheet = sheets[0]["name"] if sheets else None
                if target_sheet is None:
                    raise HTTPException(400, "xlsx 数据集 manifest 未声明任何 sheet")
            df = dataset_loader.load_excel(key, sheet=target_sheet)
        else:
            raise HTTPException(400, f"不支持的 format：{fmt}")
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    head = df.head(n).fillna("").to_dict(orient="records")
    return {
        "code": 0, "msg": "ok",
        "data": {
            "key": key,
            "name": meta["name"],
            "format": fmt,
            "sheet": sheet if fmt == "xlsx" else None,
            "rows_total": len(df),
            "cols": list(df.columns),
            "field_aliases": dataset_loader.get_field_aliases(key, sheet=sheet),
            "preview": head,
        },
    }


@router.get("/datasets/{key}/inspect")
async def inspect_dataset(
    key: str,
    sheet: Optional[str] = Query(None, description="xlsx 多 sheet 时指定 sheet 名"),
):
    """对主线数据集做 schema 自适应识别（字段角色 + 别名）"""
    try:
        result = dataset_loader.inspect(key, sheet=sheet)
    except dataset_loader.DatasetNotFoundError:
        raise HTTPException(404, f"未注册的数据集 key：{key}")
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    return {"code": 0, "msg": "ok", "data": result}


@router.get("/datasets/{key}/health")
async def dataset_health(
    key: str,
    sheet: Optional[str] = Query(None, description="xlsx 多 sheet 时指定 sheet 名"),
):
    """
    P0-2 数据体检中心:返回单数据集的健康评分 + 风险扫描 + 字段角色摘要

    输出:
      {
        score:         int         # 0-100 总分
        dimensions:    [{name, label, score, weight, detail}, ...]  # 4 维
        risks:         [{level, code, message, affected_fields}, ...]
        field_summary: [{name, role, role_label, role_confidence, ...}, ...]
        n_rows / n_cols
      }
    """
    from ..services import schema_inspector
    try:
        # 加载真实数据
        loaded = dataset_loader.load_dataset(key, sheet=sheet)
    except dataset_loader.DatasetNotFoundError:
        raise HTTPException(404, f"未注册的数据集 key:{key}")
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))

    # 取 DataFrame:csv 直接是 df, xlsx 可能是 df 或 {sheet: df}, pdf 不支持
    import pandas as pd
    if isinstance(loaded, pd.DataFrame):
        df = loaded
    elif isinstance(loaded, dict):
        # 多 sheet 时取第一个 sheet
        if not loaded:
            raise HTTPException(400, "数据集为空")
        df = next(iter(loaded.values()))
    else:
        raise HTTPException(400, f"该数据集不支持体检(format 非表格类):{key}")

    # manifest 声明的关键字段(英文 alias → 中文)
    aliases = dataset_loader.get_field_aliases(key, sheet=sheet)
    expected_cn_keys = list(aliases.values()) if aliases else None

    report = schema_inspector.compute_health_report(df, expected_keys=expected_cn_keys)
    return {"code": 0, "msg": "ok", "data": report.to_dict()}


@router.get("/datasets-join-candidates")
async def datasets_join_candidates(
    min_overlap_ratio: float = Query(0.5, ge=0.0, le=1.0),
):
    """跨主线数据集自动发现关联键候选（含主键格式不一致检测与自动对齐报告）"""
    try:
        cands = dataset_loader.cross_dataset_join_candidates(min_overlap_ratio=min_overlap_ratio)
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    return {"code": 0, "msg": "ok", "data": {"candidates": cands}}


@router.get("/rag/search")
async def rag_search(
    q: str = Query(..., min_length=1, description="查询文本(故障描述、现象等)"),
    top_k: int = Query(3, ge=1, le=20),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
):
    """故障案例 RAG 检索(售后质量 Agent 的根因检索工具)"""
    from ..services import rag_store
    try:
        store = rag_store.get_default_store()
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    results = store.search(q, top_k=top_k, min_score=min_score)
    return {
        "code": 0, "msg": "ok",
        "data": {
            "query":   q,
            "top_k":   top_k,
            "n_total": store.n_docs,
            "hits":    results,
        },
    }


@router.get("/voc/clusters")
async def voc_clusters(
    target: Optional[str] = Query("Model Y", description="目标车系(默认 Model Y);传 'all' 用全量"),
):
    """VOC 主题聚类:物理去重 + TF-IDF + KMeans + 关键词 + 情感打分(算法亮点)"""
    from ..services import voc_clustering
    target_vehicle = None if target in (None, "", "all") else target
    try:
        result = voc_clustering.cluster_voc(target_vehicle=target_vehicle)
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    return {
        "code": 0, "msg": "ok",
        "data": result.to_dict(),
    }


# ============================================================
# P0-0 非阻塞增强:对标机会地图
# 原则:if file exists then enrich, else skip
# - 主线 VOC 聚类必须正常返回,无论竞品配置文件是否存在
# - 竞品配置缺失 → enrichment_applied=false, competitor_facts=null
# - 竞品配置存在 → 抽取 1-3 个对标事实附在响应里
# ============================================================

# 关注的关键车型(可与 docs 一致:Model Y / 问界 M7 / AION V / 比亚迪汉)
_OPPORTUNITY_FOCUS_VEHICLES = ["Model Y", "问界 M7", "问界M7", "AION V", "比亚迪汉"]

# 关注的对标事实字段(英文 → 中文别名候选;真文件列名未知,做模糊匹配)
# 每项 (canonical_key, 候选关键词列表)
_OPPORTUNITY_FIELD_CANDIDATES = [
    ("续航(CLTC,km)", ["续航", "CLTC", "NEDC", "WLTP", "里程"]),
    ("充电时长(min)", ["充电时长", "充电时间", "快充", "补能"]),
    ("智能驾驶",      ["智能驾驶", "辅助驾驶", "智驾", "自动驾驶", "ADAS"]),
]


def _find_vehicle_column(df) -> Optional[str]:
    """从 DataFrame 中找出"车型"列(模糊匹配,真文件列名未知)。"""
    for col in df.columns:
        col_str = str(col).strip()
        if col_str in ("车型", "车系", "车款", "车辆", "型号", "Model", "vehicle"):
            return col_str
    # 兜底:含"车"字的列
    for col in df.columns:
        if "车" in str(col):
            return str(col)
    return None


def _find_matching_columns(df, keywords) -> list:
    """根据关键词列表,从 DataFrame 找出匹配的列名。"""
    matches = []
    for col in df.columns:
        col_str = str(col)
        for kw in keywords:
            if kw in col_str:
                matches.append(col_str)
                break
    return matches


def _extract_competitor_facts(df, focus_vehicles) -> Dict[str, list]:
    """
    从竞品配置 DataFrame 抽取对标事实。

    返回 {vehicle_name: [{key, value, source}, ...]}
    """
    facts: Dict[str, list] = {}
    veh_col = _find_vehicle_column(df)
    if veh_col is None:
        return facts

    # 给每个 focus_vehicle 找匹配行
    for vehicle in focus_vehicles:
        # 模糊匹配:列值包含 vehicle 字符串
        matched = df[df[veh_col].astype(str).str.contains(
            vehicle.replace(" ", ""), case=False, na=False, regex=False
        )]
        if matched.empty:
            # 再试一次保留空格的匹配
            matched = df[df[veh_col].astype(str).str.contains(
                vehicle, case=False, na=False, regex=False
            )]
        if matched.empty:
            continue
        row = matched.iloc[0]

        veh_facts = []
        for canonical_key, keywords in _OPPORTUNITY_FIELD_CANDIDATES:
            cols = _find_matching_columns(df, keywords)
            if not cols:
                continue
            # 取第一个匹配列的值
            val = row[cols[0]]
            if val is None:
                continue
            try:
                # NaN 检查
                import pandas as _pd
                if _pd.isna(val):
                    continue
            except Exception:
                pass
            veh_facts.append({
                "key":    canonical_key,
                "value":  str(val),
                "source": "竞品配置.xlsx",
            })
            if len(veh_facts) >= 3:
                break  # 每车型最多 3 条事实

        if veh_facts:
            facts[vehicle] = veh_facts

    return facts


@router.get("/opportunity-map")
async def opportunity_map(
    target: Optional[str] = Query("Model Y", description="VOC 聚类目标车系"),
):
    """
    P0-0 对标机会地图(非阻塞增强):
    - 主线:返回 VOC 聚类结果(永远可用)
    - 增强:如果竞品配置文件存在,附加关键车型的对标事实(续航/充电/智驾等)
    - 文件缺失 → enrichment_applied=false, competitor_facts=null,主线照常返回
    """
    from ..services import voc_clustering

    # 1. 主线:VOC 聚类(必须可用,文件缺失才抛 404)
    target_vehicle = None if target in (None, "", "all") else target
    try:
        voc_result = voc_clustering.cluster_voc(target_vehicle=target_vehicle)
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))

    # 2. 非阻塞增强:尝试加载竞品配置(失败/缺失静默降级)
    competitor_df = dataset_loader.load_competitor_configs()
    enrichment_applied = False
    competitor_facts: Optional[Dict[str, list]] = None
    note = "未提供竞品配置文件,仅返回 VOC 聚类结果"

    if competitor_df is not None and not competitor_df.empty:
        try:
            facts = _extract_competitor_facts(
                competitor_df, _OPPORTUNITY_FOCUS_VEHICLES
            )
            if facts:
                enrichment_applied = True
                competitor_facts = facts
                note = (
                    f"已结合竞品配置增强 {len(facts)} 款车型的对标事实"
                    "(续航/充电/智驾)"
                )
            else:
                note = "竞品配置文件已加载但未匹配到关注车型,仅返回 VOC 聚类结果"
        except Exception as e:
            # 任何抽取失败都静默降级,主线不挂
            note = f"竞品配置增强失败,降级为纯 VOC 结果: {e}"

    return {
        "code": 0, "msg": "ok",
        "data": {
            "voc_clusters":       voc_result.to_dict(),
            "enrichment_applied": enrichment_applied,
            "competitor_facts":   competitor_facts,
            "note":               note,
        },
    }


@router.get("/rag/stats")
async def rag_stats():
    """故障案例 RAG 库的元信息(系统分布、案例总数)"""
    from ..services import rag_store
    try:
        store = rag_store.get_default_store()
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    return {
        "code": 0, "msg": "ok",
        "data": {
            "n_docs":          store.n_docs,
            "system_counts":   store.list_systems(),
            "dataset_key":     "quality_fault_cases",
        },
    }


@router.get("/profile/{filename}")
async def profile(filename: str):
    """对已上传的文件做数据分析（profile + 5 类分析）"""
    filepath = Path(settings.data_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, "文件不存在")

    from ..services.data_pipeline import run_full_analysis, format_for_llm
    try:
        result = run_full_analysis(str(filepath))
    except Exception as e:
        raise HTTPException(500, f"分析失败: {e}")

    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "result": result,
            "llm_summary": format_for_llm(result),
        },
    }


def _build_dashboard_payload(df) -> Dict[str, Any]:
    """
    把 DataFrame 加工成可视化大屏所需的预聚合数据
    (KPI + 趋势 + 分类 + 相关性 + 异常),供两个路由共用。

    关键:用 SchemaInspector 识别字段角色,把 id 列从 metric 候选中排除,
    避免出现"文章ID 合计 88978317813.12 亿"这种荒诞 KPI。
    """
    import pandas as pd
    from ..services.data_pipeline import (
        correlation, detect_anomalies, _detect_time_col,
    )
    from ..services import schema_inspector

    roles = schema_inspector.infer_field_roles(df)
    excluded = set(roles.id_cols) | set(roles.time_cols)

    # 数值列里剔除 id 与 time 列(虽然是 number dtype,但语义上是标识/时间,不该求和)
    # 同时剔除全 NaN / 全 0 的"空列"(常见于原始数据集的预留字段)
    nums_all = df.select_dtypes(include="number")
    drop_cols = [c for c in nums_all.columns if c in excluded]
    for c in nums_all.columns:
        if c in drop_cols:
            continue
        s = nums_all[c].dropna()
        if len(s) == 0 or (s.abs().sum() == 0):
            drop_cols.append(c)
    nums = nums_all.drop(columns=drop_cols, errors="ignore")

    # 主分类列(优先 SchemaInspector dim 角色;3~30 类适合饼图,unique 数适中优先)
    # 关键过滤:含**任意值**超过 16 字符的列必须排除(典型如"43,1,47,20,53,56" 这种 ID 列表拼接)
    # 用 max_len 而非 avg_len:营销活动表"活动范围"5 个值里 4 个 28 字符 + 1 个"全部车型"
    # 4 字符,avg 才 11.7,但 max 是 28——必须用 max 判断,饼图标签才不会糊
    def _max_value_len(col_name: str) -> int:
        try:
            sample = df[col_name].dropna().astype(str).head(100)
            if sample.empty:
                return 0
            return int(sample.str.len().max())
        except Exception:
            return 999  # 出错时假设很长,过滤掉

    MAX_CAT_VALUE_LEN = 16  # 饼图/柱图分类标签合理长度上限

    cat_col = None
    dim_candidates = [
        (c, df[c].nunique(), _max_value_len(c))
        for c in roles.dim_cols
    ]
    # 先过滤掉任意值过长的(ID 列表拼接型),再按 unique 数评分
    dim_candidates_short = [t for t in dim_candidates if t[2] <= MAX_CAT_VALUE_LEN]
    def _cat_score(name_n_len):
        n = name_n_len[1]
        if n < 3 or n > 30:
            return 999
        # 与 8 的距离(8 是饼图最佳值)
        return abs(n - 8)
    dim_candidates_short = sorted(dim_candidates_short, key=_cat_score)
    if dim_candidates_short and 3 <= dim_candidates_short[0][1] <= 30:
        cat_col = dim_candidates_short[0][0]
    else:
        # 兜底:任何 3~30 类、值长度合理的字符串列
        for c in df.select_dtypes(include=["object", "category", "string"]).columns:
            n = df[c].nunique()
            if 3 <= n <= 30 and _max_value_len(c) <= MAX_CAT_VALUE_LEN:
                cat_col = c
                break
        # 最后兜底:即便 < 3 类也用上(只接受值长度合理的)
        if cat_col is None:
            for c, n, max_len in dim_candidates:
                if max_len <= MAX_CAT_VALUE_LEN:
                    cat_col = c
                    break

    time_col = _detect_time_col(df)

    # KPI 自动识别关键指标
    kpi = {"n_rows": len(df), "n_cols": len(df.columns)}
    for col in nums.columns:
        cl = col.lower()
        if "revenue" in cl and "total_revenue" not in kpi:
            kpi["total_revenue"] = float(nums[col].sum())
        elif "profit" in cl and "margin" not in cl and "total_profit" not in kpi:
            kpi["total_profit"] = float(nums[col].sum())
        elif ("csat" in cl or "satisf" in cl or "满意" in col) and "avg_csat" not in kpi:
            kpi["avg_csat"] = float(nums[col].mean())
        elif "sales" in cl and "total_sales" not in kpi:
            kpi["total_sales"] = float(nums[col].sum())

    # 异常检测只跑过滤后的 nums(防止 id/time 列产生荒诞异常)
    anomalies_full = detect_anomalies(df.drop(columns=list(excluded), errors="ignore"))
    kpi["n_anomalies"] = sum(v["n_outliers"] for v in anomalies_full.values())

    # 趋势数据：日期 × 类别 × 主指标(无 metric 时用 size 兜底)
    trend = None
    if time_col and cat_col:
        df_t = df.copy()
        df_t[time_col] = pd.to_datetime(df_t[time_col], errors="coerce")
        df_t = df_t.dropna(subset=[time_col])
        if not df_t.empty:
            df_t["_d"] = df_t[time_col].dt.date.astype(str)
            target = next(
                (c for c in ("revenue", "sales_qty", "profit") if c in df.columns),
                nums.columns[0] if len(nums.columns) > 0 else None,
            )
            if target:
                pivot = df_t.pivot_table(
                    index="_d", columns=cat_col, values=target, aggfunc="sum"
                ).fillna(0).round(0)
                trend = {
                    "metric":     target,
                    "dates":      pivot.index.tolist(),
                    "categories": pivot.columns.tolist(),
                    "series":     [
                        {"name": str(c), "data": pivot[c].tolist()}
                        for c in pivot.columns
                    ],
                }
            else:
                # 兜底:无数值字段,用记录数趋势
                pivot = df_t.pivot_table(
                    index="_d", columns=cat_col, values=time_col, aggfunc="size"
                ).fillna(0)
                trend = {
                    "metric":     "记录数",
                    "dates":      pivot.index.tolist(),
                    "categories": pivot.columns.tolist(),
                    "series":     [
                        {"name": str(c), "data": pivot[c].tolist()}
                        for c in pivot.columns
                    ],
                }

    # 按类别聚合
    by_category = None
    if cat_col:
        if len(nums.columns) > 0:
            agg_dict = {}
            for c in nums.columns:
                cl = c.lower()
                if "csat" in cl or "margin" in cl or "turnover" in cl or "rate" in cl:
                    agg_dict[c] = "mean"
                else:
                    agg_dict[c] = "sum"
            gp = df.groupby(cat_col).agg(agg_dict).round(2)
            by_category = {
                "category_col": cat_col,
                "categories":   gp.index.tolist(),
                "metrics":      {c: gp[c].astype(float).tolist() for c in gp.columns},
            }
        else:
            # 兜底:没有数值字段(纯文本数据集如 VOC)用记录数作为 metric
            counts = df.groupby(cat_col).size().sort_values(ascending=False)
            by_category = {
                "category_col": cat_col,
                "categories":   counts.index.tolist(),
                "metrics":      {"记录数": counts.astype(float).tolist()},
            }

    # 相关性(数值列 < 2 个时跳过;NaN 替换为 0 防止 JSON 序列化失败)
    import math
    corr_dict = correlation(df.drop(columns=list(excluded), errors="ignore")) if len(nums.columns) >= 2 else {}
    corr_matrix = None
    if corr_dict:
        cols = list(corr_dict.keys())
        cells = []
        for i, c1 in enumerate(cols):
            for j, c2 in enumerate(cols):
                v = corr_dict[c1].get(c2, 0)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    v = 0.0
                cells.append([j, i, round(v, 3)])
        corr_matrix = {"columns": cols, "cells": cells}

    # 异常点（带主指标的散点用）
    anomalies_view = {
        col: {
            "n":         info["n_outliers"],
            "mean":      info.get("mean"),
            "std":       info.get("std"),
            "examples":  info.get("examples", []),
        }
        for col, info in anomalies_full.items() if info["n_outliers"] > 0
    }

    return {
        "kpi":          kpi,
        "trend":        trend,
        "by_category":  by_category,
        "correlation":  corr_matrix,
        "anomalies":    anomalies_view,
        "category_col": cat_col,
        "time_col":     time_col,
    }


@router.get("/dashboard/{filename}")
async def dashboard(filename: str):
    """已上传文件的可视化大屏数据(老接口,保留)"""
    filepath = Path(settings.data_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, "文件不存在")

    # 用 (filename, mtime) 当 cache key:文件内容变了 mtime 变,自动失效
    cache_key = (f"file:{filename}", str(filepath.stat().st_mtime))
    cached = _cache_get(cache_key)
    if cached is not None:
        return {"code": 0, "msg": "ok", "data": cached, "cached": True}

    from ..services.data_pipeline import load_data

    try:
        df = load_data(filepath)
    except Exception as e:
        raise HTTPException(500, f"加载失败: {e}")

    payload = _build_dashboard_payload(df)
    _cache_put(cache_key, payload)
    return {"code": 0, "msg": "ok", "data": payload}


@router.get("/datasets/{key}/dashboard")
async def dataset_dashboard(
    key: str,
    sheet: Optional[str] = Query(None, description="xlsx 多 sheet 时指定;不传走 manifest 第一个"),
):
    """主线数据集的可视化大屏数据(基于 manifest + dataset_loader 加载)"""
    try:
        meta = dataset_loader.get_dataset_meta(key)
    except dataset_loader.DatasetNotFoundError:
        raise HTTPException(404, f"未注册的数据集 key:{key}")

    fmt = meta["format"]
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(400, f"暂不支持 format={fmt} 的可视化(仅 csv/xlsx)")

    # 解析最终 sheet,作为缓存 key 的一部分
    if fmt == "xlsx":
        sheet_used = sheet
        if sheet_used is None:
            sheets = meta.get("sheets", [])
            sheet_used = sheets[0]["name"] if sheets else None
            if sheet_used is None:
                raise HTTPException(400, "xlsx 数据集 manifest 未声明 sheet")
    else:
        sheet_used = None

    cache_key = (f"ds:{key}", sheet_used)
    cached = _cache_get(cache_key)
    if cached is not None:
        return {"code": 0, "msg": "ok", "data": cached, "cached": True}

    try:
        if fmt == "csv":
            df = dataset_loader.load_csv(key)
        else:
            df = dataset_loader.load_excel(key, sheet=sheet_used)
    except dataset_loader.DatasetFileMissingError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    payload = _build_dashboard_payload(df)
    payload.update({
        "key":           key,
        "name":          meta["name"],
        "format":        fmt,
        "sheet":         sheet_used,
        "sheet_options": [s["name"] for s in meta.get("sheets", [])] if meta.get("sheets") else [],
    })
    _cache_put(cache_key, payload)

    return {"code": 0, "msg": "ok", "data": payload}
