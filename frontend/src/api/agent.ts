import { fetchEventSource } from '@microsoft/fetch-event-source'
import { http } from './http'

export interface ChatRequest {
  prompt: string
  model?: string
  temperature?: number
}

export async function chatSync(req: ChatRequest) {
  const { data } = await http.post('/agent/chat', req)
  return data.data as { reply: string; usage: any }
}

export interface StreamHandlers {
  onStart?: (data: any) => void
  onChunk?: (text: string) => void
  onStepStart?: (data: any) => void
  onStepDone?: (data: any) => void
  onAgentToken?: (data: any) => void
  onStepError?: (data: any) => void
  onDataLoaded?: (data: any) => void
  onEnd?: (data: any) => void
  onError?: (msg: string) => void
}

/** SSE 流式对话 */
export async function streamChat(
  body: ChatRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal,
) {
  await fetchEventSource('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
    openWhenHidden: true,
    onmessage(ev) {
      const data = ev.data ? JSON.parse(ev.data) : {}
      switch (ev.event) {
        case 'start':
          handlers.onStart?.(data)
          break
        case 'chunk':
          handlers.onChunk?.(data.text || '')
          break
        case 'end':
          handlers.onEnd?.(data)
          break
        case 'error':
          handlers.onError?.(data.message || '未知错误')
          break
      }
    },
    onerror(err) {
      handlers.onError?.(err.message)
      throw err
    },
  })
}

/** 5 子 Agent 编排流式 */
export async function streamAgentRun(
  body: { topic: string; data_file?: string; model?: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
) {
  await fetchEventSource('/api/agent/run/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
    openWhenHidden: true,
    onmessage(ev) {
      const data = ev.data ? JSON.parse(ev.data) : {}
      switch (ev.event) {
        case 'start':
          handlers.onStart?.(data)
          break
        case 'step_start':
          handlers.onStepStart?.(data)
          break
        case 'agent_token':
          handlers.onAgentToken?.(data)
          break
        case 'step_done':
          handlers.onStepDone?.(data)
          break
        case 'step_error':
          handlers.onStepError?.(data)
          break
        case 'data_loaded':
          handlers.onDataLoaded?.(data)
          break
        case 'end':
          handlers.onEnd?.(data)
          break
        case 'error':
          handlers.onError?.(data.message || '未知错误')
          break
      }
    },
    onerror(err) {
      handlers.onError?.(err.message)
      throw err
    },
  })
}
