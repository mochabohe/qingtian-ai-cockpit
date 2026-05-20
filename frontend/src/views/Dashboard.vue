<template>
  <div class="dashboard">
    <div class="dashboard-head">
      <div>
        <h2 class="page-title">数据探索大屏</h2>
        <p class="page-subtitle">换数据集图表自动重组</p>
        <div class="dashboard-strip">
          <span class="strip-item">数据集 <b class="num">{{ datasets.length }}</b></span>
          <span class="strip-divider">·</span>
          <span class="strip-item">上传文件 <b class="num">{{ fileList.length }}</b></span>
          <span class="strip-divider">·</span>
          <span class="strip-item">最近刷新 <b class="num">{{ lastRefreshLabel }}</b></span>
          <span class="strip-divider">·</span>
          <span class="strip-item">系统 <b class="text-emerald">●</b> 在线</span>
        </div>
      </div>
      <div class="head-right">
        <el-select v-model="selected" placeholder="选择数据集" style="width: 320px" @change="onSelectChange" filterable>
          <el-option-group label="主线数据集" v-if="datasets.length">
            <el-option
              v-for="d in datasets"
              :key="`ds:${d.key}`"
              :label="`${d.name}${d.sheets?.length ? ' / ' + d.sheets[0] : ''}`"
              :value="`ds:${d.key}`"
              :disabled="!d.available"
            />
          </el-option-group>
          <el-option-group label="自定义上传" v-if="fileList.length">
            <el-option
              v-for="f in fileList"
              :key="`file:${f.name}`"
              :label="f.name"
              :value="`file:${f.name}`"
            />
          </el-option-group>
        </el-select>
        <el-select
          v-if="currentDsMeta && currentDsMeta.sheets && currentDsMeta.sheets.length > 1"
          v-model="sheet"
          style="width: 200px"
          @change="loadDashboard"
        >
          <el-option v-for="s in currentDsMeta.sheets" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button class="theme-refresh" :icon="RefreshRight" @click="loadDashboard({ force: true })" :loading="loading">刷新</el-button>
      </div>
    </div>

    <el-empty
      v-if="!selected"
      description="暂无选择 — 请从下拉选择主线数据集或自定义上传"
    />
    <el-skeleton v-else-if="loading" :rows="8" animated />
    <template v-else-if="data">
      <!-- KPI 卡片(schema 自适应:基础 4 卡 = 行数 / 列数 / 主指标合计 / 异常点数) -->
      <el-row :gutter="16" class="kpi-row">
        <el-col :span="6"><kpi-card title="总记录数" :value="fmtNum(data.kpi.n_rows)" :unit="'行'" color="var(--c-emerald)" /></el-col>
        <el-col :span="6"><kpi-card :title="kpiSecondary.label" :value="kpiSecondary.value" :unit="kpiSecondary.unit" color="var(--c-moss)" /></el-col>
        <el-col :span="6"><kpi-card :title="`类别字段(${data.category_col || '—'})`" :value="data.by_category?.categories?.length ?? 0" :unit="'个'" color="var(--c-emerald)" /></el-col>
        <el-col :span="6"><kpi-card title="3σ 异常点" :value="data.kpi.n_anomalies ?? 0" :unit="'个'" color="var(--c-rust)" /></el-col>
      </el-row>

      <!-- 图表区:每张卡片都是按需显示——无数据则整张卡片隐藏,避免空占位 -->
      <el-row :gutter="16" v-if="trendOption || pieOption">
        <el-col v-if="trendOption" :span="pieOption ? 14 : 24">
          <el-card class="chart-card">
            <template #header>
              <b>📈 {{ data.category_col || '类别' }} × {{ data.trend?.metric || '主指标' }} 周均时序 <span class="title-hint">· 默认显示均值 top 3 门店</span></b>
            </template>
            <e-chart :option="trendOption" height="320px" />
          </el-card>
        </el-col>
        <el-col v-if="pieOption" :span="trendOption ? 10 : 24">
          <el-card class="chart-card">
            <template #header>
              <b>🥧 各 {{ data.category_col || '类别' }} {{ pieMetricKey || '占比' }} 分布</b>
            </template>
            <e-chart :option="pieOption" height="320px" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" v-if="barOption || radarOption">
        <el-col v-if="barOption" :span="radarOption ? 12 : 24">
          <el-card class="chart-card">
            <template #header>
              <b>📊 各 {{ data.category_col || '类别' }} 多指标对比</b>
            </template>
            <e-chart :option="barOption" height="320px" />
          </el-card>
        </el-col>
        <el-col v-if="radarOption" :span="barOption ? 12 : 24">
          <el-card class="chart-card">
            <template #header><b>🎯 多维度雷达对比</b></template>
            <e-chart :option="radarOption" height="320px" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" v-if="heatmapOption || hasAnomalies">
        <el-col v-if="heatmapOption" :span="hasAnomalies ? 14 : 24">
          <el-card class="chart-card">
            <template #header><b>🌡 数值字段相关性热力图</b></template>
            <e-chart :option="heatmapOption" height="380px" />
          </el-card>
        </el-col>
        <el-col v-if="hasAnomalies" :span="heatmapOption ? 10 : 24">
          <el-card class="chart-card">
            <template #header><b>⚠️ 异常点扫描(3σ 检测)</b></template>
            <div class="anomaly-list">
              <div v-for="(info, col) in data.anomalies" :key="col" class="anomaly-row">
                <div class="anomaly-col">{{ col }}</div>
                <div class="anomaly-stat">
                  <el-tag type="danger" size="small">{{ info.n }} 个异常</el-tag>
                  <span class="anomaly-mean">均值 {{ fmtNum(info.mean) }} ± {{ fmtNum(info.std) }}</span>
                </div>
                <div v-if="info.examples?.length" class="anomaly-examples">
                  例: {{ info.examples.map(fmtNum).join(', ') }}
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 兜底提示:如果除 KPI 外什么图都没出来,告诉用户为什么 -->
      <el-alert
        v-if="!trendOption && !pieOption && !barOption && !radarOption && !heatmapOption && !hasAnomalies"
        type="info"
        :closable="false"
        show-icon
        title="该数据集字段较单一,可视化图表已隐藏"
        description="建议切换到「销售-车辆销售表」或「售后-车辆售后数据」查看完整图表(数值字段更丰富)。"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'
import { http } from '@/api/http'
import EChart from '@/components/EChart.vue'
import KpiCard from '@/components/KpiCard.vue'

const route = useRoute()

// 数据源选择策略:
//   selected = 'ds:<key>' → 主线数据集,走 /api/data/datasets/{key}/dashboard
//   selected = 'file:<filename>' → 上传文件,走 /api/data/dashboard/{filename}
const selected = ref('')
const sheet = ref<string | undefined>(undefined)

const datasets = ref<any[]>([])    // 主线数据集列表
const fileList = ref<any[]>([])    // 上传文件列表
const loading = ref(false)
const data = ref<any>(null)
const lastRefreshAt = ref<Date | null>(null)

const lastRefreshLabel = computed(() => {
  const d = lastRefreshAt.value
  if (!d) return '—'
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

// 当前主线数据集元(用于 sheet 二级下拉)
const currentDsMeta = computed(() => {
  if (!selected.value.startsWith('ds:')) return null
  const key = selected.value.slice(3)
  return datasets.value.find((d) => d.key === key) || null
})

// schema 自适应 KPI 第二张:优先金额合计,否则首个数值列均值
const kpiSecondary = computed(() => {
  const k = data.value?.kpi || {}
  // 沿用旧字段(自定义文件可能有 total_revenue / total_profit / avg_csat)
  if (k.total_revenue != null) return { label: '总营收(元)', value: fmtMoney(k.total_revenue), unit: '' }
  if (k.total_profit != null) return { label: '总利润(元)', value: fmtMoney(k.total_profit), unit: '' }
  if (k.avg_csat != null) return { label: '平均满意度', value: fmtNum(k.avg_csat), unit: '/100' }
  if (k.total_sales != null) return { label: '总销量', value: fmtNum(k.total_sales), unit: '' }
  // 主线数据集:从 by_category.metrics 第一个有意义的字段算合计
  const c = data.value?.by_category
  if (c?.metrics) {
    const keys = pickMeaningfulMetrics(c, 1)
    if (keys.length > 0) {
      const k0 = keys[0]
      const sum = (c.metrics[k0] as number[]).reduce((s, v) => s + (Number(v) || 0), 0)
      return { label: `${k0} 合计`, value: fmtMoney(sum), unit: '' }
    }
  }
  return { label: '总字段数', value: String(k.n_cols ?? 0), unit: '列' }
})

// 是否有异常点(用于决定异常卡片是否渲染)
const hasAnomalies = computed(() => {
  const a = data.value?.anomalies
  return !!a && Object.keys(a).length > 0
})

// ECharts 用 canvas 绘制,无法解析 CSS 变量字符串,必须硬编码 hex。
// 8 色 brand palette: 翡翠主调 + 砂金辅助,仅 amber/rust 用于跨主题强调,
// 避免出现糖果色拼盘(品红/紫/亮青)与暗色玻璃质感冲突。
const PALETTE = [
  '#2dd4bf', // emerald 主
  '#94d8d4', // sand 月白
  '#5eead4', // emerald light
  '#0e7c7b', // emerald deep
  '#f59e0b', // amber 强调
  '#d97757', // rust 警示
  '#84cc16', // moss
  '#38bdf8', // sky 辅助
]

async function loadDataSources() {
  try {
    const [{ data: dsRes }, { data: fRes }] = await Promise.all([
      http.get('/data/datasets'),
      http.get('/data/list'),
    ])
    datasets.value = dsRes.data?.datasets || []
    fileList.value = fRes.data || []
    // 优先读取 URL 参数:?key=<dataset-key>&sheet=<sheet-name> 或 ?file=<filename>
    const queryKey = typeof route.query.key === 'string' ? route.query.key : ''
    const queryFile = typeof route.query.file === 'string' ? route.query.file : ''
    const querySheet = typeof route.query.sheet === 'string' ? route.query.sheet : ''
    if (queryKey && datasets.value.find((d) => d.key === queryKey && d.available)) {
      selected.value = `ds:${queryKey}`
      const ds = datasets.value.find((d) => d.key === queryKey)
      sheet.value = querySheet || ds?.sheets?.[0]
      await loadDashboard()
      return
    }
    if (queryFile && fileList.value.find((f) => f.name === queryFile)) {
      selected.value = `file:${queryFile}`
      await loadDashboard()
      return
    }
    // 默认进入业务感最强的数据集(销售 → 售后 → 故障 → VOC)
    if (!selected.value) {
      const PREFERRED_KEYS = ['sales_records', 'aftersales_records', 'quality_fault_cases', 'voc_dongchedi']
      let preferred: typeof datasets.value[number] | undefined
      for (const k of PREFERRED_KEYS) {
        const ds = datasets.value.find((d) => d.key === k && d.available)
        if (ds) { preferred = ds; break }
      }
      const firstReady = preferred || datasets.value.find((d) => d.available)
      if (firstReady) {
        selected.value = `ds:${firstReady.key}`
        sheet.value = firstReady.sheets?.[0]
        await loadDashboard()
      } else if (fileList.value.length > 0) {
        selected.value = `file:${fileList.value[0].name}`
        await loadDashboard()
      }
    }
  } catch (e: any) {
    ElMessage.warning(e.message || '加载数据源失败')
  }
}

function onSelectChange(val: string) {
  if (val.startsWith('ds:')) {
    const key = val.slice(3)
    const ds = datasets.value.find((d) => d.key === key)
    sheet.value = ds?.sheets?.[0]
  } else {
    sheet.value = undefined
  }
  loadDashboard()
}

// 大屏 payload 在前端 sessionStorage 缓存,切走再回来瞬开。
// key 用 url 唯一标识,session 内有效;关浏览器/刷新自动失效。
// 后端 endpoint 已经按 (key, mtime/sheet) 做了 30min 缓存兜底,
// 前端这层只是减少一次网络往返带来的"切页等图"体感。
const SESSION_CACHE_PREFIX = 'dashboard:v1:'
const SESSION_CACHE_TTL_MS = 10 * 60 * 1000  // 10 分钟,演示场景够用

function readSessionCache(url: string): any | null {
  try {
    const raw = sessionStorage.getItem(SESSION_CACHE_PREFIX + url)
    if (!raw) return null
    const { ts, data } = JSON.parse(raw)
    if (Date.now() - ts > SESSION_CACHE_TTL_MS) {
      sessionStorage.removeItem(SESSION_CACHE_PREFIX + url)
      return null
    }
    return data
  } catch {
    return null
  }
}

function writeSessionCache(url: string, data: any) {
  try {
    sessionStorage.setItem(SESSION_CACHE_PREFIX + url, JSON.stringify({ ts: Date.now(), data }))
  } catch {
    // 配额满 / 隐身模式 → 静默降级
  }
}

async function loadDashboard(opts: { force?: boolean } = {}) {
  if (!selected.value) return
  let url: string
  if (selected.value.startsWith('ds:')) {
    const key = selected.value.slice(3)
    url = `/data/datasets/${encodeURIComponent(key)}/dashboard`
    if (sheet.value) url += `?sheet=${encodeURIComponent(sheet.value)}`
  } else {
    const filename = selected.value.slice(5)
    url = `/data/dashboard/${encodeURIComponent(filename)}`
  }

  // 命中前端缓存:不显示 loading,直接渲染
  if (!opts.force) {
    const cached = readSessionCache(url)
    if (cached) {
      data.value = cached
      lastRefreshAt.value = new Date()
      return
    }
  }

  loading.value = true
  data.value = null
  try {
    const { data: r } = await http.get(url)
    data.value = r.data
    writeSessionCache(url, r.data)
    lastRefreshAt.value = new Date()
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function fmtMoney(v: any) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + ' 万'
  return n.toFixed(0)
}

function fmtNum(v: any) {
  if (v == null) return '—'
  const n = Number(v)
  return Number.isInteger(n) ? n.toString() : n.toFixed(2)
}

// ========== ECharts Option 构造 ==========

// 时序图专用色板:emerald 单色系 8 档明度 ramp,代替 8 色拼盘。
// 同族色让"门店之间"读起来是结构对照,不是 8 个互斥实体厮杀。
const TREND_RAMP = [
  '#2dd4bf', '#5eead4', '#94d8d4', '#0e7c7b',
  '#22b8a0', '#7fdbc8', '#a7e7dd', '#0fa39c',
]

// ECharts 文字默认色在暗色玻璃底上太暗(灰蓝色 #6E7079),legend / axisLabel /
// 分页符全部接近不可见。统一用米白翡翠色 + legend 分页 icon 高亮。
const LEGEND_TEXT_COLOR = '#cfe6e3'
const LEGEND_INACTIVE_COLOR = 'rgba(207, 230, 227, 0.32)'
const AXIS_TEXT_COLOR = '#9fb8b4'
const AXIS_LINE_COLOR = 'rgba(207, 230, 227, 0.18)'
const SPLIT_LINE_COLOR = 'rgba(207, 230, 227, 0.06)'
const LEGEND_BASE = {
  textStyle: { color: LEGEND_TEXT_COLOR, fontSize: 11 },
  inactiveColor: LEGEND_INACTIVE_COLOR,
  pageIconColor: LEGEND_TEXT_COLOR,
  pageIconInactiveColor: LEGEND_INACTIVE_COLOR,
  pageTextStyle: { color: LEGEND_TEXT_COLOR },
}
const AXIS_LABEL_BASE = { color: AXIS_TEXT_COLOR, fontSize: 10 }

// 把日级时序按周聚合,365 点 → ~52 点,去掉日维度的高频噪声
function downsampleWeekly(dates: string[], values: number[]): { dates: string[]; values: number[] } {
  if (dates.length === 0 || dates.length !== values.length) return { dates, values }
  const outDates: string[] = []
  const outValues: number[] = []
  let bucket: number[] = []
  let bucketStart = ''
  for (let i = 0; i < dates.length; i++) {
    if (i % 7 === 0) {
      if (bucket.length) {
        outValues.push(bucket.reduce((s, v) => s + v, 0) / bucket.length)
        outDates.push(bucketStart)
      }
      bucket = []
      bucketStart = dates[i]
    }
    const v = Number(values[i])
    if (!Number.isNaN(v)) bucket.push(v)
  }
  if (bucket.length) {
    outValues.push(bucket.reduce((s, v) => s + v, 0) / bucket.length)
    outDates.push(bucketStart)
  }
  return { dates: outDates, values: outValues }
}

const trendOption = computed(() => {
  const t = data.value?.trend
  if (!t) return null
  // 默认只高亮前 3 条(数据均值最高的 3 个门店),其他 series 起始 hide
  const rankedIdx = t.series
    .map((s: any, i: number) => ({
      i,
      avg: (s.data || []).reduce((a: number, b: number) => a + (Number(b) || 0), 0) / Math.max(1, s.data.length),
    }))
    .sort((a: any, b: any) => b.avg - a.avg)
    .slice(0, 3)
    .map((x: any) => x.i)
  const topSet = new Set<number>(rankedIdx)
  // 周聚合后的统一 x 轴(用第一条 series 的聚合结果当 base)
  const firstAgg = t.series[0] ? downsampleWeekly(t.dates, t.series[0].data) : { dates: t.dates, values: [] }
  return {
    color: TREND_RAMP,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => Number(v).toLocaleString() },
    legend: {
      data: t.categories,
      top: 0,
      type: 'scroll',
      selected: t.categories.reduce((acc: Record<string, boolean>, name: string, i: number) => {
        acc[name] = topSet.has(i)
        return acc
      }, {}),
      ...LEGEND_BASE,
    },
    grid: { top: 40, left: 56, right: 18, bottom: 42 },
    xAxis: {
      type: 'category',
      data: firstAgg.dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
      axisLabel: AXIS_LABEL_BASE,
    },
    yAxis: {
      type: 'value',
      name: t.metric,
      nameTextStyle: AXIS_LABEL_BASE,
      axisLine: { show: false },
      axisLabel: AXIS_LABEL_BASE,
      splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
    },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 6, borderColor: 'transparent', backgroundColor: 'rgba(45, 212, 191, 0.04)', fillerColor: 'rgba(45, 212, 191, 0.18)' }],
    series: t.series.map((s: any, i: number) => {
      const agg = downsampleWeekly(t.dates, s.data)
      const isTop = topSet.has(i)
      return {
        name: s.name,
        type: 'line',
        data: agg.values,
        smooth: true,
        showSymbol: false,
        sampling: 'lttb',
        lineStyle: { width: isTop ? 1.6 : 1, opacity: isTop ? 0.95 : 0.5 },
        emphasis: { focus: 'series', lineStyle: { width: 2.4, opacity: 1 } },
      }
    }),
  }
})

// schema 自适应:从 metrics 里找出"有意义"的数值字段(全 0 / 全 NaN 跳过)
function pickMeaningfulMetrics(c: any, max = 2): string[] {
  if (!c?.metrics) return []
  const candidates = Object.keys(c.metrics).filter((k) => {
    const arr = c.metrics[k] as number[]
    if (!Array.isArray(arr) || arr.length === 0) return false
    const sum = arr.reduce((s, v) => s + (Number(v) || 0), 0)
    return sum !== 0
  })
  // 优先金额/计数类(常见汽车业务字段);其次按字段顺序
  const priority = candidates.sort((a, b) => {
    const score = (k: string) => {
      const cl = k.toLowerCase()
      if (cl.includes('金额') || cl.includes('amount') || cl.includes('revenue') || cl.includes('price')) return 0
      if (cl.includes('量') || cl.includes('count') || cl.includes('qty')) return 1
      return 2
    }
    return score(a) - score(b)
  })
  return priority.slice(0, max)
}

const pieMetricKey = computed(() => pickMeaningfulMetrics(data.value?.by_category, 1)[0] || null)
const barMetricKeys = computed(() => pickMeaningfulMetrics(data.value?.by_category, 2))

const pieOption = computed(() => {
  const c = data.value?.by_category
  const key = pieMetricKey.value
  if (!c || !key) return null
  return {
    color: PALETTE,
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    // 不显示 legend:每个扇区已用 {b}\n{d}% 外引线标注,
    // 右侧再列一遍 legend 是冗余信息,还会把饼图挤偏导致左侧 label 撞墙。
    legend: { show: false },
    series: [{
      type: 'pie',
      radius: ['44%', '72%'],
      center: ['50%', '52%'],
      avoidLabelOverlap: true,
      minAngle: 3,
      itemStyle: { borderRadius: 4, borderColor: '#0a161c', borderWidth: 2 },
      label: {
        formatter: '{b}\n{d}%',
        color: '#cfe6e3',
        fontSize: 11,
        lineHeight: 16,
      },
      labelLine: {
        length: 10,
        length2: 14,
        smooth: true,
      },
      data: c.categories.map((cat: string, i: number) => ({
        name: cat, value: c.metrics[key][i],
      })),
    }],
  }
})

const barOption = computed(() => {
  const c = data.value?.by_category
  const keys = barMetricKeys.value
  if (!c || keys.length === 0) return null
  return {
    color: ['#2dd4bf', '#94d8d4'],
    tooltip: { trigger: 'axis' },
    legend: { data: keys, top: 0, ...LEGEND_BASE },
    grid: { top: 36, left: 60, right: 16, bottom: 30 },
    xAxis: {
      type: 'category',
      data: c.categories,
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
      axisLabel: { ...AXIS_LABEL_BASE, interval: 0, rotate: 20 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: AXIS_LABEL_BASE,
      splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
    },
    series: keys.map((k) => ({ name: k, type: 'bar', data: c.metrics[k] })),
  }
})

const radarOption = computed(() => {
  const c = data.value?.by_category
  if (!c) return null
  // 选 4-5 个指标做雷达
  const candidates = ['sales_qty', 'revenue', 'profit', 'csat', 'inv_turnover']
  const indicators = candidates.filter(k => c.metrics[k])
  if (indicators.length < 3) return null
  // 各指标的 max（用于雷达 axis 上限）
  const maxes = indicators.map(k => Math.max(...c.metrics[k]))
  return {
    color: PALETTE,
    tooltip: {},
    legend: { data: c.categories, top: 0, type: 'scroll', ...LEGEND_BASE },
    radar: {
      indicator: indicators.map((k, i) => ({ name: k, max: maxes[i] * 1.1 })),
      radius: '62%',
      center: ['50%', '58%'],
      axisName: { color: AXIS_TEXT_COLOR, fontSize: 10 },
      splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
    },
    series: [{
      type: 'radar',
      data: c.categories.map((cat: string, i: number) => ({
        name: cat,
        value: indicators.map(k => c.metrics[k][i]),
      })),
    }],
  }
})

const heatmapOption = computed(() => {
  const m = data.value?.correlation
  if (!m) return null
  return {
    tooltip: {
      position: 'top',
      formatter: (p: any) => {
        const [x, y, v] = p.value
        return `${m.columns[y]} × ${m.columns[x]}<br/>相关系数: ${v}`
      },
    },
    grid: { top: 24, left: 100, right: 8, bottom: 100 },
    xAxis: {
      type: 'category',
      data: m.columns,
      splitArea: { show: true },
      axisLabel: { ...AXIS_LABEL_BASE, rotate: 35 },
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
    },
    yAxis: {
      type: 'category',
      data: m.columns,
      splitArea: { show: true },
      axisLabel: AXIS_LABEL_BASE,
      axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
    },
    visualMap: {
      min: -1, max: 1, calculable: true,
      orient: 'horizontal', left: 'center', bottom: 8,
      inRange: { color: ['#2dd4bf', '#0a161c', '#d97757'] },
      textStyle: { color: AXIS_TEXT_COLOR },
    },
    series: [{
      type: 'heatmap',
      data: m.cells,
      label: { show: true, fontSize: 10 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
    }],
  }
})

onMounted(loadDataSources)
</script>

<style scoped>
.dashboard-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.head-right { display: flex; gap: 8px; align-items: center; }
.page-title { margin: 0; color: var(--text-primary); font-weight: 600; }
.page-subtitle { margin: 6px 0 0; color: var(--text-muted); font-size: 13px; }

/* 顶部 mono 信息带 (Bloomberg Terminal 风) — 演示看板第一眼的"经营驾驶舱"质感 */
.dashboard-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 11.5px;
  color: var(--text-muted);
  letter-spacing: 0.4px;
}
.dashboard-strip .strip-item b {
  color: var(--text-primary);
  margin-left: 5px;
  font-weight: 600;
}
.dashboard-strip .strip-item b.text-emerald {
  color: var(--c-emerald);
  margin-left: 4px;
}
.dashboard-strip .strip-divider { color: var(--text-dim); opacity: 0.6; }

/* KPI 行去框化: 不堆 4 张卡, 改成横向 stat group, 用 hairline 分隔 */
.kpi-row {
  margin-bottom: 32px;
  padding: 18px 0;
  border-top: 1px solid var(--border-line);
  border-bottom: 1px solid var(--border-line);
  position: relative;
}
.kpi-row :deep(.kpi-card) {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  border-radius: 0 !important;
  padding: 4px 24px !important;
  position: relative;
}
.kpi-row :deep(.kpi-card)::before { display: none !important; }
/* 列间用细竖线分割 */
.kpi-row :deep(.el-col + .el-col .kpi-card)::after {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: var(--border-line);
}

/* 图表区去框化: 不画卡片外框, 只用大留白 + header 翡翠左条做章节区分 */
.chart-card { margin-bottom: 28px; }
.chart-card :deep(.el-card) {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
.chart-card :deep(.el-card)::before { display: none; }
.chart-card :deep(.el-card__header) {
  border-bottom: 0 !important;
  padding: 0 0 12px 14px !important;
  margin-bottom: 6px;
  position: relative;
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 19px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--text-primary);
}
.chart-card :deep(.el-card__header)::before {
  content: '';
  position: absolute;
  top: 4px;
  bottom: 16px;
  left: 0;
  width: 2px;
  background: var(--c-emerald);
  opacity: 0.7;
}
.chart-card :deep(.el-card__header) b {
  font-weight: inherit;
}
.title-hint {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.2px;
  margin-left: 4px;
}
.chart-card :deep(.el-card__body) {
  padding: 0 !important;
}

.anomaly-list { display: flex; flex-direction: column; gap: 8px; max-height: 380px; overflow: auto; padding-right: 4px; }
.anomaly-row {
  padding: 10px 12px;
  border-left: 2px solid rgba(217, 119, 87, 0.55);
  background: rgba(217, 119, 87, 0.06);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}
.anomaly-col { font-weight: 600; color: var(--c-rust); margin-bottom: 4px; letter-spacing: 0.3px; }
.anomaly-stat { display: flex; gap: 8px; align-items: center; }
.anomaly-mean { color: var(--text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.anomaly-examples { color: var(--text-muted); font-size: 12px; margin-top: 4px; font-variant-numeric: tabular-nums; }
</style>
