<template>
  <div class="opportunity-map">
    <header class="map-hero">
      <div class="hero-badge">Opportunity Map</div>
      <h1 class="hero-title">VOC 机会地图 <span>用户关注 × 情绪强度</span></h1>
      <p class="hero-desc">把对标车型 VOC 切四象限,反推 eπ007 该改什么、该放大什么。</p>
    </header>

    <el-card class="map-card">
      <template #header>
        <div class="card-head">
          <div class="head-left">
            <b>📍 对标车型口碑机会矩阵</b>
            <span v-if="result" class="head-meta">
              共 {{ result.n_clusters }} 个话题 · 来自 {{ result.n_after_dedup }} 条有效评论
            </span>
          </div>
          <div class="head-right">
            <el-radio-group v-model="target" size="small" :disabled="loading">
              <el-radio-button label="Model Y" />
              <el-radio-button label="奔驰E级" />
              <el-radio-button label="AION V" />
              <el-radio-button label="all">全部</el-radio-button>
            </el-radio-group>
            <el-button type="primary" size="small" :loading="loading" @click="loadMap({ force: true })">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="map-body" v-loading="loading">
        <EChart v-if="chartOption" :option="chartOption" height="540px" @click="onChartClick" />
        <el-empty v-else-if="!loading" description="暂无话题数据" />
      </div>

      <!-- 四象限说明 -->
      <div class="quadrant-legend">
        <div class="quad-item q-urgent">
          <span class="quad-dot"></span>
          <b>必须立即解决</b>
          <span class="quad-desc">高关注 + 高负面 → 产品 / 售后优先改</span>
        </div>
        <div class="quad-item q-amplify">
          <span class="quad-dot"></span>
          <b>可放大为卖点</b>
          <span class="quad-desc">高关注 + 低负面 → 销售话术 / 市场传播</span>
        </div>
        <div class="quad-item q-watch">
          <span class="quad-dot"></span>
          <b>监控预警</b>
          <span class="quad-desc">低关注 + 高负面 → 防扩散</span>
        </div>
        <div class="quad-item q-low">
          <span class="quad-dot"></span>
          <b>低优先级</b>
          <span class="quad-desc">暂不投入</span>
        </div>
      </div>
    </el-card>

    <!-- 选中话题详情卡 -->
    <el-card class="detail-card" v-if="selected">
      <template #header>
        <div class="card-head">
          <b>话题详情 · {{ topicName(selected) }}</b>
          <el-tag :type="quadrantTag(selected.quadrant)" size="small">{{ quadrantLabel(selected.quadrant) }}</el-tag>
        </div>
      </template>
      <div class="detail-grid">
        <div class="detail-section">
          <div class="detail-title">话题关键词</div>
          <div class="detail-tags">
            <el-tag v-for="kw in selected.keywords" :key="kw" size="small" effect="plain">{{ kw }}</el-tag>
          </div>
        </div>
        <div class="detail-section">
          <div class="detail-title">规模 / 情感</div>
          <div class="detail-stats">
            <div><b>{{ selected.size }}</b> 条评论</div>
            <div :class="sentimentClass(selected.sentiment_score)">
              情感分 {{ selected.sentiment_score >= 0 ? '+' : '' }}{{ selected.sentiment_score?.toFixed(2) }}
            </div>
          </div>
        </div>
        <div class="detail-section detail-full">
          <div class="detail-title">代表评论</div>
          <ul class="detail-quotes">
            <li v-for="(q, i) in selected.representative.slice(0, 10)" :key="i">{{ q }}</li>
          </ul>
        </div>
        <div class="detail-section detail-full" v-if="selected.suggestion">
          <div class="detail-title">建议动作</div>
          <p class="detail-suggestion">{{ selected.suggestion }}</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/api/http'
import EChart from '@/components/EChart.vue'

interface Cluster {
  cluster_id:      number
  size:            number
  keywords:        string[]
  representative:  string[]
  sentiment_label: string
  sentiment_score: number
  pos_hits?:       number
  neg_hits?:       number
}
interface VocResult {
  n_input_total: number
  n_after_dedup: number
  n_clusters:    number
  target_vehicle: string | null
  clusters:      Cluster[]
}

interface PlottedCluster extends Cluster {
  attention:  number    // 0-100 归一化
  intensity:  number    // 0-100 归一化(负面强度)
  quadrant:   'urgent' | 'amplify' | 'watch' | 'low'
  suggestion: string
}

const target  = ref('Model Y')
const loading = ref(false)
const result  = ref<VocResult | null>(null)
const selected = ref<PlottedCluster | null>(null)

const QUAD_THRESHOLDS = { attention: 50, intensity: 50 }

function classifyQuadrant(att: number, intensity: number): PlottedCluster['quadrant'] {
  if (att >= QUAD_THRESHOLDS.attention && intensity >= QUAD_THRESHOLDS.intensity) return 'urgent'
  if (att >= QUAD_THRESHOLDS.attention && intensity <  QUAD_THRESHOLDS.intensity) return 'amplify'
  if (att <  QUAD_THRESHOLDS.attention && intensity >= QUAD_THRESHOLDS.intensity) return 'watch'
  return 'low'
}

function quadrantLabel(q: PlottedCluster['quadrant']): string {
  return ({ urgent: '必须立即解决', amplify: '可放大为卖点', watch: '监控预警', low: '低优先级' })[q]
}
function quadrantTag(q: PlottedCluster['quadrant']) {
  return ({ urgent: 'danger' as const, amplify: 'success' as const, watch: 'warning' as const, low: 'info' as const })[q]
}
function sentimentClass(score: number) {
  if (score < -0.05) return 'sent-neg'
  if (score >  0.05) return 'sent-pos'
  return 'sent-neutral'
}
function topicName(c: Cluster): string {
  return (c.keywords || []).slice(0, 3).join('、') || '用户关注话题'
}

function buildSuggestion(c: Cluster, q: PlottedCluster['quadrant']): string {
  const kw = (c.keywords || []).slice(0, 3).join('、')
  switch (q) {
    case 'urgent':
      return `「${kw}」是高关注 + 高负面话题,建议产品/售后口径 2 周内完成专项排查与门店话术更新。`
    case 'amplify':
      return `「${kw}」用户关注度高且情绪正向,建议市场部纳入销售讲解卡和短视频脚本卖点。`
    case 'watch':
      return `「${kw}」当前关注度不高但情绪偏负面,纳入舆情监控,防止扩散。`
    case 'low':
      return `「${kw}」优先级较低,暂不主动投入资源,保留观察。`
  }
}

const plotted = computed<PlottedCluster[]>(() => {
  if (!result.value) return []
  const clusters = result.value.clusters || []
  if (!clusters.length) return []
  // 关注度归一化:size 取 0-100(以最大簇为 100)
  const maxSize = Math.max(...clusters.map(c => c.size), 1)
  return clusters.map(c => {
    const attention = Math.round((c.size / maxSize) * 100)
    // 负面强度:sentiment_score ∈ [-1, +1] → intensity ∈ [0, 100]
    // -1(最负面) → 100, 0 → 50, +1(最正面) → 0
    const intensity = Math.round((1 - (c.sentiment_score + 1) / 2) * 100)
    const quadrant = classifyQuadrant(attention, intensity)
    return {
      ...c,
      attention, intensity, quadrant,
      suggestion: buildSuggestion(c, quadrant),
    }
  })
})

// ECharts canvas 不解析 CSS 变量字符串,必须硬编码 hex,
// 否则 4 个象限的 itemStyle.color 全部 fallback 到 transparent,
// 气泡只剩白色描边,根本看不出象限差异。
// 与 src/style.css 里的 --c-* 保持同步。
const QUAD_COLORS: Record<PlottedCluster['quadrant'], string> = {
  urgent:  '#d97757',  // --c-rust   砖橘:必须立即解决
  amplify: '#84cc16',  // --c-moss   橄榄绿:可放大为卖点
  watch:   '#2dd4bf',  // --c-emerald 翡翠:监控预警
  low:     '#94a3a0',  // --text-muted 灰:低优先级
}

const chartOption = computed(() => {
  const data = plotted.value
  if (!data.length) return null

  // 按象限分组成 4 个 series,便于点击/筛选
  const buildSeries = (q: PlottedCluster['quadrant'], name: string) => ({
    name,
    type: 'scatter',
    symbolSize: (val: any) => {
      const c = data.find(d => d.attention === val[0] && d.intensity === val[1])
      return Math.max(14, Math.min(56, (c?.size || 1) * 0.6 + 14))
    },
    data: data.filter(c => c.quadrant === q).map(c => ({
      value: [c.attention, c.intensity],
      _cluster: c,
    })),
    itemStyle: {
      color: QUAD_COLORS[q],
      opacity: 0.85,
      borderColor: 'rgba(10, 22, 28, 0.85)',  // 暗色玻璃底色描边,贴底而不是 #fff 白边
      borderWidth: 1.5,
    },
    emphasis: { itemStyle: { opacity: 1, shadowBlur: 12, shadowColor: QUAD_COLORS[q] } },
  })

  return {
    grid: { left: 70, right: 50, top: 50, bottom: 60 },
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const c: PlottedCluster = p.data._cluster
        return `<div style="font-weight:600;margin-bottom:6px">${topicName(c)} · ${quadrantLabel(c.quadrant)}</div>
                关键词: ${c.keywords.slice(0,5).join('、')}<br/>
                规模: <b>${c.size}</b> 条 · 情感分 <b>${c.sentiment_score >= 0 ? '+' : ''}${c.sentiment_score.toFixed(2)}</b><br/>
                <span style="color:var(--text-muted);font-size:12px">点击查看代表评论与建议动作</span>`
      },
    },
    legend: {
      data: ['必须立即解决', '可放大为卖点', '监控预警', '低优先级'],
      top: 8, right: 10, icon: 'circle',
      textStyle: { color: '#cfe6e3', fontSize: 11 },
      inactiveColor: 'rgba(207, 230, 227, 0.32)',
    },
    xAxis: {
      name: '用户关注度 →', nameLocation: 'end', nameGap: 28,
      nameTextStyle: { color: '#9fb8b4', fontSize: 11 },
      type: 'value', min: 0, max: 100,
      axisLine: { lineStyle: { color: 'rgba(207, 230, 227, 0.18)' } },
      axisLabel: { formatter: (v: number) => `${v}`, color: '#9fb8b4', fontSize: 10 },
      splitLine: { show: true, lineStyle: { type: 'dashed', color: 'rgba(207, 230, 227, 0.08)' } },
    },
    yAxis: {
      name: '↑ 负面情绪强度', nameLocation: 'end', nameGap: 18,
      nameTextStyle: { color: '#9fb8b4', fontSize: 11 },
      type: 'value', min: 0, max: 100,
      axisLine: { lineStyle: { color: 'rgba(207, 230, 227, 0.18)' } },
      axisLabel: { formatter: (v: number) => `${v}`, color: '#9fb8b4', fontSize: 10 },
      splitLine: { show: true, lineStyle: { type: 'dashed', color: 'rgba(207, 230, 227, 0.08)' } },
    },
    // 四象限背景区(用 markArea 涂色)
    series: [
      {
        ...buildSeries('urgent', '必须立即解决'),
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(217, 119, 87, 0.08)' },  // rust 半透,贴 urgent 象限主色
          data: [[
            { coord: [QUAD_THRESHOLDS.attention, QUAD_THRESHOLDS.intensity] },
            { coord: [100, 100] },
          ]],
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: 'rgba(207, 230, 227, 0.28)', type: 'solid' },
          label: { color: '#9fb8b4', fontSize: 11 },
          data: [
            { xAxis: QUAD_THRESHOLDS.attention,
              label: { formatter: '关注阈值 50', position: 'end' } },
            { yAxis: QUAD_THRESHOLDS.intensity,
              label: { formatter: '情绪阈值 50', position: 'end' } },
          ],
        },
      },
      buildSeries('amplify', '可放大为卖点'),
      buildSeries('watch',   '监控预警'),
      buildSeries('low',     '低优先级'),
    ],
  }
})

async function loadMap(opts: { force?: boolean } = {}) {
  loading.value = true
  selected.value = null
  const cacheKey = `voc_clusters_${target.value}`
  // 命中 sessionStorage 缓存 → 秒出, 无 loading 抖动
  // 与 Dashboard 同款方案: 切回旧的对标车型不重新跑后端聚类
  if (!opts.force) {
    try {
      const raw = sessionStorage.getItem(cacheKey)
      if (raw) {
        const { ts, data } = JSON.parse(raw)
        if (Date.now() - ts < 10 * 60 * 1000) {  // 10 分钟内有效
          result.value = data
          loading.value = false
          nextTick(() => selectDefaultCluster())
          return
        }
      }
    } catch { /* 缓存损坏忽略 */ }
  }
  try {
    const { data } = await http.get('/data/voc/clusters', {
      params: { target: target.value },
    })
    result.value = data.data
    try { sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data: data.data })) } catch { /* 配额满忽略 */ }
    // 切换车型 / 刷新后也自动展开默认象限详情(原来只在 onMounted 调一次)
    nextTick(() => selectDefaultCluster())
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'VOC 聚类失败')
    result.value = null
  } finally {
    loading.value = false
  }
}

// 切换对标车型按钮 → 自动重新拉取(否则按钮看似无反应,需要再点"刷新"才生效)
watch(target, () => { loadMap() })

// 散点点击:从 series.data._cluster 直接拿到簇对象,展开下方话题详情。
// 同时把视图滚到详情卡,避免用户在长页面里"点了之后看不到反馈"。
function onChartClick(params: any) {
  const c = params?.data?._cluster as PlottedCluster | undefined
  if (!c) return
  selected.value = c
  nextTick(() => {
    document.querySelector('.detail-card')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  })
}

// 默认展示:进入页面或切换车型时,自动选最大的 urgent 簇
// (没有 urgent 则退化为整体最大簇),让用户一进来就看到一份样例详情。
function selectDefaultCluster() {
  const urgents = plotted.value.filter(c => c.quadrant === 'urgent')
  if (urgents.length) {
    selected.value = urgents.sort((a, b) => b.size - a.size)[0]
    return
  }
  selected.value = [...plotted.value].sort((a, b) => b.size - a.size)[0] || null
}

// 后台静默预热其它对标车型 (演示场景: 用户看 Model Y 时,
// 奔驰/AION V/全部 在 10s 内已写入 sessionStorage, 切换 0 等待)
async function prefetchOtherTargets() {
  const others = ['Model Y', '奔驰E级', 'AION V', 'all'].filter(t => t !== target.value)
  for (const t of others) {
    const cacheKey = `voc_clusters_${t}`
    try {
      const raw = sessionStorage.getItem(cacheKey)
      if (raw) {
        const { ts } = JSON.parse(raw)
        if (Date.now() - ts < 10 * 60 * 1000) continue  // 已有新鲜缓存, 跳过
      }
    } catch { /* 忽略 */ }
    try {
      const { data } = await http.get('/data/voc/clusters', { params: { target: t } })
      sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data: data.data }))
    } catch { /* 静默, 用户主动切再走真请求 */ }
  }
}

onMounted(async () => {
  await loadMap()
  // 用户首屏看到 Model Y 后, 后台串行预热其它 3 个车型
  // 串行而非并行, 避免后端聚类峰值打挂; 失败不影响主流程
  prefetchOtherTargets()
})
</script>

<style scoped>
.opportunity-map {
  padding-bottom: 80px;
}

.map-hero {
  text-align: center;
  padding: 24px 16px 28px;
  margin-bottom: 16px;
}
.hero-badge {
  display: inline-block;
  padding: 4px 12px;
  font-size: 11px;
  letter-spacing: 1.4px;
  background: rgba(45, 212, 191, 0.10);
  border: 1px solid rgba(45, 212, 191, 0.32);
  color: var(--c-emerald);
  border-radius: 999px;
  font-weight: 600;
  margin-bottom: 12px;
  text-transform: uppercase;
}
.hero-title {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 10px;
  letter-spacing: 0.6px;
}
.hero-title span {
  color: var(--c-emerald);
  font-style: italic;
}
.hero-desc {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 820px;
  margin: 0 auto;
  line-height: 1.7;
}

.map-card { border-radius: 12px; }
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.head-left { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.head-meta {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 400;
}
.head-right { display: flex; align-items: center; gap: 10px; }

.map-body { min-height: 540px; }

.quadrant-legend {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 16px;
  padding: 14px;
  background: rgba(180, 230, 225, 0.025);
  border-radius: 8px;
  font-size: 12.5px;
}
.quad-item {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.quad-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.q-urgent  .quad-dot { background: var(--c-rust); }
.q-amplify .quad-dot { background: var(--c-moss); }
.q-watch   .quad-dot { background: var(--c-emerald); }
.q-low     .quad-dot { background: var(--text-muted); }
.quad-item b { color: var(--text-primary); font-size: 13px; flex-shrink: 0; }
.quad-desc { color: var(--text-muted); font-size: 12px; }

.detail-card {
  margin-top: 16px;
  border-radius: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 18px;
}
.detail-section { display: flex; flex-direction: column; gap: 8px; }
.detail-full { grid-column: 1 / -1; }
.detail-title {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  font-weight: 600;
}
.detail-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.detail-stats {
  display: flex;
  gap: 18px;
  font-size: 14px;
  color: var(--text-secondary);
}
.detail-stats b { font-size: 18px; color: var(--text-primary); }
.sent-pos { color: var(--c-moss); font-weight: 600; }
.sent-neg { color: var(--c-rust); font-weight: 600; }
.sent-neutral { color: var(--text-muted); }
.detail-quotes {
  margin: 0; padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-quotes li {
  padding: 8px 12px;
  background: rgba(180, 230, 225, 0.025);
  border-left: 3px solid var(--border-line);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.detail-suggestion {
  margin: 0;
  padding: 12px 14px;
  background: rgba(45, 212, 191, 0.08);
  border-left: 3px solid var(--c-emerald);
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--c-emerald);
}

@media (max-width: 900px) {
  .quadrant-legend { grid-template-columns: repeat(2, 1fr); }
  .detail-grid { grid-template-columns: 1fr; }
}
</style>
