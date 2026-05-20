# 智擎参谋 · 汽车经营全景 AI 助手

> 一套围绕汽车行业核心业务的 AI 经营参谋系统，完成
>
> **数据接入 → Schema 自适应 → 多 Agent 协同分析 → 战略简报生成 → AI 业务视频自动产出**
>
> 的全链路闭环。

---

## 一、产品定位

**一句话定位**：

> **「这款车卖得怎么样？售后健康吗？用户怎么看？该怎么改？」** —— 一键生成战略简报。

**核心命题**：

> 输入车型，系统在数分钟内给出战略级答案：销售-售后联动诊断 + 市场口碑挖掘 + 改进路线图。

---

## 二、数据闭环

```
                    输入：目标车型
                          │
                          ▼
   ┌──────────────────────────────────────────────────┐
   │  数据感知 Agent (collector) · 第 1 步             │
   │  └─ 盘点销售/售后/VOC + 标记跨源关联键           │
   └────────────────────┬─────────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────────┐
   │  双路分析 Agent (analyzer) · 第 2 步              │
   │  ├─ 销售-售后联动路:销售曲线 / 月度环比 / 跨源 join │
   │  │   售后 3σ 异常 / TOP 维修 / 故障根因 RAG      │
   │  └─ 市场口碑路:VOC 10万条 → TF-IDF + KMeans →      │
   │      LLM 主题命名(逻辑去重) → 情感强度 →          │
   │      TOP10 痛点/卖点 + 对标机会四象限             │
   └────────────────────┬─────────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────────┐
   │  合规审查 Agent (compliance) · 第 3 步            │
   │  └─ 7 类汽车敏感正则 + LLM 复审                   │
   └────────────────────┬─────────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────────┐
   │  简报合成 Agent (writer) · 第 4 步                │
   │  └─ 模板装配 → BriefingDoc + Markdown + 视频脚本  │
   └────────────────────┬─────────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────────┐
   │  发布 + 业务视频 Agent (publisher) · 第 5 步      │
   │  ├─ 飞书群机器人推送(executive_summary)           │
   │  └─ Seedance 1080p 视频(口语化旁白 + 实车特征)    │
   └────────────────────┬─────────────────────────────┘
                        ▼
       输出：战略改进简报 + 飞书推送 + AI 业务视频
   「3 个改进方向 + 5 个对标动作 + 12 周路线图」

   ┌─ 全流程随时可叫: 浮动经营分析陪伴专家(RAG 5 工作流) ─┐
   │  销售归因 / 行业基准 / 漏斗诊断 / 竞品矩阵 / 合规自检 │
   └──────────────────────────────────────────────────────┘
```

---

## 三、技术架构

### 1. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│  前端  Vue3 + Vite + TypeScript + Element Plus + ECharts      │
│        ├─ 战情室主页（经营驾驶舱 / KPI / 简报快照）           │
│        ├─ 数据接入页（算法可信度证据 + Schema 自适应）        │
│        ├─ 智擎 Agent 控制台（5 步流式协作 + Tool use 可视化） │
│        ├─ 战略简报预览（Markdown / 全链路追溯 / 修订）        │
│        ├─ AI 业务视频工作室（脚本 → 进度 → 字幕 mp4）         │
│        ├─ 对标机会地图（VOC 四象限散点）                      │
│        └─ 浮动经营分析陪伴专家（外接 RAG · 5 工作流）         │
└────────────────────────────┬─────────────────────────────────┘
                             │  HTTP / SSE
┌────────────────────────────┴─────────────────────────────────┐
│  后端  FastAPI + Uvicorn                                     │
│        ├─ /api/data/*       数据接入 + Schema 自适应 + 体检   │
│        ├─ /api/agent/*      5 步 Agent 编排（流式 SSE）        │
│        ├─ /api/report/*     简报生命周期 + 全链路追溯         │
│        ├─ /api/compliance/* 双层合规审查                      │
│        ├─ /api/video/*      Seedance 业务视频 + 实时进度      │
│        ├─ /api/expert/*     外接 RAG 平台 SSE proxy           │
│        └─ /api/system/*     OFFLINE_MODE 兜底切换             │
│                                                              │
│  核心模块                                                    │
│        ├─ LLMClient          多 provider 可插拔               │
│        ├─ SchemaInspector    字段角色自动识别 + 主键格式对齐  │
│        ├─ DatasetLoader      4 类主线数据集统一加载           │
│        ├─ DataPipeline       pandas / sklearn 处理            │
│        ├─ VocClustering      物理 + 逻辑双层去重 + KMeans     │
│        ├─ RAGStore           故障案例 TF-IDF 字符 n-gram 向量库 │
│        ├─ Orchestrator       5 步 Agent 编排 + trace 落盘     │
│        ├─ Compliance         正则 + LLM 双层(7 类汽车敏感)    │
│        ├─ Reporter           Markdown / PPTX / HTML 导出      │
│        ├─ VideoSynth         简报 → Seedance 1080p + Edge-TTS │
│        ├─ FallbackPlayer     OFFLINE_MODE 演示兜底            │
│        └─ FeishuBot          publisher 推送                   │
└──────────────────────────────────────────────────────────────┘
```

### 2. 智能体架构（5 步主编排 Agent + 1 个浮动陪伴专家）

主编排链路 5 步，由 `services/orchestrator.py` 流式驱动；浮动陪伴专家是产品化亮点，独立于主链路。

| # | Agent | 主职责 | 数据源 / 工具 |
| --- | --- | --- | --- |
| 1 | **数据感知 Agent**(collector) | 盘点销售/售后/VOC 数据源 + 跨源关联键标记 | `DatasetLoader` / `SchemaInspector` |
| 2 | **双路分析 Agent**(analyzer) | 销售-售后联动 + 市场口碑(VOC 情感&主题聚类)双路结构化分析 | `query_table` / `join_by_key` / `anomaly_detect` / `vector_cluster` / `sentiment_score` / `rag_search` |
| 3 | **合规审查 Agent**(compliance) | 汽车行业敏感信息脱敏(VIN/车主/精确金额) | 正则黑名单 + LLM 复审 |
| 4 | **简报合成 Agent**(writer) | 整合双路结论生成战略简报封面/摘要/行动项 | `template_compose` / `briefing_schema` |
| 5 | **发布 + 业务视频 Agent**(publisher) | 多渠道推送 + 90 秒 AI 业务视频口播脚本 | `feishu_bot.send_briefing_card` / `video_synth.extract_script_from_briefing` |

| 浮动入口 | 主职责 | 实现 |
| --- | --- | --- |
| **经营分析陪伴专家** | 用户随时追问的陪伴式 Agent，挂 5 个工作流 | 外接 RAG 平台：销售归因引擎 / 行业基准对比器 / 销售漏斗诊断器 / 竞品矩阵分析器 / 合规自检器；前端 `FloatingExpertBot.vue` 接 `/api/expert/*` SSE proxy |

**LLM 与确定性代码分工**：清洗、聚类、异常检测、跨源 join 这类**有标准答案的环节用确定性代码**（pandas / sklearn）；LLM 只承担**需要语言能力的环节**（字段语义解释、主题命名、洞察表达、简报撰写）。

**Memory 设计**：

- 短期：当前会话的 schema、双路 Agent 中间结论、简报草稿
- 长期：历史简报库 + `*.trace.json` 全链路追溯
- 缓存层：dashboard payload 30 分钟 TTL（后端） + sessionStorage 10 分钟（前端）；agent-info localStorage 秒出 + 后端内存兜底

### 3. Schema 自适应数据接入层（核心创新）

> 真实数据集字段可能更多、规模更大，但结构同源。任何写死字段名的代码都会在新数据上翻车。

`SchemaInspector` 自动识别字段角色：

```
infer_field_roles(df) →
  {
    time_cols:    ["销售时间", "维修日期"],
    dim_cols:     ["车型", "门店", "区域"],
    metric_cols:  ["最终价格", "维修总金额"],
    id_cols:      ["销售id", "维修单号"],
    text_cols:    ["内容", "故障现象"]
  }
```

下游 Agent / 图表 / 简报全部基于角色而非字段名工作。LLM 兜底：当字段名是无意义代号（`f1`、`col_a`）时，用 LLM 看样本值反推含义。

**主键格式自动对齐（项目最硬算法亮点）**：销售表 `销售id` 用 6 位前导零格式（`S040829`），售后表 `车辆销售ID` 用无前导零格式（`S40829`）；同一笔订单两表写法不一致，靠 `SchemaInspector` 给售后侧自动补前导零达成 join，关联率从 0% 拉到 100%（11,259 笔完整对齐）。

### 4. RAG 知识层（聚焦版）

只对**与主线强相关的非结构化数据**入向量库：

| 来源 | 用途 |
| --- | --- |
| 故障案例数据（384 条 RAG 索引） | 双路分析 Agent · 故障根因 + 维修方案检索 |

向量库选型：TF-IDF 字符 n-gram（轻量，无需 GPU），不依赖外部平台；阈值 0.2 过滤防业务上不通的低分误命中。

### 5. 算法深度演示：VOC 情感 + 主题聚类（双路分析 Agent · 市场口碑路）

```
10万条 VOC 评论
   │
   ├─ 文本预处理（去重、去水帖、长度过滤、业务停用词扩展） ← 物理去重
   │
   ├─ TF-IDF 字符 n-gram 向量化（轻量,无需 GPU）
   │
   ├─ KMeans 聚类（候选 k 自适应 [3,4,5] / [5,7,9] / [6,8,10]）
   │   · 大数据自动切 MiniBatchKMeans(内存 1/10、速度 5-10x)
   │
   ├─ LLM 主题命名（每个簇取代表性评论让 LLM 命名）   ← 逻辑去重（同根因不同表述合一）
   │
   ├─ 情感强度打分（积极/消极/中性 + 强度 0-1）
   │
   └─ 输出：「目标车型用户 TOP10 痛点 / TOP10 卖点 + 情感强度 + 代表评论」
```

输出可视化：词云 + 主题树状图 + 情感分布堆叠图 + 对标机会地图（VOC 关注度 × 负面强度四象限散点）。

### 6. 业务视频自动生成链路

简报生成完成后，系统自动产出业务播报视频：

```
简报 BriefingDoc(JSON)
   │
   ├─ 旁白口语化重写(extract_script_from_briefing)
   │
   ├─ 实车视觉特征 prompt 注入(车型 spec)
   │
   ├─ Seedance 1080p 图生视频(doubao-seedance-1-5-pro / 2-0)
   │   后缀强制 no readable text/logos/emblems —— 文字交给字幕烧录
   │
   ├─ Edge-TTS 语音(XiaoxiaoNeural)
   │
   ├─ FFmpeg 拼接 + SRT 字幕硬烧录(1920×1080)
   │   单段失败用 LocalStub 静态图兜底,整片不挂
   │
   └─ 输出：MP4 / 60-90s
```

实时进度：后端 `_compute_progress` 扫工作目录算 stage / eta_s / scene_timeline，前端 VideoStudio 显示 "已等 X · 预计剩余 Y" + 单段时间线高亮。

### 7. 模型可插拔策略

所有 LLM 调用走统一 `LLMClient` 封装，通过环境变量切换 provider：

| 阶段 | Provider | 模型 | API Type |
| --- | --- | --- | --- |
| 主力（默认） | DeepSeek 官方 | deepseek-chat | chat_completions |
| 备选 | OpenAI 官方 | gpt-4o | chat_completions |
| 兜底（隔离网） | 本地 Ollama | qwen2.5:7b | chat_completions |
| 任意兼容 API | 自定义 | 自定义 | chat_completions / responses / messages |

---

## 四、数据集（聚焦 4 份，主线必须）

| # | 数据集 | 体量 | 角色 | 主键 |
| --- | --- | --- | --- | --- |
| 1 | VOC 评论数据 | 43 MB / 100000 行 | 市场口碑路 · 算法亮点 | — |
| 2 | 车辆销售表 | 4.8 MB / 5 sheet | 销售-售后联动路 · 销售视角 | 销售id (S040829) / 车型id / 活动id / 芯片型号 |
| 3 | 车辆售后数据 | 1.95 MB / 3 sheet | 销售-售后联动路 · 售后视角 | 维修单号 / 车辆销售ID (S40829) / 项目编号 |
| 4 | 故障案例 | 138 KB / 384 条 | RAG 来源 · 故障根因 | 故障编号 |

**关联线**：销售表 `销售id`（6 位前导零，如 `S040829`）↔ 售后表 `车辆销售ID`（无前导零，如 `S40829`），同一笔订单两表写法不一致 → `SchemaInspector` 自动补齐前导零达成 join，11,259 笔完整对齐；`车型id` 把销售流水关联到价格表与车型芯片表。

**目录结构**：

```
data/datasets/
  manifest.json             # 数据集元信息（key/agent/字段别名）
  raw/                      # 原始数据，不进 git
    voc_dongchedi.csv
    sales_records.xlsx
    aftersales_records.xlsx
    quality_fault_cases.xlsx
```

> 原始数据集不进 git。请把上述同名 csv/xlsx 自行放到 `data/datasets/raw/` 下，再启动后端。

---

## 五、5 步主编排链路细节

主编排链路 5 步由 `services/orchestrator.py` 流式驱动；每步细节如下（更详细的 prompt 见 `backend/app/services/agents.py`）：

### 1. 数据感知 Agent (collector)

- **输入**：车型 ID
- **数据**：4 类主线数据集 + manifest.json 字段别名
- **核心工作**：盘点销售/售后/VOC 数据源、识别字段角色、标记跨源关联键
- **输出**：data_summary（数据规模 + 关联键证据链）

### 2. 双路分析 Agent (analyzer · 算法亮点)

- **销售-售后联动路**：销售曲线 / 月度环比 / 跨源 join → 销售爆款 vs 售后频次对照 / 售后 3σ 时序异常检测 / TOP 维修项目排行 / 故障根因 RAG 检索
- **市场口碑路**：VOC 10万条 → TF-IDF 字符 n-gram → KMeans 聚类 → LLM 主题命名 → 情感强度打分 → TOP10 痛点/卖点
- **输出**：analysis（双路结构化结论 + KPI strip + 趋势图配置 + 对标机会地图四象限）

### 3. 合规审查 Agent (compliance)

- **第一层**：正则黑名单 7 类（VIN / 手机号 / 身份证 / 银行卡 / 邮箱 / 内部代号 / 精确金额）—— 装配前强制本地脱敏
- **第二层**：LLM 复审 `{has_risk, risk_items, sanitized_text}`
- **输出**：compliance（风险报告 + sanitized_text + 6 处精确金额脱敏样例）

### 4. 简报合成 Agent (writer)

- **输入**：双路分析结构化结论 + 合规审查结果
- **核心工作**：模板装配 → Markdown 简报 → LLM 校阅润色
- **输出**：BriefingDoc(JSON) + report_md + 90 秒视频脚本

### 5. 发布 + 业务视频 Agent (publisher)

- **飞书推送**：调 `feishu_bot.send_briefing_card` 推 `executive_summary` 到群机器人；webhook 未配 / OFFLINE_MODE → 静默跳过
- **业务视频**：把简报切成 5-7 幕分镜，旁白口语化重写 + 实车视觉特征注入 + Seedance 1080p 生成
- **输出**：publish_status（多渠道发布状态） + 视频脚本

---

## 六、前端主视图

| 视图 | 路由 | 说明 |
| --- | --- | --- |
| 经营任务台 (Home) | `/` | 项目第一画面：焦点车型 + KPI + 简报快照 + 行动 TOP3 |
| 数据接入页 (DataUpload) | `/data` | Schema 自适应展示：11,259 笔跨源关联爆点 |
| 数据可视化大屏 (Dashboard) | `/dashboard` | 5 类分析 + 8 色 brand palette |
| 智擎 Agent 控制台 (AgentConsole) | `/agent` | 5 步流式协作 + Tool use 可视化 |
| 战略简报预览 (ReportPreview) | `/report` | Markdown 渲染 / 全链路追溯 / 修订模式 |
| 对标机会地图 (OpportunityMap) | `/opportunity` | VOC 关注度 × 负面强度四象限散点 |
| AI 业务视频工作室 (VideoStudio) | `/video` | 脚本预览 + 实时进度 + 单段时间线 |
| 浮动陪伴专家 (FloatingExpertBot) | 全局 | 5 工作流陪伴 Agent |

---

## 七、项目结构

```
qingtian-ai-cockpit/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── core/
│   │   ├── routers/
│   │   ├── services/
│   │   └── llm_client.py
│   ├── .env.example
│   ├── requirements.txt
│   └── run.py
│
├── frontend/                   # Vue3 前端
│   ├── src/
│   │   ├── views/
│   │   ├── components/
│   │   ├── api/
│   │   ├── stores/
│   │   ├── App.vue / main.ts
│   ├── vite.config.ts
│
├── data/
│   ├── datasets/
│   │   ├── manifest.json
│   │   └── raw/                # 原始数据(不进 git)
│   ├── reports/                # 历史简报(运行期生成)
│   └── videos/                 # 视频任务工作目录(不进 git)
│
├── scripts/
│   ├── seed_real_data.py       # 数据初始化
│   ├── run_e2e_brief.py        # 真简报代跑
│   ├── run_e2e_with_retry.py   # 带整轮重试的简报代跑
│   ├── dry_run_real_data.py    # 不调 LLM 探雷脚本
│   ├── test_field_compat.py    # 字段映射兼容测试
│   └── kill-port-8000.ps1      # 端口清理工具
│
├── llm_client.py / example.py  # LLMClient 最小示例
└── README.md
```

---

## 八、快速启动

> **环境前置**：Python 3.10+ / Node 18+ / pnpm 8+。Windows PowerShell（项目脚本基于 PowerShell）。

### 一键启动（推荐）

在**项目根目录**打开终端：

```powershell
pnpm install          # 自动: Node 依赖 + 创建 .venv + pip install backend 依赖 + 生成 backend\.env
# 编辑 backend\.env 填入自己的 API Key
pnpm dev              # 同时拉起 backend (8000) 和 frontend (5173)
```

- 后端：http://localhost:8000 ，Swagger 文档：http://localhost:8000/docs
- 前端：http://localhost:5173 ，已配 `/api` 代理到后端 8000

> `pnpm install` 的 postinstall 钩子会自动跑 `scripts/setup-venv.ps1` 建虚拟环境 + 装 Python 包，首次约 2-3 分钟。如果失败可手动重跑：`pnpm setup:venv`。

### 单独启动 / 调试

```powershell
pnpm dev:backend      # 只起后端
pnpm dev:frontend     # 只起前端
pnpm kill:backend     # 清理被占住的 8000 端口
```

### 数据初始化

把准备好的 4 类核心数据放入 `data/datasets/raw/`（或修改 `scripts/seed_real_data.py` 的源路径后执行）：

```powershell
.\.venv\Scripts\python.exe scripts\seed_real_data.py
```

---

## 九、关键决策与取舍

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 主线场景 | 销售-售后联动 + 市场口碑（聚焦） | 1-3 个强关联数据集足以撑起完整业务故事，避免堆砌 |
| 主案例 | 单一车型纵向钻取 | 销售记录、售后维修、故障案例联动，故事最完整 |
| 算法亮点 | 市场口碑 Agent（VOC 情感聚类） | 命中"挖掘表面看不到的关联"；视频出片率高 |
| Agent 分工 | 5 步主编排 + 1 个浮动陪伴专家 | 主链路严肃确定性，陪伴专家产品化亮点 |
| Schema 策略 | 角色识别 + 字段映射兜底 | 真实数据字段可能更多，自适应是核心能力 |
| 前端框架 | Vue3 + Element Plus | 开发速度 + Demo 表现力兼顾 |
| 后端语言 | Python（FastAPI） | pandas/sklearn 生态强；RAG 库齐全 |
| 模型策略 | 多 provider 可插拔 | 主力默认 + 自由切换 |

---

## 十、技术栈

- 后端：Python 3.12 / FastAPI / Uvicorn / pandas / scikit-learn / openpyxl / httpx
- 前端：Vue 3 / Vite / TypeScript / Element Plus / ECharts / Pinia
- LLM：OpenAI 兼容协议（responses / chat_completions 自动切换）
- 视频：Seedance 1080p 图生视频 / Edge-TTS / FFmpeg
- 推送：飞书自定义机器人 Webhook（可选）

---

**License**: 仅供学习交流使用。
