<template>
  <div class="home">
    <section class="command-hero">
      <div class="hero-media" aria-hidden="true">
        <img src="/assets/gpt-image2/cover-command-center.png" alt="" />
        <span class="hero-media-shade"></span>
        <span class="hero-scanline"></span>
      </div>

      <div class="hero-content">
        <h1 class="hero-title">点一下,让 AI 把经营问题讲清楚</h1>

        <div class="hero-actions">
          <button class="hero-btn hero-btn-primary" type="button" @click="startTask(taskTopics[0])">
            <span>启动综合诊断</span>
            <span class="btn-arrow">→</span>
          </button>
        </div>

        <div class="hero-metrics">
          <div v-for="s in impactStats" :key="s.label" class="metric-tile">
            <div class="metric-value">{{ s.value }}</div>
            <div class="metric-label">{{ s.label }}</div>
            <div class="metric-sub">{{ s.sub }}</div>
          </div>
        </div>

        <div class="hero-flowline" aria-label="Agent 分析流程">
          <span v-for="node in pipelineNodes" :key="node">{{ node }}</span>
        </div>
      </div>

      <aside class="hero-command-panel" aria-label="演示链路状态">
        <div class="panel-head">
          <span class="panel-title">Agent 作战雷达</span>
          <span class="panel-status">LIVE</span>
        </div>

        <div class="radar-wrap" aria-hidden="true">
          <div class="radar">
            <span class="radar-ring ring-1"></span>
            <span class="radar-ring ring-2"></span>
            <span class="radar-ring ring-3"></span>
            <span class="radar-sweep"></span>
            <span class="radar-core"></span>
            <span class="radar-node node-a"></span>
            <span class="radar-node node-b"></span>
            <span class="radar-node node-c"></span>
            <span class="radar-node node-d"></span>
          </div>
        </div>

      </aside>
    </section>

    <section class="task-stage">
      <header class="stage-head">
        <div>
          <div class="stage-eyebrow">Recommended Missions</div>
          <h2 class="stage-title">{{ greeting }} · 今天让 AI 先跑哪条业务线?</h2>
        </div>
        <div class="stage-meta">
          车型 <b>{{ mission.focusVehicle }}</b>
          <span></span>
          <b>{{ mission.period }}</b>
          <span></span>
          对标 <b>{{ mission.benchmarkVehicle }}</b>
        </div>
      </header>

      <div class="task-grid">
        <button
          v-for="t in taskTopics"
          :key="t.id"
          class="task-card"
          :class="`task-${t.kind}`"
          type="button"
          :title="t.fields"
          @click="startTask(t)"
        >
          <span class="task-icon">{{ t.icon }}</span>
          <span class="task-content">
            <span class="task-title">{{ t.title }}</span>
            <span class="task-desc">{{ t.desc }}</span>
          </span>
          <span class="task-signal">{{ t.signal }}</span>
          <span class="task-arrow">→</span>
        </button>

        <div class="task-card task-card-custom">
          <span class="task-icon">✦</span>
          <span class="task-content">
            <span class="task-title">自定义经营议题</span>
            <input
              v-model="customTopic"
              class="task-input"
              placeholder="例如: 高里程车型故障复盘"
              @keyup.enter="startCustom"
            />
          </span>
          <button
            class="task-launch"
            type="button"
            :disabled="!customTopic.trim()"
            @click.stop="startCustom"
          >
            启动
          </button>
        </div>
      </div>
    </section>

    <section class="recent-stage">
      <header class="stage-head compact">
        <div>
          <div class="stage-eyebrow">Briefing Library</div>
          <h2 class="stage-title">最近简报</h2>
        </div>
        <button v-if="recentReports.length" class="text-link" type="button" @click="goToReport">
          查看全部 →
        </button>
      </header>

      <div v-if="recentReports.length" class="recent-list">
        <button
          v-for="r in recentReports"
          :key="r.name"
          class="recent-row"
          type="button"
          @click="openReport(r)"
        >
          <span class="recent-mark">DOC</span>
          <span class="recent-name">{{ recentTitle(r) }}</span>
          <span class="recent-time">{{ formatTime(r.modified) }}</span>
          <span class="recent-go">查看</span>
        </button>
      </div>
      <div v-else class="recent-empty">
        还没有产出过简报。点击上方推荐任务,可以直接启动 AI 分析。
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'
import { useMissionStore } from '@/stores/mission'
import { listReports, type ReportItem } from '@/api/report'

const mission = useMissionStore()
const router = useRouter()

const reportItems = ref<ReportItem[]>([])
const customTopic = ref('')

interface TaskTopic {
  id: string
  kind: 'diagnose' | 'benchmark' | 'service' | 'voc'
  icon: string
  title: string
  desc: string
  signal: string
  topic: string
  fields: string
}

const pipelineNodes = ['数据感知', '双路分析', '合规审查', '简报合成', '视频发布']

const impactStats = computed(() => [
  {
    label: '主线数据池',
    value: `${mission.dataReady}/${mission.dataTotal || 4}`,
    sub: '销售 / 售后 / VOC / 基准',
  },
  {
    label: 'Agent 编排',
    value: '5 路',
    sub: '可观测、可追踪、可复盘',
  },
  {
    label: '演示产出',
    value: '3 分钟',
    sub: '简报 + PPTX + 业务视频',
  },
])

const taskTopics = computed<TaskTopic[]>(() => {
  const focus = mission.focusVehicle || 'eπ007'
  const bench = mission.benchmarkVehicle || 'Model Y'
  return [
    {
      id: 'monthly-review',
      kind: 'diagnose',
      icon: '01',
      title: '月度经营诊断',
      desc: '定位销量波动、渠道效率和售后异常,给出本月经营动作。',
      signal: '战略简报',
      topic: `${focus} 月度经营诊断,跨源联动销售/售后/口碑数据,识别业绩波动与服务异常`,
      fields: '使用字段:销售记录表(销售时间/销售门店/最终价格/活动id) + 维修记录表(维修日期/服务类型) + VOC评论',
    },
    {
      id: 'benchmark',
      kind: 'benchmark',
      icon: '02',
      title: '竞品对标分析',
      desc: `对比 ${bench} 的用户口碑、价格带和卖点差异。`,
      signal: 'VOC 对标',
      topic: `${focus} 与 ${bench} 竞品对标分析,基于 VOC 10万条评论提炼差异化卖点与共性痛点`,
      fields: `使用字段:voc_dongchedi(车系/内容/评论时间) + 车辆配置表(指导价/车型名称/动力类型/配置级别)`,
    },
    {
      id: 'service',
      kind: 'service',
      icon: '03',
      title: '服务网络复盘',
      desc: '识别高压门店、维修拥堵时段和服务类型偏移。',
      signal: '售后预警',
      topic: `${focus} 服务网络复盘,定位售后异常时段、维修门店分布与服务类型偏移`,
      fields: '使用字段:维修记录表 10000 条 (维修门店 4 家 / 维修日期 / 服务类型三类 / 维修总金额);高压=单店工单密度z-score,拥堵=日期3σ异常,偏移=三类占比时序漂移',
    },
    {
      id: 'voc',
      kind: 'voc',
      icon: '04',
      title: '口碑机会地图',
      desc: '从评论主题聚类中提炼营销话术、产品改进和销售抓手。',
      signal: '机会地图',
      topic: `${focus} VOC 机会地图,聚类用户评论主题,提炼高价值卖点、抱怨根因和下一步行动建议`,
      fields: '使用字段:voc_dongchedi 10万条(车系/标题/内容);TF-IDF 向量化 + KMeans/MiniBatchKMeans 聚类 + LLM 主题命名',
    },
  ]
})

const recentReports = computed(() => reportItems.value.slice(0, 3))

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '深夜好'
  if (h < 11) return '早上好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

function startTask(t: TaskTopic) {
  router.push({
    path: '/agent',
    query: { prompt: t.topic, autoStart: '1' },
  })
}

function startCustom() {
  const text = customTopic.value.trim()
  if (!text) return
  router.push({
    path: '/agent',
    query: { prompt: text, autoStart: '1' },
  })
}

function recentTitle(r: ReportItem) {
  const name = r.name.replace(/\.md$/i, '').replace(/-\d{10,}$/, '')
  const m = name.match(/^(\d{8}_\d{6})_(.+)$/)
  const reordered = m ? `${m[2]}_${m[1]}` : name
  return reordered || r.name
}

function formatTime(ts: number) {
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function openReport(r: ReportItem) {
  router.push({ path: '/report', query: { name: r.name } })
}

function goToReport() {
  router.push('/report')
}

async function loadDatasets() {
  try {
    const { data } = await http.get('/data/datasets')
    const datasets = data.data?.datasets || []
    mission.dataTotal = datasets.length || 4
    mission.dataReady = datasets.filter((d: any) => d.available).length
  } catch {
    // 静默,保留 mission store 默认值
  }
}

async function loadRecentReports() {
  try {
    const items = await listReports()
    reportItems.value = items
  } catch {
    /* ignore */
  }
}

onMounted(async () => {
  await Promise.all([loadDatasets(), loadRecentReports()])
})
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding-bottom: 42px;
}

.command-hero {
  position: relative;
  z-index: 0;
  isolation: isolate;
  min-height: 520px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  align-items: stretch;
  gap: 34px;
  padding: 52px 40px 44px;
  overflow: visible;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.command-hero::before {
  content: '';
  position: absolute;
  inset: -24px -34px -18px -34px;
  background:
    linear-gradient(90deg, rgba(5, 13, 17, 0.96) 0%, rgba(5, 13, 17, 0.78) 42%, rgba(5, 13, 17, 0.22) 100%),
    linear-gradient(180deg, rgba(5, 13, 17, 0.16) 0%, rgba(5, 13, 17, 0.72) 100%);
  mask-image: radial-gradient(ellipse at center, #000 0%, #000 62%, transparent 82%);
  z-index: 1;
}

.command-hero::after {
  content: '';
  position: absolute;
  inset: -24px -34px -18px -34px;
  background-image:
    linear-gradient(rgba(180, 230, 225, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(180, 230, 225, 0.035) 1px, transparent 1px);
  background-size: 52px 52px;
  mask-image: linear-gradient(90deg, rgba(0,0,0,0.78), rgba(0,0,0,0.10));
  z-index: 2;
  pointer-events: none;
}

.hero-media {
  position: absolute;
  inset: -24px -34px -18px -34px;
  z-index: 0;
  mask-image: radial-gradient(ellipse at center, #000 0%, #000 58%, transparent 82%);
}

.hero-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
  filter: saturate(1.08) contrast(1.08);
}

.hero-media-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.38));
}

.hero-scanline {
  position: absolute;
  left: 0;
  right: 0;
  top: 18%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.76), rgba(245, 158, 11, 0.45), transparent);
  animation: scanline 5.2s cubic-bezier(0.22, 1, 0.36, 1) infinite;
}

.hero-content,
.hero-command-panel {
  position: relative;
  z-index: 3;
}

.hero-content {
  align-self: center;
  max-width: 900px;
  padding-top: 0;
}

.hero-kicker,
.stage-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--c-mint);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-emerald);
  box-shadow: 0 0 0 5px rgba(45, 212, 191, 0.12), 0 0 18px rgba(45, 212, 191, 0.76);
  animation: live-pulse 1.8s ease-in-out infinite;
}

.hero-title {
  max-width: 760px;
  margin: 0;
  font-family: 'Source Han Serif SC', 'Noto Serif SC', 'Noto Serif CJK SC', 'Songti SC', 'STSong', serif;
  font-size: 58px;
  line-height: 1.08;
  font-weight: 700;
  letter-spacing: 0;
  color: #f2fffb;
  text-wrap: balance;
  text-shadow: 0 16px 40px rgba(0, 0, 0, 0.56);
}

.hero-copy {
  max-width: 620px;
  margin: 0;
  color: #d2e8e2;
  font-size: 18px;
  line-height: 1.65;
  letter-spacing: 0;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 34px;
}

.hero-btn {
  min-height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 0 28px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-family: inherit;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0;
  cursor: pointer;
  transition: transform .22s cubic-bezier(0.22, 1, 0.36, 1), box-shadow .22s, border-color .22s, background .22s;
}

.hero-btn-primary {
  color: #031416;
  background: linear-gradient(180deg, #63f5df 0%, #22c3b2 54%, #0e7c7b 100%);
  box-shadow:
    0 18px 38px rgba(45, 212, 191, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.34);
}

.hero-btn:hover {
  transform: translateY(-2px);
}

.hero-btn-primary:hover {
  box-shadow:
    0 22px 44px rgba(45, 212, 191, 0.46),
    inset 0 1px 0 rgba(255, 255, 255, 0.44);
}

.btn-arrow {
  font-size: 18px;
  line-height: 1;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 52px;
  max-width: 760px;
  margin-top: 44px;
  background: transparent;
  border: 0;
}

.metric-tile {
  min-height: 104px;
  padding: 12px 0;
  background: transparent;
  backdrop-filter: none;
}

.metric-tile + .metric-tile {
  padding-left: 0;
  border-left: 0;
}

.metric-value {
  color: #f6fffb;
  font-family: 'Source Han Serif SC', 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 34px;
  line-height: 1;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.metric-label {
  margin-top: 10px;
  color: var(--c-mint);
  font-size: 12px;
  font-weight: 700;
}

.metric-sub {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 11.5px;
  line-height: 1.45;
}

.hero-flowline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0;
  max-width: 760px;
  margin-top: 12px;
  padding-top: 0;
  border-top: 0;
  color: rgba(230, 241, 240, 0.70);
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0;
}

.hero-flowline span {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
}

.hero-flowline span + span::before {
  content: '';
  width: 1px;
  height: 13px;
  margin: 0 16px;
  background: rgba(78, 205, 196, 0.38);
}

.hero-command-panel {
  align-self: center;
  min-height: 300px;
  padding: 6px 0 0 10px;
  background: transparent;
  border: 0;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  opacity: 0.86;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  margin-bottom: 6px;
}

.panel-title {
  color: rgba(230, 241, 240, 0.82);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

.panel-status {
  padding: 2px 7px;
  border: 1px solid rgba(45, 212, 191, 0.24);
  color: rgba(78, 205, 196, 0.82);
  font-size: 10px;
  font-weight: 800;
}

.radar-wrap {
  display: grid;
  place-items: center;
  min-height: 140px;
  margin: 4px 0 12px;
}

.radar {
  position: relative;
  width: 126px;
  height: 126px;
  border-radius: 50%;
  background:
    linear-gradient(90deg, transparent calc(50% - 1px), rgba(45, 212, 191, 0.32) 50%, transparent calc(50% + 1px)),
    linear-gradient(0deg, transparent calc(50% - 1px), rgba(45, 212, 191, 0.22) 50%, transparent calc(50% + 1px));
}

.radar-ring,
.radar-core,
.radar-sweep,
.radar-node {
  position: absolute;
  display: block;
}

.radar-ring {
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(45, 212, 191, 0.22);
}

.ring-2 {
  inset: 22px;
  border-color: rgba(45, 212, 191, 0.34);
}

.ring-3 {
  inset: 44px;
  border-color: rgba(245, 158, 11, 0.30);
}

.radar-core {
  inset: 54px;
  border-radius: 50%;
  background: var(--c-emerald);
  box-shadow: 0 0 18px rgba(45, 212, 191, 0.62);
}

.radar-sweep {
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, rgba(45, 212, 191, 0.34), rgba(45, 212, 191, 0.05) 44deg, transparent 82deg);
  animation: radar-sweep 4.2s linear infinite;
}

.radar-node {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #f59e0b;
  box-shadow: 0 0 15px rgba(245, 158, 11, 0.72);
}

.node-a { top: 34px; left: 58px; }
.node-b { top: 41px; right: 22px; background: var(--c-mint); }
.node-c { bottom: 27px; left: 28px; background: var(--c-emerald); }
.node-d { bottom: 35px; right: 41px; }

.task-stage,
.recent-stage {
  position: relative;
  z-index: 2;
}

.stage-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
}

.stage-head.compact {
  align-items: center;
}

.stage-title {
  margin: 7px 0 0;
  color: var(--text-primary);
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 30px;
  line-height: 1.16;
  font-weight: 600;
  letter-spacing: 0;
}

.stage-meta {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  color: var(--text-muted);
  font-size: 12.5px;
}

.stage-meta span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(180, 230, 225, 0.26);
}

.stage-meta b {
  color: var(--c-mint);
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 14px;
  align-items: stretch;
}

.task-card {
  position: relative;
  isolation: isolate;
  min-height: 108px;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) auto 26px;
  align-items: center;
  gap: 16px;
  padding: 20px 22px;
  border: 0;
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(180, 230, 225, 0.055), transparent 34%),
    radial-gradient(560px 130px at -10% 52%, rgba(78, 205, 196, 0.13), transparent 58%),
    linear-gradient(118deg, rgba(12, 31, 34, 0.76), rgba(5, 16, 18, 0.68) 56%, rgba(4, 10, 13, 0.86));
  color: inherit;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  backdrop-filter: blur(14px);
  box-shadow:
    0 14px 32px rgba(0, 8, 12, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.055),
    inset 0 -1px 0 rgba(78, 205, 196, 0.05);
  transition: transform .22s cubic-bezier(0.22, 1, 0.36, 1), background .22s, box-shadow .22s;
}

.task-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 46%;
  background: linear-gradient(90deg, rgba(94, 234, 212, 0.115), transparent);
  opacity: 0.72;
  z-index: -1;
}

.task-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 38%, rgba(255, 255, 255, 0.105) 48%, transparent 58%);
  opacity: 0;
  transform: translateX(-130%);
  transition: opacity .22s, transform .5s cubic-bezier(0.22, 1, 0.36, 1);
  pointer-events: none;
}

.task-card:hover {
  transform: translateY(-3px);
  background:
    linear-gradient(135deg, rgba(180, 230, 225, 0.075), transparent 34%),
    radial-gradient(600px 140px at -10% 52%, rgba(78, 205, 196, 0.18), transparent 60%),
    linear-gradient(118deg, rgba(14, 39, 41, 0.82), rgba(5, 16, 18, 0.72) 56%, rgba(4, 10, 13, 0.90));
  box-shadow:
    0 22px 44px rgba(0, 8, 12, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.075),
    inset 0 -1px 0 rgba(78, 205, 196, 0.08);
}

.task-card:hover::after {
  opacity: 0.9;
  transform: translateX(130%);
}

.task-card:active {
  transform: translateY(-1px);
}

.task-card:focus-visible {
  outline: 2px solid rgba(94, 234, 212, 0.42);
  outline-offset: 3px;
}

.task-icon {
  position: relative;
  z-index: 1;
  width: 58px;
  height: 58px;
  display: inline-grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: rgba(94, 234, 212, 0.86);
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 34px;
  line-height: 1;
  font-weight: 650;
  letter-spacing: 0;
  text-shadow: 0 0 22px rgba(94, 234, 212, 0.24);
}

.task-content {
  position: relative;
  z-index: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.task-title {
  color: var(--text-primary);
  font-size: 16.8px;
  line-height: 1.25;
  font-weight: 760;
  letter-spacing: 0;
}

.task-desc {
  color: var(--text-muted);
  font-size: 12.5px;
  line-height: 1.58;
}

.task-signal {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0;
  border: 0;
  color: rgba(94, 234, 212, 0.76);
  background: transparent;
  font-size: 11.5px;
  font-weight: 700;
  white-space: nowrap;
}

.task-signal::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(94, 234, 212, 0.72);
  box-shadow: 0 0 12px rgba(94, 234, 212, 0.38);
}

.task-arrow {
  position: relative;
  z-index: 1;
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  color: rgba(94, 234, 212, 0.92);
  font-size: 18px;
  transition: transform .18s cubic-bezier(0.22, 1, 0.36, 1);
}

.task-card:hover .task-arrow {
  transform: translateX(4px);
}

.task-card-custom {
  grid-column: 1 / -1;
  min-height: 82px;
  cursor: default;
  grid-template-columns: 58px minmax(0, 1fr) auto;
  padding-block: 17px;
  padding-right: clamp(22px, 8vw, 112px);
  background:
    linear-gradient(90deg, rgba(78, 205, 196, 0.09), rgba(5, 16, 18, 0.58) 42%, rgba(5, 16, 18, 0.42)),
    linear-gradient(118deg, rgba(12, 31, 34, 0.62), rgba(4, 10, 13, 0.74));
}

.task-card-custom::before {
  width: 34%;
  opacity: 0.44;
}

.task-card-custom .task-icon {
  font-size: 25px;
}

.task-input {
  width: 100%;
  min-height: 32px;
  padding: 5px 0 7px;
  border: 0;
  border-bottom: 1px solid rgba(180, 230, 225, 0.14);
  border-radius: 0;
  color: var(--text-primary);
  background: transparent;
  outline: none;
  font-family: inherit;
  font-size: 13px;
}

.task-input::placeholder {
  color: var(--text-muted);
}

.task-input:focus {
  border-color: rgba(45, 212, 191, 0.56);
  box-shadow: none;
}

.task-launch {
  position: relative;
  z-index: 1;
  min-height: 36px;
  padding: 0 20px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(94, 234, 212, 0.92), rgba(31, 184, 169, 0.82));
  color: #062322;
  font-family: inherit;
  font-weight: 800;
  cursor: pointer;
  transition: all .18s cubic-bezier(0.22, 1, 0.36, 1);
}

.task-launch:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(125, 255, 235, 0.96), rgba(45, 212, 191, 0.88));
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(45, 212, 191, 0.18);
}

.task-launch:disabled {
  opacity: 0.38;
  cursor: not-allowed;
  filter: grayscale(0.4);
}

.text-link {
  border: 0;
  background: transparent;
  color: var(--c-mint);
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 800;
}

.recent-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid rgba(180, 230, 225, 0.10);
}

.recent-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) 96px 50px;
  gap: 14px;
  align-items: center;
  padding: 14px 4px;
  border: 0;
  border-bottom: 1px solid rgba(180, 230, 225, 0.10);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
}

.recent-row:hover {
  background: rgba(45, 212, 191, 0.035);
}

.recent-mark {
  color: var(--c-mint);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  font-weight: 800;
}

.recent-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
  font-size: 13.5px;
  font-weight: 650;
}

.recent-time {
  color: var(--text-muted);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11.5px;
  text-align: right;
}

.recent-go {
  color: var(--c-mint);
  font-size: 12px;
  font-weight: 750;
  text-align: right;
}

.recent-empty {
  padding: 22px;
  border: 1px dashed rgba(180, 230, 225, 0.18);
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
}

@keyframes live-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.58; transform: scale(0.82); }
}

@keyframes radar-sweep {
  to { transform: rotate(360deg); }
}

@keyframes scanline {
  0% { transform: translateY(-120px); opacity: 0; }
  15% { opacity: 1; }
  70% { opacity: 0.75; }
  100% { transform: translateY(420px); opacity: 0; }
}

@media (max-width: 1280px) {
  .command-hero {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .hero-content {
    padding-top: 44px;
  }

  .hero-title {
    font-size: 52px;
  }

  .hero-command-panel {
    min-height: 0;
  }

  .radar-wrap {
    min-height: 220px;
  }

}

@media (max-width: 980px) {
  .command-hero {
    padding: 30px;
  }

  .hero-title {
    font-size: 42px;
  }

  .hero-metrics,
  .task-grid {
    grid-template-columns: 1fr;
  }

}

@media (max-width: 680px) {
  .command-hero {
    padding: 24px 18px;
    border-left: 0;
    border-right: 0;
  }

  .hero-content {
    padding-top: 28px;
  }

  .hero-title {
    font-size: 34px;
  }

  .hero-copy {
    font-size: 14px;
  }

  .hero-actions,
  .stage-head {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-btn {
    width: 100%;
  }

  .task-card,
  .task-card-custom {
    grid-template-columns: 48px minmax(0, 1fr) 24px;
    gap: 10px 14px;
    padding-right: 20px;
  }

  .task-card:not(.task-card-custom) .task-icon {
    grid-row: 1 / 3;
  }

  .task-card:not(.task-card-custom) .task-content {
    grid-column: 2 / 4;
  }

  .task-signal,
  .task-arrow {
    grid-row: 2;
  }

  .task-signal {
    grid-column: 2;
    justify-self: start;
  }

  .task-arrow {
    grid-column: 3;
    justify-self: end;
  }

  .task-card-custom {
    grid-template-columns: 44px minmax(0, 1fr);
  }

  .task-launch {
    grid-column: 2;
    justify-self: start;
  }

  .recent-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .recent-time,
  .recent-go {
    text-align: left;
  }
}
</style>
