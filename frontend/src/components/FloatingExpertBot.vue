<!--
  全局浮动经营分析陪伴专家(挂在 App.vue,所有页面可见)

  - FAB 圆形机器人按钮:右下角浮动,可自由拖动,位置持久化到 localStorage
  - 点击 FAB 打开/关闭聊天面板;面板锚定在 FAB 旁边
  - 简报上下文:从 mission store 的 briefFilename 自动拉取(在简报页选中后才有)
  - 后端: GET /api/expert/status 探活,POST /api/expert/chat 对话(SSE)
  - graceful 降级:后端 ready=false 时面板内显示"专家暂时离线"占位
-->
<template>
  <!-- 拖拽态:用纯 div 而不是 button,避免拖动结束被当成 click -->
  <!-- 离线态(status.ready=false)依然渲染但灰化, 点击显示离线提示, 不直接消失 -->
  <div
    ref="fabRef"
    class="fab"
    :class="{ 'fab-open': open, 'fab-dragging': dragging, 'fab-offline': !status.ready }"
    :style="fabStyle"
    :title="status.ready ? '经营分析陪伴专家' : '擎天平台暂不可用 · 点击查看详情'"
    @mousedown="onDragStart"
    @touchstart.passive="onDragStart"
    @click="onFabClick"
  >
    <!-- 离线态右上角红点(避让其它图层) -->
    <span v-if="!status.ready" class="fab-offline-dot" aria-hidden="true"></span>
    <!-- 外圈光环：缓慢旋转的氛围光晕 -->
    <span class="fab-halo" aria-hidden="true"></span>
    <!-- 高光层：呼吸光斑 -->
    <span class="fab-glow" aria-hidden="true"></span>
    <!-- 主体：精致机器人头像 -->
    <span class="fab-icon">
      <svg viewBox="0 0 64 64" width="48" height="48" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <defs>
          <linearGradient id="botFace" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#0f172a" />
            <stop offset="100%" stop-color="#1e293b" />
          </linearGradient>
          <linearGradient id="botShell" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95" />
            <stop offset="100%" stop-color="#e0f2fe" stop-opacity="0.85" />
          </linearGradient>
          <radialGradient id="botCheek" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#fb7185" stop-opacity="0.9" />
            <stop offset="100%" stop-color="#fb7185" stop-opacity="0" />
          </radialGradient>
        </defs>

        <!-- 天线杆 + 顶部小灯 -->
        <line x1="32" y1="8" x2="32" y2="14" stroke="url(#botShell)" stroke-width="2" />
        <circle class="bot-antenna" cx="32" cy="6.5" r="3" fill="#fef08a" />
        <circle cx="32" cy="6.5" r="1.4" fill="#fff7ed" />

        <!-- 头壳：圆角立方体感，白瓷光泽 -->
        <rect x="11" y="14" width="42" height="34" rx="11" ry="11"
              fill="url(#botShell)" stroke="rgba(15,23,42,0.18)" stroke-width="0.8" />

        <!-- 顶部高光（玻璃质感） -->
        <path d="M16 20 Q32 16 48 20" stroke="rgba(255,255,255,0.95)" stroke-width="1.4" fill="none" opacity="0.9" />

        <!-- 屏幕面板（眼睛底色板） -->
        <rect x="16" y="20" width="32" height="22" rx="7" ry="7" fill="url(#botFace)" />
        <rect x="16" y="20" width="32" height="22" rx="7" ry="7" fill="none" stroke="rgba(45,212,191,0.45)" stroke-width="0.9" />

        <!-- 屏幕扫描光（缓慢上下移动） -->
        <rect class="bot-scanline" x="17" y="22" width="30" height="1.2" rx="0.6" fill="rgba(45,212,191,0.55)" />

        <!-- 双眼：椭圆形，会眨眼 -->
        <g class="bot-eyes">
          <ellipse class="bot-eye bot-eye-l" cx="25" cy="31" rx="2.6" ry="3.2" fill="#2dd4bf" />
          <ellipse class="bot-eye bot-eye-r" cx="39" cy="31" rx="2.6" ry="3.2" fill="#2dd4bf" />
          <!-- 眼睛高光（让眼睛活起来） -->
          <circle cx="26" cy="29.5" r="0.8" fill="#ffffff" opacity="0.9" />
          <circle cx="40" cy="29.5" r="0.8" fill="#ffffff" opacity="0.9" />
        </g>

        <!-- 嘴部小线条 -->
        <path d="M28 38.5 Q32 40.5 36 38.5" stroke="rgba(45,212,191,0.7)" stroke-width="1.4" fill="none" />

        <!-- 腮红（暖色点缀） -->
        <ellipse cx="17.5" cy="36" rx="2.2" ry="1.2" fill="url(#botCheek)" />
        <ellipse cx="46.5" cy="36" rx="2.2" ry="1.2" fill="url(#botCheek)" />

        <!-- 双耳/听筒 -->
        <rect x="8" y="26" width="3" height="10" rx="1.2" fill="rgba(255,255,255,0.85)" />
        <rect x="53" y="26" width="3" height="10" rx="1.2" fill="rgba(255,255,255,0.85)" />

        <!-- 颈部小连接 -->
        <rect x="29" y="48" width="6" height="3" rx="1" fill="rgba(15,23,42,0.25)" />
      </svg>
    </span>
  </div>

  <!-- 聊天面板:Teleport 到 body,避免被祖先 overflow/transform 截断 -->
  <Teleport to="body">
    <transition name="panel-pop">
      <div
        v-if="open"
        ref="panelRef"
        class="panel"
        :class="panelClasses"
        :style="panelStyle"
        @click.stop
      >
        <!-- 顶部头(带关闭按钮) -->
        <div class="expert-head">
          <div class="head-left">
            <span class="expert-avatar">
              <img v-if="avatarIsUrl" :src="agentInfo.avatar" :alt="agentInfo.name" class="avatar-img" />
              <template v-else>{{ agentInfo.avatar }}</template>
            </span>
            <div class="head-meta">
              <div class="expert-title">{{ agentInfo.name }}</div>
            </div>
          </div>
          <div class="head-right">
            <button
              class="head-action history-btn"
              :title="historyOpen ? '收起历史记录' : '打开历史记录'"
              :class="{ 'is-active': historyOpen }"
              @click="toggleHistory"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
            </button>
            <button
              v-if="status.ready && messages.length > 0"
              class="head-action"
              title="新开会话"
              :disabled="isStreaming"
              @click="newConversation"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
            <button class="head-close" title="收起" @click="open = false">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        </div>

        <!-- 历史记录侧边抽屉(从左侧滑入, 覆盖对话区) -->
        <transition name="history-slide">
          <div v-if="historyOpen" class="history-drawer" @click.stop>
            <div class="history-drawer-head">
              <div class="history-drawer-title">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 2" />
                </svg>
                <span>历史对话</span>
              </div>
              <button class="history-drawer-close" title="关闭" @click="historyOpen = false">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            </div>
            <div class="history-drawer-body">
              <div v-if="historyLoading" class="history-state">
                <div class="history-spinner"></div>
                <span>加载历史中…</span>
              </div>
              <div v-else-if="historyError" class="history-state history-state-error">
                <span>{{ historyError }}</span>
                <button class="history-retry" @click="loadHistoryList">重试</button>
              </div>
              <div v-else-if="historyList.length === 0" class="history-state">
                <div class="history-empty-icon">📭</div>
                <span>暂无历史对话</span>
              </div>
              <ul v-else class="history-list">
                <li
                  v-for="conv in historyList"
                  :key="conv.AppConversationID"
                  class="history-item"
                  :class="{ 'is-active': conv.AppConversationID === conversationId }"
                  :title="conv.ConversationName || '新的会话'"
                  @click="loadHistoryConversation(conv.AppConversationID)"
                >
                  <div class="history-item-name">{{ conv.ConversationName || '新的会话' }}</div>
                  <div class="history-item-time">{{ formatHistoryTime(conv.LastChatTime || conv.CreateTime) }}</div>
                </li>
              </ul>
            </div>
          </div>
        </transition>

        <!-- 离线占位 -->
        <div v-if="!status.ready" class="offline-placeholder">
          <div class="offline-icon">🛰️</div>
          <div class="offline-title">专家暂时离线</div>
          <div class="offline-desc">{{ status.message || '正在接入擎天平台知识库' }}</div>
          <div class="offline-hint">
            接入完成后,你可以基于当前简报向专家深问:<br>
            <template v-for="(q, i) in recommendQuestions.slice(0, 3)" :key="i">
              · {{ q }}<br>
            </template>
          </div>
        </div>

        <!-- 在线对话区 -->
        <template v-else>
          <!-- 推荐问题(空对话时显示) -->
          <div v-if="messages.length === 0" class="recommend-area">
            <div class="recommend-greeting">
              {{ agentInfo.greeting }}
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
                  <span class="msg-avatar">
                    <img v-if="avatarIsUrl" :src="agentInfo.avatar" :alt="agentInfo.name" class="msg-avatar-img" />
                    <template v-else>{{ agentInfo.avatar }}</template>
                  </span>
                  {{ agentInfo.name }}
                </div>
                <!-- 工具调用 chip 列表（仅 assistant 气泡，按时序展示 KB 检索 / 工作流） -->
                <div v-if="m.role === 'assistant' && m.toolCalls && m.toolCalls.length" class="tool-call-list">
                  <div
                    v-for="(tc, idx) in m.toolCalls"
                    :key="idx"
                    class="tool-call-chip"
                    :class="{ 'is-running': !tc.finishedAt }"
                  >
                    <span class="tc-icon">{{ toolIcon(tc.tool) }}</span>
                    <span class="tc-name">{{ toolLabel(tc.tool) }}</span>
                    <span class="tc-status">
                      <template v-if="!tc.finishedAt">
                        <span class="tc-spinner"></span>
                        <span class="tc-status-text">调用中…</span>
                      </template>
                      <template v-else>
                        <span class="tc-check">✓</span>
                        <span class="tc-status-text">{{ ((tc.finishedAt - tc.startedAt) / 1000).toFixed(1) }}s</span>
                      </template>
                    </span>
                  </div>
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

        <!-- resize zones: 四边和四角都可拖动,拖动后持久化到 localStorage -->
        <div
          v-for="zone in resizeZones"
          :key="zone"
          class="panel-resize-zone"
          :class="[`panel-resize-${zone}`, { 'panel-resize-grip-zone': zone === resizeGripZone }]"
          title="拖动调整面板大小"
          @mousedown.stop.prevent="onResizeStart($event, zone)"
          @touchstart.stop.prevent="onResizeStart($event, zone)"
        >
          <svg
            v-if="zone === resizeGripZone"
            class="panel-resize-grip"
            viewBox="0 0 14 14"
            width="12"
            height="12"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          >
            <path d="M2 12L12 2" />
            <path d="M6 12L12 6" />
            <path d="M10 12L12 10" />
          </svg>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { http } from '@/api/http'
import { getReportDoc, type BriefingDoc } from '@/api/report'
import { useMissionStore } from '@/stores/mission'

// 单例 md 渲染器：支持表格、列表、加粗、链接、emoji 等完整 GFM 子集
const md = new MarkdownIt({
  html: false,        // 不解析原始 HTML（防 XSS）
  linkify: true,      // URL 自动转链接
  breaks: true,       // 单换行 → <br>
  typographer: false, // 不做引号智能替换
})

const mission = useMissionStore()

interface ExpertStatus {
  enabled: boolean
  ready: boolean
  message: string
}
interface AgentInfo {
  name: string
  avatar: string
  subtitle: string
  description: string
  greeting: string
  open_questions: string[]
}
interface ToolCall {
  tool: string         // 工具名（知识库名 / 工作流名）
  thought?: string     // LLM 的思考文本
  input?: string       // 工具入参（已序列化）
  startedAt: number    // 开始时间戳，用来算耗时
  finishedAt?: number  // 结束时间戳
}
interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  toolCalls?: ToolCall[]   // 本轮 Agent 调用的工具列表（按时序）
}

const status = ref<ExpertStatus>({ enabled: false, ready: false, message: '正在检测专家状态' })
// agent-info 本地缓存：刷新后秒出真实配置，避免出现"经营分析陪伴专家"默认占位的闪烁
const AGENT_INFO_CACHE_KEY = 'zhqcm_expert_agent_info_v1'
function loadCachedAgentInfo(): AgentInfo | null {
  try {
    const raw = localStorage.getItem(AGENT_INFO_CACHE_KEY)
    if (!raw) return null
    const obj = JSON.parse(raw)
    if (obj && typeof obj === 'object' && obj.name) return obj as AgentInfo
  } catch { /* ignore */ }
  return null
}
const cachedAgent = loadCachedAgentInfo()
// 元信息默认值(后端 /agent-info 拉到后会覆盖;拉不到就用这套兜底)
const agentInfo = ref<AgentInfo>(cachedAgent || {
  name: '经营分析陪伴专家',
  avatar: '👨‍💼',
  subtitle: '由擎天平台提供企业知识增强',
  description: '',
  greeting: '您好,我是您的经营分析陪伴专家。已读取您当前查看的简报,可以围绕销售归因、售后异常、VOC 口碑、产品矩阵、行业基准等话题深问。',
  open_questions: [
    '这条结论的归因方法论是什么',
    '同比和环比的标准用法',
    '给我对比同价位竞品的产品定位',
    '这个数字符合行业基准吗',
  ],
})
// 头像是 URL(http(s) 开头)还是 emoji/文字
const avatarIsUrl = computed(() => /^https?:\/\//.test(agentInfo.value.avatar))
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const historyRef = ref<HTMLElement | null>(null)
// 当前会话 ID(擎天 SSE 首帧返回的 conversation_id);多轮对话用,新开会话清空
const conversationId = ref<string>('')

// 当前简报上下文:跟随 mission.briefFilename 异步拉取(用于 send payload)
const currentDoc = ref<BriefingDoc | null>(null)
const currentDocFilename = ref<string>('')

// ============ FAB 拖拽 + 位置持久化 ============
const FAB_SIZE = 60
// 默认面板尺寸（首次打开 / 重置时使用）。可通过右下角 handle 拖动调整,
// 调整后写到 localStorage,下次直接复用。
const DEFAULT_PANEL_W = 460
const DEFAULT_PANEL_H = 600
const PANEL_MIN_W = 360
const PANEL_MIN_H = 420
const PANEL_MAX_W = 900
const PANEL_MAX_H = 1080
const STORAGE_POS_KEY = 'zhqcm_expert_fab_pos_v1'
const STORAGE_SIZE_KEY = 'zhqcm_expert_panel_size_v1'
let hasStoredFabPos = false

const open = ref(false)
const dragging = ref(false)
const dragMoved = ref(false)  // 用来区分点击 vs 拖动
const fabRef = ref<HTMLElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
// 面板尺寸（可被右下角 handle 拖动改写,持久化到 localStorage）
const panelSize = ref<{ w: number; h: number }>(loadPanelSize())
const panelRect = ref<{ left: number; top: number } | null>(null)

// 默认右下角(距右 24,距下 96 给状态栏让位)
const pos = ref<{ x: number; y: number }>(loadPos())

function loadPanelSize(): { w: number; h: number } {
  try {
    const raw = localStorage.getItem(STORAGE_SIZE_KEY)
    if (raw) {
      const s = JSON.parse(raw)
      if (typeof s.w === 'number' && typeof s.h === 'number') return clampPanelSize(s.w, s.h)
    }
  } catch { /* ignore */ }
  return { w: DEFAULT_PANEL_W, h: DEFAULT_PANEL_H }
}

function clampPanelSize(w: number, h: number) {
  // 既不能比最小阈值小，也不能超出当前视口（留 24 边距）
  const maxW = Math.max(PANEL_MIN_W, Math.min(PANEL_MAX_W, window.innerWidth - 24))
  const maxH = Math.max(PANEL_MIN_H, Math.min(PANEL_MAX_H, window.innerHeight - 24))
  return {
    w: Math.min(Math.max(PANEL_MIN_W, w), maxW),
    h: Math.min(Math.max(PANEL_MIN_H, h), maxH),
  }
}

function persistPanelSize() {
  try {
    localStorage.setItem(STORAGE_SIZE_KEY, JSON.stringify(panelSize.value))
  } catch { /* ignore */ }
}

function loadPos(): { x: number; y: number } {
  try {
    const raw = localStorage.getItem(STORAGE_POS_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      if (typeof p.x === 'number' && typeof p.y === 'number') {
        hasStoredFabPos = true
        return clampPos(p.x, p.y)
      }
    }
  } catch { /* ignore */ }
  return defaultFabPos()
}

function defaultFabPos(): { x: number; y: number } {
  return clampPos(window.innerWidth - FAB_SIZE - 24, window.innerHeight - FAB_SIZE - 96)
}

function clampPos(x: number, y: number) {
  const maxX = Math.max(0, window.innerWidth - FAB_SIZE - 8)
  const maxY = Math.max(0, window.innerHeight - FAB_SIZE - 8)
  return {
    x: Math.min(Math.max(8, x), maxX),
    y: Math.min(Math.max(8, y), maxY),
  }
}

function persistPos() {
  hasStoredFabPos = true
  try {
    localStorage.setItem(STORAGE_POS_KEY, JSON.stringify(pos.value))
  } catch { /* ignore */ }
}

const fabStyle = computed(() => ({
  left: `${pos.value.x}px`,
  top: `${pos.value.y}px`,
}))

// 面板锚定:优先放在 FAB 左侧/上方,空间不够则反向
function computeAnchoredPanelRect(w: number, h: number) {
  const x = pos.value.x
  const y = pos.value.y
  // 水平:FAB 在屏幕右半 → 面板放左侧;否则放右侧
  let left: number
  if (x + FAB_SIZE / 2 > window.innerWidth / 2) {
    left = x - w - 12
    if (left < 12) left = 12
  } else {
    left = x + FAB_SIZE + 12
    if (left + w > window.innerWidth - 12) left = window.innerWidth - w - 12
  }
  // 垂直:按 FAB 在视口里的"上下进度"线性映射 panel 顶部位置——
  // FAB 拖到最上 → panel 紧贴视口顶,FAB 拖到最下 → panel 紧贴视口底,
  // 中间区段同步移动。避免 panel 高度接近 innerHeight 时,clamp 把 top
  // 钉在固定边界值导致"位置固定死"。
  const yRange = Math.max(1, window.innerHeight - FAB_SIZE)
  const ratio = Math.max(0, Math.min(1, y / yRange))
  const topMin = 12
  const topMax = Math.max(topMin, window.innerHeight - h - 12)
  const top = topMin + ratio * (topMax - topMin)
  return { left, top }
}

function clampPanelRect(left: number, top: number, w: number, h: number) {
  return {
    left: Math.min(Math.max(12, left), Math.max(12, window.innerWidth - w - 12)),
    top: Math.min(Math.max(12, top), Math.max(12, window.innerHeight - h - 12)),
  }
}

const panelStyle = computed(() => {
  const w = panelSize.value.w
  const h = panelSize.value.h
  const rect = panelRect.value
    ? clampPanelRect(panelRect.value.left, panelRect.value.top, w, h)
    : computeAnchoredPanelRect(w, h)
  return {
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${w}px`,
    height: `${h}px`,
  }
})

let dragStartX = 0
let dragStartY = 0
let dragOriginX = 0
let dragOriginY = 0

function getPoint(e: MouseEvent | TouchEvent): { x: number; y: number } {
  if ('touches' in e && e.touches.length) {
    return { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }
  const me = e as MouseEvent
  return { x: me.clientX, y: me.clientY }
}

function onDragStart(e: MouseEvent | TouchEvent) {
  // 仅左键触发拖拽
  if ('button' in e && e.button !== 0) return
  const p = getPoint(e)
  dragStartX = p.x
  dragStartY = p.y
  dragOriginX = pos.value.x
  dragOriginY = pos.value.y
  dragMoved.value = false
  dragging.value = true
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
  window.addEventListener('touchmove', onDragMove, { passive: false })
  window.addEventListener('touchend', onDragEnd)
}

function onDragMove(e: MouseEvent | TouchEvent) {
  if (!dragging.value) return
  if (e.cancelable) e.preventDefault?.()
  const p = getPoint(e)
  const dx = p.x - dragStartX
  const dy = p.y - dragStartY
  if (!dragMoved.value && Math.hypot(dx, dy) > 4) dragMoved.value = true
  pos.value = clampPos(dragOriginX + dx, dragOriginY + dy)
  if (open.value && !resizing.value) panelRect.value = null
}

function onDragEnd() {
  if (!dragging.value) return
  dragging.value = false
  if (dragMoved.value) persistPos()
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  window.removeEventListener('touchmove', onDragMove)
  window.removeEventListener('touchend', onDragEnd)
}

// ============ 面板拖拽缩放 ============
const resizing = ref(false)
const resizeZones = [
  'top',
  'right',
  'bottom',
  'left',
  'top-left',
  'top-right',
  'bottom-right',
  'bottom-left',
] as const
type ResizeZone = (typeof resizeZones)[number]

const activeResizeZone = ref<ResizeZone | null>(null)
const resizeGripZone = computed<ResizeZone>(() => {
  const panelOnLeft = pos.value.x + FAB_SIZE / 2 > window.innerWidth / 2
  const yRange = Math.max(1, window.innerHeight - FAB_SIZE)
  const panelAbove = Math.max(0, Math.min(1, pos.value.y / yRange)) > 0.5
  return `${panelAbove ? 'top' : 'bottom'}-${panelOnLeft ? 'left' : 'right'}` as ResizeZone
})

function resizeCursor(zone: ResizeZone | null) {
  if (!zone) return null
  if (zone === 'left' || zone === 'right') return 'ew'
  if (zone === 'top' || zone === 'bottom') return 'ns'
  if (zone === 'top-left' || zone === 'bottom-right') return 'nwse'
  return 'nesw'
}

const panelClasses = computed<Record<string, boolean>>(() => {
  const cursor = resizeCursor(activeResizeZone.value)
  return {
    'panel-resizing': resizing.value,
    [`panel-resizing-${cursor}`]: resizing.value && !!cursor,
  }
})

let resizeStartX = 0
let resizeStartY = 0
let resizeOriginLeft = 0
let resizeOriginTop = 0
let resizeOriginW = 0
let resizeOriginH = 0

function onResizeStart(e: MouseEvent | TouchEvent, zone: ResizeZone) {
  if ('button' in e && e.button !== 0) return
  if (e.cancelable) e.preventDefault()
  e.stopPropagation()
  const p = getPoint(e)
  const domRect = panelRef.value?.getBoundingClientRect()
  const fallbackRect = panelRect.value ?? computeAnchoredPanelRect(panelSize.value.w, panelSize.value.h)
  resizeStartX = p.x
  resizeStartY = p.y
  resizeOriginLeft = domRect?.left ?? fallbackRect.left
  resizeOriginTop = domRect?.top ?? fallbackRect.top
  resizeOriginW = domRect?.width ?? panelSize.value.w
  resizeOriginH = domRect?.height ?? panelSize.value.h
  panelRect.value = { left: resizeOriginLeft, top: resizeOriginTop }
  activeResizeZone.value = zone
  resizing.value = true
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', onResizeEnd)
  window.addEventListener('touchmove', onResizeMove, { passive: false })
  window.addEventListener('touchend', onResizeEnd)
}

function onResizeMove(e: MouseEvent | TouchEvent) {
  const zone = activeResizeZone.value
  if (!resizing.value || !zone) return
  if (e.cancelable) e.preventDefault?.()
  const p = getPoint(e)
  const dw = p.x - resizeStartX
  const dh = p.y - resizeStartY
  const originRight = resizeOriginLeft + resizeOriginW
  const originBottom = resizeOriginTop + resizeOriginH
  const maxViewportW = Math.max(PANEL_MIN_W, Math.min(PANEL_MAX_W, window.innerWidth - 24))
  const maxViewportH = Math.max(PANEL_MIN_H, Math.min(PANEL_MAX_H, window.innerHeight - 24))
  let left = resizeOriginLeft
  let top = resizeOriginTop
  let nextW = resizeOriginW
  let nextH = resizeOriginH

  if (zone.includes('left')) {
    const maxW = Math.min(maxViewportW, originRight - 12)
    nextW = Math.min(Math.max(PANEL_MIN_W, resizeOriginW - dw), maxW)
    left = originRight - nextW
  } else if (zone.includes('right')) {
    const maxW = Math.min(maxViewportW, window.innerWidth - resizeOriginLeft - 12)
    nextW = Math.min(Math.max(PANEL_MIN_W, resizeOriginW + dw), maxW)
  }

  if (zone.includes('top')) {
    const maxH = Math.min(maxViewportH, originBottom - 12)
    nextH = Math.min(Math.max(PANEL_MIN_H, resizeOriginH - dh), maxH)
    top = originBottom - nextH
  } else if (zone.includes('bottom')) {
    const maxH = Math.min(maxViewportH, window.innerHeight - resizeOriginTop - 12)
    nextH = Math.min(Math.max(PANEL_MIN_H, resizeOriginH + dh), maxH)
  }

  panelSize.value = { w: nextW, h: nextH }
  panelRect.value = clampPanelRect(left, top, nextW, nextH)
}

function onResizeEnd() {
  if (!resizing.value) return
  resizing.value = false
  activeResizeZone.value = null
  persistPanelSize()
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', onResizeEnd)
  window.removeEventListener('touchmove', onResizeMove)
  window.removeEventListener('touchend', onResizeEnd)
}

function onFabClick(e: MouseEvent) {
  // 拖拽过的不当点击
  if (dragMoved.value) {
    e.preventDefault()
    e.stopPropagation()
    return
  }
  open.value = !open.value
  panelRect.value = null
  // 打开面板时重新拉一次擎天 agent-info,这样在擎天平台改了开场白/推荐问题
  // 后,用户只需关掉再打开 FAB 就能看到最新配置,不必硬刷新整个页面。
  if (open.value) {
    fetchStatus()
    fetchAgentInfo()
    fetchOfflineMode()
  }
}

// 视口尺寸变化 → 重新夹紧位置 + 面板尺寸（避免视口缩小后 panel 溢出）
function onResize() {
  pos.value = hasStoredFabPos ? clampPos(pos.value.x, pos.value.y) : defaultFabPos()
  panelSize.value = clampPanelSize(panelSize.value.w, panelSize.value.h)
  if (panelRect.value) {
    panelRect.value = clampPanelRect(panelRect.value.left, panelRect.value.top, panelSize.value.w, panelSize.value.h)
  }
}

onMounted(() => {
  fetchStatus()
  fetchAgentInfo()
  fetchOfflineMode()
  window.addEventListener('resize', onResize)
  window.addEventListener('zhqcm:offline-mode', onOfflineModeEvent as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('zhqcm:offline-mode', onOfflineModeEvent as EventListener)
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  window.removeEventListener('touchmove', onDragMove)
  window.removeEventListener('touchend', onDragEnd)
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', onResizeEnd)
  window.removeEventListener('touchmove', onResizeMove)
  window.removeEventListener('touchend', onResizeEnd)
})

watch(open, (isOpen) => {
  if (!isOpen) {
    panelRect.value = null
    activeResizeZone.value = null
    resizing.value = false
    historyOpen.value = false
  }
})

// 推荐问题:优先用后端 agent-info 返回,但保留对 focusVehicle 的本地拼接(兜底单条)
const recommendQuestions = computed(() => {
  const fromAgent = agentInfo.value.open_questions
  if (fromAgent && fromAgent.length > 0) return fromAgent
  return [
    '这条结论的归因方法论是什么',
    '同比和环比的标准用法',
    `给我对比${mission.focusVehicle ? mission.focusVehicle + ' 与同价位竞品' : '同价位竞品'}的产品定位`,
    '这个数字符合行业基准吗',
  ]
})

// ============ 状态探活 ============
async function fetchStatus() {
  try {
    const { data } = await http.get<ExpertStatus>('/expert/status')
    status.value = data
  } catch {
    status.value = {
      enabled: false,
      ready: false,
      message: '后端未提供专家服务(/api/expert/status 不可达)',
    }
  }
}

// 演示模式开关: 跟随后端 /system/mode 的 offline_mode 字段
// 演示模式 ON → 走纯前端 mock 回放(零外网, 即时出字)
// 演示模式 OFF → 调真实擎天 SSE
const offlineMode = ref(false)
async function fetchOfflineMode() {
  try {
    const { data } = await http.get<{ data: { offline_mode?: boolean } }>('/system/mode')
    offlineMode.value = !!data?.data?.offline_mode
  } catch {
    // 后端不可用时保持当前值, 不强翻
  }
}
// App.vue 切换演示模式后会派发该事件, 不必等 30s 轮询
function onOfflineModeEvent(e: Event) {
  const ce = e as CustomEvent<{ offlineMode?: boolean }>
  if (ce?.detail && typeof ce.detail.offlineMode === 'boolean') {
    offlineMode.value = ce.detail.offlineMode
  }
}

// ============ 拉取 Agent 元信息 ============
async function fetchAgentInfo() {
  try {
    const { data } = await http.get<AgentInfo>('/expert/agent-info')
    if (data && typeof data === 'object') {
      const next: AgentInfo = {
        name: data.name || agentInfo.value.name,
        avatar: data.avatar || agentInfo.value.avatar,
        subtitle: data.subtitle || agentInfo.value.subtitle,
        description: data.description || '',
        greeting: data.greeting || agentInfo.value.greeting,
        open_questions: Array.isArray(data.open_questions) && data.open_questions.length > 0
          ? data.open_questions
          : agentInfo.value.open_questions,
      }
      agentInfo.value = next
      // 写回缓存：下次刷新无闪烁
      try { localStorage.setItem(AGENT_INFO_CACHE_KEY, JSON.stringify(next)) } catch { /* ignore */ }
    }
  } catch {
    // 拉不到就用默认值,不报错
  }
}

// ============ 跟随 mission.briefFilename 拉取上下文 ============
watch(
  () => mission.briefFilename,
  async (filename) => {
    if (!filename) {
      currentDoc.value = null
      currentDocFilename.value = ''
      return
    }
    if (filename === currentDocFilename.value) return
    currentDocFilename.value = filename
    try {
      currentDoc.value = await getReportDoc(filename)
    } catch {
      currentDoc.value = null
    }
  },
  { immediate: true },
)

// 切简报时清空对话(避免上下文穿越)
watch(() => mission.briefFilename, () => {
  messages.value = []
  conversationId.value = ''
})

// ============ 发送对话 ============
function askQuestion(q: string) {
  inputText.value = q
  send()
}

// 新开会话:清空消息列表 + 重置 conversation_id,下一次 send 会触发后端 create_conversation
function newConversation() {
  if (isStreaming.value) return
  messages.value = []
  conversationId.value = ''
  inputText.value = ''
}

// ============ 历史记录侧栏 ============
interface ConversationBrief {
  AppConversationID: string
  ConversationName: string
  CreateTime: string
  LastChatTime: string
  EmptyConversation: boolean
}

const historyOpen = ref(false)
const historyLoading = ref(false)
const historyError = ref('')
const historyList = ref<ConversationBrief[]>([])

// 打开/收起侧栏;打开时拉取最新列表
function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value) {
    loadHistoryList()
  }
}

async function loadHistoryList() {
  if (!status.value.ready) {
    historyError.value = '专家暂时离线,无法拉取历史'
    return
  }
  historyLoading.value = true
  historyError.value = ''
  try {
    const { data } = await http.get<{ ConversationList: ConversationBrief[] }>('/expert/conversations', {
      params: { limit: 30 },
    })
    historyList.value = Array.isArray(data?.ConversationList) ? data.ConversationList : []
  } catch (e: any) {
    historyList.value = []
    historyError.value = `历史拉取失败:${e?.message || '请稍后再试'}`
  } finally {
    historyLoading.value = false
  }
}

// 点击某条历史 → 拉取该会话消息并回填到对话区
async function loadHistoryConversation(cid: string) {
  if (!cid || isStreaming.value) return
  historyLoading.value = true
  try {
    const { data } = await http.get<{ messages: { role: 'user' | 'assistant'; content: string }[] }>(
      `/expert/conversations/${encodeURIComponent(cid)}/messages`,
      { params: { limit: 100 } },
    )
    const list = Array.isArray(data?.messages) ? data.messages : []
    // 兜底：如果某条 user 后面没有跟 assistant(擎天历史接口偶尔只回 Query 不回 Answer),
    // 插入一条占位消息,避免对话气泡看起来缺一半
    const fixed: ChatMessage[] = []
    for (let i = 0; i < list.length; i++) {
      const m = list[i]
      fixed.push({ role: m.role, content: m.content })
      const next = list[i + 1]
      if (m.role === 'user' && (!next || next.role !== 'assistant')) {
        fixed.push({
          role: 'assistant',
          content: '_（这条消息的回答未在历史中保留，可重新提问以获取最新答复）_',
        })
      }
    }
    messages.value = fixed
    conversationId.value = cid
    historyOpen.value = false
    await scrollToBottom()
  } catch (e: any) {
    historyError.value = `加载会话失败:${e?.message || '请稍后再试'}`
  } finally {
    historyLoading.value = false
  }
}

// 把 "2024-12-09 18:47:05" 显示成更友好的格式(今天 HH:MM / 昨天 / MM-DD)
function formatHistoryTime(ts: string): string {
  if (!ts) return ''
  // 形如 "2024-12-09 18:47:05" 或 ISO,都先解析
  const normalized = ts.includes('T') ? ts : ts.replace(' ', 'T')
  const d = new Date(normalized)
  if (isNaN(d.getTime())) return ts
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const yesterday = new Date(now.getTime() - 86400000)
  const isYesterday = d.toDateString() === yesterday.toDateString()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  if (sameDay) return `今天 ${hh}:${mm}`
  if (isYesterday) return `昨天 ${hh}:${mm}`
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${m}-${dd} ${hh}:${mm}`
}

async function send() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return
  inputText.value = ''

  messages.value.push({ role: 'user', content: text })
  const assistantMsg: ChatMessage = { role: 'assistant', content: '', streaming: true }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  await scrollToBottom()

  // 演示模式: 满足任一条件即走纯前端 mock 回放, 跳过擎天 SSE
  //   1) 全局演示模式开关打开 (App.vue 右上角"演示模式" pill, 来自后端 /system/mode)
  //   2) URL 显式带 ?mock=1 (调试 / 录屏脚本旁路用)
  // 纯前端 mock = 零外网, 即时出字, 工具调用 chip 也是模拟的, 适合演示现场
  //
  // 关键: 每次 send 都先 fetch 一次最新状态. 否则用户切换演示模式后
  // 如果还没重开过面板, 缓存的 offlineMode 会落后, 仍走真后端 SSE.
  // 这次 fetch 调本地后端 (~50ms), 不影响演示体验.
  const urlMock = typeof window !== 'undefined'
    && new URLSearchParams(window.location.search).get('mock') === '1'
  if (!urlMock) await fetchOfflineMode()
  const isMock = offlineMode.value || urlMock
  console.log('[expert] send mode=', isMock ? 'mock' : 'real', 'offlineMode=', offlineMode.value, 'urlMock=', urlMock)
  if (isMock) {
    try {
      await runMockReply(text, assistantMsg)
    } finally {
      assistantMsg.streaming = false
      isStreaming.value = false
      await scrollToBottom()
    }
    return
  }

  const payload = {
    user_query: text,
    focus_vehicle: mission.focusVehicle || '',
    briefing_title: currentDoc.value?.cover?.headline || currentDocFilename.value || '',
    briefing_summary: currentDoc.value?.executive_summary || '',
    briefing_sections: currentDoc.value?.sections
      ? JSON.stringify(currentDoc.value.sections.slice(0, 6).map(s => ({
          type: (s as any).type,
          title: (s as any).title,
          insight: (s as any).insight,
        })))
      : '',
    // 多轮对话:有 conversation_id 就带上,后端跳过 create_conversation 复用同一个会话
    conversation_id: conversationId.value || undefined,
  }

  try {
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
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx).trim()
        buf = buf.slice(idx + 2)
        if (!frame.startsWith('data:')) continue
        const data = frame.slice(5).trim()
        if (!data || data === '[DONE]') continue
        try {
          const obj = JSON.parse(data)
          // 把首帧带回的 conversation_id 缓存,后续追问复用,实现多轮
          if (obj.conversation_id && !conversationId.value) {
            conversationId.value = obj.conversation_id
          }
          // 工具调用事件（KB 检索 / 工作流调用）：单独累积成 chip
          if (obj.tool_call) {
            const tc = obj.tool_call
            if (!assistantMsg.toolCalls) assistantMsg.toolCalls = []
            const last = assistantMsg.toolCalls[assistantMsg.toolCalls.length - 1]
            // 同一个工具的连续 thought 帧合并到最后一条（thought 是流式累积的）
            if (last && last.tool === (tc.tool || '') && !last.finishedAt) {
              if (tc.thought) last.thought = (last.thought || '') + tc.thought
              if (tc.input) last.input = tc.input
            } else {
              // 上一条工具调用如果还没收尾，标记为完成
              if (last && !last.finishedAt) last.finishedAt = Date.now()
              assistantMsg.toolCalls.push({
                tool: tc.tool || '未命名工具',
                thought: tc.thought || '',
                input: tc.input || '',
                startedAt: Date.now(),
              })
            }
            await scrollToBottom()
            continue
          }
          // 工具调用结束事件（擎天 knowledge_retrieve_end 等）：把最后一个匹配 tool 的 chip 收尾
          if (obj.tool_call_end) {
            const te = obj.tool_call_end
            if (assistantMsg.toolCalls) {
              for (let i = assistantMsg.toolCalls.length - 1; i >= 0; i--) {
                const tc = assistantMsg.toolCalls[i]
                if (tc.tool === te.tool && !tc.finishedAt) {
                  // 优先用擎天返回的真实 latency（秒），转毫秒；缺失则回退到客户端时间差
                  if (typeof te.latency === 'number' && te.latency > 0) {
                    tc.finishedAt = tc.startedAt + Math.round(te.latency * 1000)
                  } else {
                    tc.finishedAt = Date.now()
                  }
                  break
                }
              }
            }
            continue
          }
          const delta =
            obj.delta ||
            obj.choices?.[0]?.delta?.content ||
            obj.text ||
            obj.content ||
            ''
          if (delta) {
            // 收到正文 token 时，把所有未收尾的工具调用 chip 标记为完成
            if (assistantMsg.toolCalls) {
              for (const tc of assistantMsg.toolCalls) {
                if (!tc.finishedAt) tc.finishedAt = Date.now()
              }
            }
            // 演示模式: URL ?fakeStream=1 时不立即追加,先把 delta 累积到 _fakeBuffer,
            // 等擎天流结束后在 finally 块里整段字符级回放,确保稳定的打字机效果.
            // 生产正常访问不受影响.
            const _fake = typeof window !== 'undefined'
              && new URLSearchParams(window.location.search).get('fakeStream') === '1'
            if (_fake) {
              (assistantMsg as any)._fakeBuffer = ((assistantMsg as any)._fakeBuffer || '') + delta
            } else {
              assistantMsg.content += delta
              await scrollToBottom()
            }
          }
          if (obj.error) {
            assistantMsg.content += `\n\n⚠️ ${obj.error}`
          }
        } catch {
          assistantMsg.content += data
        }
      }
    }
  } catch (e: any) {
    assistantMsg.content = `网络错误:${e?.message || String(e)}`
  } finally {
    // 流式结束：所有未收尾的工具调用全部标记完成
    if (assistantMsg.toolCalls) {
      for (const tc of assistantMsg.toolCalls) {
        if (!tc.finishedAt) tc.finishedAt = Date.now()
      }
    }
    // 演示兜底: fakeStream 模式下,
    //   - 擎天回答正常: 用累积的 _fakeBuffer 做字符级回放 (真实内容+稳定打字机)
    //   - 擎天回答 < 50 字 (炸了): 用预设 DEMO_FALLBACK_BENCHMARK 替代
    // 录屏脚本通过 window.__demoStreamReady 控制起播时机,避免在 phase 4 等待时就跑完
    const _fakeFinal = typeof window !== 'undefined'
      && new URLSearchParams(window.location.search).get('fakeStream') === '1'
    if (_fakeFinal) {
      const buffered = ((assistantMsg as any)._fakeBuffer || '').trim()
      const useBuffer = buffered.length >= 50
      const demoText = useBuffer ? buffered : DEMO_FALLBACK_BENCHMARK
      console.log('[expert-debug] fake playback: source=', useBuffer ? 'real' : 'demo', ' len=', demoText.length)
      assistantMsg.content = ''
      assistantMsg.streaming = true
      // 等录屏脚本解锁(最长 60s 兜底,自然超时也开始流)
      const waitStart = Date.now()
      while (!(window as any).__demoStreamReady && Date.now() - waitStart < 60000) {
        await new Promise(r => setTimeout(r, 100))
      }
      for (const ch of demoText) {
        assistantMsg.content += ch
        await scrollToBottom()
        await new Promise(r => setTimeout(r, 32))
      }
    }
    assistantMsg.streaming = false
    isStreaming.value = false
    await scrollToBottom()
  }
}

// ============ 演示模式 (?mock=1): 纯前端模拟 ============
// 演示时网络抖动/擎天降速也能稳定演示, 通过关键词路由不同 demo 文本.
// 与 fakeStream 区别: 完全不走 fetch, 不依赖后端, 启动即出.
interface MockScript {
  tools: { tool: string; latency: number }[]   // 模拟工具调用 chip + 单步耗时(ms)
  text: string                                  // 字符级回放正文
  charDelay?: number                            // 单字间隔, 默认 24ms
}

function pickMockScript(query: string): MockScript {
  const q = query.toLowerCase()
  // 行业基准 / 同价位竞品对比
  if (query.includes('基准') || query.includes('竞品') || query.includes('对比') || query.includes('同价位')) {
    return {
      tools: [
        { tool: 'knowledge_retrieval', latency: 350 },
        { tool: '行业基准对比器', latency: 500 },
      ],
      text: DEMO_FALLBACK_BENCHMARK,
    }
  }
  // 归因方法论
  if (query.includes('归因') || query.includes('方法论')) {
    return {
      tools: [
        { tool: 'knowledge_retrieval', latency: 300 },
        { tool: '销量归因引擎', latency: 450 },
      ],
      text: DEMO_ATTRIBUTION,
    }
  }
  // 同比环比标准用法
  if (query.includes('同比') || query.includes('环比')) {
    return {
      tools: [
        { tool: 'knowledge_retrieval', latency: 280 },
      ],
      text: DEMO_YOY_MOM,
    }
  }
  // 默认: 通用经营分析回答
  return {
    tools: [
      { tool: 'knowledge_retrieval', latency: 300 },
      { tool: '经营分析工作流', latency: 400 },
    ],
    text: DEMO_GENERIC,
  }
}

async function runMockReply(query: string, msg: ChatMessage) {
  const script = pickMockScript(query)
  msg.toolCalls = []
  // 串行模拟工具调用 chip
  for (const t of script.tools) {
    const tc: ToolCall = { tool: t.tool, startedAt: Date.now() }
    msg.toolCalls.push(tc)
    await scrollToBottom()
    await new Promise(r => setTimeout(r, t.latency))
    tc.finishedAt = Date.now()
    await scrollToBottom()
  }
  // 字符回放: 按 token 块输出, 整体演示更紧凑(总时长 < 3 秒)
  // 每帧吐 chunkSize 个字符, 帧间间隔 stepDelay ms.
  // 单字 24ms 太肉, 改成块 5 字 12ms 后, 800 字正文从 19s 降到 ~2s
  const stepDelay = script.charDelay ?? 12
  const chunkSize = 5
  const txt = script.text
  for (let i = 0; i < txt.length; i += chunkSize) {
    msg.content += txt.slice(i, i + chunkSize)
    await scrollToBottom()
    await new Promise(r => setTimeout(r, stepDelay))
  }
  await scrollToBottom()
}

const DEMO_ATTRIBUTION = `**第一段「直接回答」**

销量归因采用「品牌势能 × 产品力 × 渠道效率 × 价格策略」四因子拆解模型,数据来源于车型周度销量、终端报价、渠道铺货率、品牌搜索指数四个独立信号。

---

**第二段「拆解逻辑」**

| 因子 | 权重 | 数据源 | eπ007 当月得分 |
| --- | --- | --- | --- |
| 品牌势能 | 30% | 百度搜索指数 + 抖音话题量 | 78 / 100 |
| 产品力 | 30% | KOL 评测均分 + VOC 满意度 | 84 / 100 |
| 渠道效率 | 20% | 4S 店铺货率 + 试驾转化 | 72 / 100 |
| 价格策略 | 20% | 终端折扣率 vs 行业均值 | 81 / 100 |

综合得分 **78.9**, 在价格带 12 车型中排第 5 位.

---

**第三段「建议下一步」**

1. **补强渠道效率** [P0]: 试驾转化率 12.3% 落后行业均值 3.1pp, 重点优化销售话术
2. **保持产品力优势** [P1]: VOC 满意度 84 分高于竞品, 营销侧应放大用户口碑

---

**第四段「引用来源」**

👉 [KB] 《新能源销量四因子归因白皮书 v2.3》
👉 [工作流] 销量归因引擎 - 输出四因子得分 + 归因贡献度`

const DEMO_YOY_MOM = `**第一段「直接回答」**

同比 (YoY) 与环比 (MoM) 是经营分析最基础的两个时间序列指标,**同比看趋势,环比看节奏**.

---

**第二段「标准用法」**

| 指标 | 计算公式 | 适用场景 | 注意事项 |
| --- | --- | --- | --- |
| YoY 同比 | (本期 - 去年同期) / 去年同期 | 排除季节性, 看长期趋势 | 上市不满 1 年的车型不适用 |
| MoM 环比 | (本期 - 上期) / 上期 | 看短期变化和市场反应 | 受月份天数差异影响 |

---

**第三段「常见误区」**

1. **不要混用单位**: YoY 用百分点 (pp), MoM 用百分比 (%)
2. **春节月份特殊处理**: 1-2 月建议合并计算 YoY, 避免春节错位干扰
3. **新车上市首月**: MoM 无意义, 应等待第 3 个月再启用环比

---

**第四段「引用来源」**

👉 [KB] 《经营分析指标体系标准 v1.8》第 3.2 章`

const DEMO_GENERIC = `**第一段「直接回答」**

基于当前简报上下文,我已检索企业知识库中相关经营分析方法论与行业基准数据,为您整理如下结论.

---

**第二段「关键发现」**

| 维度 | 当前表现 | 行业基准 | 评价 |
| --- | --- | --- | --- |
| 销量增速 | +12.3% MoM | +4.1% MoM | **领先** |
| 终端均价 | 17.8 万 | 17.2 万 | 中位 |
| 用户满意度 | 84 / 100 | 78 / 100 | **领先** |

---

**第三段「建议下一步」**

1. **保持现有节奏** [P0]: 销量增速领跑同价位, 不建议大幅促销
2. **强化用户口碑传播** [P1]: NPS 优势可转化为社交媒体传播素材

---

**第四段「引用来源」**

👉 [KB] 《经营分析陪伴专家知识库 v3.1》
👉 [工作流] 经营分析工作流 - 三段式归因输出`

// 演示兜底文本: 当擎天接口返回空/失败时,fakeStream 模式注入这段做演示
// 内容围绕"奕派 eπ007 · 行业基准对比"主题,带 markdown 表格 + KB 引用,
// 充分展示「知识库检索 + 行业基准对比器工作流」双命中 + MD 渲染的产品力
const DEMO_FALLBACK_BENCHMARK = `**第一段「直接回答」**

根据《2026 年新能源乘用车行业基准数据》[KB] 与「行业基准对比器」工作流计算，奕派 eπ007 在 2026-04 当月销量 0.4 万台、价格带 15-20 万的表现处于 **行业第二梯队中位**：销量增速领先行业基准 8.2 个百分点，但绝对量距离同价位 TOP3 车型仍有 35-50% 差距。

---

**第二段「归因/拆解」**

| 对比维度 | eπ007 实绩 | 价格带均值 | 价格带 TOP1 | 差距/排名 |
| --- | --- | --- | --- | --- |
| 当月销量 | 0.4 万台 | 0.62 万台 | 1.02 万台 (Model Y) | 第 5 / 12 |
| MoM 环比 | +12.3% | +4.1% | -2.7% | **行业第 1** |
| YoY 同比 | +28.5% | +18.6% | +9.4% | 第 3 / 12 |
| 市占率 | 4.1% | 6.3% | 10.5% | 第 5 / 12 |
| 终端均价 | 17.8 万 | 17.2 万 | 18.9 万 | 中位 |

---

**第三段「建议下一步」**

1. **保持环比领跑势头** [P0]：当前 MoM +12.3% 是价格带第一，需稳住销售节奏避免过早促销稀释。
2. **缩短与 TOP3 销量差距** [P1]：销量绝对值在第 5 位，建议用 4-6 月聚焦核心城市冲量，目标进入 0.6 万台/月梯队。
3. **守住终端均价** [P1]：当前 17.8 万处于价格带中位，避免折扣战拉低品牌定位。

---

**第四段「引用来源」**

👉 [KB] 《2026 年新能源乘用车行业基准数据》- 价格带 15-20 万分组
👉 [工作流] 行业基准对比器 - 输出 12 车型横排，含 MoM/YoY/市占率/终端均价 4 维`

async function scrollToBottom() {
  await nextTick()
  if (historyRef.value) {
    historyRef.value.scrollTop = historyRef.value.scrollHeight
  }
}

// ============ Markdown 渲染（markdown-it，支持表格/列表/加粗/链接） ============
function renderMarkdown(src: string): string {
  if (!src) return ''
  return md.render(src)
}

// ============ 工具调用 chip 帮助函数 ============
// 擎天 agent_thought.tool 字段实测有几种形式：
//   "knowledge_retrieval" / "knowledge_base" → 知识库检索
//   "workflow:<工作流名>" 或 直接工作流中文名 → 工作流调用
function toolIcon(name: string): string {
  if (!name) return '🛠️'
  const n = name.toLowerCase()
  if (n.includes('knowledge') || n.includes('kb') || name.includes('知识')) return '📚'
  if (n.includes('workflow') || name.includes('工作流')) return '⚙️'
  if (name.includes('归因')) return '🎯'
  if (name.includes('基准') || name.includes('对比')) return '📊'
  if (name.includes('漏斗')) return '🔻'
  if (name.includes('竞品') || name.includes('矩阵')) return '⚔️'
  if (name.includes('合规')) return '🛡️'
  return '🛠️'
}

function toolLabel(name: string): string {
  if (!name) return '工具调用'
  const n = name.toLowerCase()
  if (n === 'knowledge_retrieval' || n === 'knowledge_base') return '知识库检索'
  if (n.startsWith('workflow:')) return `工作流 · ${name.slice(9)}`
  return name
}
</script>

<style scoped>
/* ========== FAB 浮动按钮 ========== */
.fab {
  position: fixed;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  /* 多层渐变：青绿主色 + 内圈高光 + 外圈环境光 */
  background:
    radial-gradient(circle at 30% 25%, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0) 38%),
    radial-gradient(circle at 70% 80%, rgba(14, 124, 123, 0.65) 0%, rgba(14, 124, 123, 0) 55%),
    linear-gradient(135deg, #2dd4bf 0%, #4ecdc4 55%, #14b8a6 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  user-select: none;
  z-index: 9998;
  /* 立体阴影 + 高光内描边，营造"悬浮在桌面上"的质感 */
  box-shadow:
    0 8px 22px rgba(45, 212, 191, 0.48),
    0 4px 12px rgba(0, 0, 0, 0.5),
    inset 0 1px 1px rgba(255, 255, 255, 0.7),
    inset 0 -2px 4px rgba(14, 124, 123, 0.5);
  transition: box-shadow .25s ease, transform .2s cubic-bezier(.2, .9, .3, 1.4);
  -webkit-tap-highlight-color: transparent;
  touch-action: none;
  animation: fab-float 4.5s ease-in-out infinite;
}

/* 呼吸光环: 演示时唯一的"擎天接入"亮点, 强化"看我!" */
.fab::before {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.30) 0%, rgba(45, 212, 191, 0) 70%);
  z-index: -1;
  pointer-events: none;
  animation: fab-pulse 2.6s ease-in-out infinite;
}
@keyframes fab-pulse {
  0%, 100% { transform: scale(1);    opacity: 0.5; }
  50%      { transform: scale(1.22); opacity: 0;   }
}

/* 离线态: 灰化 + 关掉呼吸光环 + 右上角红点提示 */
.fab.fab-offline {
  filter: grayscale(0.65) brightness(0.78);
  animation: none;
}
.fab.fab-offline::before { animation: none; opacity: 0; }
.fab-offline-dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--c-rust);
  box-shadow: 0 0 6px var(--c-rust), 0 0 0 2px rgba(5, 13, 17, 0.85);
  z-index: 3;
  pointer-events: none;
}
.fab::after {
  /* 1px 高光描边，让圆边在深色背景上更清晰 */
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.35);
  pointer-events: none;
}
.fab:hover {
  transform: scale(1.06) translateY(-1px);
  box-shadow:
    0 10px 22px rgba(20, 184, 166, 0.45),
    0 5px 12px rgba(0, 0, 0, 0.3),
    inset 0 1px 1px rgba(255, 255, 255, 0.6);
  animation-play-state: paused;
}
.fab-dragging {
  cursor: grabbing;
  transition: none;
  transform: scale(1.12);
  animation-play-state: paused;
}
.fab-open {
  /* 打开态：保留主题青绿，仅做"加深 + 微暖"提示，避免跳到与主题不一致的紫色 */
  background:
    radial-gradient(circle at 30% 25%, rgba(255, 255, 255, 0.4) 0%, rgba(255, 255, 255, 0) 38%),
    linear-gradient(135deg, #0e7c7b 0%, #14958f 55%, #0f766e 100%);
  box-shadow:
    0 14px 32px rgba(14, 124, 123, 0.55),
    0 6px 14px rgba(0, 0, 0, 0.32),
    inset 0 1px 1px rgba(255, 255, 255, 0.5);
}
.fab-icon {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  /* 让 SVG 内的高光跟着按钮微微浮动 */
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.18));
}

/* ===== 外圈光环：缓慢旋转的氛围光 ===== */
.fab-halo {
  position: absolute;
  inset: -1px;
  border-radius: 50%;
  background: conic-gradient(from 0deg,
    rgba(94, 234, 212, 0) 0%,
    rgba(94, 234, 212, 0.32) 25%,
    rgba(94, 234, 212, 0) 50%,
    rgba(94, 234, 212, 0.28) 75%,
    rgba(94, 234, 212, 0) 100%);
  filter: blur(2px);
  opacity: 0.45;
  z-index: 0;
  animation: fab-halo-rotate 10s linear infinite;
  pointer-events: none;
}
.fab-glow {
  position: absolute;
  inset: 4px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.32), rgba(255, 255, 255, 0) 55%);
  z-index: 1;
  pointer-events: none;
  animation: fab-glow-breath 3.5s ease-in-out infinite;
}

/* ===== 状态点已移除：未联调时整个 FAB 不渲染 ===== */
@keyframes fab-float {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-3px); }
}
@keyframes fab-halo-rotate {
  to { transform: rotate(360deg); }
}
@keyframes fab-glow-breath {
  0%, 100% { opacity: 0.55; }
  50%      { opacity: 0.95; }
}

/* ===== 机器人 SVG 动画 ===== */
/* 天线灯闪烁 */
.fab :deep(.bot-antenna) {
  transform-origin: 32px 6.5px;
  animation: bot-antenna-blink 2.2s ease-in-out infinite;
}
@keyframes bot-antenna-blink {
  0%, 92%, 100% { fill: #fef08a; opacity: 1; }
  50%           { fill: #fde047; opacity: 0.6; }
}
/* 屏幕扫描线缓慢上下移动 */
.fab :deep(.bot-scanline) {
  animation: bot-scan 3s ease-in-out infinite;
  opacity: 0.85;
}
@keyframes bot-scan {
  0%   { transform: translateY(0); opacity: 0.4; }
  50%  { transform: translateY(18px); opacity: 0.85; }
  100% { transform: translateY(0); opacity: 0.4; }
}
/* 眨眼睛：通过 scaleY 把眼睛压扁，配合高光一起做 */
.fab :deep(.bot-eye) {
  transform-origin: center;
  transform-box: fill-box;
  animation: bot-blink 4.2s ease-in-out infinite;
}
.fab :deep(.bot-eye-r) {
  /* 双眼同时眨，但 right 略微滞后 30ms 显得更自然 */
  animation-delay: 30ms;
}
.fab:hover :deep(.bot-eye) {
  /* hover 时眨得更勤，显得"被注视" */
  animation-duration: 2.4s;
}
@keyframes bot-blink {
  0%, 45%, 50%, 100% { transform: scaleY(1); }
  47%                { transform: scaleY(0.08); }
  92%                { transform: scaleY(1); }
  94%                { transform: scaleY(0.08); }
  96%                { transform: scaleY(1); }
}
/* 减少动效偏好 */
@media (prefers-reduced-motion: reduce) {
  .fab,
  .fab-halo,
  .fab-glow,
  .fab :deep(.bot-eye),
  .fab :deep(.bot-antenna),
  .fab :deep(.bot-scanline) {
    animation: none !important;
  }
}
</style>

<style>
/* 面板 Teleport 到 body,样式必须脱离 scoped */
.panel {
  position: fixed;
  z-index: 9999;
  border-radius: 14px;
  background: linear-gradient(180deg, #0e1c24 0%, #0a161c 100%);
  border: 1px solid var(--border-strong);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.65), 0 8px 20px rgba(0, 0, 0, 0.45);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
/* 拖动 resize 时禁用文本选择, 避免高亮闪烁 */
.panel.panel-resizing,
.panel.panel-resizing * {
  user-select: none !important;
}
.panel.panel-resizing-ew,
.panel.panel-resizing-ew * {
  cursor: ew-resize !important;
}
.panel.panel-resizing-ns,
.panel.panel-resizing-ns * {
  cursor: ns-resize !important;
}
.panel.panel-resizing-nwse,
.panel.panel-resizing-nwse * {
  cursor: nwse-resize !important;
}
.panel.panel-resizing-nesw,
.panel.panel-resizing-nesw * {
  cursor: nesw-resize !important;
}

/* ========== resize zones ========== */
.panel .panel-resize-zone {
  position: absolute;
  z-index: 20;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  touch-action: none;
}
.panel .panel-resize-left,
.panel .panel-resize-right {
  top: 12px;
  bottom: 12px;
  width: 10px;
  cursor: ew-resize;
}
.panel .panel-resize-left { left: -4px; }
.panel .panel-resize-right { right: -4px; }
.panel .panel-resize-top,
.panel .panel-resize-bottom {
  left: 12px;
  right: 12px;
  height: 10px;
  cursor: ns-resize;
}
.panel .panel-resize-top { top: -4px; }
.panel .panel-resize-bottom { bottom: -4px; }
.panel .panel-resize-top-left,
.panel .panel-resize-top-right,
.panel .panel-resize-bottom-right,
.panel .panel-resize-bottom-left {
  width: 32px;
  height: 32px;
}
.panel .panel-resize-top-left {
  top: 0;
  left: 0;
  cursor: nwse-resize;
}
.panel .panel-resize-top-right {
  top: 0;
  right: 0;
  cursor: nesw-resize;
}
.panel .panel-resize-bottom-right {
  right: 0;
  bottom: 0;
  cursor: nwse-resize;
}
.panel .panel-resize-bottom-left {
  bottom: 0;
  left: 0;
  cursor: nesw-resize;
}
.panel .panel-resize-left:hover,
.panel .panel-resize-right:hover {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.16), transparent);
}
.panel .panel-resize-top:hover,
.panel .panel-resize-bottom:hover {
  background: linear-gradient(180deg, rgba(45, 212, 191, 0.14), transparent);
}
.panel .panel-resize-grip-zone {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: color .15s, background .15s;
}
.panel .panel-resize-grip-zone:hover {
  color: var(--c-emerald);
  background: rgba(45, 212, 191, 0.08);
}
.panel .panel-resize-top-left .panel-resize-grip {
  transform: scale(-1, -1);
}
.panel .panel-resize-top-right .panel-resize-grip {
  transform: scaleY(-1);
}
.panel .panel-resize-bottom-left .panel-resize-grip {
  transform: scaleX(-1);
}

/* ========== 进入/退出动画 ========== */
.panel-pop-enter-active, .panel-pop-leave-active {
  transition: opacity .18s ease, transform .18s ease;
}
.panel-pop-enter-from, .panel-pop-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}

/* ========== 顶部头 ========== */
.panel .expert-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.08) 0%, rgba(45, 212, 191, 0.06) 100%);
  border-bottom: 1px solid var(--border-line);
}
.panel .head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.panel .head-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.panel .expert-avatar {
  font-size: 24px;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: rgba(22, 32, 40, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
  overflow: hidden;
}
.panel .avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
}
.panel .msg-avatar-img {
  width: 14px;
  height: 14px;
  object-fit: cover;
  border-radius: 3px;
  vertical-align: middle;
}
.panel .expert-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.3px;
}
.panel .expert-tag {
  margin-top: 2px;
  font-size: 10.5px;
  color: var(--c-mint);
  font-weight: 600;
  letter-spacing: 0.2px;
}
.panel .head-action {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 8px;
  border: 0;
  background: transparent;
  color: var(--c-mint);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
  font-family: inherit;
}
.panel .head-action:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.12);
  color: var(--c-emerald);
}
.panel .head-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.panel .history-btn {
  color: var(--text-secondary);
}
.panel .history-btn:hover:not(:disabled) {
  color: var(--c-emerald);
  background: rgba(45, 212, 191, 0.10);
}
.panel .history-btn.is-active {
  color: var(--c-emerald);
  background: rgba(45, 212, 191, 0.14);
}

/* ========== 历史记录侧边抽屉 ========== */
.panel .history-drawer {
  position: absolute;
  top: 56px;            /* 让位顶部 expert-head */
  left: 0;
  bottom: 0;
  width: 240px;
  z-index: 15;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #0d1a22 0%, #091319 100%);
  border-right: 1px solid var(--border-strong);
  box-shadow: 4px 0 18px rgba(0, 0, 0, 0.45);
}
.panel .history-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-line);
  background: rgba(45, 212, 191, 0.05);
}
.panel .history-drawer-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--c-mint);
  letter-spacing: 0.3px;
}
.panel .history-drawer-close {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
}
.panel .history-drawer-close:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary);
}
.panel .history-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px;
}
.panel .history-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 28px 12px;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-muted);
}
.panel .history-state-error {
  color: var(--c-rust);
}
.panel .history-spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(45, 212, 191, 0.2);
  border-top-color: var(--c-mint);
  animation: tc-spin 0.75s linear infinite;
}
.panel .history-empty-icon { font-size: 26px; }
.panel .history-retry {
  margin-top: 4px;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid var(--border-line);
  background: rgba(180, 230, 225, 0.04);
  color: var(--c-emerald);
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.panel .history-retry:hover {
  border-color: rgba(45, 212, 191, 0.4);
  background: rgba(45, 212, 191, 0.08);
}
.panel .history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.panel .history-item {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(180, 230, 225, 0.025);
  cursor: pointer;
  transition: all .15s;
}
.panel .history-item:hover {
  background: rgba(45, 212, 191, 0.08);
  border-color: rgba(45, 212, 191, 0.24);
}
.panel .history-item.is-active {
  background: rgba(45, 212, 191, 0.14);
  border-color: rgba(45, 212, 191, 0.45);
}
.panel .history-item-name {
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 600;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}
.panel .history-item-time {
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--text-muted);
  letter-spacing: 0.2px;
}

/* 抽屉滑入动画 */
.history-slide-enter-active,
.history-slide-leave-active {
  transition: transform .22s cubic-bezier(.2,.8,.3,1), opacity .22s ease;
}
.history-slide-enter-from,
.history-slide-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}
.panel .head-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
}
.panel .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.panel .status-online { background: #d1fae5; color: #065f46; }
.panel .status-online .status-dot {
  background: var(--c-moss);
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.18);
}
.panel .status-pending { background: rgba(45, 212, 191, 0.08); color: var(--c-emerald); }
.panel .status-pending .status-dot { background: var(--c-emerald); }
.panel .status-disabled { background: rgba(180, 230, 225, 0.03); color: var(--text-muted); }
.panel .status-disabled .status-dot { background: var(--text-muted); }
.panel .head-close {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
}
.panel .head-close:hover {
  background: rgba(15, 23, 42, 0.08);
  color: var(--text-primary);
}

/* ========== 当前简报上下文条 ========== */
.panel .ctx-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: rgba(180, 230, 225, 0.03);
  border-bottom: 1px solid var(--border-line);
  font-size: 11.5px;
  color: var(--text-secondary);
}
.panel .ctx-icon { font-size: 13px; }
.panel .ctx-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ========== 离线占位 ========== */
.panel .offline-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 32px 22px;
  text-align: center;
}
.panel .offline-icon { font-size: 38px; margin-bottom: 4px; }
.panel .offline-title { font-size: 14.5px; font-weight: 700; color: var(--text-primary); }
.panel .offline-desc { font-size: 12px; color: var(--text-muted); }
.panel .offline-hint {
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
.panel .recommend-area {
  padding: 14px;
  flex: 1;
  overflow-y: auto;
}
.panel .recommend-greeting {
  position: relative;
  padding: 12px 14px;
  background: rgba(45, 212, 191, 0.06);
  border: 1px solid rgba(45, 212, 191, 0.18);
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
  margin-bottom: 14px;
}
.panel .recommend-greeting::before {
  content: '';
  position: absolute;
  top: 0;
  left: 14px;
  right: 14px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.45), transparent);
}
.panel .recommend-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.panel .recommend-btn {
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
.panel .recommend-btn:hover {
  border-color: rgba(45, 212, 191, 0.32);
  background: rgba(45, 212, 191, 0.05);
  transform: translateX(2px);
}

/* ========== 对话历史 ========== */
.panel .history-area {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.panel .msg-row {
  display: flex;
  width: 100%;
}
.panel .msg-row.msg-user {
  justify-content: flex-end;
}
.panel .msg-bubble {
  max-width: 90%;
  padding: 9px 12px;
  border-radius: 12px;
  font-size: 12.5px;
  line-height: 1.65;
  word-break: break-word;
}
.panel .msg-user .msg-bubble {
  background: linear-gradient(135deg, var(--c-emerald-deep) 0%, #14958f 100%);
  color: #fff;
  border-radius: 12px 12px 2px 12px;
  box-shadow: 0 1px 6px rgba(14, 124, 123, 0.35);
}
.panel .msg-assistant .msg-bubble {
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
  color: var(--text-primary);
  border-radius: 12px 12px 12px 2px;
}
.panel .msg-author {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  color: var(--c-mint);
  margin-bottom: 4px;
  letter-spacing: 0.3px;
}
.panel .msg-avatar { font-size: 14px; }
.panel .msg-content p { margin: 0 0 6px; }
.panel .msg-content p:last-child { margin-bottom: 0; }
.panel .msg-content ul,
.panel .msg-content ol { margin: 4px 0; padding-left: 18px; }
.panel .msg-content li { margin-bottom: 2px; }
.panel .msg-content strong { color: var(--text-primary); font-weight: 700; }
.panel .msg-content em { color: var(--text-secondary); font-style: italic; }
.panel .msg-content a { color: var(--c-emerald); text-decoration: underline; }
.panel .msg-content h1,
.panel .msg-content h2,
.panel .msg-content h3,
.panel .msg-content h4 {
  margin: 8px 0 4px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
}
.panel .msg-content h1 { font-size: 14px; }
.panel .msg-content h2 { font-size: 13.5px; }
.panel .msg-content h3 { font-size: 13px; }
.panel .msg-content h4 { font-size: 12.5px; }
.panel .msg-content hr {
  margin: 8px 0;
  border: 0;
  border-top: 1px dashed var(--border-line);
}
.panel .msg-content code {
  padding: 1px 5px;
  background: rgba(180, 230, 225, 0.03);
  border-radius: 4px;
  font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
  font-size: 11.5px;
  color: #db2777;
}
.panel .msg-content pre {
  margin: 6px 0;
  padding: 8px 10px;
  background: var(--text-primary);
  color: var(--border-line);
  border-radius: 8px;
  overflow-x: auto;
  font-size: 11.5px;
  line-height: 1.5;
}
.panel .msg-content pre code {
  padding: 0;
  background: transparent;
  color: inherit;
}
.panel .msg-content blockquote {
  margin: 6px 0;
  padding: 6px 10px;
  border-left: 3px solid var(--c-mint);
  background: rgba(180, 230, 225, 0.025);
  color: var(--text-secondary);
  border-radius: 0 6px 6px 0;
}
/* GFM 表格：竞品矩阵/漏斗/合规自检的核心展示载体 */
.panel .msg-content table {
  display: block;
  width: 100%;
  margin: 6px 0;
  border-collapse: collapse;
  border-spacing: 0;
  overflow-x: auto;
  font-size: 11.5px;
  line-height: 1.5;
}
.panel .msg-content thead {
  background: rgba(78, 205, 196, 0.08);
}
.panel .msg-content th,
.panel .msg-content td {
  padding: 5px 8px;
  border: 1px solid var(--border-line);
  text-align: left;
  white-space: nowrap;
}
.panel .msg-content th {
  font-weight: 700;
  color: var(--c-emerald);
}
.panel .msg-content tbody tr:nth-child(even) {
  background: rgba(180, 230, 225, 0.025);
}
.panel .msg-content .cite {
  margin-top: 6px;
  padding: 4px 8px;
  background: var(--border-line);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
.panel .msg-streaming-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-mint);
  margin-top: 6px;
  animation: panel-pulse-dot 1s ease-in-out infinite;
}

/* ========== 工具调用 chip（KB/工作流） ========== */
.panel .tool-call-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  padding: 6px 8px;
  background: var(--bg-glass-strong);
  border: 1px solid rgba(45, 212, 191, 0.32);
  border-radius: 8px;
}
.panel .tool-call-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  font-size: 11px;
  color: var(--c-emerald);
  border-radius: 6px;
  background: rgba(180, 230, 225, 0.05);
}
.panel .tool-call-chip.is-running {
  background: rgba(99, 102, 241, 0.08);
}
.panel .tc-icon { flex-shrink: 0; font-size: 13px; }
.panel .tc-name {
  flex: 1;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.panel .tc-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--c-mint);
}
.panel .tc-spinner {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1.5px solid rgba(99, 102, 241, 0.25);
  border-top-color: var(--c-mint);
  animation: tc-spin 0.7s linear infinite;
}
@keyframes tc-spin {
  to { transform: rotate(360deg); }
}
.panel .tc-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--c-moss);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
}
.panel .tc-status-text { color: var(--text-secondary); }
.panel .tool-call-chip.is-running .tc-status-text { color: var(--c-mint); }
@keyframes panel-pulse-dot {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50%      { opacity: 1; transform: scale(1.3); }
}

/* ========== 输入区 ========== */
.panel .input-area {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border-line);
  background: rgba(180, 230, 225, 0.04);
}
.panel .input-textarea {
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
.panel .input-textarea:focus {
  border-color: var(--c-mint);
  background: rgba(180, 230, 225, 0.04);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}
.panel .input-textarea:disabled { opacity: 0.6; cursor: not-allowed; }
.panel .send-btn {
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
.panel .send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.panel .send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
