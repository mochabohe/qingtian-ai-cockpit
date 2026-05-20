import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface AgentStep {
  index: number
  name: string
  title: string
  desc: string
  status: 'pending' | 'running' | 'done' | 'error' | 'stopped'
  output: string
  result?: string
}

export const useAgentStore = defineStore('agent', () => {
  const isRunning = ref(false)
  const steps = ref<AgentStep[]>([])
  const liveText = ref('')
  const finalReport = ref('')
  const error = ref('')
  const dataLoaded = ref<{ file: string; rows: number; cols: number; summary?: string } | null>(null)
  // 编排器 _save_report 三写产出的文件名(md/json/trace.json 同 stem)
  // 有值 → "保存到简报库" 直接复用,不再走 /report/save 二次落盘(否则只剩 md,丢失卡片+链路)
  const savedFilename = ref<string>('')

  function reset() {
    isRunning.value = false
    steps.value = []
    liveText.value = ''
    finalReport.value = ''
    error.value = ''
    dataLoaded.value = null
    savedFilename.value = ''
  }

  function appendStepOutput(index: number, text: string) {
    const s = steps.value.find(x => x.index === index)
    if (s) s.output += text
  }

  function setStepDone(index: number, output: string) {
    const s = steps.value.find(x => x.index === index)
    if (s) {
      s.status = 'done'
      s.output = output
    }
  }

  function setStepError(index: number, msg: string) {
    const s = steps.value.find(x => x.index === index)
    if (s) {
      s.status = 'error'
      s.result = msg
      // 同步写 output,让 getAgentOutput 能拿到真实错误消息
      s.output = msg
    }
  }

  function setStepStopped(index: number, msg = '分析已停止') {
    const s = steps.value.find(x => x.index === index)
    if (s) {
      s.status = 'stopped'
      s.result = msg
      s.output = msg
    }
  }

  return {
    isRunning, steps, liveText, finalReport, error, dataLoaded, savedFilename,
    reset, appendStepOutput, setStepDone, setStepError, setStepStopped,
  }
})
