<!--
  东风经营分析陪伴专家 panel(挂在简报详情页右侧)

  - props: briefingDoc(当前简报 doc),focusVehicle(焦点车型)
  - 后端: GET /api/expert/status 探活,POST /api/expert/chat 对话(SSE)
  - graceful 降级:后端 ready=false 时显示"专家暂时离线"占位

  关键点:
  1. 后端配置未完成时(QingtianExpertConfig.is_ready() === false),
     status 接口返回 ready=false,前端展示离线占位,不影响主流程
  2. 简报上下文(标题/摘要/关键章节)通过请求 body 注入,擎天平台
     在 system prompt 里替换变量
  3. 流式响应:用 fetch + ReadableStream 处理 SSE,不用 EventSource
     (因为 EventSource 不支持自定义 header / POST body)
-->
<template>
  <div class="expert-panel">
    <!-- 顶部头 -->
    <div class="expert-head">
      <div class="head-left">
        <span class="expert-avatar">👨‍💼</span>
        <div class="head-meta">
          <div class="expert-title">经营分析陪伴专家</div>
        </div>
      </div>
      <div class="head-status" :class="`status-${statusKind}`">
        <span class="status-dot"></span>
        <span>{{ statusText }}</span>
      </div>
    </div>

    <!-- 离线占位 -->
    <div v-if="!status.ready" class="offline-placeholder">
      <div class="offline-icon">🛰️</div>
      <div class="offline-title">专家暂时离线</div>
      <div class="offline-desc">{{ status.message || '正在接入擎天平台知识库' }}</div>
      <div class="offline-hint">
        接入完成后,你可以基于当前简报向专家深问:<br>
        · 这条结论的归因方法论是什么<br>
        · 同比和环比的标准用法<br>
        · 给我对比奕派和岚图的产品定位
      </div>
    </div>

    <!-- 在线对话区 -->
    <template v-else>
      <!-- 推荐问题(空对话时显示) -->
      <div v-if="messages.length === 0" class="recommend-area">
        <div class="recommend-greeting">
          您好,我是您的经营分析陪伴专家。已读取您当前查看的简报,可以围绕销售归因、售后异常、VOC 口碑、产品矩阵、行业基准等话题深问。
        </div>
        <div class="recommend-list">
          <button
            v-for="q in recommendQuestions"
            :key="q"
            class="recommend-btn"
            @click="askQuestion(q)"
          >
            {{ q }}
          </button>
        </div>
      </div>

      <!-- 对话历史 -->
      <div v-else ref="historyRef" class="history-area">
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="msg-row"
          :class="`msg-${m.role}`"
        >
          <div class="msg-bubble">
            <div v-if="m.role === 'assistant'" class="msg-author">
              <span class="msg-avatar">👨‍💼</span>
              专家
            </div>
            <div class="msg-content" v-html="renderMarkdown(m.content)"></div>
            <div v-if="m.role === 'assistant' && m.streaming" class="msg-streaming-dot"></div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <textarea
          v-model="inputText"
          class="input-textarea"
          placeholder="向专家深问(Shift+Enter 换行)"
          :disabled="isStreaming"
          @keydown.enter.exact.prevent="send"
          @keydown.enter.shift.exact.stop
        />
        <button
          class="send-btn"
          :disabled="isStreaming || !inputText.trim()"
          @click="send"
        >
          <span v-if="isStreaming">回复中…</span>
          <span v-else>发送 →</span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { http } from '@/api/http'
import type { BriefingDoc } from '@/api/report'

const props = defineProps<{
  briefingDoc: BriefingDoc | null
  briefingFilename: string
  focusVehicle: string
}>()

interface ExpertStatus {
  enabled: boolean
  ready: boolean
  message: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

const status = ref<ExpertStatus>({ enabled: false, ready: false, message: '正在检测专家状态' })
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const historyRef = ref<HTMLElement | null>(null)

// 状态展示
const statusKind = computed(() => {
  if (!status.value.enabled) return 'disabled'
  if (!status.value.ready) return 'pending'
  return 'online'
})
const statusText = computed(() => {
  if (statusKind.value === 'online') return '专家在线'
  if (statusKind.value === 'pending') return '配置中'
  return '未启用'
})

// 推荐问题
const recommendQuestions = computed(() => [
  '这条结论的归因方法论是什么',
  '同比和环比的标准用法',
  `给我对比${props.focusVehicle ? '奕派与岚图' : '同价位竞品'}的产品定位`,
  '这个数字符合行业基准吗',
])

// ============ 状态探活 ============
async function fetchStatus() {
  try {
    const { data } = await http.get<ExpertStatus>('/expert/status')
    status.value = data
  } catch (e: any) {
    // 端点 404 = 后端没起或没注册路由 → 视为未启用
    status.value = {
      enabled: false,
      ready: false,
      message: '后端未提供专家服务(/api/expert/status 不可达)',
    }
  }
}

onMounted(() => {
  fetchStatus()
})

// 切换简报时清空历史(避免上下文穿越)
watch(() => props.briefingFilename, () => {
  messages.value = []
})

// ============ 发送对话 ============
function askQuestion(q: string) {
  inputText.value = q
  send()
}

async function send() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return
  inputText.value = ''

  // 用户消息上屏
  messages.value.push({ role: 'user', content: text })
  // 占位 assistant 消息(流式填充)
  const assistantMsg: ChatMessage = { role: 'assistant', content: '', streaming: true }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  await scrollToBottom()

  // 组装 payload(把简报上下文塞进去)
  const payload = {
    user_query: text,
    focus_vehicle: props.focusVehicle || '',
    briefing_title: props.briefingDoc?.cover?.headline || props.briefingFilename || '',
    briefing_summary: props.briefingDoc?.executive_summary || '',
    briefing_sections: props.briefingDoc?.sections
      ? JSON.stringify(props.briefingDoc.sections.slice(0, 6).map(s => ({
          type: (s as any).type,
          title: (s as any).title,
          insight: (s as any).insight,
        })))
      : '',
  }

  try {
    // 流式 fetch
    const resp = await fetch('/api/expert/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok || !resp.body) {
      const errText = await resp.text().catch(() => '')
      assistantMsg.content = `专家暂时无法响应:${resp.status} ${errText}`
      assistantMsg.streaming = false
      return
    }

    // SSE 解析
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // 按 \n\n 切 SSE 帧
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx).trim()
        buf = buf.slice(idx + 2)
        if (!frame.startsWith('data:')) continue
        const data = frame.slice(5).trim()
        if (!data || data === '[DONE]') continue
        try {
          const obj = JSON.parse(data)
          // 适配 OpenAI / 擎天 / 自定义 三种字段命名
          const delta =
            obj.delta ||
            obj.choices?.[0]?.delta?.content ||
            obj.text ||
            obj.content ||
            ''
          if (delta) {
            assistantMsg.content += delta
            await scrollToBottom()
          }
          if (obj.error) {
            assistantMsg.content += `\n\n⚠️ ${obj.error}`
          }
        } catch {
          // 非 JSON 直接拼入
          assistantMsg.content += data
        }
      }
    }
  } catch (e: any) {
    assistantMsg.content = `网络错误:${e?.message || String(e)}`
  } finally {
    assistantMsg.streaming = false
    isStreaming.value = false
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (historyRef.value) {
    historyRef.value.scrollTop = historyRef.value.scrollHeight
  }
}

// ============ 简易 Markdown 渲染(够用即可,不引新依赖) ============
function renderMarkdown(src: string): string {
  if (!src) return ''
  let html = escapeHtml(src)
  // 加粗
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // 列表项 (- xxx)
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
  // 引用段(— 引用:...)单独成段加灰
  html = html.replace(/^(——?\s*引用[:：].+)$/gm, '<div class="cite">$1</div>')
  // 段落
  html = html.split(/\n{2,}/).map(p => {
    if (p.startsWith('<') || !p.trim()) return p
    return `<p>${p.replace(/\n/g, '<br>')}</p>`
  }).join('\n')
  return html
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
</script>

<style scoped>
.expert-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 14px;
  background: var(--bg-glass-strong);
  border: 1px solid var(--border-line);
  overflow: hidden;
}

/* ========== 入场 stagger 动画 ========== */
.expert-head,
.offline-placeholder,
.recommend-area,
.expert-messages,
.expert-composer {
  opacity: 0;
  transform: translateX(16px);
  animation: expert-fadein 0.42s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
.expert-head            { animation-delay: 0.04s; }
.offline-placeholder    { animation-delay: 0.10s; }
.recommend-area         { animation-delay: 0.14s; }
.expert-messages        { animation-delay: 0.16s; }
.expert-composer        { animation-delay: 0.20s; }
@keyframes expert-fadein {
  to { opacity: 1; transform: translateX(0); }
}

/* ========== 顶部头 ========== */
.expert-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.08) 0%, rgba(45, 212, 191, 0.06) 100%);
  border-bottom: 1px solid var(--border-line);
}
.head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.expert-avatar {
  font-size: 28px;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: rgba(22, 32, 40, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
}
.expert-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.3px;
}
.expert-tag {
  margin-top: 2px;
  font-size: 10.5px;
  color: var(--c-mint);
  font-weight: 600;
  letter-spacing: 0.2px;
}
.head-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.status-online {
  background: #d1fae5;
  color: #065f46;
}
.status-online .status-dot { background: var(--c-moss); box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.18); }
.status-pending {
  background: rgba(45, 212, 191, 0.08);
  color: var(--c-emerald);
}
.status-pending .status-dot { background: var(--c-emerald); }
.status-disabled {
  background: rgba(180, 230, 225, 0.03);
  color: var(--text-muted);
}
.status-disabled .status-dot { background: var(--text-muted); }

/* ========== 离线占位 ========== */
.offline-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 32px 22px;
  text-align: center;
}
.offline-icon { font-size: 38px; margin-bottom: 4px; }
.offline-title { font-size: 14.5px; font-weight: 700; color: var(--text-primary); }
.offline-desc { font-size: 12px; color: var(--text-muted); }
.offline-hint {
  margin-top: 16px;
  padding: 12px 14px;
  background: rgba(180, 230, 225, 0.025);
  border: 1px dashed var(--border-line);
  border-radius: 10px;
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.8;
  text-align: left;
}

/* ========== 推荐问题(空状态) ========== */
.recommend-area {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
}
.recommend-greeting {
  padding: 12px 14px;
  background: rgba(180, 230, 225, 0.025);
  border-left: 3px solid var(--c-mint);
  border-radius: 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
  margin-bottom: 14px;
}
.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.recommend-btn {
  text-align: left;
  padding: 9px 12px;
  border: 1px solid var(--border-line);
  border-radius: 10px;
  background: rgba(180, 230, 225, 0.04);
  font-size: 12.5px;
  color: var(--text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: all .15s;
}
.recommend-btn:hover {
  border-color: rgba(45, 212, 191, 0.32);
  background: rgba(45, 212, 191, 0.05);
  transform: translateX(2px);
}

/* ========== 对话历史 ========== */
.history-area {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg-row {
  display: flex;
  width: 100%;
}
.msg-row.msg-user {
  justify-content: flex-end;
}
.msg-bubble {
  max-width: 90%;
  padding: 9px 12px;
  border-radius: 12px;
  font-size: 12.5px;
  line-height: 1.65;
}
.msg-user .msg-bubble {
  background: linear-gradient(135deg, var(--c-emerald) 0%, var(--c-mint) 100%);
  color: #fff;
  border-radius: 12px 12px 2px 12px;
}
.msg-assistant .msg-bubble {
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
  color: var(--text-primary);
  border-radius: 12px 12px 12px 2px;
}
.msg-author {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  color: var(--c-mint);
  margin-bottom: 4px;
  letter-spacing: 0.3px;
}
.msg-avatar { font-size: 14px; }
.msg-content :deep(p) { margin: 0 0 6px; }
.msg-content :deep(p:last-child) { margin-bottom: 0; }
.msg-content :deep(ul) { margin: 4px 0; padding-left: 18px; }
.msg-content :deep(li) { margin-bottom: 2px; }
.msg-content :deep(.cite) {
  margin-top: 6px;
  padding: 4px 8px;
  background: var(--border-line);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
.msg-streaming-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-mint);
  margin-top: 6px;
  animation: pulse-dot 1s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.3); }
}

/* ========== 输入区 ========== */
.input-area {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border-line);
  background: rgba(180, 230, 225, 0.04);
}
.input-textarea {
  flex: 1;
  resize: none;
  height: 48px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border-line);
  font-size: 12.5px;
  font-family: inherit;
  outline: none;
  background: rgba(180, 230, 225, 0.025);
  color: var(--text-primary);
}
.input-textarea:focus {
  border-color: var(--c-mint);
  background: rgba(180, 230, 225, 0.04);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}
.input-textarea:disabled { opacity: 0.6; cursor: not-allowed; }
.send-btn {
  flex-shrink: 0;
  padding: 0 14px;
  border-radius: 10px;
  border: 0;
  background: linear-gradient(135deg, var(--c-emerald), var(--c-mint));
  color: #fff;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
  letter-spacing: 0.3px;
  transition: all .15s;
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
