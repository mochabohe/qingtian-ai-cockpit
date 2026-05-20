<template>
  <el-container class="app-root">
    <el-aside width="252px" class="app-aside">
      <div class="aside-glow"></div>
      <div class="logo-card">
        <div class="logo-mark">
          <svg class="logo-svg" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <!-- 外环:数据圈 -->
            <circle cx="16" cy="16" r="12" opacity="0.45" />
            <!-- 内核:十字轴 + 中心节点(致敬"参谋"——指挥参考点) -->
            <circle cx="16" cy="16" r="6.5" />
            <circle cx="16" cy="16" r="2" fill="currentColor" stroke="none" />
            <path d="M16 4v4M16 24v4M4 16h4M24 16h4" />
            <!-- 4 颗外围数据节点(销售/售后/口碑/对标) -->
            <circle cx="16" cy="6" r="1.4" fill="currentColor" stroke="none" />
            <circle cx="26" cy="16" r="1.4" fill="currentColor" stroke="none" />
            <circle cx="16" cy="26" r="1.4" fill="currentColor" stroke="none" />
            <circle cx="6" cy="16" r="1.4" fill="currentColor" stroke="none" />
          </svg>
          <span class="logo-ring"></span>
        </div>
        <div class="logo-text">
          <div class="title">智擎参谋</div>
          <div class="subtitle">汽车经营全景 AI</div>
        </div>
      </div>

      <el-menu :default-active="activePath" :router="true" class="nav-menu">
        <!-- 主链路:用户跟着这 4 步看完整闭环 -->
        <div class="nav-section-h1">主链路</div>
        <el-menu-item index="/" class="nav-link nav-link-flow">
          <span class="step-num">1</span>
          <el-icon><HomeFilled /></el-icon>
          <span>经营任务台</span>
        </el-menu-item>

        <el-menu-item index="/agent" class="nav-link nav-link-flow">
          <span class="step-num">2</span>
          <el-icon><Cpu /></el-icon>
          <span>启动分析</span>
        </el-menu-item>
        <el-menu-item index="/report" class="nav-link nav-link-flow">
          <span class="step-num">3</span>
          <el-icon><Document /></el-icon>
          <span>战略简报</span>
        </el-menu-item>
        <el-menu-item index="/video" class="nav-link nav-link-flow">
          <span class="step-num">4</span>
          <el-icon><VideoCamera /></el-icon>
          <span>AI 视频</span>
          <!-- 视频任务进行中 → 环形 spinner;已完成且未读 → 红点呼吸 -->
          <span v-if="mission.videoStatus === 'running'" class="nav-spinner" title="视频合成中…"></span>
          <span v-else-if="mission.videoUnread" class="nav-dot" title="新视频已生成"></span>
        </el-menu-item>

        <!-- 一级:辅助证据(防御·算法可观测 + 业务延伸) -->
        <div class="nav-section-h1 nav-section-secondary">辅助证据</div>
        <el-menu-item index="/upload" class="nav-link">
          <el-icon><UploadFilled /></el-icon>
          <span>数据体检与算法验证</span>
        </el-menu-item>
        <el-menu-item index="/opportunity" class="nav-link">
          <el-icon><Aim /></el-icon>
          <span>VOC 机会地图</span>
        </el-menu-item>
        <el-menu-item index="/dashboard" class="nav-link">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据探索大屏</span>
        </el-menu-item>
      </el-menu>

      <!-- 左下角模型切换器:在 backend 已注册的 profile 之间切换,主力不稳时一键切 -->
      <div class="model-switcher">
        <el-dropdown
          trigger="click"
          placement="top-start"
          popper-class="model-switcher-popper"
          :disabled="modelSwitching"
          @command="handleSwitchModel"
        >
          <button class="model-switcher-btn" :class="{ 'is-switching': modelSwitching }">
            <span class="model-switcher-dot"></span>
            <div class="model-switcher-meta">
              <div class="model-switcher-label">LLM 模型</div>
              <div class="model-switcher-name">
                {{ activeModelLabel }}
                <span v-if="modelSwitching" class="model-switcher-spin"></span>
              </div>
            </div>
            <el-icon class="model-switcher-chev"><ArrowUpBold /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu class="model-switcher-menu">
              <el-dropdown-item
                v-for="p in modelProfiles"
                :key="p.id"
                :command="p.id"
                :disabled="modelSwitching"
                :class="{ 'is-active': p.id === activeModelId }"
              >
                <div class="model-item">
                  <div class="model-item-head">
                    <span class="model-item-label">{{ p.label }}</span>
                    <span v-if="p.id === activeModelId" class="model-item-tag">当前</span>
                  </div>
                  <div class="model-item-desc">{{ p.description }}</div>
                  <div class="model-item-meta">
                    <span class="meta-pill">{{
                      p.api_type === 'responses' ? '/v1/responses'
                      : p.api_type === 'messages' ? '/v1/messages'
                      : '/v1/chat/completions'
                    }}</span>
                    <span class="meta-pill">{{ p.model }}</span>
                  </div>
                </div>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-aside>

    <el-container>
      <el-main class="app-main">
        <div class="top-status-bar">
          <div class="status-cluster">
            <span class="status-pill" :class="`pill-${backendOk ? 'ok' : 'down'}`">
              <span class="status-dot"></span>
              <span>后端服务</span>
              <span class="pill-value">{{ backendOk ? '在线' : '离线' }}</span>
            </span>
            <span class="status-pill pill-info">
              <span class="status-dot"></span>
              <span>主线数据池</span>
              <span class="pill-value">{{ mission.dataReady }}/{{ mission.dataTotal }}</span>
            </span>
            <button
              class="status-pill pill-clickable"
              :class="offlineMode ? 'pill-warn' : 'pill-live'"
              :disabled="modeSwitching"
              :title="offlineMode
                ? '当前:演示模式(Agent 走预热缓存,~12s 完成,零外网依赖)。点击切换到真实 LLM 模式。'
                : '当前:真实 LLM 模式(走在线推理,~30s 完成)。点击切换到演示模式。'"
              @click="toggleOfflineMode"
            >
              <span class="status-dot"></span>
              <span>{{ offlineMode ? '演示模式' : '真实模式' }}</span>
              <span class="pill-value">{{ offlineMode ? '预热案例' : '在线 LLM' }}</span>
              <span v-if="modeSwitching" class="mode-switching"></span>
            </button>
          </div>
        </div>
        <!-- 全局工作流进度条已下线:产品/工程双视图下,"4 步线性流水线"
             暗示与新的导航分区冲突。需要时各页面可自行内嵌局部 stepper。 -->
        <router-view v-slot="{ Component }">
          <transition name="route-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>

    <!-- 全局浮动经营分析陪伴专家:右下角可拖动机器人,点击展开聊天 -->
    <FloatingExpertBot />
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { HomeFilled, UploadFilled, Cpu, Document, DataAnalysis, VideoCamera, Aim, ArrowUpBold } from '@element-plus/icons-vue'
import { useMissionStore } from '@/stores/mission'
import { http } from '@/api/http'
import FloatingExpertBot from '@/components/FloatingExpertBot.vue'

const route = useRoute()
const activePath = computed(() => route.path)
const mission = useMissionStore()

const backendOk = ref(false)
const offlineMode = ref(false)
const modeSwitching = ref(false)

// ============== LLM 模型切换(左下角下拉) ==============
interface LLMProfile {
  id: string
  label: string
  description: string
  provider: string
  base_url: string
  api_key: string
  model: string
  api_type: 'chat_completions' | 'responses' | 'messages'
}
const modelProfiles = ref<LLMProfile[]>([])
const activeModelId = ref<string>('')
const modelSwitching = ref(false)
const activeModelLabel = computed(() => {
  const p = modelProfiles.value.find(x => x.id === activeModelId.value)
  return p?.label || '加载中…'
})

async function pollLLMModel() {
  try {
    const { data } = await http.get('/system/llm-model')
    modelProfiles.value = data.data?.profiles || []
    activeModelId.value = data.data?.current?.id || ''
  } catch {
    // 后端未就绪 → 静默,模型切换 UI 显示「加载中…」
  }
}

async function handleSwitchModel(profileId: string) {
  if (profileId === activeModelId.value || modelSwitching.value) return
  const target = modelProfiles.value.find(x => x.id === profileId)
  if (!target) return
  const tip = `切到「${target.label}」后, 所有 Agent / 简报 / 对话调用将走\n${target.model} @ ${
    target.api_type === 'responses' ? '/v1/responses'
    : target.api_type === 'messages' ? '/v1/messages'
    : '/v1/chat/completions'
  }\n\n确认切换?`
  try {
    await ElMessageBox.confirm(tip, '切换 LLM 模型', {
      confirmButtonText: '确认切换',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  modelSwitching.value = true
  try {
    const { data } = await http.post('/system/llm-model', { profile_id: profileId })
    modelProfiles.value = data.data?.profiles || modelProfiles.value
    activeModelId.value = data.data?.current?.id || profileId
    ElMessage.success(`已切到 ${target.label}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '切换失败')
  } finally {
    modelSwitching.value = false
  }
}

async function pollSystemMode() {
  try {
    const { data } = await http.get('/system/mode')
    backendOk.value = true
    offlineMode.value = !!data.data?.offline_mode
  } catch {
    backendOk.value = false
  }
}

// 启动扫一次视频任务历史:把最近一条已完成任务回填到 mission store。
// 解决"VideoStudio 已经成功合成过视频,但 MissionBar 仍然显示「视频待生成」"的 bug ——
// 原来只在 VideoStudio 当前轮询的任务完成时才回写,刷新页面或第一次进首页都不会触发。
async function syncLatestVideoFromHistory() {
  try {
    const { data } = await http.get('/video/list')
    const items = (data.data || []) as any[]
    // 任意一条 status=0(进行中)就算 running
    const running = items.find((t: any) => t.status === 0)
    if (running) {
      mission.videoStatus = 'running'
      return
    }
    // 否则取最近一条 status=1 + 有 final_mp4 的回填
    const done = items.find((t: any) => t.status === 1 && t.artifacts?.final_mp4)
    if (done) {
      // 已有相同 id 不重复触发未读(避免每次刷新都重新闪红点)
      if (mission.videoTaskId !== done.id) {
        mission.videoTaskId = done.id
      }
      mission.videoStatus = 'done'
    }
  } catch {
    // 后端未起 / 接口不可用 → 静默,菜单按 store 现有状态显示
  }
}

async function toggleOfflineMode() {
  // 演示模式是演示关键防线,误切风险高,加 confirm
  const target = !offlineMode.value
  const tip = target
    ? '切到「演示模式」后,Agent 编排会走预热缓存(~12s),不调外网 LLM。\n适用场景:演示现场、演示视频录制、断网应急。\n\n确认切换?'
    : '切到「真实模式」后,Agent 编排会调外网 LLM(~30s),需稳定网络。\n适用场景:开发/调试、跑新简报、生产环境。\n\n确认切换?'
  try {
    await ElMessageBox.confirm(tip, target ? '启用演示模式' : '切回真实模式', {
      confirmButtonText: '确认切换',
      cancelButtonText: '取消',
      type: target ? 'warning' : 'info',
    })
  } catch {
    return  // 用户取消
  }
  modeSwitching.value = true
  try {
    const { data } = await http.post('/system/mode', { offline_mode: target })
    offlineMode.value = !!data.data?.offline_mode
    // 通知全局组件(FloatingExpertBot 等)立即同步, 不必等下一轮 30s 轮询
    window.dispatchEvent(new CustomEvent('zhqcm:offline-mode', { detail: { offlineMode: offlineMode.value } }))
    ElMessage.success(target ? '已切到演示模式 · Agent 走预热缓存' : '已切到真实模式 · Agent 调真 LLM')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '切换失败')
  } finally {
    modeSwitching.value = false
  }
}

onMounted(() => {
  pollSystemMode()
  pollLLMModel()
  syncLatestVideoFromHistory()
  // 每 30s 复探一次后端状态(轻量,不轮询业务接口)
  setInterval(pollSystemMode, 30000)
  // 模型切换是低频操作,但跨标签页/多人协作时偶尔需要同步,60s 拉一次
  setInterval(pollLLMModel, 60000)
  // 视频状态每 15s 回探一次,用于"在 VideoStudio 之外的页面操作完合成回首页时"
  // 也能更新菜单红点 / spinner(VideoStudio 内部仍然有自己的 2s 轮询,精度更高)
  setInterval(syncLatestVideoFromHistory, 15000)
})

// 路由守卫:进入 /video 路由时清未读红点(用户已经看到结果了)
watch(() => route.path, (p: string) => {
  if (p === '/video') mission.videoUnread = false
})
</script>

<style scoped>
.app-root {
  height: 100vh;
  background: transparent;
}

.app-aside {
  position: relative;
  padding: 22px 14px 24px;
  background:
    linear-gradient(180deg, rgba(10, 22, 28, 0.94) 0%, rgba(5, 13, 17, 0.98) 100%);
  border-right: 1px solid var(--border-line);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
}
/* 侧边栏顶部 hairline 极弱金线 */
.aside-glow {
  position: absolute;
  top: 0;
  left: 18px;
  right: 18px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.35), transparent);
  pointer-events: none;
  z-index: 0;
}

.logo-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 4px 16px;
  border-bottom: 1px solid var(--border-line);
  z-index: 1;
}

.logo-mark {
  position: relative;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #163040 0%, #0a161c 100%);
  border: 1px solid rgba(45, 212, 191, 0.40);
  box-shadow:
    inset 0 1px 0 rgba(45, 212, 191, 0.22),
    0 4px 14px rgba(0, 8, 12, 0.55);
  color: var(--c-emerald);
}
.logo-svg {
  position: relative;
  z-index: 2;
  width: 26px;
  height: 26px;
  filter: drop-shadow(0 0 6px currentColor);
}
.logo-ring {
  position: absolute;
  inset: -3px;
  border-radius: 12px;
  border: 1px solid rgba(45, 212, 191, 0.18);
  pointer-events: none;
}

.logo-text .title {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', 'Noto Serif SC', Georgia, serif;
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 1px;
  line-height: 1.1;
}

.logo-text .subtitle {
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 1.4px;
  text-transform: uppercase;
}

.nav-menu {
  position: relative;
  z-index: 1;
  margin-top: 14px;
  background: transparent;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 一级标题: 纯排版,无装饰色块 */
.nav-section-h1 {
  position: relative;
  margin: 22px 14px 8px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 2px;
  text-transform: uppercase;
}
.nav-section-h1:first-child { margin-top: 8px; }
.nav-section-secondary {
  margin-top: 24px;
  padding-top: 14px;
  border-top: 1px solid var(--border-line);
}

.nav-section-sub {
  margin: 0 14px 10px;
  font-size: 10.5px;
  color: var(--text-dim);
  letter-spacing: 0.2px;
  font-weight: 400;
  line-height: 1.5;
}

.nav-link {
  position: relative;
  height: 42px !important;
  border-radius: 8px;
  color: var(--text-secondary) !important;
  font-size: 13.5px !important;
  margin: 0 !important;
  padding-left: 14px !important;
  background: transparent !important;
  transition: all .15s ease;
}

.nav-menu :deep(.el-menu-item .el-icon) {
  color: var(--text-muted);
  font-size: 16px;
}

.nav-menu :deep(.el-menu-item:hover) {
  background: rgba(240, 236, 228, 0.04) !important;
  color: var(--text-primary) !important;
}
.nav-menu :deep(.el-menu-item:hover .el-icon) { color: var(--c-emerald); }

/* active 项: 不用左侧竖条纹,改用淡琥珀背景 + 右侧小圆点 */
.nav-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.10) 0%, rgba(45, 212, 191, 0.02) 100%) !important;
  color: var(--text-primary) !important;
}
.nav-menu :deep(.el-menu-item.is-active::after) {
  content: '';
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--c-emerald);
  box-shadow: 0 0 10px rgba(45, 212, 191, 0.7);
}
/* 状态指示符(spinner / 红点)占据右侧位时,隐藏 active 小绿点避免双圆撞在一起 */
.nav-menu :deep(.el-menu-item.is-active:has(.nav-spinner)::after),
.nav-menu :deep(.el-menu-item.is-active:has(.nav-dot)::after) {
  display: none;
}
.nav-menu :deep(.el-menu-item.is-active .el-icon) { color: var(--c-emerald); }

/* 工作台主线项的步骤编号: 衬线数字小标 */
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: rgba(240, 236, 228, 0.04);
  border: 1px solid var(--border-line);
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 600;
  margin-right: 6px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  font-family: 'Cormorant Garamond', Georgia, serif;
}
.nav-link-flow:hover .step-num {
  color: var(--c-emerald);
  border-color: rgba(45, 212, 191, 0.35);
}
.nav-menu :deep(.el-menu-item.nav-link-flow.is-active) .step-num {
  background: rgba(45, 212, 191, 0.18);
  border-color: rgba(45, 212, 191, 0.45);
  color: var(--c-emerald);
}

/* 菜单项右侧状态指示:视频合成中 → 蓝色环形 spinner */
.nav-spinner {
  margin-left: auto;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(45, 212, 191, 0.25);
  border-top-color: var(--c-emerald);
  border-radius: 50%;
  flex-shrink: 0;
  animation: nav-spin 0.85s linear infinite;
}
@keyframes nav-spin { to { transform: rotate(360deg); } }

/* 菜单项右侧状态指示:视频已生成且未读 → 红点呼吸动画 */
.nav-dot {
  margin-left: auto;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #ef4444;
  flex-shrink: 0;
  box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.55);
  animation: nav-pulse 1.6s ease-in-out infinite;
}
@keyframes nav-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(239, 68, 68, 0.55); }
  70%  { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);    }
  100% { box-shadow: 0 0 0 0   rgba(239, 68, 68, 0);    }
}

.top-status-bar {
  position: relative;
  z-index: 30;
  display: flex;
  justify-content: flex-end;
  margin-bottom: 14px;
  pointer-events: none;
}
.status-cluster {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 5px 8px;
  border-radius: 999px;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--shadow-card);
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
  background: rgba(240, 236, 228, 0.04);
  border: 1px solid var(--border-line);
  color: var(--text-secondary);
  font-family: inherit;
  outline: none;
  line-height: 1.2;
  letter-spacing: 0.3px;
}
button.status-pill { cursor: pointer; }
.status-pill .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 6px currentColor;
}
.status-pill .pill-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-left: 2px;
  color: var(--text-primary);
}

.pill-ok {
  background: rgba(138, 153, 112, 0.10);
  border-color: rgba(138, 153, 112, 0.32);
  color: #b3c094;
}
.pill-ok .status-dot { background: var(--c-moss); color: var(--c-moss); }
.pill-down {
  background: rgba(196, 122, 94, 0.10);
  border-color: rgba(196, 122, 94, 0.40);
  color: #d99a7e;
}
.pill-down .status-dot { background: var(--c-rust); color: var(--c-rust); }
.pill-info {
  background: rgba(125, 169, 185, 0.10);
  border-color: rgba(125, 169, 185, 0.32);
  color: var(--c-teal);
}
.pill-info .status-dot { background: var(--c-teal); color: var(--c-teal); }
.pill-warn {
  background: rgba(45, 212, 191, 0.10);
  border-color: rgba(45, 212, 191, 0.45);
  color: var(--c-emerald);
}
.pill-warn .status-dot {
  background: var(--c-emerald);
  color: var(--c-emerald);
  animation: pill-pulse 1.6s ease-in-out infinite;
}

.pill-live {
  background: rgba(45, 212, 191, 0.08);
  border-color: rgba(45, 212, 191, 0.32);
  color: var(--c-emerald);
}
.pill-live .status-dot { background: var(--c-emerald); color: var(--c-emerald); }

.pill-clickable {
  cursor: pointer;
  font-family: inherit;
  position: relative;
  transition: all .15s;
}
.pill-clickable:hover {
  filter: brightness(1.15);
  border-color: var(--c-emerald);
}
.pill-clickable:active { transform: translateY(0); }
.pill-clickable:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.mode-switching {
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  margin-left: 4px;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

@keyframes pill-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.45; }
}

.app-main {
  background: transparent;
  padding: 18px 28px 28px;
  overflow: auto;
}

.route-fade-enter-active,
.route-fade-leave-active {
  transition:
    opacity 0.26s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.26s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.26s cubic-bezier(0.22, 1, 0.36, 1);
}

.route-fade-enter-from {
  opacity: 0;
  transform: translateY(12px);
  filter: blur(4px);
}

.route-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
  filter: blur(3px);
}

/* =========================================================================
 * 左下角模型切换器
 * 主力 profile 不稳时可一键切到备选 profile 兜底
 * ========================================================================= */
.model-switcher {
  margin-top: auto;
  padding: 14px 6px 4px;
  position: relative;
  z-index: 1;
}

.model-switcher-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.06) 0%, rgba(45, 212, 191, 0.01) 100%);
  border: 1px solid var(--border-line);
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s ease;
  outline: none;
  line-height: 1.25;
  text-align: left;
}
.model-switcher-btn:hover {
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.12) 0%, rgba(45, 212, 191, 0.04) 100%);
  border-color: rgba(45, 212, 191, 0.45);
  color: var(--text-primary);
}
.model-switcher-btn:active { transform: translateY(1px); }
.model-switcher-btn.is-switching { opacity: 0.7; cursor: progress; }

.model-switcher-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-emerald);
  box-shadow: 0 0 8px rgba(45, 212, 191, 0.6);
  flex-shrink: 0;
  animation: pill-pulse 2.4s ease-in-out infinite;
}

.model-switcher-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.model-switcher-label {
  font-size: 9.5px;
  letter-spacing: 1.8px;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 600;
}
.model-switcher-name {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  letter-spacing: 0.3px;
  font-variant-numeric: tabular-nums;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.model-switcher-spin {
  width: 10px;
  height: 10px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
.model-switcher-chev {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
  transition: transform .2s ease;
}
.model-switcher-btn:hover .model-switcher-chev {
  color: var(--c-emerald);
  transform: translateY(-1px);
}

@media (max-width: 900px) {
  .app-aside {
    width: 76px !important;
    padding: 16px 10px;
  }

  .logo-text,
  .nav-section-h1,
  .nav-link span:not(.step-num):not(.nav-spinner):not(.nav-dot),
  .status-pill span:not(.status-dot):not(.mode-switching),
  .model-switcher-meta,
  .model-switcher-chev {
    display: none;
  }

  .model-switcher {
    padding: 12px 4px 4px;
    display: flex;
    justify-content: center;
  }
  .model-switcher-btn {
    width: 44px;
    justify-content: center;
    padding: 10px 0;
  }

  .logo-card {
    justify-content: center;
    padding-bottom: 14px;
  }

  .nav-link {
    justify-content: center;
    padding-left: 0 !important;
  }

  .step-num {
    margin-right: 0;
  }

  .app-main {
    padding: 14px 14px 22px;
  }
}
</style>

<!-- 非 scoped: el-dropdown 的 popper teleport 到 body, scoped style 命中不到 -->
<style>
.model-switcher-popper.el-popper {
  background: linear-gradient(180deg, rgba(12, 26, 33, 0.98) 0%, rgba(6, 16, 21, 0.99) 100%) !important;
  border: 1px solid rgba(45, 212, 191, 0.30) !important;
  border-radius: 12px !important;
  padding: 6px !important;
  min-width: 280px;
  box-shadow:
    0 18px 48px rgba(0, 6, 10, 0.55),
    0 0 0 1px rgba(45, 212, 191, 0.08) inset !important;
  backdrop-filter: blur(18px) saturate(120%);
  -webkit-backdrop-filter: blur(18px) saturate(120%);
}
.model-switcher-popper .el-popper__arrow::before {
  background: rgba(12, 26, 33, 0.98) !important;
  border-color: rgba(45, 212, 191, 0.30) !important;
}
.model-switcher-popper .el-dropdown-menu {
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
}
.model-switcher-popper .el-dropdown-menu__item {
  padding: 10px 12px !important;
  border-radius: 8px !important;
  color: var(--text-secondary) !important;
  line-height: 1.4 !important;
  transition: background .15s ease;
}
.model-switcher-popper .el-dropdown-menu__item:not(.is-disabled):hover {
  background: rgba(45, 212, 191, 0.08) !important;
  color: var(--text-primary) !important;
}
.model-switcher-popper .el-dropdown-menu__item.is-active {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.14) 0%, rgba(45, 212, 191, 0.04) 100%) !important;
  color: var(--text-primary) !important;
}
.model-switcher-popper .model-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.model-switcher-popper .model-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-switcher-popper .model-item-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
}
.model-switcher-popper .model-item-tag {
  font-size: 9.5px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(45, 212, 191, 0.18);
  color: var(--c-emerald);
  border: 1px solid rgba(45, 212, 191, 0.45);
  letter-spacing: 1px;
  font-weight: 600;
}
.model-switcher-popper .model-item-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
.model-switcher-popper .model-item-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 2px;
}
.model-switcher-popper .meta-pill {
  font-size: 9.5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(240, 236, 228, 0.04);
  border: 1px solid var(--border-line);
  color: var(--text-muted);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  letter-spacing: 0.2px;
}
</style>
