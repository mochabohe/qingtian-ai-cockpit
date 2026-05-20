<template>
  <div class="video-studio">
    <!-- 经营任务单(P0-1):跨页面共享当前任务上下文 -->
    <MissionBar />
    <!-- 顶部操作 -->
    <section class="action-card video-command">
      <div class="studio-main">
        <div class="action-head">
          <div>
            <div class="studio-eyebrow">AI VIDEO BRIEFING</div>
            <div class="section-title">AI 业务视频工作室</div>
            <div class="section-subtitle">
              选一份简报,自动拆分镜、配音、字幕,生成可播放的业务播报视频。
            </div>
          </div>
          <el-tag effect="dark" round class="brand-tag">商务 + 科技</el-tag>
        </div>

        <div class="production-points" aria-label="视频生产链路">
          <span>简报拆镜</span>
          <span>TTS 配音</span>
          <span>字幕烧录</span>
          <span>MP4 导出</span>
        </div>

        <div class="action-row">
          <el-select
            v-model="selectedReport"
            placeholder="选择简报来源"
            filterable
            class="report-picker"
            size="large"
          >
            <el-option
              v-for="r in reports"
              :key="r.name"
              :label="r.name"
              :value="r.name"
            >
              <span class="picker-name">{{ r.name }}</span>
              <span class="picker-tag" v-if="r.has_doc">结构化</span>
            </el-option>
          </el-select>

          <el-button
            type="primary"
            size="large"
            :loading="generating"
            :disabled="!selectedReport"
            @click="startGenerate"
            class="generate-btn"
          >
            {{ generating ? '正在合成...' : '开始合成视频' }}
          </el-button>

          <el-button size="large" class="theme-refresh" @click="loadReports" :icon="Refresh">刷新</el-button>
        </div>

        <div v-if="task" class="task-status">
          <div class="status-line">
            <span class="status-label">任务 ID</span>
            <code>{{ task.id }}</code>
            <el-tag :type="statusType" size="small" effect="dark">{{ statusText }}</el-tag>
            <span v-if="task.model" class="model-chip">{{ task.model }} · {{ task.resolution || '1080p' }}</span>
          </div>
          <div v-if="task.artifacts?.notes?.length" class="status-notes">
            <div v-for="(n, i) in task.artifacts.notes" :key="i" class="note">· {{ n }}</div>
          </div>
          <el-progress
            v-if="task.status === 0"
            :percentage="progressPercent"
            :stroke-width="8"
            status="success"
            :indeterminate="task.status === 0"
            :duration="2"
          />
          <div v-if="task.status === 0" class="stage-strip">
            <span class="stage-text">{{ stageHint }}</span>
            <span class="stage-eta">
              <span class="elapsed">已等 {{ elapsedHint }}</span>
              <span class="eta-sep">·</span>
              <span>预计剩余 <b>{{ etaHint }}</b></span>
            </span>
          </div>
          <!-- 实时进度面板:已出 N/M 段画面 + 单段时间线 -->
          <div v-if="task.status === 0 && task.progress" class="progress-detail">
            <div v-if="renderProgressHint" class="progress-summary">{{ renderProgressHint }}</div>
            <div v-if="task.progress.scene_timeline?.length" class="scene-timeline">
              <div
                v-for="item in task.progress.scene_timeline"
                :key="item.index"
                class="timeline-item done"
              >
                <span class="ti-dot" />
                <span class="ti-label">第 {{ item.index }} 段画面</span>
                <span class="ti-meta">{{ Math.round(item.size_kb / 1024 * 10) / 10 }} MB · {{ formatClock(item.ready_at) }}</span>
              </div>
              <!-- 当前正在出片的占位 -->
              <div
                v-if="task.progress.scenes_ready < task.progress.total_scenes"
                class="timeline-item pending"
              >
                <span class="ti-dot pulsing" />
                <span class="ti-label">第 {{ task.progress.scenes_ready + 1 }} 段画面</span>
                <span class="ti-meta">生成中…</span>
              </div>
              <!-- 未开始的剩余幕,灰色占位 -->
              <div
                v-for="i in Math.max(0, task.progress.total_scenes - task.progress.scenes_ready - 1)"
                :key="`waiting-${i}`"
                class="timeline-item waiting"
              >
                <span class="ti-dot" />
                <span class="ti-label">第 {{ task.progress.scenes_ready + 1 + i }} 段画面</span>
                <span class="ti-meta">排队中</span>
              </div>
            </div>
          </div>
          <div v-if="task.error" class="task-error">⚠️ {{ task.error }}</div>
        </div>
      </div>

      <aside class="video-stage" aria-label="视频预览舞台">
        <div class="stage-screen">
          <video
            v-if="heroPreviewTask?.artifacts?.final_mp4"
            :src="fileUrl(heroPreviewTask.artifacts.final_mp4)"
            :poster="heroPreviewPoster ? fileUrl(heroPreviewPoster) : undefined"
            muted
            loop
            autoplay
            playsinline
          />
          <img
            v-else-if="heroPreviewPoster"
            :src="fileUrl(heroPreviewPoster)"
            alt=""
          />
          <div v-else class="stage-empty">
            <img
              class="stage-empty-art"
              src="/assets/gpt-image2/agent-factory-line.png"
              alt=""
            />
            <div class="stage-hud">
              <span>待生成预览</span>
              <b>16:9</b>
            </div>
            <span class="stage-scanline"></span>
          </div>
        </div>
        <div class="stage-footer">
          <span>Seedance · {{ heroPreviewTask?.resolution || '1080p' }}</span>
          <b>{{ heroSceneCount }} 幕业务播报</b>
        </div>
      </aside>
    </section>

    <!-- 视频播放器 + 摘要 -->
    <section class="content-card" v-if="task?.artifacts?.final_mp4">
      <div class="section-head">
        <div>
          <div class="section-title">成片预览</div>
          <div class="section-subtitle">{{ scriptMeta.title }} · {{ scriptMeta.duration_s.toFixed(0) }} 秒 · {{ scriptMeta.scenes }} 幕</div>
        </div>
        <div class="actions-mini">
          <el-button size="small" :icon="Download" @click="download(task.artifacts.final_mp4)">下载 MP4</el-button>
          <el-button size="small" :icon="Document" @click="download(task.artifacts.script_md)">下载脚本</el-button>
          <el-button size="small" :icon="Document" @click="download(task.artifacts.srt)" v-if="task.artifacts.srt">下载字幕</el-button>
        </div>
      </div>
      <video
        :src="fileUrl(task.artifacts.final_mp4)"
        :poster="task.artifacts.storyboards?.[0] ? fileUrl(task.artifacts.storyboards[0]) : undefined"
        controls
        class="video-player"
      />
    </section>

    <!-- 分镜图廊 -->
    <section class="content-card" v-if="task?.artifacts?.storyboards?.length">
      <div class="section-head">
        <div>
          <div class="section-title">分镜画面</div>
        </div>
      </div>
      <div class="storyboard-grid">
        <div
          v-for="(img, i) in task.artifacts.storyboards"
          :key="img"
          class="storyboard-cell"
        >
          <img :src="fileUrl(img)" :alt="`分镜 ${i + 1}`" />
          <div class="storyboard-label">
            <span class="scene-num">SCENE {{ String(i + 1).padStart(2, '0') }}</span>
            <span class="scene-style" v-if="scenes[i]">
              {{ scenes[i].style === 'tech_future' ? '科技未来' : '商务写实' }} · {{ scenes[i].duration_s.toFixed(0) }}s
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- 脚本 + 配音 -->
    <section class="content-card" v-if="scenes.length">
      <div class="section-head">
        <div>
          <div class="section-title">脚本与配音</div>
          <div class="section-subtitle">微软 Edge TTS · 中文女声(小晓)</div>
        </div>
      </div>
      <div class="scene-list">
        <div v-for="(s, i) in scenes" :key="s.index" class="scene-row">
          <div class="scene-head">
            <span class="scene-tag" :class="`tone-${s.style === 'tech_future' ? 'tech' : 'biz'}`">
              幕 {{ s.index }}
            </span>
            <span class="scene-title">{{ s.title }}</span>
            <span class="scene-meta">{{ s.duration_s.toFixed(0) }}s</span>
          </div>
          <div class="scene-voice">{{ s.voiceover }}</div>
          <div class="scene-prompt">
            <span class="prompt-label">画面 prompt</span>
            {{ s.prompt }}
          </div>
          <audio
            v-if="task?.artifacts?.audios?.[i]"
            :src="fileUrl(task.artifacts.audios[i])"
            controls
            class="scene-audio"
          />
        </div>
      </div>
    </section>

    <!-- 历史任务 -->
    <section class="content-card" v-if="history.length">
      <div class="section-head">
        <div>
          <div class="section-title">历史合成</div>
        </div>
      </div>
      <el-table :data="history" stripe size="small">
        <el-table-column label="简报" prop="report_filename" />
        <el-table-column label="后端" width="170">
          <template #default="{ row }">
            <el-tag v-if="row.backend === 'Seedance'" type="primary" size="small" effect="light">
              {{ row.backend }} · {{ row.resolution || '720p' }}
            </el-tag>
            <el-tag v-else-if="row.backend" type="info" size="small" effect="plain">
              {{ row.backend }}
            </el-tag>
            <span v-else style="color:var(--text-muted);font-size:12px">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : row.status === 2 ? 'danger' : 'info'" size="small">
              {{ ['生成中', '完成', '失败'][row.status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTs(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" link class="op-btn op-view" @click="loadTask(row.id)">查看</el-button>
            <el-button
              v-if="row.artifacts?.final_mp4"
              size="small"
              link
              class="op-btn op-download"
              @click="download(row.artifacts.final_mp4)"
            >下载</el-button>
            <el-button
              size="small"
              link
              type="danger"
              :loading="deletingId === row.id"
              @click="deleteTask(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Document, Refresh } from '@element-plus/icons-vue'
import { http } from '@/api/http'
import { useMissionStore } from '@/stores/mission'
import MissionBar from '@/components/MissionBar.vue'

const mission = useMissionStore()

interface ReportItem { name: string; has_doc?: boolean }
interface Scene {
  index: number; style: string; title: string; voiceover: string;
  prompt: string; duration_s: number;
}
interface Artifacts {
  workdir: string;
  script_md: string; script_json: string;
  storyboards: string[]; audios: string[];
  srt?: string | null; final_mp4?: string | null;
  notes: string[];
}
interface ProgressInfo {
  total_scenes: number;
  scenes_ready: number;
  audios_ready: number;
  stage: 'preparing' | 'rendering' | 'assembling' | 'burning_subtitles' | 'done';
  stage_label: string;
  elapsed_s: number;
  eta_s: number | null;
  avg_scene_s: number | null;
  scene_timeline: Array<{ index: number; size_kb: number; ready_at: number }>;
}
interface Task {
  id: string; status: 0 | 1 | 2;
  report_filename: string;
  backend?: string;         // Seedance / LocalStub (2026-05-08 加)
  model?: string;           // doubao-seedance-1-5-pro-251215 等
  resolution?: string;      // 720p / 1080p
  created_at: number; updated_at: number;
  artifacts: Artifacts | null;
  error: string | null;
  progress?: ProgressInfo;  // 后端实时进度(仅 status=0 时下发)
}

const reports = ref<ReportItem[]>([])
const selectedReport = ref<string>('')
const generating = ref(false)
const deletingId = ref<string | null>(null)
const task = ref<Task | null>(null)
const scenes = ref<Scene[]>([])
const history = ref<Task[]>([])
let pollTimer: number | null = null

// 当前时间戳(秒) - 1s 心跳更新,用于已等待时长跳动展示
// 后端 progress.elapsed_s 是上次请求时的快照,中间 2s 轮询间隔里前端自己跳秒
const nowTs = ref(Math.floor(Date.now() / 1000))
let clockTimer: number | null = null

const statusText = computed(() => {
  if (!task.value) return ''
  return ['正在合成', '已完成', '失败'][task.value.status]
})
const statusType = computed(() => {
  if (!task.value) return 'info'
  return (['warning', 'success', 'danger'] as const)[task.value.status]
})

const progressPercent = computed(() => {
  if (!task.value) return 0
  if (task.value.status === 1) return 100
  if (task.value.status === 2) return 0
  // 优先用后端实时进度,精确到段
  const p = task.value.progress
  if (p && p.total_scenes > 0) {
    // 实拍画面占 80%(主要耗时), TTS+ffmpeg 占 20%
    const renderPct = (p.scenes_ready / p.total_scenes) * 80
    const postPct =
      p.stage === 'done' ? 20 :
      p.stage === 'burning_subtitles' ? 15 :
      p.stage === 'assembling' ? 10 :
      p.audios_ready > 0 ? 5 : 0
    return Math.min(99, Math.round(renderPct + postPct))
  }
  // 没拿到 progress 时兜底:用 notes 数量估算
  const noteCount = task.value.artifacts?.notes?.length || 0
  return Math.min(95, 15 + noteCount * 20)
})

// 阶段文案 — 优先用后端给的 stage_label,兜底用百分比映射
const stageHint = computed(() => {
  if (!task.value || task.value.status !== 0) return ''
  if (task.value.progress?.stage_label) return task.value.progress.stage_label
  const p = progressPercent.value
  if (p < 25)  return '正在拆解脚本与分镜…'
  if (p < 50)  return '正在调用模型生成画面…'
  if (p < 75)  return '正在合成语音与字幕…'
  if (p < 95)  return '正在导出 MP4 与封面…'
  return '即将完成,正在收尾…'
})

const etaHint = computed(() => {
  if (!task.value || task.value.status !== 0) return ''
  // 优先用后端基于实际单段耗时的 eta_s
  const eta = task.value.progress?.eta_s
  if (eta !== null && eta !== undefined) {
    if (eta < 60) return `约 ${eta} 秒`
    if (eta < 3600) return `约 ${Math.ceil(eta / 60)} 分钟`
    const h = Math.floor(eta / 3600)
    const m = Math.ceil((eta % 3600) / 60)
    return `约 ${h} 小时 ${m} 分钟`
  }
  // 没拿到 progress 时兜底
  const p = progressPercent.value
  if (p >= 95) return '< 10 秒'
  const totalSec = 105
  const remain = Math.max(10, Math.round(totalSec * (1 - p / 100)))
  if (remain >= 60) return `约 ${Math.ceil(remain / 60)} 分钟`
  return `约 ${remain} 秒`
})

// 已等待时长(实时刷新,带秒钟跳动感)
const elapsedHint = computed(() => {
  if (!task.value || task.value.status !== 0) return ''
  const sec = task.value.progress?.elapsed_s ?? Math.max(0, Math.round(nowTs.value - task.value.created_at))
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
})

// 已生成画面文案: "已出 4/7 段画面 · 平均 4 分 12 秒/段"
const renderProgressHint = computed(() => {
  const p = task.value?.progress
  if (!p || p.total_scenes <= 0) return ''
  const base = `已生成 ${p.scenes_ready}/${p.total_scenes} 段画面`
  if (!p.avg_scene_s) return base
  const avg = p.avg_scene_s
  const avgStr = avg < 60 ? `${avg} 秒/段` : `${Math.floor(avg / 60)} 分 ${avg % 60} 秒/段`
  return `${base} · 平均 ${avgStr}`
})

const scriptMeta = computed(() => {
  const total = scenes.value.reduce((s, x) => s + x.duration_s, 0)
  return {
    title: scenes.value[0]?.title || task.value?.report_filename || 'AI 业务视频',
    duration_s: total,
    scenes: scenes.value.length,
  }
})

const heroPreviewTask = computed(() => {
  if (task.value?.artifacts?.final_mp4) return task.value
  return history.value.find(t => t.status === 1 && !!t.artifacts?.final_mp4) || null
})

const heroPreviewPoster = computed(() => heroPreviewTask.value?.artifacts?.storyboards?.[0] || null)
const heroSceneCount = computed(() => scenes.value.length || heroPreviewTask.value?.artifacts?.storyboards?.length || 6)

function fileUrl(path: string | null | undefined): string {
  if (!path) return ''
  return `/api/video/file/${path}`
}

function download(path: string | null | undefined) {
  if (!path) return
  const url = fileUrl(path)
  const a = document.createElement('a')
  a.href = url
  a.download = path.split('/').pop() || 'download'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function formatTs(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
}

// 时间线只显示"几分几秒前"的钟点(HH:MM:SS) - 任务进度面板里用
function formatClock(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

async function loadReports() {
  try {
    const { data } = await http.get('/report/list')
    reports.value = (data.data || []).filter((r: ReportItem) => r.name.endsWith('.md'))
    if (!selectedReport.value && reports.value.length > 0) {
      selectedReport.value = reports.value[0].name
    }
  } catch {
    ElMessage.warning('未能加载简报列表')
  }
}

async function loadHistory() {
  try {
    const { data } = await http.get('/video/list')
    history.value = data.data || []
  } catch {
    /* ignore */
  }
}

async function deleteTask(row: Task) {
  try {
    await ElMessageBox.confirm(
      `确认删除视频任务?\n\n任务 ID: ${row.id}\n` +
      `${row.artifacts?.final_mp4 ? '⚠️ 该任务有 final.mp4 视频成品,删除后无法恢复' : '该任务无 final.mp4'}\n\n` +
      `磁盘整个目录(分镜/音频/字幕)都会被删除。`,
      '删除视频任务',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return  // 用户取消
  }
  deletingId.value = row.id
  try {
    await http.delete(`/video/${encodeURIComponent(row.id)}`)
    ElMessage.success(`已删除任务 ${row.id}`)
    // 如果删的是当前查看的任务,清空详情面板
    if (task.value?.id === row.id) {
      task.value = null
      scenes.value = []
      // 同步清 mission store(避免任务条还显示已删的视频)
      if (mission.videoTaskId === row.id) {
        mission.videoTaskId = null
      }
    }
    await loadHistory()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

async function loadScenes() {
  if (!task.value?.artifacts?.script_json) return
  try {
    const { data } = await http.get(`/video/file/${task.value.artifacts.script_json}`)
    scenes.value = data?.scenes || []
  } catch {
    scenes.value = []
  }
}

async function loadTask(id: string) {
  try {
    const { data } = await http.get(`/video/task/${id}`)
    task.value = data.data
    if (task.value?.status === 1) {
      await loadScenes()
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载任务失败')
  }
}

function pollTask() {
  if (!task.value) return
  pollTimer = window.setTimeout(async () => {
    if (!task.value) return
    try {
      const { data } = await http.get(`/video/task/${task.value.id}`)
      task.value = data.data
      if (task.value?.status === 0) {
        pollTask()
      } else {
        if (task.value?.status === 1) {
          ElMessage.success('视频合成完成')
          // 回写 mission store:视频已生成 + 触发菜单红点
          mission.videoTaskId = task.value.id
          mission.videoStatus = 'done'
          mission.videoUnread = true
          await loadScenes()
        } else if (task.value?.status === 2) {
          ElMessage.error('视频合成失败:' + (task.value?.error || ''))
          mission.videoStatus = 'idle'
        }
        generating.value = false
        loadHistory()
      }
    } catch {
      pollTask()
    }
  }, 2000)
}

async function startGenerate() {
  if (!selectedReport.value) {
    ElMessage.warning('请先选择一份简报')
    return
  }
  generating.value = true
  scenes.value = []
  // 标记视频任务进入 running 态,菜单出现 spinner
  mission.videoStatus = 'running'
  mission.videoUnread = false
  try {
    const { data } = await http.post('/video/generate', {
      report_filename: selectedReport.value,
      do_assemble: true,
    })
    const id = data.data.id
    await loadTask(id)
    pollTask()
  } catch (e: any) {
    ElMessage.error(e.message || '提交失败')
    generating.value = false
    mission.videoStatus = 'idle'
  }
}

onMounted(async () => {
  await loadReports()
  await loadHistory()

  // 截图/演示深链: /video?task=latest 或 /video?task=<id>
  // 用于 PPT 自动截取时直接展开有成片/脚本的历史任务详情。
  const params = new URLSearchParams(window.location.search)
  const taskParam = params.get('task')
  if (taskParam) {
    const target = taskParam === 'latest'
      ? history.value.find(t => t.status === 1)?.id || history.value[0]?.id
      : taskParam
    if (target) await loadTask(target)
  }

  // 用户进入了视频页 → 清掉菜单红点(已读)
  mission.videoUnread = false
  // 1s 心跳:让"已等待"时长在两次后端轮询之间也能跳秒
  clockTimer = window.setInterval(() => {
    nowTs.value = Math.floor(Date.now() / 1000)
  }, 1000)
})
onBeforeUnmount(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
  if (clockTimer) window.clearInterval(clockTimer)
})
</script>

<style scoped>
.video-studio {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 8px;
}

.action-card,
.content-card {
  position: relative;
  border-radius: 18px;
  padding: 28px 32px;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  overflow: hidden;
}
.action-card::before,
.content-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 28px;
  right: 28px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(45, 212, 191, 0.45), transparent);
  pointer-events: none;
}

.action-head,
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 18px;
}
.section-title { font-size: 20px; font-weight: 700; color: var(--text-primary); }
.section-subtitle { margin-top: 6px; font-size: 13px; color: var(--text-muted); }

.brand-tag {
  background: linear-gradient(135deg, var(--c-mint), var(--c-emerald));
  border: 0;
}

.action-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.report-picker { flex: 1; min-width: 320px; }
.generate-btn {
  background: linear-gradient(135deg, var(--c-mint) 0%, var(--c-emerald) 100%);
  border: 0;
  min-width: 160px;
}

.picker-name { color: var(--text-primary); }
.picker-tag {
  margin-left: 8px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(132, 204, 22, 0.08);
  color: #047857;
}

.task-status {
  margin-top: 18px;
  padding: 16px 18px;
  border-radius: 14px;
  background: rgba(180, 230, 225, 0.04);
  border: 1px solid #e0ebff;
}
.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.status-label { color: var(--text-muted); font-size: 12px; }
.status-line code {
  font-family: 'JetBrains Mono', Menlo, monospace;
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(180, 230, 225, 0.04);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-line);
}
.status-notes { margin: 8px 0 12px; }
.note { font-size: 12px; line-height: 1.8; color: var(--text-secondary); }
.task-error { margin-top: 8px; color: var(--c-rust); font-size: 13px; }

/* J5: 长任务等待感 — 阶段文案 + 预估剩余 */
.stage-strip {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(45, 212, 191, 0.06);
  border: 1px solid rgba(45, 212, 191, 0.18);
  border-radius: var(--r-sm);
  font-size: 12.5px;
}
.stage-strip .stage-text {
  color: var(--c-emerald);
  font-weight: 500;
  letter-spacing: 0.3px;
}
.stage-strip .stage-eta {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
}
.stage-strip .stage-eta b {
  color: var(--text-primary);
  font-weight: 600;
  margin-left: 4px;
}
.stage-strip .stage-eta .elapsed {
  color: var(--c-mint);
  font-weight: 600;
}
.stage-strip .stage-eta .eta-sep {
  margin: 0 8px;
  color: var(--text-muted);
  opacity: 0.5;
}

/* 模型 chip - 让用户一眼看到当前用的是 1.5 Pro 还是 2.0 */
.model-chip {
  margin-left: auto;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  letter-spacing: 0.3px;
  padding: 3px 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.12), rgba(45, 212, 191, 0.04));
  color: var(--c-mint);
  border: 1px solid rgba(45, 212, 191, 0.25);
}

/* 实时进度详情面板 - 已出 N/M 段 + 时间线 */
.progress-detail {
  margin-top: 12px;
  padding: 14px 16px;
  background: rgba(15, 23, 42, 0.18);
  border: 1px solid rgba(45, 212, 191, 0.12);
  border-radius: var(--r-sm);
}
.progress-summary {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 10px;
  font-weight: 500;
}
.scene-timeline {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.timeline-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
  font-size: 12.5px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.timeline-item .ti-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-emerald);
  flex-shrink: 0;
  box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.15);
}
.timeline-item.pending .ti-dot {
  background: var(--c-mint);
  box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.3);
}
.timeline-item.pending .ti-dot.pulsing {
  animation: pulse-dot 1.4s ease-in-out infinite;
}
.timeline-item.waiting .ti-dot {
  background: rgba(148, 163, 184, 0.3);
  box-shadow: none;
}
.timeline-item.done .ti-label {
  color: var(--text-secondary);
}
.timeline-item.pending .ti-label {
  color: var(--c-mint);
  font-weight: 600;
}
.timeline-item.waiting .ti-label {
  color: var(--text-muted);
  opacity: 0.7;
}
.timeline-item .ti-meta {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--text-muted);
}
.timeline-item.pending .ti-meta {
  color: var(--c-mint);
  opacity: 0.85;
}
@keyframes pulse-dot {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.3);
  }
  50% {
    transform: scale(1.3);
    box-shadow: 0 0 0 6px rgba(45, 212, 191, 0.1);
  }
}

.actions-mini { display: flex; gap: 8px; flex-wrap: wrap; }

.video-player {
  width: 100%;
  max-height: 540px;
  border-radius: 16px;
  background: #000;
  display: block;
}

/* 分镜图廊 */
.storyboard-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.storyboard-cell {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--border-line);
  background: rgba(180, 230, 225, 0.04);
  transition: all 0.2s ease;
  cursor: zoom-in;
}
.storyboard-cell:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(99, 102, 241, 0.18);
}
.storyboard-cell img {
  width: 100%;
  display: block;
  aspect-ratio: 16 / 9;
  object-fit: cover;
}
.storyboard-label {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  background: rgba(180, 230, 225, 0.04);
}
.scene-num {
  font-family: 'JetBrains Mono', Menlo, monospace;
  font-weight: 700;
  color: var(--c-mint);
}
.scene-style { color: var(--text-muted); }

/* 脚本 / 配音 */
.scene-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.scene-row {
  padding: 16px 18px;
  border-radius: 14px;
  background: rgba(180, 230, 225, 0.04);
  border: 1px solid #ebf1ff;
}
.scene-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.scene-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
}
.tone-tech {
  background: linear-gradient(135deg, #312e81, var(--c-mint));
  color: #fff;
}
.tone-biz {
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.06), rgba(45, 212, 191, 0.10));
  color: #1e3a8a;
}
.scene-title {
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
}
.scene-meta {
  font-size: 12px;
  color: var(--text-muted);
}
.scene-voice {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
  padding: 10px 14px;
  background: rgba(180, 230, 225, 0.04);
  border-radius: 10px;
  border-left: 3px solid var(--c-mint);
  margin-bottom: 8px;
}
.scene-prompt {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-muted);
}
.prompt-label {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.08);
  color: var(--c-mint);
  font-weight: 600;
  font-size: 10px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.scene-audio {
  margin-top: 10px;
  width: 100%;
  height: 36px;
}

/* 历史 */
.task-id {
  font-family: 'JetBrains Mono', Menlo, monospace;
  font-size: 11px;
  color: var(--text-muted);
}

/* 历史合成 - 操作列按钮高亮（el-button link 默认 muted，按主题色亮起来） */
:deep(.op-btn.el-button.is-link) {
  font-weight: 600;
  letter-spacing: 0.3px;
}
:deep(.op-view.el-button.is-link) {
  color: var(--c-emerald);
}
:deep(.op-view.el-button.is-link:hover) {
  color: var(--c-mint);
  text-shadow: 0 0 8px rgba(45, 212, 191, 0.55);
}
:deep(.op-download.el-button.is-link) {
  color: var(--c-mint);
}
:deep(.op-download.el-button.is-link:hover) {
  color: #5eead4;
  text-shadow: 0 0 8px rgba(78, 205, 196, 0.55);
}

/* Premium video studio pass:把闭环终点做成"可出片的控制台" */
.action-card.video-command {
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(320px, 0.62fr);
  gap: 30px;
  align-items: stretch;
  border: 0;
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(180, 230, 225, 0.06), transparent 36%),
    radial-gradient(520px 220px at 100% 12%, rgba(78, 205, 196, 0.13), transparent 70%),
    linear-gradient(112deg, rgba(9, 28, 31, 0.80), rgba(4, 12, 15, 0.62));
  box-shadow:
    0 18px 44px rgba(0, 8, 12, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.055),
    inset 0 -1px 0 rgba(78, 205, 196, 0.055);
}

.studio-main,
.video-stage {
  position: relative;
  z-index: 1;
}

.studio-eyebrow {
  margin-bottom: 8px;
  color: rgba(94, 234, 212, 0.86);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1.6px;
}

.video-command .section-title {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 34px;
  line-height: 1.1;
  font-weight: 600;
  letter-spacing: 0;
}

.video-command .section-subtitle {
  max-width: 620px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.brand-tag {
  background: rgba(78, 205, 196, 0.13);
  border: 1px solid rgba(94, 234, 212, 0.25);
  color: rgba(94, 234, 212, 0.94);
}

.production-points {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin: 6px 0 18px;
  color: var(--text-muted);
  font-size: 12px;
}

.production-points span {
  position: relative;
  padding-left: 13px;
}

.production-points span::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(94, 234, 212, 0.74);
  box-shadow: 0 0 12px rgba(94, 234, 212, 0.28);
}

.video-command .action-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
}

.video-command .report-picker {
  min-width: 0;
}

.generate-btn {
  min-width: 158px;
  border-radius: 8px;
  color: #04211f;
  font-weight: 800;
  box-shadow: 0 10px 24px rgba(45, 212, 191, 0.18);
}

.theme-refresh {
  border: 0;
  background: rgba(180, 230, 225, 0.055);
  color: var(--text-secondary);
}

.task-status {
  border: 0;
  background:
    linear-gradient(90deg, rgba(78, 205, 196, 0.08), transparent 72%),
    rgba(180, 230, 225, 0.035);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.status-line {
  flex-wrap: wrap;
}

.video-stage {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 294px;
  padding: 14px;
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(180, 230, 225, 0.055), rgba(180, 230, 225, 0.018)),
    rgba(2, 8, 12, 0.42);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 18px 34px rgba(0, 8, 12, 0.22);
  overflow: hidden;
}

.video-stage::before {
  content: '';
  position: absolute;
  inset: 12px;
  border-radius: 9px;
  background-image:
    linear-gradient(rgba(180, 230, 225, 0.038) 1px, transparent 1px),
    linear-gradient(90deg, rgba(180, 230, 225, 0.028) 1px, transparent 1px);
  background-size: 38px 38px;
  opacity: 0.72;
  pointer-events: none;
}

.stage-screen {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 224px;
  border-radius: 9px;
  background: rgba(2, 8, 12, 0.74);
  overflow: hidden;
}

.stage-screen video,
.stage-screen img {
  width: 100%;
  height: 100%;
  min-height: 224px;
  display: block;
  object-fit: cover;
}

.stage-screen::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, transparent 56%, rgba(2, 8, 12, 0.68)),
    linear-gradient(90deg, rgba(2, 8, 12, 0.18), transparent 45%);
  pointer-events: none;
}

.stage-empty {
  position: relative;
  height: 100%;
  min-height: 224px;
  background: rgba(2, 8, 12, 0.82);
  overflow: hidden;
}

.stage-empty::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(70% 80% at 58% 72%, transparent 28%, rgba(2, 8, 12, 0.42) 78%),
    linear-gradient(180deg, rgba(2, 8, 12, 0.12), rgba(2, 8, 12, 0.72));
  z-index: 1;
  pointer-events: none;
}

.stage-empty-art {
  position: absolute;
  inset: 0;
  transform: scale(1.035);
  filter: saturate(0.78) contrast(1.04) brightness(0.82);
}

.stage-hud {
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 12px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(2, 8, 12, 0.58);
  color: rgba(222, 247, 242, 0.84);
  font-size: 12px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.07);
}

.stage-hud b {
  color: rgba(94, 234, 212, 0.90);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  letter-spacing: 0.3px;
}

.stage-scanline {
  position: absolute;
  inset: 0;
  z-index: 2;
  background: linear-gradient(180deg, transparent 0%, rgba(94, 234, 212, 0.14) 50%, transparent 100%);
  opacity: 0.42;
  transform: translateY(-100%);
  animation: studio-scan 4.2s cubic-bezier(0.22, 1, 0.36, 1) infinite;
  pointer-events: none;
}

@keyframes studio-scan {
  0% { transform: translateY(-100%); opacity: 0; }
  18% { opacity: 0.42; }
  54% { opacity: 0.24; }
  100% { transform: translateY(100%); opacity: 0; }
}

.stage-footer {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding-top: 12px;
  color: var(--text-muted);
  font-size: 12px;
}

.stage-footer b {
  color: rgba(94, 234, 212, 0.92);
  font-weight: 750;
  white-space: nowrap;
}

.content-card {
  border: 0;
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(180, 230, 225, 0.045), transparent 34%),
    rgba(8, 24, 27, 0.58);
  box-shadow:
    0 14px 34px rgba(0, 8, 12, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.content-card::before {
  left: 0;
  right: auto;
  bottom: 24px;
  width: 3px;
  height: auto;
  background: linear-gradient(180deg, rgba(94, 234, 212, 0.82), rgba(94, 234, 212, 0.08));
}

.content-card .section-title {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: 0;
}

.video-player {
  border-radius: 10px;
  box-shadow: 0 18px 44px rgba(0, 8, 12, 0.28);
}

.storyboard-cell {
  border: 0;
  border-radius: 10px;
  background: rgba(180, 230, 225, 0.035);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.storyboard-cell:hover {
  box-shadow: 0 14px 28px rgba(0, 8, 12, 0.22);
}

.scene-row {
  border: 0;
  border-radius: 10px;
  background: rgba(180, 230, 225, 0.035);
}

.scene-voice {
  border-left: 0;
  background:
    linear-gradient(90deg, rgba(78, 205, 196, 0.095), transparent),
    rgba(180, 230, 225, 0.035);
}

.tone-biz {
  color: rgba(94, 234, 212, 0.92);
}

@media (max-width: 1100px) {
  .action-card.video-command {
    grid-template-columns: 1fr;
  }

  .storyboard-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .action-row,
  .video-command .action-row {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
  .report-picker { width: 100%; }
}
@media (max-width: 768px) {
  .storyboard-grid { grid-template-columns: 1fr; }
  .action-card, .content-card { padding: 18px; border-radius: 20px; }
  .video-command .action-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .video-command .section-title {
    font-size: 23px;
    line-height: 1.08;
    white-space: nowrap;
  }
}
</style>
