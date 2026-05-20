<template>
  <div class="agent-console">
    <!-- 背景装饰 -->
    <div class="page-bg-accent"></div>

    <!-- 经营任务单(P0-1):跨页面共享当前任务上下文 -->
    <MissionBar />

    <!-- Header: 工作流第 1 步入口 -->
    <header class="console-hero">
      <div class="hero-badge">第 1 步 · 启动分析</div>
      <h1 class="hero-title">启动 <span>经营分析</span></h1>
      <p class="hero-desc">输入分析主题,下方实时展示 Agent 工具调用与流式推理过程。</p>
      
      <div class="hero-input-bar" :class="{ 'is-running': store.isRunning }">
        <input
          v-model="topic"
          type="text"
          placeholder="例如：eπ007 综合经营诊断 / Model Y 口碑对标分析"
          :disabled="store.isRunning"
          @keyup.enter="startAnalysis"
        />
        <button v-if="!store.isRunning" class="launch-btn" :disabled="!topic.trim()" @click="startAnalysis">
          <span class="btn-text">{{ store.isRunning ? '编排运行中...' : '启动智擎分析' }}</span>
          <svg v-if="!store.isRunning" class="icon-launch" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          <div v-else class="loader-spinner"></div>
        </button>
        <button v-else class="stop-btn" type="button" @click="stopAnalysis">
          <span class="stop-icon" aria-hidden="true"></span>
          <span class="btn-text">停止分析</span>
        </button>
      </div>

      <!-- 快捷主题:一键填充 topic 输入框,避免演示时输入麻烦 -->
      <div class="quick-topics" v-if="!store.isRunning">
        <span class="quick-label">快捷主题:</span>
        <button
          v-for="t in quickTopics"
          :key="t"
          class="quick-chip"
          :class="{ active: topic === t }"
          @click="topic = t"
        >{{ t }}</button>
      </div>
      
      <div class="data-status" v-if="dataFiles.length">
        <span class="status-dot"></span> 
        <span class="status-text">底层数据池就绪：{{ dataFiles.map(f => f.name).join(', ') }}</span>
      </div>
    </header>

    <!-- Agent Flow -->
    <div class="agent-flow">
      <div 
        v-for="(agent, i) in definedAgents" 
        :key="i"
        class="agent-card"
        :class="getAgentState(i + 1)"
        :style="{ '--agent-order': i }"
      >
        <!-- Card Header -->
        <div class="agent-header">
          <div class="agent-index">{{ String(i + 1).padStart(2, '0') }}</div>
          <div class="agent-title-wrap">
            <h3 class="agent-title">{{ agent.name }}</h3>
            <div class="agent-subtitle">{{ agent.desc }}</div>
          </div>
          <div class="agent-status-badge">
            <span class="badge-dot"></span>
            {{ stateLabels[getAgentState(i + 1)] }}
          </div>
        </div>

        <!-- Card Body -->
        <div class="agent-body">
          <!-- Pending State -->
          <div v-if="getAgentState(i + 1) === 'pending'" class="state-pending">
            <div class="pending-illustration">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            </div>
            <ul class="capabilities">
              <li v-for="cap in agent.capabilities" :key="cap">{{ cap }}</li>
            </ul>
          </div>

          <!-- Running / Done State -->
          <div v-else class="state-active">
            <!-- Tool Use Visualization (配置驱动,三态变色) -->
            <div class="tool-use-track" v-if="agent.tools?.length">
              <div class="tool-label">智能体工具:</div>
              <div class="tool-tags">
                <span
                  v-for="t in agent.tools"
                  :key="t.key"
                  class="tool-tag"
                  :class="`tool-${getToolState(i + 1)}`"
                >
                  <span class="tool-dot"></span>
                  {{ t.label }}
                </span>
              </div>
            </div>

            <!-- Streaming Terminal -->
            <div class="terminal-window" v-if="getAgentState(i + 1) === 'running'">
              <pre>{{ getAgentOutput(i + 1) }}</pre>
              <div class="cursor"></div>
            </div>

            <!-- Structured Conclusion (Done State) -->
            <div class="structured-conclusion" v-if="getAgentState(i + 1) === 'done'">
              <StepConclusion :raw="getAgentOutput(i + 1)" />
            </div>

            <div class="error-msg" v-if="getAgentState(i + 1) === 'error' || getAgentState(i + 1) === 'stopped'">
              <span class="error-icon" aria-hidden="true">⚠</span>
              <span class="error-text">{{ getAgentOutput(i + 1) || (getAgentState(i + 1) === 'stopped' ? '分析已停止' : 'Agent 执行异常,请检查日志或网络连接。') }}</span>
              <button
                class="retry-btn"
                type="button"
                @click="startAnalysis"
                :disabled="store.isRunning"
                title="重新触发完整分析流程"
              >
                重试
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Final CTA Banner -->
    <transition name="fade-up">
      <div class="final-cta-wrap" v-if="store.finalReport">
        <div class="final-cta-box">
          <div class="cta-left">
            <div class="cta-icon">🎉</div>
            <div class="cta-text">
              <h3>简报合成完毕</h3>
              <p>结构化决策简报与可视化图表已就绪。</p>
            </div>
          </div>
          <div class="cta-right">
            <button class="btn-save" @click="saveCurrentReport">保存至简报库</button>
            <button class="btn-view" @click="goReport">查看完整战略简报</button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAgentStore } from '@/stores/agent'
import { useMissionStore } from '@/stores/mission'
import { streamAgentRun } from '@/api/agent'
import { http } from '@/api/http'
import { saveReport } from '@/api/report'
import StepConclusion from '@/components/agent/StepConclusion.vue'
import MissionBar from '@/components/MissionBar.vue'

const router = useRouter()
const route = useRoute()
const store = useAgentStore()
const mission = useMissionStore()

// topic 双向绑定到 mission store(全局共享)
const topic = computed({
  get: () => mission.topic,
  set: (v: string) => { mission.topic = v },
})
const dataFiles = ref<any[]>([])
const runAbortController = ref<AbortController | null>(null)
// 快捷主题:演示时一键切换分析角度,避免现场敲字
const quickTopics = [
  'eπ007 综合经营诊断',
  'eπ007 vs Model Y 口碑对标分析',
  '售后服务网络断层应急复盘',
]

// Agents Configuration Definition (5 step,顺序对齐 backend AGENT_DEFS)
interface AgentTool { key: string; label: string }
interface AgentDef {
  name: string
  icon: string
  iconKey: 'sensor' | 'analytics' | 'shield' | 'doc' | 'rocket'
  desc: string
  capabilities: string[]
  tools: AgentTool[]
}

const definedAgents: AgentDef[] = [
  {
    name: "数据感知 Agent",
    icon: "📡",
    iconKey: 'sensor',
    desc: "盘点数据源与跨源关联键",
    capabilities: ["主线 4 数据集元信息盘点", "字段角色自动识别(time/id/dim/metric/text)", "跨源关联键自动发现", "Schema 自适应兜底"],
    tools: [
      { key: 'inventory',      label: '数据盘点' },
      { key: 'schema_inspect', label: '字段识别' },
      { key: 'join_detect',    label: '关联键发现' },
    ],
  },
  {
    name: "双路分析 Agent",
    icon: "📊",
    iconKey: 'analytics',
    desc: "销售-售后联动 + VOC 主题聚类",
    capabilities: ["10万条销售 × 2万条售后跨源 join", "价格带与营销 ROI 分析", "时序异常检测 (3σ)", "VOC 10万条主题聚类 + 情感打分", "基于 RAG 384 条案例的故障根因挖掘"],
    tools: [
      { key: 'query_table',      label: '数据查询' },
      { key: 'align_id_columns', label: '主键对齐' },
      { key: 'anomaly_detect',   label: '异常检测' },
      { key: 'rag_search',       label: '故障检索' },
      { key: 'vector_cluster',   label: '语义聚类' },
      { key: 'sentiment_score',  label: '情感打分' },
    ],
  },
  {
    name: "合规审查 Agent",
    icon: "🛡️",
    iconKey: 'shield',
    desc: "敏感信息双层过滤",
    capabilities: ["7 类汽车敏感正则强制脱敏", "VIN / 车牌 / 客户姓名 / 精确金额", "LLM 语义级补充审查", "审计 ID + 脱敏明细"],
    tools: [
      { key: 'regex_scan', label: '本地正则脱敏' },
      { key: 'llm_audit',  label: 'LLM 语义审查' },
    ],
  },
  {
    name: "简报合成 Agent",
    icon: "📝",
    iconKey: 'doc',
    desc: "结构化战略简报",
    capabilities: ["双路结论模板装配", "封面 / 摘要 / 行动项结构化", "汽车经营文案润色", "高/中/低优先级行动建议"],
    tools: [
      { key: 'template_compose', label: '模板装配' },
      { key: 'llm_polish',       label: '文案润色' },
    ],
  },
  {
    name: "发布 + 视频 Agent",
    icon: "🚀",
    iconKey: 'rocket',
    desc: "飞书推送 + 业务视频脚本",
    capabilities: ["飞书群推送", "90 秒口播脚本切分", "数字人 / 自动剪辑接入位", "审计追溯链路"],
    tools: [
      { key: 'feishu_push',   label: '飞书推送' },
      { key: 'video_script',  label: '视频脚本生成' },
    ],
  },
]

const stateLabels: Record<string, string> = {
  pending: '待命',
  running: '执行中',
  done: '完成',
  error: '异常',
  stopped: '已停止'
}

function getAgentState(index: number): 'pending' | 'running' | 'done' | 'error' | 'stopped' {
  const step = store.steps.find(s => s.index === index)
  if (!step) return 'pending'
  return step.status
}

function getAgentOutput(index: number): string {
  const step = store.steps.find(s => s.index === index)
  return step?.output || ''
}

// 工具状态:pending(灰)/ active(running 时蓝色脉冲)/ done(绿色实色)
function getToolState(stepIndex: number): 'pending' | 'active' | 'done' {
  const state = getAgentState(stepIndex)
  if (state === 'running') return 'active'
  if (state === 'done') return 'done'
  return 'pending'
}

async function loadDataFiles() {
  try {
    // 用主线数据集接口(和 DataUpload / Home 一致),不要走 /data/list
    // ——后者返回的是用户自定义上传的文件,没传过文件就是空数组,
    // 会让 MissionBar 显示 "0 / 4 就绪" 但其实主线 4 份业务库快照都已就绪
    const { data } = await http.get('/data/datasets')
    const datasets = data.data?.datasets || []
    const ready = datasets.filter((d: any) => d.available)
    // dataFiles 用于本页面下方"底层数据池就绪"提示行,展示主线已就绪数据集名称
    dataFiles.value = ready.map((d: any) => ({ name: d.name }))
    mission.dataReady = ready.length
    mission.dataTotal = datasets.length || 4
  } catch {
    // ignore
  }
}

async function startAnalysis() {
  if (!topic.value.trim()) return

  runAbortController.value?.abort()
  const controller = new AbortController()
  runAbortController.value = controller
  
  store.reset()
  store.isRunning = true
  
  try {
    await streamAgentRun(
      { topic: topic.value },
      {
        onStart: (d) => {
          store.liveText = `编排开始：${d.topic}\n`
        },
        onDataLoaded: (d) => {
          store.dataLoaded = { file: d.file, rows: d.rows, cols: d.cols, summary: d.summary }
        },
        onStepStart: (d) => {
          store.steps.push({
            index: d.index, name: d.name, title: d.title, desc: d.desc,
            status: 'running', output: ''
          })
        },
        onAgentToken: (d) => {
          store.appendStepOutput(d.index, d.text)
        },
        onStepDone: (d) => {
          store.setStepDone(d.index, d.output)
        },
        onStepError: (d) => {
          store.setStepError(d.index, d.message)
        },
        onEnd: (d) => {
          store.finalReport = d.report || ''
          // 编排器 _save_report 已三写 md+json+trace.json,这里接住文件名供"保存"按钮复用,
          // 避免再调 /report/save 写出只有 md 的二次副本(丢失卡片+链路徽章)
          store.savedFilename = d.saved_as || ''
          if (store.savedFilename) {
            mission.briefFilename = store.savedFilename
          }
          ElMessage.success('智能简报生成完成')
        },
        onError: (msg) => {
          store.error = msg
          ElMessage.error(msg)
        }
      },
      controller.signal
    )
  } catch (e: any) {
    const stopped = controller.signal.aborted || e?.name === 'AbortError'
    if (stopped) {
      store.error = '分析已停止'
    } else {
      throw e
    }
  } finally {
    if (runAbortController.value === controller) {
      runAbortController.value = null
      store.isRunning = false
    }
  }
}

function stopAnalysis() {
  if (!store.isRunning) return

  const runningStep = store.steps.find(s => s.status === 'running')
  if (runningStep) {
    const stopText = runningStep.output ? `${runningStep.output}\n\n分析已停止` : '分析已停止'
    store.setStepStopped(runningStep.index, stopText)
  }

  store.error = '分析已停止'
  runAbortController.value?.abort()
  runAbortController.value = null
  store.isRunning = false
  ElMessage.info('已停止当前分析')
}

async function saveCurrentReport() {
  if (!store.finalReport) return
  // 编排器自动跑完时已经把 md+json+trace.json 三件套落盘了(saved_as)
  // 这里直接复用,不再二次调 /report/save —— 否则会写出一个只有 md 的副本,
  // 简报列表里就显示成普通 MD 而非"卡片+链路"
  if (store.savedFilename) {
    mission.briefFilename = store.savedFilename
    ElMessage.success('简报已保存到简报库')
    return
  }
  // 兜底:editor 手改 / 编排未返回 saved_as 时,旧逻辑保底,只写 md
  try {
    const filename = `${topic.value.replace(/[\\/:*?"<>|]/g, '-').trim() || 'briefing'}-${Date.now()}.md`
    await saveReport(topic.value, store.finalReport, filename)
    mission.briefFilename = filename
    ElMessage.success('简报已保存到简报库')
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

function goReport() {
  router.push('/report')
}

// Auto-scroll terminals
watch(() => store.steps.map(s => s.output), () => {
  nextTick(() => {
    const els = document.querySelectorAll('.terminal-window')
    els.forEach(el => {
      el.scrollTop = el.scrollHeight
    })
  })
}, { deep: true })

onMounted(() => {
  loadDataFiles()
  const rawPrompt = route.query.prompt
  if (typeof rawPrompt === 'string' && rawPrompt.trim()) {
    topic.value = rawPrompt.trim()
  }
  // autoStart=1: 来自任务台,自动启动一次,避免分析师再点一次启动按钮
  // 守护:不在运行中、有 topic、上一轮没产出 finalReport(避免热重载/回退误触)
  const autoStart = route.query.autoStart
  if (autoStart === '1' && topic.value.trim() && !store.isRunning && !store.finalReport) {
    nextTick(() => {
      startAnalysis()
    })
  }
})

onUnmounted(() => {
  runAbortController.value?.abort()
})
</script>

<style>
/* Global overrides for inner HTML parsed content */
.sc-h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--c-emerald);
  margin: 14px 0 8px;
  letter-spacing: 0.3px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(45, 212, 191, 0.18);
}
.sc-h4 {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--c-mint);
  margin: 12px 0 6px;
  letter-spacing: 0.2px;
}
.sc-strong { font-weight: 700; color: var(--c-emerald-light, #5eead4); }
.sc-ul { margin: 8px 0; padding-left: 18px; list-style-type: '— '; }
.sc-li {
  margin-bottom: 6px;
  color: var(--text-secondary);
  line-height: 1.65;
  font-size: 12.5px;
}
</style>

<style scoped>
.agent-console {
  min-height: 100%;
  position: relative;
  font-family: system-ui, -apple-system, sans-serif;
  padding-bottom: 120px; /* Space for bottom CTA */
}

/* Background accents for a tech vibe */
.page-bg-accent {
  position: absolute;
  top: -100px;
  right: -100px;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.06) 0%, transparent 70%);
  z-index: 0;
  pointer-events: none;
}

/* Header Area:左对齐 hero,跟下方 grid 边缘对齐 */
.console-hero {
  position: relative;
  z-index: 1;
  padding: 30px 32px 28px;
  border-radius: 18px;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  backdrop-filter: blur(18px) saturate(120%);
  -webkit-backdrop-filter: blur(18px) saturate(120%);
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
  margin-bottom: 24px;
  overflow: hidden;
}
.console-hero::before {
  content: '';
  position: absolute;
  top: 0;
  left: 32px;
  right: 32px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.6), transparent);
  pointer-events: none;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: rgba(45, 212, 191, 0.10);
  color: var(--c-emerald);
  border: 1px solid rgba(45, 212, 191, 0.32);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  margin-bottom: 14px;
}

.hero-title {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 10px;
  letter-spacing: 0.6px;
  line-height: 1.15;
}

.hero-title span {
  color: var(--c-emerald);
  font-style: italic;
  -webkit-text-fill-color: var(--c-emerald);
}

.hero-desc {
  font-size: 13.5px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0 0 22px;
  max-width: 760px;
  letter-spacing: 0.2px;
}

/* Hero Input Bar */
.hero-input-bar {
  display: flex;
  background: rgba(5, 13, 17, 0.6);
  border: 1px solid var(--border-line);
  border-radius: 12px;
  padding: 6px;
  transition: all 0.18s ease;
  max-width: 880px;
}

.hero-input-bar:focus-within {
  border-color: var(--c-emerald);
  box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.12);
}

.hero-input-bar.is-running {
  border-color: rgba(45, 212, 191, 0.4);
  background: rgba(45, 212, 191, 0.04);
}

.hero-input-bar input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0 16px;
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  font-family: inherit;
}

.hero-input-bar input::placeholder {
  color: var(--text-muted);
}

.launch-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(180deg, #2dd4bf 0%, #0e7c7b 100%);
  color: #ffffff;
  border: 0;
  padding: 0 24px;
  height: 42px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  text-shadow: 0 1px 2px rgba(4, 22, 26, 0.35);
  box-shadow:
    0 4px 14px rgba(45, 212, 191, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.launch-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.08);
  box-shadow: 0 8px 22px rgba(45, 212, 191, 0.42);
}

.launch-btn:disabled {
  background: rgba(180, 230, 225, 0.06);
  color: var(--text-muted);
  cursor: not-allowed;
  box-shadow: none;
}

.stop-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 42px;
  padding: 0 22px;
  border-radius: 9px;
  border: 1px solid rgba(217, 119, 87, 0.58);
  background: rgba(217, 119, 87, 0.14);
  color: #f5b69c;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  cursor: pointer;
  box-shadow:
    0 4px 14px rgba(217, 119, 87, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  transition: all 0.15s;
}

.stop-btn:hover {
  transform: translateY(-1px);
  background: rgba(217, 119, 87, 0.22);
  border-color: rgba(245, 182, 156, 0.72);
  box-shadow: 0 8px 22px rgba(217, 119, 87, 0.26);
}

.stop-icon {
  width: 11px;
  height: 11px;
  border-radius: 3px;
  background: currentColor;
  box-shadow: 0 0 10px rgba(245, 182, 156, 0.42);
}

.icon-launch {
  width: 16px;
  height: 16px;
}

.loader-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: #ffffff;
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.data-status {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.3px;
}
.data-status .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-emerald);
  box-shadow: 0 0 8px var(--c-emerald);
}

/* 极简配置 chip */
.hero-config {
  margin-top: 18px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}
.config-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12.5px;
}
.chip-label {
  color: var(--text-muted);
  font-weight: 500;
}
.chip-value {
  color: var(--text-primary);
  font-weight: 600;
}
.chip-select {
  appearance: none;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-weight: 600;
  font-size: 12.5px;
  cursor: pointer;
  padding: 2px 18px 2px 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6' fill='none'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2364748b' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0 center;
}
.chip-select:hover {
  color: var(--c-emerald);
}

/* 快捷主题 */
.quick-topics {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  align-items: center;
}
.quick-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-right: 4px;
}
.quick-chip {
  padding: 6px 14px;
  background: rgba(180, 230, 225, 0.04);
  border: 1px solid var(--border-line);
  border-radius: 999px;
  font-size: 12.5px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all .15s;
}
.quick-chip:hover {
  border-color: #93c5fd;
  background: rgba(45, 212, 191, 0.08);
  color: var(--c-emerald);
}
.quick-chip.active {
  background: rgba(45, 212, 191, 0.06);
  border-color: var(--c-emerald);
  color: var(--c-emerald-deep);
  font-weight: 600;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: var(--c-moss);
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}

/* Agent Flow Grid (3 业务 Agent · 5 步执行,响应式)
   1680+ → 5 列 / 1200~1680 → 3+2 / 768~1200 → 2 列 / 移动端 → 1 列 */
.agent-flow {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 18px;
  margin-top: 8px;
}

@media (max-width: 1599px) {
  .agent-flow { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 1199px) {
  .agent-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 767px) {
  .agent-flow { grid-template-columns: 1fr; }
}

.agent-card {
  position: relative;
  background: var(--bg-glass);
  border-radius: 14px;
  border: 1px solid var(--border-line);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  min-height: 420px;
}
/* 顶部翡翠 hairline */
.agent-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 16px;
  right: 16px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.4), transparent);
  opacity: 0.5;
  transition: opacity .3s ease;
  pointer-events: none;
}

/* States styling */
.agent-card.pending {
  background: rgba(180, 230, 225, 0.025);
  border-color: var(--border-subtle);
  opacity: 0.55;
  filter: grayscale(0.4);
}
.agent-card.pending::before { opacity: 0.18; }
.agent-card.pending .badge-dot { background: var(--text-dim); }

.agent-card.running {
  border-color: rgba(45, 212, 191, 0.78);
  box-shadow:
    0 14px 32px rgba(45, 212, 191, 0.28),
    0 0 0 2px rgba(45, 212, 191, 0.18);
  transform: translateY(-3px);
}
.agent-card.running::before {
  /* 流光 hairline (强化"在跑"的状态感) */
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(45, 212, 191, 0.85) 50%,
    transparent 100%);
  background-size: 200% 100%;
  animation: agent-running-shimmer 1.6s ease-in-out infinite;
  opacity: 1;
}
@keyframes agent-running-shimmer {
  0%   { background-position: 0 0, 160% 0, 0 0; }
  100% { background-position: 0 0, -160% 0, 0 0; }
}
.agent-card.running .badge-dot {
  background: var(--c-emerald);
  animation: pulse-dot 1.5s infinite;
}
.agent-card.running .agent-status-badge {
  color: var(--c-emerald);
  background: rgba(45, 212, 191, 0.10);
}

.agent-card.done {
  border-color: rgba(132, 204, 22, 0.65);
  box-shadow: 0 14px 32px rgba(132, 204, 22, 0.18);
}
.agent-card.done::before {
  background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.65), transparent);
  opacity: 1;
}
.agent-card.done .badge-dot { background: var(--c-moss); }
.agent-card.done .agent-status-badge {
  color: var(--c-moss);
  background: rgba(132, 204, 22, 0.08);
}

/* 失败态: 砖橘边框 + 红橘阴影, 与 done 区别开 */
.agent-card.error {
  border-color: rgba(217, 119, 87, 0.65);
  box-shadow: 0 14px 32px rgba(217, 119, 87, 0.18);
}
.agent-card.error::before {
  background: linear-gradient(90deg, transparent, rgba(217, 119, 87, 0.6), transparent);
  opacity: 1;
}
.agent-card.error .badge-dot { background: var(--c-rust); }
.agent-card.error .agent-status-badge {
  color: var(--c-rust);
  background: rgba(217, 119, 87, 0.10);
}

.agent-card.stopped {
  border-color: rgba(217, 119, 87, 0.55);
  box-shadow: 0 14px 32px rgba(217, 119, 87, 0.12);
}
.agent-card.stopped::before {
  background: linear-gradient(90deg, transparent, rgba(217, 119, 87, 0.48), transparent);
  opacity: 1;
}
.agent-card.stopped .badge-dot { background: var(--c-rust); }
.agent-card.stopped .agent-status-badge {
  color: var(--c-rust);
  background: rgba(217, 119, 87, 0.10);
}

@keyframes pulse-dot {
  0%   { box-shadow: 0 0 0 0 rgba(45, 212, 191, 0.55); }
  70%  { box-shadow: 0 0 0 6px rgba(45, 212, 191, 0); }
  100% { box-shadow: 0 0 0 0 rgba(45, 212, 191, 0); }
}

/* Card Header */
.agent-header {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(180, 230, 225, 0.04);
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(180, 230, 225, 0.04);
}

.agent-icon {
  position: relative;
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.14) 0%, rgba(14, 124, 123, 0.06) 100%);
  border: 1px solid rgba(45, 212, 191, 0.28);
  color: var(--c-emerald);
  border-radius: 10px;
  flex-shrink: 0;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 4px 12px rgba(0, 8, 12, 0.25);
}
.agent-icon svg {
  width: 20px;
  height: 20px;
  filter: drop-shadow(0 0 5px currentColor);
  opacity: 0.95;
}

.agent-title-wrap {
  flex: 1;
  min-width: 0;
}

.agent-title {
  margin: 0 0 2px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}

.agent-subtitle {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.3;
}

.agent-status-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 12px;
  background: rgba(180, 230, 225, 0.03);
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}
.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

/* Card Body */
.agent-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  background: rgba(180, 230, 225, 0.025);
}

/* Pending State View */
.state-pending {
  padding: 16px 16px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  color: var(--text-muted);
}

.pending-illustration {
  margin: 4px 0 14px;
  opacity: 0.4;
  transform: scale(0.7);
}

.capabilities {
  list-style: none;
  padding: 0;
  margin: 0;
  width: 100%;
}

.capabilities li {
  padding: 9px 14px;
  background: rgba(45, 212, 191, 0.10);
  border: 1px solid rgba(45, 212, 191, 0.30);
  border-radius: 8px;
  margin-bottom: 7px;
  font-size: 12.5px;
  line-height: 1.5;
  color: #e6faf5;
  text-align: center;
  letter-spacing: 0.3px;
  font-weight: 500;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

/* Active State View */
.state-active {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tool-use-track {
  padding: 16px 24px;
  background: rgba(180, 230, 225, 0.04);
  border-bottom: 1px solid var(--border-line);
}

.tool-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.tool-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  border: 1px solid transparent;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.tool-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  display: inline-block;
}

/* 三态:pending(虚线灰)/ active(翡翠脉冲)/ done(橄榄绿实色) */
.tool-tag.tool-pending {
  background: rgba(180, 230, 225, 0.04);
  color: var(--text-secondary);
  border: 1px dashed rgba(180, 230, 225, 0.18);
  opacity: 0.7;
}

.tool-tag.tool-active {
  background: rgba(45, 212, 191, 0.10);
  color: var(--c-emerald);
  border: 1px solid rgba(45, 212, 191, 0.45);
}
.tool-tag.tool-active .tool-dot {
  animation: tool-pulse 1.4s infinite;
}

.tool-tag.tool-done {
  background: rgba(132, 204, 22, 0.08);
  color: var(--c-moss);
  border-color: rgba(132, 204, 22, 0.40);
}
.tool-tag.tool-done::before {
  content: '✓';
  font-size: 11px;
  font-weight: 700;
  margin-right: -2px;
}
.tool-tag.tool-done .tool-dot {
  display: none;
}

@keyframes tool-pulse {
  0% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.5); }
  70% { box-shadow: 0 0 0 5px rgba(37, 99, 235, 0); }
  100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
}

/* Terminal View */
.terminal-window {
  flex: 1;
  background: rgba(2, 8, 12, 0.78);
  border-top: 1px solid rgba(45, 212, 191, 0.18);
  padding: 20px 24px;
  overflow-y: auto;
  max-height: 400px;
  position: relative;
}

.terminal-window pre {
  margin: 0;
  color: #5eead4;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  text-shadow: 0 0 6px rgba(45, 212, 191, 0.22);
}

.cursor {
  display: inline-block;
  width: 8px;
  height: 15px;
  background: #5eead4;
  vertical-align: middle;
  animation: blink 1s step-end infinite;
  margin-left: 2px;
  box-shadow: 0 0 6px rgba(45, 212, 191, 0.45);
}

@keyframes blink {
  50% { opacity: 0; }
}

/* Structured Conclusion (Done state) */
.structured-conclusion {
  flex: 1;
  background: rgba(180, 230, 225, 0.04);
  padding: 24px;
  overflow-y: auto;
  max-height: 400px;
}

.conclusion-content {
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
}

.error-msg {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin: 12px 16px 16px;
  background: rgba(217, 119, 87, 0.10);
  border: 1px solid rgba(217, 119, 87, 0.32);
  border-radius: var(--r-sm);
  color: var(--c-rust);
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.55;
}
.error-msg .error-icon {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(217, 119, 87, 0.20);
  border: 1px solid rgba(217, 119, 87, 0.42);
  font-size: 13px;
}
.error-msg .error-text {
  flex: 1;
  word-break: break-word;
}
.error-msg .retry-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  border-radius: var(--r-sm);
  background: rgba(217, 119, 87, 0.18);
  border: 1px solid rgba(217, 119, 87, 0.45);
  color: var(--c-rust);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.4px;
  cursor: pointer;
  transition: all var(--t-fast);
}
.error-msg .retry-btn:hover:not(:disabled) {
  background: rgba(217, 119, 87, 0.28);
  border-color: var(--c-rust);
  color: #f5b69c;
}
.error-msg .retry-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Premium orchestration pass: 首页定稿后,分析页用更轻的任务编排语言承接主视觉 */
.agent-console {
  font-family: 'Avenir Next', 'Source Han Sans SC', system-ui, -apple-system, sans-serif;
}

.page-bg-accent {
  top: -90px;
  right: -80px;
  width: 620px;
  height: 620px;
  background:
    radial-gradient(circle at 44% 36%, rgba(45, 212, 191, 0.10) 0%, transparent 42%),
    radial-gradient(circle at 76% 68%, rgba(132, 204, 22, 0.045) 0%, transparent 48%);
}

.console-hero {
  padding: 30px 34px 26px;
  border: 0;
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(180, 230, 225, 0.06), transparent 32%),
    linear-gradient(105deg, rgba(10, 29, 32, 0.78), rgba(4, 14, 17, 0.58));
  box-shadow:
    0 18px 42px rgba(0, 8, 12, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.055),
    inset 0 -1px 0 rgba(78, 205, 196, 0.05);
  margin-bottom: 16px;
}

.console-hero::before {
  top: 22px;
  left: 0;
  right: auto;
  bottom: 22px;
  width: 3px;
  height: auto;
  background: linear-gradient(180deg, rgba(94, 234, 212, 0.92), rgba(94, 234, 212, 0.10));
}

.hero-badge {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: rgba(94, 234, 212, 0.88);
  font-weight: 800;
  margin-bottom: 12px;
}

.hero-title {
  font-size: 34px;
  letter-spacing: 0;
}

.hero-input-bar {
  max-width: 920px;
  border-color: rgba(180, 230, 225, 0.10);
  border-radius: 10px;
  background: rgba(5, 13, 17, 0.68);
}

.launch-btn {
  background: linear-gradient(180deg, #5eead4 0%, #1fb8a9 100%);
  color: #04211f;
  text-shadow: none;
}

.quick-topics {
  justify-content: flex-start;
}

.quick-chip {
  border: 0;
  border-radius: 7px;
  background: rgba(180, 230, 225, 0.035);
}

.quick-chip.active {
  background: rgba(45, 212, 191, 0.12);
  color: var(--c-mint);
}

.agent-flow {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.agent-card {
  isolation: isolate;
  min-height: 350px;
  overflow: visible;
  border: 0;
  border-radius: 10px;
  background:
    linear-gradient(145deg, rgba(180, 230, 225, 0.050), transparent 38%),
    linear-gradient(180deg, rgba(8, 24, 27, 0.74), rgba(4, 12, 15, 0.56));
  box-shadow:
    0 14px 32px rgba(0, 8, 12, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.045),
    inset 0 -1px 0 rgba(78, 205, 196, 0.04);
  animation: agent-card-in .56s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: calc(var(--agent-order) * 45ms);
}

@media (min-width: 1280px) {
  .agent-flow::before {
    content: '';
    position: absolute;
    left: 24px;
    right: 24px;
    top: 47px;
    height: 1px;
    background: linear-gradient(90deg, rgba(94, 234, 212, 0.22), rgba(94, 234, 212, 0.06));
    pointer-events: none;
  }

  .agent-card {
    z-index: 1;
  }

  .agent-card:not(:last-child)::after {
    content: '→';
    position: absolute;
    top: 33px;
    right: -13px;
    z-index: 3;
    width: 24px;
    height: 24px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: rgba(5, 16, 18, 0.92);
    color: rgba(94, 234, 212, 0.80);
    font-size: 15px;
    font-weight: 800;
    box-shadow: 0 0 0 1px rgba(94, 234, 212, 0.18), 0 0 18px rgba(94, 234, 212, 0.12);
  }
}

@keyframes agent-card-in {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}

.agent-card::before {
  inset: 0;
  right: 0;
  width: auto;
  height: auto;
  border-radius: inherit;
  background:
    linear-gradient(118deg, rgba(160, 216, 205, 0.026), rgba(160, 216, 205, 0.010) 52%, rgba(160, 216, 205, 0.018)),
    radial-gradient(110% 80% at 18% 18%, rgba(118, 199, 186, 0.038), transparent 62%);
  opacity: 0.44;
  z-index: 0;
}

.agent-card.running::before {
  background:
    linear-gradient(118deg, rgba(128, 210, 198, 0.034), rgba(128, 210, 198, 0.014) 45%, rgba(128, 210, 198, 0.028)),
    linear-gradient(100deg, transparent 0%, rgba(180, 230, 225, 0.000) 26%, rgba(180, 230, 225, 0.052) 49%, rgba(180, 230, 225, 0.000) 72%, transparent 100%),
    radial-gradient(105% 84% at 22% 14%, rgba(94, 184, 176, 0.050), transparent 68%);
  background-size: 100% 100%, 260% 100%, 100% 100%;
  animation: agent-running-shimmer 3.4s cubic-bezier(0.25, 1, 0.5, 1) infinite;
  opacity: 0.58;
}

.agent-card.done::before {
  background:
    linear-gradient(118deg, rgba(152, 190, 142, 0.032), rgba(114, 178, 166, 0.016) 48%, rgba(152, 190, 142, 0.024)),
    radial-gradient(105% 82% at 18% 14%, rgba(152, 190, 142, 0.040), transparent 70%);
  opacity: 0.48;
}

.agent-card.error::before {
  background:
    linear-gradient(118deg, rgba(194, 128, 104, 0.044), rgba(194, 128, 104, 0.014) 54%, rgba(194, 128, 104, 0.026)),
    radial-gradient(105% 82% at 18% 14%, rgba(194, 128, 104, 0.048), transparent 70%);
  opacity: 0.52;
}

.agent-card.stopped::before {
  background:
    linear-gradient(118deg, rgba(194, 128, 104, 0.038), rgba(194, 128, 104, 0.012) 54%, rgba(194, 128, 104, 0.022)),
    radial-gradient(105% 82% at 18% 14%, rgba(194, 128, 104, 0.040), transparent 70%);
  opacity: 0.48;
}

.agent-header,
.agent-body {
  position: relative;
  z-index: 1;
}

.agent-card.pending {
  background:
    linear-gradient(180deg, rgba(180, 230, 225, 0.030), rgba(4, 12, 15, 0.48));
  opacity: 0.72;
  filter: grayscale(0.18);
}

.agent-card.running {
  border-color: transparent;
  box-shadow:
    0 18px 40px rgba(0, 8, 12, 0.34),
    0 0 0 1px rgba(45, 212, 191, 0.26),
    inset 0 1px 0 rgba(255, 255, 255, 0.075);
}

.agent-card.done {
  border-color: transparent;
  box-shadow:
    0 14px 32px rgba(0, 8, 12, 0.22),
    inset 0 1px 0 rgba(132, 204, 22, 0.10);
}

.agent-card.running .agent-status-badge,
.agent-card.done .agent-status-badge,
.agent-card.error .agent-status-badge,
.agent-card.stopped .agent-status-badge {
  background: transparent;
}

.agent-header {
  padding: 16px 16px 13px;
  align-items: flex-start;
  border-bottom: 0;
  background: transparent;
}

.agent-index {
  color: rgba(94, 234, 212, 0.86);
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 27px;
  font-weight: 700;
  line-height: 1;
  min-width: 38px;
  text-shadow: 0 0 18px rgba(94, 234, 212, 0.18);
}

.agent-title {
  font-size: 14.5px;
}

.agent-status-badge {
  position: absolute;
  top: 17px;
  right: 15px;
  z-index: 2;
  grid-column: auto;
  justify-self: auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(180, 230, 225, 0.045);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.agent-card.pending .agent-status-badge {
  color: rgba(180, 230, 225, 0.58);
}

.agent-card.running .agent-status-badge {
  color: rgba(94, 234, 212, 0.96);
  background: rgba(45, 212, 191, 0.10);
}

.agent-card.done .agent-status-badge {
  color: rgba(163, 230, 53, 0.88);
  background: rgba(132, 204, 22, 0.08);
}

.agent-card.stopped .agent-status-badge {
  color: rgba(245, 182, 156, 0.88);
  background: rgba(217, 119, 87, 0.08);
}

.agent-title-wrap {
  padding-right: 48px;
}

.agent-body {
  background: transparent;
}

.state-pending {
  padding: 8px 16px 18px;
}

.pending-illustration {
  display: none;
}

.capabilities li {
  position: relative;
  padding: 8px 0 8px 15px;
  margin-bottom: 0;
  border: 0;
  border-top: 1px solid rgba(180, 230, 225, 0.055);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  color: rgba(230, 250, 245, 0.72);
  text-align: left;
  text-shadow: none;
  font-size: 12px;
  line-height: 1.45;
  letter-spacing: 0;
}

.capabilities li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 16px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(94, 234, 212, 0.72);
}

.tool-use-track {
  padding: 14px 16px;
  background: rgba(180, 230, 225, 0.030);
  border-top: 1px solid rgba(180, 230, 225, 0.045);
  border-bottom: 1px solid rgba(180, 230, 225, 0.045);
}

.terminal-window {
  padding: 17px 16px;
}

.structured-conclusion {
  padding: 17px 16px;
  background: rgba(180, 230, 225, 0.025);
}

@media (max-width: 1279px) {
  .agent-flow {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .agent-flow {
    grid-template-columns: 1fr;
  }
}

.agent-header {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  gap: 4px 12px;
}

.agent-status-badge {
  grid-column: auto;
  justify-self: auto;
}

.agent-title {
  font-size: 13.6px;
  line-height: 1.18;
}

.agent-subtitle {
  margin-top: 3px;
}

@media (max-width: 680px) {
  .console-hero {
    padding: 24px 18px 22px;
  }

  .hero-title {
    font-size: 30px;
  }

  .hero-input-bar {
    flex-direction: column;
    gap: 8px;
    align-items: stretch;
  }

  .hero-input-bar input {
    min-height: 38px;
    padding: 0 10px;
  }

  .launch-btn {
    width: 100%;
  }

  .stop-btn {
    width: 100%;
  }

  .quick-topics {
    flex-direction: column;
    align-items: stretch;
  }

  .quick-label {
    margin-right: 0;
  }

  .quick-chip {
    width: 100%;
  }

  .agent-card {
    overflow: hidden;
  }

  .agent-status-badge {
    top: 16px;
    right: 14px;
  }
}

/* Final CTA Banner */
.final-cta-wrap {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 24px;
  display: flex;
  justify-content: center;
  z-index: 100;
  pointer-events: none;
}

.final-cta-box {
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  background: linear-gradient(135deg,
    rgba(16, 32, 40, 0.96) 0%,
    rgba(22, 48, 64, 0.96) 100%);
  padding: 22px 32px;
  border-radius: var(--r-xl);
  border: 1px solid rgba(45, 212, 191, 0.32);
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  box-shadow:
    0 24px 48px rgba(0, 8, 12, 0.65),
    0 8px 20px rgba(45, 212, 191, 0.18),
    inset 0 1px 0 rgba(180, 230, 225, 0.08);
  max-width: 900px;
  width: 100%;
  position: relative;
  overflow: hidden;
}
/* 顶部翡翠 hairline 强化 banner 的视觉锚点 */
.final-cta-box::before {
  content: '';
  position: absolute;
  top: 0;
  left: 32px;
  right: 32px;
  height: 1px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(45, 212, 191, 0.65) 50%,
    transparent 100%);
  pointer-events: none;
}

.cta-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.cta-icon {
  font-size: 40px;
}

.cta-text h3 {
  margin: 0 0 6px;
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.4px;
}

.cta-text p {
  margin: 0;
  font-size: 13.5px;
  color: var(--text-secondary);
  letter-spacing: 0.2px;
}

.cta-right {
  display: flex;
  gap: 12px;
}

.btn-save {
  padding: 11px 20px;
  background: rgba(180, 230, 225, 0.06);
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  font-weight: 600;
  letter-spacing: 0.3px;
  cursor: pointer;
  transition: all var(--t-fast);
}

.btn-save:hover {
  background: rgba(45, 212, 191, 0.10);
  color: var(--c-emerald);
  border-color: rgba(45, 212, 191, 0.45);
}

.btn-view {
  padding: 11px 26px;
  background: linear-gradient(180deg, var(--c-emerald) 0%, var(--c-emerald-deep) 100%);
  color: #04161a;
  border: 1px solid rgba(45, 212, 191, 0.5);
  border-radius: var(--r-sm);
  font-weight: 700;
  letter-spacing: 0.4px;
  cursor: pointer;
  box-shadow:
    0 6px 18px rgba(45, 212, 191, 0.36),
    inset 0 1px 0 rgba(255, 255, 255, 0.22);
  transition: all var(--t-fast);
}

.btn-view:hover {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow:
    0 10px 24px rgba(45, 212, 191, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

/* Transitions */
.fade-up-enter-active,
.fade-up-leave-active {
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}

.fade-up-enter-from,
.fade-up-leave-to {
  opacity: 0;
  transform: translateY(40px);
}

/* Responsive */
@media (max-width: 1200px) {
  .agent-flow {
    grid-template-columns: 1fr;
    max-width: 600px;
  }
  
  .final-cta-box {
    flex-direction: column;
    text-align: center;
    gap: 20px;
  }
  
  .cta-left {
    flex-direction: column;
  }
}
</style>
