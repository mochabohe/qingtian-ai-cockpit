// 经营任务单 (P0-1):全局共享当前分析任务的上下文,跨页面同步
//
// 价值:用户说"换 ID.4 看看" → 切上下文,所有页面 MissionBar 同步刷新
//
// 设计原则(对抗审查后):
// - 不做"任务历史列表"——用户不会翻历史
// - 不做"自定义任务命名"——topic 联动即可,减少现场操作步骤
// - localStorage 持久化:刷新页面或切走再回来,任务状态不丢
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

export type MissionStatus = 'idle' | 'analyzing' | 'briefing' | 'reviewing'

export interface MissionState {
  // 配置项(可手动改)
  topic: string                  // 任务名 / 主题
  focusVehicle: string           // 焦点车型(自家)
  period: string                 // 分析周期
  benchmarkVehicle: string       // 对标车型(VOC 反向参照用)

  // 进度状态(自动更新)
  dataReady: number              // 已就绪数据集数
  dataTotal: number              // 总数据集数
  briefFilename: string | null   // 已选中/生成的简报文件名
  videoTaskId: string | null     // 已生成的视频任务 ID
  videoStatus: 'idle' | 'running' | 'done'   // 视频任务全局状态(menu 用)
  videoUnread: boolean            // 视频已生成但用户尚未访问 /video(菜单红点用)
  status: MissionStatus
}

const STORAGE_KEY = 'zhqcm_mission_v1'

const DEFAULTS: MissionState = {
  topic:            'eπ007 综合经营诊断',
  focusVehicle:     'eπ007',
  period:           '近 12 月',
  benchmarkVehicle: 'Model Y',
  dataReady:        0,
  dataTotal:        4,
  briefFilename:    null,
  videoTaskId:      null,
  videoStatus:      'idle',
  videoUnread:      false,
  status:           'idle',
}

function normalizeLegacyMissionText(text: string): string {
  return text
    .replace(/VOC\s*1000\s*条评论/g, 'VOC 10万条评论')
    .replace(/VOC\s*1000\s*条/g, 'VOC 10万条')
    .replace(/1000\s*条评论/g, '10万条评论')
    .replace(/5\s*万条销售/g, '10万条销售')
    .replace(/1\s*万条售后/g, '2万条售后')
}

function loadFromStorage(): Partial<MissionState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return {}
    if (typeof parsed.topic === 'string') {
      parsed.topic = normalizeLegacyMissionText(parsed.topic)
    }
    return parsed
  } catch {
    return {}
  }
}

export const useMissionStore = defineStore('mission', () => {
  const persisted = loadFromStorage()
  const state: MissionState = { ...DEFAULTS, ...persisted }

  const topic            = ref(state.topic)
  const focusVehicle     = ref(state.focusVehicle)
  const period           = ref(state.period)
  const benchmarkVehicle = ref(state.benchmarkVehicle)
  const dataReady        = ref(state.dataReady)
  const dataTotal        = ref(state.dataTotal)
  const briefFilename    = ref<string | null>(state.briefFilename)
  const videoTaskId      = ref<string | null>(state.videoTaskId)
  const videoStatus      = ref<'idle' | 'running' | 'done'>(state.videoStatus || 'idle')
  const videoUnread      = ref<boolean>(!!state.videoUnread)
  const status           = ref<MissionStatus>(state.status)

  // 派生:展示用的简短摘要
  const summary = computed(() => {
    const parts: string[] = []
    parts.push(`焦点 ${focusVehicle.value}`)
    parts.push(`周期 ${period.value}`)
    if (benchmarkVehicle.value) parts.push(`对标 ${benchmarkVehicle.value}`)
    return parts.join(' · ')
  })

  // 派生:数据池就绪进度文案
  const dataReadyText = computed(() => `${dataReady.value} / ${dataTotal.value} 就绪`)

  // 派生:整体进度阶段(给 MissionBar 显示)
  const progressStage = computed(() => {
    if (videoTaskId.value)   return 'video-done'
    if (briefFilename.value) return 'brief-done'
    if (dataReady.value >= dataTotal.value && dataTotal.value > 0) return 'data-ready'
    return 'configuring'
  })

  // 重置(切换车型/任务时不全清,只清进度)
  function resetProgress() {
    dataReady.value     = 0
    briefFilename.value = null
    videoTaskId.value   = null
    videoStatus.value   = 'idle'
    videoUnread.value   = false
    status.value        = 'idle'
  }

  // 切焦点车型时,顺手把 topic 也按规则更新一下(让现场切换更自然)
  function setFocusVehicle(v: string) {
    focusVehicle.value = v
    // 仅当 topic 是默认模板时才自动更新,避免覆盖用户自定义主题
    if (topic.value.endsWith('综合经营诊断') || topic.value.endsWith('经营战略简报')) {
      topic.value = `${v} 综合经营诊断`
    }
    resetProgress()
  }

  // 持久化:任意字段变更都同步写盘
  watch(
    [topic, focusVehicle, period, benchmarkVehicle, dataReady, dataTotal, briefFilename, videoTaskId, videoStatus, videoUnread, status],
    () => {
      try {
        const snap: MissionState = {
          topic:            topic.value,
          focusVehicle:     focusVehicle.value,
          period:           period.value,
          benchmarkVehicle: benchmarkVehicle.value,
          dataReady:        dataReady.value,
          dataTotal:        dataTotal.value,
          briefFilename:    briefFilename.value,
          videoTaskId:      videoTaskId.value,
          videoStatus:      videoStatus.value,
          videoUnread:      videoUnread.value,
          status:           status.value,
        }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(snap))
      } catch {
        // localStorage 满 / 隐私模式 → 静默失败,不影响主流程
      }
    },
    { deep: true },
  )

  return {
    topic, focusVehicle, period, benchmarkVehicle,
    dataReady, dataTotal, briefFilename, videoTaskId, videoStatus, videoUnread, status,
    summary, dataReadyText, progressStage,
    resetProgress, setFocusVehicle,
  }
})
