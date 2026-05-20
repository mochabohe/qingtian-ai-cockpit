<template>
  <div class="evidence-page">
    <!-- ╔══════ HERO: 一个巨型数字爆点, 用户 1 秒锁定 ══════╗ -->
    <section class="hero">
      <div class="hero-eyebrow">
        <span class="eyebrow-dot"></span>
        <span class="eyebrow-text">ALGORITHM EVIDENCE · 算法可信度证据</span>
      </div>
      <div class="hero-grid">
        <div class="hero-headline">
          <div class="hero-kicker">销售单 ↔ 售后单 跨源关联</div>
          <div class="hero-mega">
            <span class="mega-num" data-text="11,259">11,259</span>
            <span class="mega-unit">笔 · 完整对齐</span>
          </div>
          <div class="hero-claim">
            字面 ID 对不上 → 系统自动补前导零,<b class="claim-hl">11,259 条销售记录与售后维修工单 100% 关联</b>
          </div>
          <div class="hero-sub">
            <span class="sub-pair">
              <span class="sub-label">销售表</span>
              <code class="kbd">S040829</code>
              <span class="sub-arrow">↔</span>
              <span class="sub-label">售后表</span>
              <code class="kbd">S40829</code>
            </span>
            <span class="sub-divider">|</span>
            <span class="sub-fix">
              <span class="sub-label">关联率</span>
              <b class="bad">0%</b>
              <span class="sub-arrow">→</span>
              <b class="good">100%</b>
            </span>
          </div>
        </div>
        <div class="hero-stats">
          <div class="hero-stat">
            <div class="stat-num">{{ datasets.length || 4 }}<span class="stat-deno">/4</span></div>
            <div class="stat-label">主线数据源</div>
          </div>
          <div class="hero-stat">
            <div class="stat-num">{{ totalRows }}</div>
            <div class="stat-label">业务记录(条)</div>
          </div>
          <div class="hero-stat">
            <div class="stat-num">{{ ragStats?.n_docs || '—' }}</div>
            <div class="stat-label">RAG 索引案例</div>
          </div>
          <div class="hero-stat">
            <div class="stat-num">3</div>
            <div class="stat-label">活跃算法引擎</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ╔══════ 数据底座: 4 张数据源徽章, 一行排开 ══════╗ -->
    <section class="page-section">
      <div class="section-bar">
        <span class="bar-num">01</span>
        <span class="bar-label">数据底座</span>
        <span class="bar-hairline"></span>
        <span class="bar-meta">点击任一项查字段画像与数据体检</span>
      </div>

      <el-skeleton v-if="datasetsLoading" :rows="2" animated />
      <div v-else-if="datasets.length === 0" class="empty-tip">
        未发现主线数据集,请运行 <code>python scripts/seed_real_data.py</code> 完成数据初始化。
      </div>
      <div v-else class="ds-deck">
        <div
          v-for="ds in datasets"
          :key="ds.key"
          class="ds-card-mini"
          :class="`ds-card-mini--${ds.domain}`"
          @click="inspect(ds)"
        >
          <div class="mini-top">
            <span class="mini-format">{{ ds.format.toUpperCase() }}</span>
            <span class="mini-dot" :class="{ ok: ds.available }"></span>
          </div>
          <div class="mini-name">{{ ds.name }}</div>
          <div class="mini-num">
            <b>{{ ds.rows ? ds.rows.toLocaleString() : '—' }}</b>
            <span class="mini-unit">行</span>
          </div>
          <div class="mini-foot">
            <span v-for="a in ds.agents" :key="a" class="mini-tag">{{ agentLabel(a) }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ╔══════ 现场试算法: 双栏可交互工具区 ══════╗ -->
    <section class="page-section">
      <div class="section-bar">
        <span class="bar-num">02</span>
        <span class="bar-label">现场试算法</span>
        <span class="bar-hairline"></span>
        <span class="bar-meta">真接后端跑 · 不是 PPT 截图、不是预录视频</span>
      </div>

      <div class="algo-lab">
        <!-- 左:RAG -->
        <div class="lab-pane">
          <div class="lab-title">
            <span class="lab-num">A</span>
            故障 → 历史维修方案
            <span class="lab-who">售后顾问</span>
          </div>
          <div class="lab-tech-row" v-if="ragStats">
            <span class="tech-stat"><b>{{ ragStats.n_docs }}</b> 条工单</span>
            <span class="tech-stat"><b>{{ Object.keys(ragStats.system_counts || {}).length }}</b> 类系统</span>
            <span class="tech-pill">关键词检索</span>
            <span class="tech-pill">中文分词</span>
            <span class="tech-pill">最相似 Top 3</span>
          </div>
          <div class="lab-input-row">
            <el-input
              v-model="ragQuery"
              placeholder="输入故障现象,如:刹车异响 / 续航缩短 / 中控黑屏"
              clearable
              size="small"
              @keyup.enter="doRagSearch"
            />
            <el-button type="primary" size="small" :loading="ragLoading" @click="doRagSearch">查相似案例</el-button>
          </div>
          <!-- 预置问题 chip:用户一键试,免现场打字翻车 -->
          <div class="lab-presets">
            <span class="presets-label">一键试:</span>
            <el-tag
              v-for="p in ragPresets"
              :key="p"
              size="small"
              effect="plain"
              class="preset-chip"
              @click="quickRag(p)"
            >{{ p }}</el-tag>
          </div>
          <div v-if="ragHits.length" class="lab-results">
            <!-- AI 一句话解读:把数字翻译成人话 -->
            <div class="ai-readout">
              <span class="readout-icon">💡</span>
              <span>
                Top 1 "<b>{{ ragHits[0].topic }}</b>" 相似度 <b class="hl">{{ ragHits[0].score?.toFixed(2) }}</b>
                · {{ ragHits[0].score > 0.3 ? '高度相关' : ragHits[0].score > 0.15 ? '中度相关' : '弱相关' }}
                <span class="readout-link">→ 写入简报"售后异常根因"段</span>
              </span>
            </div>
            <div v-for="(h, i) in ragHits" :key="i" class="lab-hit">
              <div class="hit-head">
                <span class="hit-rank">#{{ i + 1 }}</span>
                <span class="hit-topic">{{ h.topic }}</span>
                <el-tag size="small" :type="h.score > 0.3 ? 'success' : h.score > 0.15 ? 'warning' : 'info'">
                  相似度 {{ h.score?.toFixed(2) }}
                </el-tag>
              </div>
              <div class="hit-detail">
                <div><b>根因:</b> {{ h.root_cause || '—' }}</div>
                <div><b>维修方法:</b> {{ h.repair_method || '—' }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右:VOC -->
        <div class="lab-pane">
          <div class="lab-title">
            <span class="lab-num">B</span>
            竞品评论 → 用户痛点话题
            <span class="lab-who">产品经理</span>
          </div>
          <div class="lab-tech-row">
            <span class="tech-pill">中文分词</span>
            <span class="tech-pill">关键词权重</span>
            <span class="tech-pill">话题聚类</span>
            <span class="tech-pill">情感打分</span>
          </div>
          <!-- 车型选择 chip:对齐左侧"一键试"风格,点击即跑,无需按钮 -->
          <div class="lab-presets lab-presets-primary">
            <span class="presets-label">选车型 →</span>
            <el-tag
              v-for="opt in vocTargets"
              :key="opt.value"
              size="small"
              :effect="vocTarget === opt.value ? 'dark' : 'plain'"
              :class="['preset-chip', { 'preset-chip-active': vocTarget === opt.value, 'preset-chip-loading': vocTarget === opt.value && vocLoading }]"
              @click="quickVoc(opt.value)"
            >{{ opt.label }}</el-tag>
            <span v-if="vocLoading" class="voc-loading">提炼中…</span>
          </div>
          <div v-if="vocResult" class="lab-results">
            <div class="voc-stat">
              <b>{{ vocResult.n_input_total }}</b> 条 → 去重 <b>{{ vocResult.n_after_dedup }}</b> 条 → 提炼 <b class="hl">{{ vocResult.n_clusters }}</b> 个用户话题
            </div>
            <!-- AI 一句话解读 -->
            <div class="ai-readout" v-if="vocResult.clusters?.length && (vocBestPain || vocBestPraise)">
              <span class="readout-icon">💡</span>
              <span v-if="vocBestPain">
                痛点话题 "<b>{{ (vocBestPain.keywords || []).slice(0, 3).join('、') }}</b>"
                · 情感 <b class="text-danger">{{ vocBestPain.sentiment_score?.toFixed(2) }}</b>
                <span class="readout-link">→ 竞品痛点 = 我们的机会</span>
              </span>
              <span v-else-if="vocBestPraise">
                卖点话题 "<b>{{ (vocBestPraise.keywords || []).slice(0, 3).join('、') }}</b>"
                · 情感 <b class="text-emerald">+{{ vocBestPraise.sentiment_score?.toFixed(2) }}</b>
                <span class="readout-link">→ 竞品卖点 = 我们要追的标杆</span>
              </span>
            </div>
            <div v-for="(c, i) in (vocResult.clusters || []).slice(0, 5)" :key="c.cluster_id" class="lab-hit">
              <div class="hit-head">
                <span class="hit-rank">{{ c.sentiment_score < -0.05 ? '痛点' : c.sentiment_score > 0.05 ? '卖点' : '关注' }} {{ i + 1 }}</span>
                <span class="hit-topic">{{ (c.keywords || []).slice(0, 5).join('、') }}</span>
                <el-tag size="small" :type="c.sentiment_score < -0.05 ? 'danger' : c.sentiment_score > 0.05 ? 'success' : 'info'">
                  {{ c.size }} 条 · 情感 {{ c.sentiment_score >= 0 ? '+' : '' }}{{ c.sentiment_score?.toFixed(2) }}
                </el-tag>
              </div>
              <div class="hit-detail" v-if="c.representative?.[0]">
                <span style="color:var(--text-muted)">用户原话:</span> {{ c.representative[0] }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 主线数据集预览 dialog -->
    <el-dialog
      v-model="inspectDialog"
      :title="`数据体检 · ${currentDs?.name || ''}`"
      width="1080"
      destroy-on-close
    >
      <el-tabs v-model="inspectTab" class="inspect-tabs">
        <el-tab-pane label="🩺 数据体检" name="health">
          <HealthReport
            v-if="currentDs"
            :dataset-key="currentDs.key"
            :dataset-name="currentDs.name"
            :auto-load="inspectTab === 'health'"
          />
        </el-tab-pane>

        <el-tab-pane label="📋 字段画像与预览" name="preview">
          <el-skeleton v-if="inspectLoading" :rows="6" animated />
          <div v-else-if="inspectResult" class="inspect-body">
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="格式">{{ inspectResult.format }}</el-descriptions-item>
              <el-descriptions-item label="规模">{{ inspectResult.rows_total?.toLocaleString() || '-' }} 行</el-descriptions-item>
              <el-descriptions-item label="字段数">{{ inspectResult.cols?.length || '-' }}</el-descriptions-item>
            </el-descriptions>

            <h4 class="section-h">字段角色识别</h4>
            <div class="schema-adaptive-tip">
              <span class="sa-badge">Schema 自适应</span>
              <span class="sa-text">
                系统从字段名启发式识别角色（时间/主键/金额/类别），跨源主键格式不一致时自动补齐前导零达成对齐。
                manifest 用业务语义别名（sale_id / repair_id / vehicle）声明字段映射，
                <b>换任意 4S 店的销售/售后数据，3 个 Agent 不用改一行代码就能跑出简报</b>。
              </span>
            </div>
            <div v-if="inspectRoles" class="roles-grid">
              <div v-if="inspectRoles.time?.length" class="role-row">
                <span class="role-tag time">时间</span>
                <span v-for="c in inspectRoles.time" :key="c">{{ c }}</span>
              </div>
              <div v-if="inspectRoles.id?.length" class="role-row">
                <span class="role-tag id">ID</span>
                <span v-for="c in inspectRoles.id" :key="c">{{ c }}</span>
              </div>
              <div v-if="inspectRoles.metric?.length" class="role-row">
                <span class="role-tag metric">指标</span>
                <span v-for="c in inspectRoles.metric" :key="c">{{ c }}</span>
              </div>
              <div v-if="inspectRoles.dim?.length" class="role-row">
                <span class="role-tag dim">维度</span>
                <span v-for="c in inspectRoles.dim" :key="c">{{ c }}</span>
              </div>
              <div v-if="inspectRoles.text?.length" class="role-row">
                <span class="role-tag text">文本</span>
                <span v-for="c in inspectRoles.text" :key="c">{{ c }}</span>
              </div>
            </div>

            <h4 class="section-h">数据预览(前 10 行)</h4>
            <el-table v-if="inspectResult.preview?.length" :data="inspectResult.preview" max-height="320" size="small" border>
              <el-table-column
                v-for="col in inspectResult.cols"
                :key="col"
                :prop="col"
                :label="col"
                min-width="120"
                show-overflow-tooltip
              />
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/api/http'
import { readCache, writeCache } from '@/utils/sessionCache'
import { useMissionStore } from '@/stores/mission'
import HealthReport from '@/components/HealthReport.vue'

const mission = useMissionStore()

// 数据体检 dialog 当前 tab(默认 health,inspect 时优先看体检报告)
const inspectTab = ref<'health' | 'preview'>('health')

// ---- 主线数据集 ----
const datasets = ref<any[]>([])
const datasetsLoading = ref(false)
const inspectDialog = ref(false)
const currentDs = ref<any>(null)
const inspectLoading = ref(false)
const inspectResult = ref<any>(null)
const inspectRoles = ref<any>(null)

const dsSummary = computed(() => {
  if (datasets.value.length === 0) return ''
  const total = datasets.value.length
  const ok = datasets.value.filter((d) => d.available).length
  const totalRows = datasets.value.reduce((acc, d) => acc + (d.rows || 0), 0)
  const totalKb = datasets.value.reduce((acc, d) => acc + (d.size_kb || 0), 0)
  const sizeStr = totalKb >= 1024 ? `${(totalKb / 1024).toFixed(1)} MB` : `${totalKb} KB`
  return `${ok} / ${total} 已就绪 · ${totalRows.toLocaleString()} 行 · ${sizeStr}`
})

// Hero 区用的总行数(简洁格式: 6.1万 / 12.3万),爆点数字优先
const totalRows = computed(() => {
  const sum = datasets.value.reduce((acc, d) => acc + (d.rows || 0), 0)
  if (!sum) return '—'
  if (sum >= 10000) return `${(sum / 10000).toFixed(1)}万`
  return sum.toLocaleString()
})

const AGENT_LABEL_MAP: Record<string, string> = {
  linkage: '销售-售后联动',
  market_voc: '市场口碑',
  composer: '简报合成',
  aftersales: '售后质量',
  benchmark: '参数对标',
  operation: '经营分析',
}

function agentLabel(key: string) {
  return AGENT_LABEL_MAP[key] || key
}

async function loadDatasets() {
  datasetsLoading.value = true
  try {
    const { data } = await http.get('/data/datasets')
    datasets.value = data.data?.datasets || []
    // 回写 mission store(MissionBar 显示数据池就绪进度)
    mission.dataTotal = datasets.value.length || 4
    mission.dataReady = datasets.value.filter((d: any) => d.available).length
  } catch (e: any) {
    ElMessage.error(e.message || '加载主线数据集失败')
  } finally {
    datasetsLoading.value = false
  }
}

async function inspect(ds: any) {
  if (!ds.available) {
    ElMessage.warning('该数据集尚未就绪')
    return
  }
  if (ds.format === 'pdf') {
    ElMessage.info('PDF 类数据集走 RAG 检索,请到 Agent 控制台查看')
    return
  }
  currentDs.value = ds
  inspectDialog.value = true
  inspectLoading.value = true
  inspectResult.value = null
  inspectRoles.value = null
  const sheet = ds.sheets?.[0]
  const cacheKey = `inspect:${ds.key}:${sheet || ''}`
  // 命中 sessionStorage 缓存 → 秒开
  // 数据集字段画像 / 预览在一次会话内不会变, 缓存 10min 避免反复打开等待
  const cached = readCache<{ result: any; roles: any }>(cacheKey)
  if (cached) {
    inspectResult.value = cached.result
    inspectRoles.value = cached.roles
    inspectLoading.value = false
    return
  }
  try {
    const previewParams: any = { n: 10 }
    if (sheet) previewParams.sheet = sheet
    const previewRes = await http.get(`/data/datasets/${ds.key}/preview`, { params: previewParams })
    inspectResult.value = previewRes.data.data

    const inspectParams: any = {}
    if (sheet) inspectParams.sheet = sheet
    const inspectRes = await http.get(`/data/datasets/${ds.key}/inspect`, { params: inspectParams })
    const roles = inspectRes.data.data?.field_roles || {}
    inspectRoles.value = {
      time: roles.time_cols,
      id: roles.id_cols,
      metric: roles.metric_cols,
      dim: roles.dim_cols,
      text: roles.text_cols,
    }
    writeCache(cacheKey, { result: inspectResult.value, roles: inspectRoles.value })
  } catch (e: any) {
    ElMessage.error(e.message || '预览失败')
  } finally {
    inspectLoading.value = false
  }
}

// ============ 算法测试台:RAG / VOC ============
const ragQuery = ref('')
const ragHits = ref<any[]>([])
const ragLoading = ref(false)
const ragStats = ref<any>(null)
const ragPresets = ['刹车异响', '续航缩短', '中控黑屏', '电池衰减', '空调异响']

async function loadRagStats() {
  try {
    const { data } = await http.get('/data/rag/stats')
    ragStats.value = data.data
  } catch (e: any) {
    // 静默,统计失败不影响主流程
  }
}

async function doRagSearch() {
  if (!ragQuery.value.trim()) {
    ElMessage.warning('请输入故障描述')
    return
  }
  ragLoading.value = true
  try {
    const { data } = await http.get('/data/rag/search', {
      params: { q: ragQuery.value.trim(), top_k: 3, min_score: 0.05 },
    })
    ragHits.value = data.data?.hits || []
    if (ragHits.value.length === 0) ElMessage.info('未命中,可换个关键词试试')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'RAG 检索失败')
  } finally {
    ragLoading.value = false
  }
}

function quickRag(q: string) {
  ragQuery.value = q
  doRagSearch()
}

const vocTarget = ref('Model Y')
const vocResult = ref<any>(null)
const vocLoading = ref(false)

// 车型预设:对齐左侧"一键试"风格,免下拉
const vocTargets = [
  { label: '全部车系', value: 'all' },
  { label: 'Model Y', value: 'Model Y' },
  { label: '奔驰E级', value: '奔驰E级' },
  { label: 'AION V', value: 'AION V' },
]

function quickVoc(target: string) {
  vocTarget.value = target
  doVocCluster()
}

// 最负面话题(痛点 = 我们的机会),按情感分升序取头
const vocBestPain = computed(() => {
  const cs = vocResult.value?.clusters || []
  if (!cs.length) return null
  const sorted = [...cs].sort((a, b) => (a.sentiment_score ?? 0) - (b.sentiment_score ?? 0))
  return sorted[0].sentiment_score < -0.05 ? sorted[0] : null
})
// 最正面话题(竞品卖点 = 我们要追的标杆),按情感分降序取头(仅当没有显著痛点时显示)
const vocBestPraise = computed(() => {
  const cs = vocResult.value?.clusters || []
  if (!cs.length) return null
  const sorted = [...cs].sort((a, b) => (b.sentiment_score ?? 0) - (a.sentiment_score ?? 0))
  return sorted[0].sentiment_score > 0.05 ? sorted[0] : null
})

async function doVocCluster() {
  vocLoading.value = true
  try {
    const { data } = await http.get('/data/voc/clusters', {
      params: { target: vocTarget.value },
    })
    vocResult.value = data.data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'VOC 聚类失败')
  } finally {
    vocLoading.value = false
  }
}

onMounted(() => {
  loadDatasets()
  loadRagStats()
})
</script>

<style scoped>
.evidence-page {
  padding: 0 4px;
}
.page-title { display: none; }
.page-subtitle { display: none; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.hint { font-size: 12px; color: var(--text-muted); font-weight: normal; }
.empty-tip { color: var(--text-muted); font-size: 13px; padding: 24px; text-align: center; }
.empty-tip code { background: rgba(180, 230, 225, 0.03); padding: 2px 8px; border-radius: 4px; color: #334155; }

/* ════════════════════════════════════════════════════════════
   HERO: 巨型数字爆点 + 4 个支撑数据
   ──────────────────────────────────────────────────────────── */
.hero {
  position: relative;
  margin: 0 0 56px;
  padding: 36px 36px 36px;
  background: radial-gradient(ellipse 1200px 400px at 25% -20%, rgba(45, 212, 191, 0.10), transparent 60%),
              linear-gradient(180deg, rgba(255, 255, 255, 0.012) 0%, transparent 100%);
  border: 1px solid var(--border-line);
  border-radius: 12px;
  overflow: hidden;
}
.hero::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(45, 212, 191, 0.5) 50%, transparent 100%);
}
.hero-eyebrow {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 22px;
  font-size: 11px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 2.4px;
  color: var(--c-emerald);
  text-transform: uppercase;
}
.eyebrow-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-emerald);
  box-shadow: 0 0 12px rgba(45, 212, 191, 0.7);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 48px;
  align-items: center;
}
.hero-headline { min-width: 0; }
.hero-kicker {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  letter-spacing: 1.5px;
  margin-bottom: 14px;
  display: inline-block;
  padding: 4px 12px;
  background: rgba(45, 212, 191, 0.06);
  border: 1px solid rgba(45, 212, 191, 0.20);
  border-radius: var(--r-pill);
  color: var(--c-emerald);
}
.hero-mega {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 14px;
  line-height: 1;
  flex-wrap: wrap;
}
.mega-num {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 88px;
  font-weight: 600;
  letter-spacing: -2px;
  color: var(--text-primary);
  background: linear-gradient(135deg, var(--c-emerald) 0%, var(--c-mint) 50%, var(--c-emerald) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  font-variant-numeric: tabular-nums;
  position: relative;
  text-shadow: 0 0 80px rgba(45, 212, 191, 0.18);
}
.mega-unit {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 22px;
  color: var(--text-secondary);
  font-weight: 400;
  letter-spacing: 1px;
}
.hero-claim {
  font-size: 14px;
  color: var(--text-secondary);
  letter-spacing: 0.3px;
  margin-bottom: 18px;
  font-weight: 400;
  line-height: 1.6;
}
.claim-hl {
  color: var(--text-primary);
  font-weight: 600;
}
.hero-sub {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', Consolas, monospace;
  flex-wrap: wrap;
}
.sub-pair, .sub-fix {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.sub-label {
  font-family: 'PingFang SC', sans-serif;
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}
.sub-arrow {
  color: var(--c-emerald);
  font-weight: 700;
}
.sub-divider {
  color: var(--border-strong);
}
.sub-fix .bad { color: var(--c-rust); font-weight: 700; font-size: 13px; }
.sub-fix .good { color: var(--c-moss); font-weight: 700; font-size: 13px; }

.hero-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px 22px;
  border-left: 1px solid var(--border-line);
  padding-left: 36px;
}
.hero-stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stat-num {
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.stat-deno {
  font-size: 16px;
  color: var(--text-muted);
  margin-left: 2px;
}
.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 1px;
  font-family: 'PingFang SC', sans-serif;
}

/* ════════════════════════════════════════════════════════════
   SECTION BAR: 极简横排 章节锚点 (代替章节标题卡)
   ──────────────────────────────────────────────────────────── */
.page-section {
  margin-top: 44px;
}
.section-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
}
.bar-num {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.6px;
  color: var(--c-emerald);
  background: rgba(45, 212, 191, 0.08);
  border: 1px solid rgba(45, 212, 191, 0.28);
  padding: 3px 9px;
  border-radius: 3px;
}
.bar-label {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.5px;
}
.bar-hairline {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--border-line) 0%, transparent 100%);
}
.bar-meta {
  font-size: 11.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 0.3px;
  flex-shrink: 0;
}

/* 旧 ds-card / algo-lab-card 包裹层不再需要, 留个空壳 */
.ds-card, .algo-lab-card { display: none; }
/* 旧 join-fix-card 不再使用 */
.join-fix-card { display: none; }
.section-head { display: none; }

/* 算法测试台预置 chip */
.lab-presets {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.lab-presets .presets-label {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-right: 2px;
}
.preset-chip {
  cursor: pointer;
  transition: all 0.15s;
}
.preset-chip:hover {
  background: rgba(45, 212, 191, 0.08) !important;
  border-color: #93c5fd !important;
  color: var(--c-emerald-deep) !important;
}
.preset-chip-active {
  background: rgba(45, 212, 191, 0.95) !important;
  color: #0a0e1a !important;
  border-color: var(--c-emerald) !important;
  box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.3) !important;
  font-weight: 600 !important;
}
.preset-chip-loading {
  animation: chipPulse 1.4s ease-in-out infinite;
}
@keyframes chipPulse {
  0%, 100% { box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.3) !important; }
  50% { box-shadow: 0 0 0 4px rgba(45, 212, 191, 0.18) !important; }
}
/* 主交互 chip 排:替代按钮,字号略大、间距宽一点 */
.lab-presets-primary {
  margin-top: 2px;
  gap: 8px;
}
.lab-presets-primary .preset-chip {
  height: 26px !important;
  padding: 0 12px !important;
  font-size: 12px !important;
}
.lab-presets-primary .presets-label {
  font-size: 12.5px;
  color: var(--text-secondary);
  font-weight: 500;
  margin-right: 4px;
}
.voc-loading {
  margin-left: 8px;
  font-size: 11.5px;
  color: var(--c-emerald);
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 0.3px;
  animation: pulse 1.4s ease-in-out infinite;
}

/* ════════════════════════════════════════════════════════════
   DS DECK: 4 张数据源迷你卡, 一行排开
   ──────────────────────────────────────────────────────────── */
.ds-deck {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.ds-card-mini {
  position: relative;
  padding: 18px 18px 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.018) 0%, transparent 100%);
  border: 1px solid var(--border-line);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 130px;
  overflow: hidden;
}
.ds-card-mini::before {
  content: '';
  position: absolute;
  top: 0; left: 18px; right: 18px;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(45, 212, 191, 0.32) 50%, transparent 100%);
  opacity: 0.5;
  transition: opacity 0.2s;
}
.ds-card-mini:hover {
  border-color: rgba(45, 212, 191, 0.4);
  background: linear-gradient(180deg, rgba(45, 212, 191, 0.04) 0%, transparent 100%);
  transform: translateY(-1px);
}
.ds-card-mini:hover::before {
  opacity: 1;
}
.mini-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mini-format {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: 1.5px;
}
.mini-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(217, 119, 87, 0.55);
}
.mini-dot.ok {
  background: var(--c-emerald);
  box-shadow: 0 0 8px rgba(45, 212, 191, 0.55);
}
.mini-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
  line-height: 1.4;
}
.mini-num {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-top: auto;
}
.mini-num b {
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 24px;
  font-weight: 600;
  color: var(--c-emerald);
  letter-spacing: -0.3px;
  font-variant-numeric: tabular-nums;
}
.mini-unit {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.3px;
}
.mini-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.mini-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: rgba(45, 212, 191, 0.06);
  color: var(--c-emerald);
  border: 1px solid rgba(45, 212, 191, 0.20);
  letter-spacing: 0.2px;
}

@media (max-width: 1100px) {
  .ds-deck { grid-template-columns: repeat(2, 1fr); }
  .hero-grid { grid-template-columns: 1fr; gap: 32px; }
  .hero-stats { border-left: 0; padding-left: 0; border-top: 1px solid var(--border-line); padding-top: 24px; }
  .mega-num { font-size: 64px; }
}

/* 旧 ds-tile / ds-grid 不再使用 */
.ds-grid, .ds-tile { display: none; }

.section-h { margin: 18px 0 8px; font-size: 14px; color: var(--text-primary); }
.schema-adaptive-tip {
  display: flex; align-items: flex-start; gap: 10px;
  margin: 4px 0 12px; padding: 10px 12px;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.08) 0%, rgba(78, 205, 196, 0.04) 100%);
  border-left: 3px solid var(--c-mint); border-radius: 6px;
  font-size: 12.5px; line-height: 1.65; color: var(--text-secondary);
}
.schema-adaptive-tip .sa-badge {
  flex-shrink: 0; font-size: 11px; font-weight: 700;
  padding: 2px 10px; border-radius: 999px;
  background: var(--c-mint); color: #04161a;
}
.schema-adaptive-tip .sa-text { flex: 1; }
.schema-adaptive-tip .sa-text b { color: var(--c-emerald); }
.roles-grid { display: flex; flex-direction: column; gap: 8px; padding: 8px 0; }
.role-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 12.5px; color: var(--text-secondary); }
.role-tag {
  font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 999px;
  background: rgba(180, 230, 225, 0.03); color: var(--text-secondary);
}
.role-tag.time { background: rgba(45, 212, 191, 0.06); color: var(--c-emerald); }
.role-tag.id { background: rgba(45, 212, 191, 0.08); color: var(--c-emerald); }
.role-tag.metric { background: rgba(132, 204, 22, 0.10); color: var(--c-moss); }
.role-tag.dim { background: rgba(45, 212, 191, 0.06); color: var(--c-mint); }
.role-tag.text { background: rgba(78, 205, 196, 0.10); color: var(--c-mint); }

.inspect-body { padding-bottom: 8px; }

/* 算法测试台: 双栏报刊版面, 中间一条竖向 hairline 分隔, 不再用左右两个卡 */
.algo-lab {
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  gap: 28px 24px;
  align-items: stretch;
}
.algo-lab::after {
  content: '';
  grid-column: 2;
  grid-row: 1;
  background: var(--border-line);
  align-self: stretch;
}
.lab-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 0 4px;
}
.lab-title {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}
.lab-num {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  color: var(--c-emerald);
  letter-spacing: 1px;
}
.lab-who {
  margin-left: auto;
  font-family: inherit;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  letter-spacing: 0.3px;
}
.lab-sub {
  font-size: 11.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 0.3px;
  margin-left: 12px;
}
.lab-tech-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  min-height: 28px;
}
.tech-stat,
.tech-pill {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  letter-spacing: 0.2px;
}
/* tech-stat: 只读统计, 圆角小 pill, 自身垂直居中 */
.tech-stat {
  align-self: center;
  height: 24px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font-size: 11px;
  line-height: 1;
  color: var(--text-secondary);
  background: rgba(180, 230, 225, 0.04);
  border: 1px solid var(--border-line);
}
.tech-stat b {
  margin-right: 2px;
  color: var(--text-primary);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
/* tech-pill: 算法栈说明标签(只读·非按钮)
   极简版:左侧一根翡翠 hairline + 中文单行,跟下方可点 chip 完全区分 */
.tech-pill {
  align-self: center;
  height: auto;
  padding: 2px 0 2px 10px;
  background: transparent;
  border: 0;
  border-radius: 0;
  border-left: 1px solid rgba(45, 212, 191, 0.32);
  cursor: default;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: 0.4px;
  white-space: nowrap;
}
.lab-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.lab-presets { /* margin reset */ }
.lab-results {
  display: flex;
  flex-direction: column;
  margin-top: 6px;
  max-height: 360px;
  overflow: auto;
  border-top: 1px solid var(--border-line);
}
/* 单条命中: 行式版本, hairline 分隔 */
.lab-hit {
  padding: 10px 4px;
  background: transparent;
  border: 0;
  border-radius: 0;
  border-bottom: 1px solid var(--border-line);
}
.hit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}
.hit-rank {
  font-family: ui-monospace, monospace;
  color: var(--text-muted);
  font-size: 12px;
}
.hit-topic {
  flex: 1;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}
.hit-detail {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.55;
}
.hit-detail b {
  color: var(--text-primary);
}
.voc-stat {
  font-size: 12px;
  color: var(--c-emerald);
  font-weight: 600;
  padding: 6px 10px;
  background: rgba(45, 212, 191, 0.08);
  border-radius: 4px;
}

/* AI 解读条:把数字翻译成业务结论 */
.ai-readout {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  margin: 6px 0 10px;
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.10) 0%, rgba(45, 212, 191, 0.02) 100%);
  border-left: 2px solid var(--c-emerald);
  border-radius: 0 4px 4px 0;
  font-size: 12.5px;
  color: var(--text-primary);
  line-height: 1.6;
}
.readout-icon {
  flex-shrink: 0;
  font-size: 14px;
}
.ai-readout b {
  color: var(--text-primary);
}
.ai-readout b.hl {
  color: var(--c-emerald);
}
.ai-readout b.text-danger {
  color: #f87171;
}
.ai-readout b.text-emerald {
  color: var(--c-emerald);
}
.readout-link {
  margin-left: 6px;
  color: var(--c-emerald);
  font-weight: 500;
}

@media (max-width: 900px) {
  .algo-lab { grid-template-columns: 1fr; }
}
</style>
