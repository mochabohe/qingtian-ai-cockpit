<template>
  <!--
    经营任务单 (P0-1):跨页面共享的当前任务上下文
    设计原则:
    - 一行紧凑展示,不抢主内容焦点
    - 任务字段可点开抽屉编辑(车型/周期/对标),不直接占主屏
    - 进度可视(数据/简报/视频三段),让用户一眼看出系统进展
    - OFFLINE_MODE 时显示"演示模式"角标(不假装在线)
  -->
  <div class="mission-bar" :class="[`stage-${mission.progressStage}`, { 'is-offline': offlineMode }]">
    <!-- 演示模式角标:OFFLINE_MODE=true 时显示,不欺骗用户 -->
    <div v-if="offlineMode" class="offline-banner">
      <span class="offline-dot"></span>
      <span>演示模式 · 使用预热案例(零外网依赖)</span>
      <span class="offline-tip">{{ fallbackCaseCount }} 个预热案例就绪</span>
    </div>

    <div class="mission-main">
      <div class="mission-body">
        <div class="mission-row-1">
          <span class="mission-label">当前任务</span>
          <span class="mission-topic">{{ mission.topic }}</span>
        </div>
        <div class="mission-row-2">
          <div class="progress-step" :class="dataReadyClass">
            <span class="step-dot"></span>
            <span class="step-text">数据池 {{ mission.dataReadyText }}</span>
          </div>
          <span class="step-arrow">→</span>
          <div class="progress-step" :class="briefClass">
            <span class="step-dot"></span>
            <span class="step-text">{{ mission.briefFilename ? '简报已生成' : '简报待生成' }}</span>
          </div>
          <span class="step-arrow">→</span>
          <div class="progress-step" :class="videoClass">
            <span class="step-dot"></span>
            <span class="step-text">{{ mission.videoTaskId ? '视频已生成' : '视频待生成' }}</span>
          </div>
        </div>
      </div>
      <button class="mission-edit" v-if="!hideEdit" @click="editorOpen = true">
        <span>切换 / 编辑</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"></path>
          <path d="M18.5 2.5a2.121 2.121 0 113 3L12 15l-4 1 1-4 9.5-9.5z"></path>
        </svg>
      </button>
    </div>

    <!-- 编辑抽屉 -->
    <el-drawer v-model="editorOpen" title="编辑经营任务" size="420px" direction="rtl">
      <div class="editor-form">
        <div class="form-row">
          <label>任务名</label>
          <el-input v-model="draft.topic" placeholder="例如:eπ007 综合经营诊断" />
        </div>
        <div class="form-row">
          <label>焦点车型</label>
          <el-select v-model="draft.focusVehicle">
            <el-option
              v-for="v in focusOptions"
              :key="v"
              :label="vehicleLabel(v)"
              :value="v"
            />
          </el-select>
          <div class="form-hint">
            当前演示版仅 <b>eπ007</b> 业务库已对接,其余车型为 SaaS 节奏下的 roadmap 占位。
          </div>
        </div>
        <div class="form-row">
          <label>
            分析周期
            <el-tooltip
              effect="dark"
              placement="top"
              content="演示版固定按近 12 月聚合。生产环境下后端按所选周期重新聚合数据。"
            >
              <span class="label-tip">ⓘ</span>
            </el-tooltip>
          </label>
          <el-select v-model="draft.period">
            <el-option v-for="p in periodOptions" :key="p" :label="p" :value="p" />
          </el-select>
        </div>
        <div class="form-row">
          <label>对标车型</label>
          <el-select v-model="draft.benchmarkVehicle">
            <el-option v-for="v in benchmarkOptions" :key="v" :label="v" :value="v" />
          </el-select>
        </div>
        <div class="form-tip">
          <strong>提示</strong>:切换焦点车型会清空当前进度(数据/简报/视频),需要重新启动 Agent 分析。
        </div>
        <div class="form-actions">
          <el-button @click="editorOpen = false">取消</el-button>
          <el-button type="primary" @click="applyDraft">应用</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useMissionStore } from '@/stores/mission'
import { http } from '@/api/http'

defineProps<{ hideEdit?: boolean }>()

const mission = useMissionStore()
const editorOpen = ref(false)

// 演示兜底状态:启动时拉一次,不重复轮询(模式不会运行时变)
const offlineMode = ref(false)
const fallbackCaseCount = ref(0)

onMounted(async () => {
  try {
    const { data } = await http.get('/system/mode')
    offlineMode.value = !!data.data?.offline_mode
    fallbackCaseCount.value = (data.data?.fallback_cases || []).length
  } catch {
    // 后端未起或路由不存在 → 静默,默认在线模式
  }

  // 拉取 manifest 维护的车型/周期下拉源(失败则保留下方默认硬编码兜底)
  try {
    const { data } = await http.get('/data/vehicle-options')
    const opts = data?.data || {}
    // focus 必须收敛在已知奕派序列内:即便后端 manifest 漏改也兜住(避免出现岚图全系)
    if (Array.isArray(opts.focus) && opts.focus.length) {
      const allowed = new Set(['eπ007', 'eπ007+', 'eπ008'])
      const filtered = opts.focus.filter((v: string) => allowed.has(v))
      if (filtered.length) focusOptions.value = filtered
    }
    if (Array.isArray(opts.benchmark) && opts.benchmark.length) benchmarkOptions.value = opts.benchmark
    if (Array.isArray(opts.period) && opts.period.length)       periodOptions.value    = opts.period
  } catch {
    // manifest / 接口不可用 → 保留默认硬编码,UI 不破
  }
})

// 抽屉内的草稿(取消则不应用)
const draft = reactive({
  topic:            mission.topic,
  focusVehicle:     mission.focusVehicle,
  period:           mission.period,
  benchmarkVehicle: mission.benchmarkVehicle,
})

watch(editorOpen, (open) => {
  if (open) {
    draft.topic            = mission.topic
    draft.focusVehicle     = mission.focusVehicle
    draft.period           = mission.period
    draft.benchmarkVehicle = mission.benchmarkVehicle
  }
})

// 默认值作为接口不可用时的兜底,启动后被 /data/vehicle-options 覆盖。
// 收敛为奕派品牌单一旗舰序列:仅 eπ007 业务库已对接,eπ007+ / eπ008 为 SaaS
// 节奏下的 roadmap 占位(选中后会触发 LOCKED_VEHICLES 友好提示并回退)。
const focusOptions     = ref<string[]>(['eπ007', 'eπ007+', 'eπ008'])
const periodOptions    = ref<string[]>(['近 12 月', '近 6 月', '近 3 月', '2026 Q1', '2025 全年'])
const benchmarkOptions = ref<string[]>(['Model Y', '奔驰E级', 'Model 3', 'AION V', 'AION Y', '乐道L60'])

// "已对接业务库"的车型白名单 —— 选其他车型会被回退,不会真的切过去。
// 这是把"装饰道具"包装成"产品 roadmap"的关键开关:可点 + 友好兜底,
// 比直接置灰更符合真实 SaaS 按车型逐步开放的故事。
const ACTIVE_VEHICLES = new Set(['eπ007'])

const VEHICLE_ROADMAP_MSG: Record<string, string> = {
  'eπ007+': 'eπ007+ 业务库正在同步,预计 6 月上线。当前演示版仅 eπ007 数据已就绪。',
  'eπ008':  'eπ008 业务库排期中,预计 Q3 上线。当前演示版仅 eπ007 数据已就绪。',
}

function vehicleLabel(v: string): string {
  return ACTIVE_VEHICLES.has(v) ? v : `${v} · roadmap`
}

function applyDraft() {
  // 焦点车型变化:先校验是否在白名单中,不在则弹友好提示并回退到 eπ007。
  // 真实业务里"切车型"在生产环境根本不存在(单车型 SaaS),
  // 这里的"占位 + 回退"是把演示版的克制讲清楚,而不是假装能切。
  if (draft.focusVehicle !== mission.focusVehicle) {
    if (!ACTIVE_VEHICLES.has(draft.focusVehicle)) {
      ElMessage({
        type: 'warning',
        message: VEHICLE_ROADMAP_MSG[draft.focusVehicle] || '该车型业务库尚未接入,演示版仅 eπ007 数据已就绪。',
        duration: 4000,
      })
      draft.focusVehicle = 'eπ007'
      // 不 return —— 仍然应用其他字段(period / benchmark / topic)的修改
    }
    if (draft.focusVehicle !== mission.focusVehicle) {
      mission.setFocusVehicle(draft.focusVehicle)
    }
  }
  mission.topic            = draft.topic
  mission.period           = draft.period
  mission.benchmarkVehicle = draft.benchmarkVehicle
  editorOpen.value = false
}

const dataReadyClass = computed(() => {
  if (mission.dataReady >= mission.dataTotal && mission.dataTotal > 0) return 'done'
  if (mission.dataReady > 0) return 'partial'
  return 'pending'
})
const briefClass = computed(() => mission.briefFilename ? 'done' : 'pending')
const videoClass = computed(() => mission.videoTaskId ? 'done' : 'pending')
</script>

<style scoped>
.mission-bar {
  position: relative;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  border-radius: 14px;
  padding: 14px 20px;
  margin-bottom: 18px;
  transition: all .25s ease;
  overflow: hidden;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
}
/* 顶部细翡翠 hairline:取代左侧竖条纹 */
.mission-bar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 20px;
  right: 20px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.55), transparent);
  pointer-events: none;
}
/* 右上极弱翡翠光晕 */
.mission-bar::after {
  content: '';
  position: absolute;
  top: -100px;
  right: -120px;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(45, 212, 191, 0.08), transparent 70%);
  pointer-events: none;
}

/* 不同阶段:仅切换顶部 hairline 颜色 */
.mission-bar.stage-data-ready::before {
  background: linear-gradient(90deg, transparent, rgba(78, 205, 196, 0.65), transparent);
}
.mission-bar.stage-brief-done::before {
  background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.65), transparent);
}
.mission-bar.stage-video-done::before {
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.85), transparent);
}

/* 演示兜底模式角标 */
.mission-bar.is-offline {
  border-color: rgba(217, 119, 87, 0.35);
}
.offline-banner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  margin: -14px -20px 12px -20px;
  background: linear-gradient(90deg, rgba(217, 119, 87, 0.85) 0%, rgba(185, 28, 92, 0.7) 100%);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  border-radius: 14px 14px 0 0;
  letter-spacing: 0.3px;
}
.offline-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #fff;
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.4; }
}
.offline-tip {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.86);
}

.mission-main {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 16px;
}

.mission-icon {
  position: relative;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.16) 0%, rgba(14, 124, 123, 0.06) 100%);
  border: 1px solid rgba(45, 212, 191, 0.32);
  color: var(--c-emerald);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 4px 12px rgba(0, 8, 12, 0.25);
}
.mission-icon svg {
  width: 20px;
  height: 20px;
  filter: drop-shadow(0 0 5px currentColor);
  opacity: 0.95;
}

.mission-body {
  flex: 1;
  min-width: 0;
}

.mission-row-1 {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.mission-label {
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 1.6px;
  font-weight: 600;
  text-transform: uppercase;
  flex-shrink: 0;
}

.mission-topic {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', 'Noto Serif SC', Georgia, serif;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.5px;
}

.mission-summary {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.mission-row-2 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.progress-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 0;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-weight: 500;
  letter-spacing: 0.2px;
}
.progress-step.partial {
  background: transparent;
  border: none;
  color: #4ecdc4;
}
.progress-step.done {
  background: transparent;
  border: none;
  color: var(--c-emerald);
}
.step-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}
.step-arrow {
  color: var(--text-dim);
  font-size: 11px;
}

.mission-edit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: rgba(180, 230, 225, 0.04);
  border: 1px solid var(--border-line);
  border-radius: 8px;
  font-size: 12.5px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all .15s;
  flex-shrink: 0;
  font-family: inherit;
}
.mission-edit:hover {
  border-color: var(--c-emerald);
  color: var(--c-emerald);
  background: rgba(45, 212, 191, 0.08);
}

/* 抽屉表单 */
.editor-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 0 4px;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-row label {
  font-size: 12.5px;
  color: var(--text-secondary);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.form-row .label-tip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(45, 212, 191, 0.18);
  color: var(--c-emerald);
  font-size: 10px;
  font-weight: 700;
  cursor: help;
  user-select: none;
}
.form-hint {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.55;
  margin-top: 2px;
}
.form-hint b {
  color: var(--c-emerald);
  font-weight: 600;
}
.form-row :deep(.el-select) {
  width: 100%;
}
.form-tip {
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.10);
  border-left: 3px solid var(--c-amber-warm);
  border-radius: var(--r-sm);
  font-size: 12px;
  color: var(--c-amber-warm);
  line-height: 1.6;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

@media (max-width: 768px) {
  .mission-row-1 { gap: 6px; }
  .mission-summary { display: none; }
  .step-arrow { display: none; }
  .mission-edit span { display: none; }
}
</style>
