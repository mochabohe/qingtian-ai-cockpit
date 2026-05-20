<template>
  <div class="report">
    <!-- 经营任务单(P0-1):跨页面共享当前任务上下文 -->
    <MissionBar />

    <div class="head">
      <h2 class="page-title">简报预览与导出</h2>
      <el-button class="refresh-btn" :icon="Refresh" @click="loadList">刷新</el-button>
    </div>

    <el-tabs v-model="activeTab" class="report-tabs">
      <!-- ───────── tab 1:简报列表 ───────── -->
      <el-tab-pane name="list">
        <template #label>
          <span class="tab-label">📄 简报列表 <span class="tab-count">{{ reports.length }}</span></span>
        </template>
        <el-card class="list-card" shadow="never">
          <el-empty v-if="reports.length === 0" description="还没有简报，去 Agent 控制台跑一次编排" />
          <div v-else class="list-grid">
            <div
              v-for="r in reports"
              :key="r.name"
              class="list-item"
              :class="{ active: selected === r.name }"
              @click="selectAndPreview(r.name)"
            >
              <div class="item-name-row">
                <span class="item-name">{{ displayName(r.name) }}</span>
              </div>
              <div class="item-tags">
                <el-tag v-if="r.has_doc" size="small" type="primary" effect="light">卡片</el-tag>
                <el-tag v-else size="small" type="info" effect="plain">MD</el-tag>
                <el-tag v-if="r.has_trace" size="small" type="success" effect="light">链路</el-tag>
              </div>
              <div class="item-meta">
                {{ (r.size / 1024).toFixed(1) }} KB · {{ formatTime(r.modified) }}
              </div>
              <button
                class="item-delete"
                title="删除该简报"
                @click.stop="del(r.name)"
              >
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ───────── tab 2:简报预览 ───────── -->
      <el-tab-pane name="preview" :disabled="!selected">
        <template #label>
          <span class="tab-label">
            🔍 简报预览
            <span v-if="selected" class="tab-current">· {{ displayName(selected) }}</span>
          </span>
        </template>
        <el-card class="preview-card" shadow="never">
          <template #header>
            <div class="card-head">
              <b>{{ displayName(selected) || '简报预览' }}</b>
              <div v-if="selected" class="head-actions">
                <el-radio-group v-model="viewMode" size="small" :disabled="isEditing">
                  <el-radio-button v-if="hasDoc" value="card">卡片视图</el-radio-button>
                  <el-radio-button value="markdown">Markdown 源</el-radio-button>
                  <el-radio-button v-if="hasTrace" value="trace">全链路追溯</el-radio-button>
                </el-radio-group>
                <el-button
                  v-if="viewMode === 'markdown' && !isEditing"
                  class="action-btn"
                  size="small"
                  :icon="Edit"
                  @click="enterEditMode"
                >编辑修订</el-button>
                <el-button class="action-btn" size="small" :icon="Download" :disabled="isEditing" @click="exportHtml">导出 HTML / PDF</el-button>
                <el-button class="action-btn" size="small" :icon="Document" :disabled="isEditing" @click="exportPptx">导出 PPTX</el-button>
                <el-button v-if="hasDoc" class="action-btn" size="small" :icon="Files" :disabled="isEditing" @click="exportJson">导出 JSON</el-button>
                <el-button class="action-btn action-btn--danger" size="small" :icon="Delete" :disabled="isEditing" @click="del">删除</el-button>
              </div>
            </div>
          </template>

          <el-skeleton v-if="loading" :rows="6" animated />
          <el-empty v-else-if="!selected" description="请从“简报列表”选择一份简报" />

          <div v-else-if="viewMode === 'card' && doc" class="card-view">
            <BriefingDoc :doc="doc" />
          </div>

          <el-alert
            v-else-if="viewMode === 'card' && !doc && hasDoc"
            type="warning"
            :title="docError || '结构化简报加载失败'"
            description="可切换到 Markdown 源查看,或重新生成本简报"
            show-icon
            :closable="false"
          />

          <div v-else-if="viewMode === 'trace'" class="trace-view">
            <el-alert
              v-if="traceError"
              type="warning"
              :title="traceError"
              show-icon
              :closable="false"
            />
            <template v-else-if="trace">
              <div class="trace-summary">
                <div class="summary-item">
                  <div class="summary-label">主题</div>
                  <div class="summary-value">{{ trace.topic || '—' }}</div>
                </div>
                <div class="summary-item">
                  <div class="summary-label">数据集</div>
                  <div class="summary-value mono">{{ trace.data_file || '—' }}</div>
                </div>
                <div class="summary-item">
                  <div class="summary-label">审计号</div>
                  <div class="summary-value mono">{{ trace.audit_id || '—' }}</div>
                </div>
                <div class="summary-item">
                  <div class="summary-label">总耗时</div>
                  <div class="summary-value">{{ trace.totals.duration_s }} s</div>
                </div>
                <div class="summary-item">
                  <div class="summary-label">Prompt tokens</div>
                  <div class="summary-value">{{ trace.totals.tokens_prompt.toLocaleString() }}</div>
                </div>
                <div class="summary-item">
                  <div class="summary-label">Completion tokens</div>
                  <div class="summary-value">{{ trace.totals.tokens_completion.toLocaleString() }}</div>
                </div>
              </div>

              <el-timeline class="trace-timeline">
                <el-timeline-item
                  v-for="step in trace.steps"
                  :key="step.index"
                  :type="step.status === 'error' ? 'danger' : 'primary'"
                  :hollow="step.status !== 'done'"
                  :timestamp="`${step.started_at} · ${step.duration_s}s`"
                  placement="top"
                >
                  <div class="trace-step">
                    <div class="trace-step-head">
                      <span class="trace-step-index">#{{ step.index }}</span>
                      <span class="trace-step-title">{{ step.title }}</span>
                      <el-tag size="small" :type="statusTag(step.status)">{{ statusLabel(step.status) }}</el-tag>
                      <span class="trace-step-name">{{ step.name }}</span>
                    </div>
                    <div class="trace-step-desc">{{ step.desc }}</div>
                    <div class="trace-step-stats">
                      <span v-if="step.model">模型 <b>{{ step.model }}</b></span>
                      <span v-if="step.tokens?.prompt != null">in {{ step.tokens.prompt }}</span>
                      <span v-if="step.tokens?.completion != null">out {{ step.tokens.completion }}</span>
                      <span>产物 {{ step.output_len.toLocaleString() }} 字符</span>
                    </div>
                    <el-alert
                      v-if="step.error"
                      type="error"
                      :title="step.error"
                      show-icon
                      :closable="false"
                      class="trace-step-error"
                    />
                    <details v-if="step.output" class="trace-step-output">
                      <summary>查看产物</summary>
                      <pre>{{ step.output }}</pre>
                    </details>
                  </div>
                </el-timeline-item>
              </el-timeline>
            </template>
            <el-empty v-else description="未找到全链路追溯数据" />
          </div>

          <div v-else-if="viewMode === 'markdown' && isEditing" class="edit-pane">
            <div class="edit-banner">
              <span class="edit-banner-tag">编辑模式</span>
              <span class="edit-banner-text">
                ⚠️ 不会调用 LLM，直接保存为新文件 (原简报保留)
              </span>
              <span v-if="isDirty" class="edit-dirty-dot" title="有未保存修改"></span>
            </div>
            <textarea
              v-model="editBuffer"
              class="edit-textarea"
              spellcheck="false"
              placeholder="在此编辑简报正文..."
            ></textarea>
            <div class="edit-actions">
              <el-button size="small" :disabled="saving" @click="cancelEdit">取消</el-button>
              <el-button
                type="primary"
                size="small"
                :loading="saving"
                @click="saveEdit"
              >保存修订版</el-button>
            </div>
          </div>

          <div v-else class="preview" v-html="renderedHtml"></div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Download, Document, Files, Edit, Delete } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import {
  listReports, getReportMarkdown, deleteReport, getReportDoc, getReportTrace,
  getHtmlUrl, getPptxUrl, getJsonUrl, saveRevision,
  type ReportItem, type BriefingDoc as BriefingDocType, type ReportTrace,
} from '@/api/report'
import { BriefingDoc } from '@/components/briefing'
import { useMissionStore } from '@/stores/mission'
import MissionBar from '@/components/MissionBar.vue'

const mission = useMissionStore()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const reports = ref<ReportItem[]>([])
const selected = ref('')
// tab 切换:list = 简报列表,preview = 简报预览
const activeTab = ref<'list' | 'preview'>('list')
const markdown = ref('')
const doc = ref<BriefingDocType | null>(null)
const docError = ref('')
const trace = ref<ReportTrace | null>(null)
const traceError = ref('')
const loading = ref(false)
const viewMode = ref<'card' | 'markdown' | 'trace'>('card')

// P1-1 简报最小审阅:编辑修订模式(仅在 markdown view 下生效)
const isEditing = ref(false)
const editBuffer = ref('')
const saving = ref(false)
const isDirty = computed(() => isEditing.value && editBuffer.value !== markdown.value)

const renderedHtml = computed(() => markdown.value ? md.render(markdown.value) : '')

const currentItem = computed(() => reports.value.find(r => r.name === selected.value))
const hasDoc = computed(() => !!currentItem.value?.has_doc)
const hasTrace = computed(() => !!currentItem.value?.has_trace)

function humanizeVocClusterText(text: string): string {
  return text
    .replace(/形成\s*(\d+)\s*个主题簇/g, '提炼$1个用户话题')
    .replace(/主题聚类\s*(\d+)\s*簇/g, '提炼$1个用户话题')
    .replace(/聚类\s*(\d+)\s*簇/g, '提炼$1个用户话题')
    .replace(/TOP\s*痛点簇/g, 'TOP 痛点话题')
    .replace(/TOP\s*卖点簇/g, 'TOP 卖点话题')
    .replace(/痛点簇\d+\s*[：｜|]/g, '痛点话题：')
    .replace(/卖点簇\d+\s*[：｜|]/g, '卖点话题：')
    .replace(/痛点簇\d+/g, '痛点话题')
    .replace(/卖点簇\d+/g, '卖点话题')
    .replace(/负面簇\d+/g, '负面话题')
    .replace(/正面簇\d+/g, '正面话题')
    .replace(/簇\d+\(([^)]*)\)\s*[：:]/g, '话题($1)：')
    .replace(/簇\d+\s*[：｜|]/g, '话题：')
    .replace(/簇\d+/g, '话题')
    .replace(/聚类簇心/g, '主题关键词')
}

function humanizeVocClusterDoc<T>(value: T): T {
  if (typeof value === 'string') return humanizeVocClusterText(value) as T
  if (Array.isArray(value)) return value.map(item => humanizeVocClusterDoc(item)) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, humanizeVocClusterDoc(item)]),
    ) as T
  }
  return value
}

watch(hasDoc, (v) => {
  // 切换简报后,如果新简报没有结构化版本,自动切到 markdown 视图
  if (!v) viewMode.value = 'markdown'
  else viewMode.value = 'card'
})

watch(viewMode, async (mode) => {
  // 离开 markdown 视图时强制退出编辑模式(避免脏数据残留)
  if (mode !== 'markdown' && isEditing.value) {
    isEditing.value = false
    editBuffer.value = ''
  }
  if (mode === 'trace' && selected.value && !trace.value && !traceError.value) {
    try {
      trace.value = humanizeVocClusterDoc(await getReportTrace(selected.value))
    } catch (e: any) {
      traceError.value = e?.message || '全链路追溯加载失败'
    }
  }
})

async function loadList() {
  reports.value = await listReports()
  if (!selected.value && reports.value.length) {
    // 首次加载时只在后台预选第一份(填好 mission/markdown/doc),不自动跳到预览 tab
    // 让用户从列表上明确点击一次再过去预览,避免 onMounted 自动切 tab 引起视觉跳变
    await select(reports.value[0].name)
  }
}

// 列表点击 → 选中 + 自动切到预览 tab
async function selectAndPreview(name: string) {
  await select(name)
  activeTab.value = 'preview'
}

async function select(name: string) {
  selected.value = name
  // 回写 mission store:用户选中此简报作为当前任务的产物
  mission.briefFilename = name
  loading.value = true
  doc.value = null
  docError.value = ''
  markdown.value = ''
  trace.value = null
  traceError.value = ''
  // 切换简报时一并清空编辑态
  isEditing.value = false
  editBuffer.value = ''
  const item = reports.value.find(r => r.name === name)
  viewMode.value = item?.has_doc ? 'card' : 'markdown'
  try {
    const tasks: Promise<any>[] = [
      getReportMarkdown(name).then(m => { markdown.value = humanizeVocClusterText(m) }),
    ]
    if (item?.has_doc) {
      tasks.push(
        getReportDoc(name)
          .then(d => { doc.value = humanizeVocClusterDoc(d) })
          .catch(e => { docError.value = e?.message || '结构化简报加载失败' }),
      )
    }
    await Promise.all(tasks)
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function statusLabel(s: 'running' | 'done' | 'error') {
  return s === 'done' ? '完成' : s === 'error' ? '失败' : '运行中'
}
function statusTag(s: 'running' | 'done' | 'error'): 'success' | 'danger' | 'warning' {
  return s === 'done' ? 'success' : s === 'error' ? 'danger' : 'warning'
}

function exportHtml() {
  if (!selected.value) return
  window.open(getHtmlUrl(selected.value), '_blank')
}

function exportPptx() {
  if (!selected.value) return
  window.location.href = getPptxUrl(selected.value)
  ElMessage.success('正在生成 PPTX，下载即将开始')
}

function exportJson() {
  if (!selected.value) return
  window.location.href = getJsonUrl(selected.value)
  ElMessage.success('正在下载 BriefingDoc JSON')
}

async function del(name?: string) {
  // 不传 name 时删当前选中(预览页用),传 name 时删指定项(列表卡片用)
  const target = name || selected.value
  if (!target) return
  try {
    await ElMessageBox.confirm(`确认删除 ${target}？`, '提示', { type: 'warning' })
  } catch {
    return  // 用户取消
  }
  await deleteReport(target)
  ElMessage.success('已删除')
  // 如果删的就是当前选中的简报,清空预览状态 + 跳回列表 tab
  if (target === selected.value) {
    selected.value = ''
    markdown.value = ''
    doc.value = null
    trace.value = null
    traceError.value = ''
    activeTab.value = 'list'
  }
  await loadList()
}

// ─────────── P1-1 简报最小审阅:编辑修订模式 ───────────
function enterEditMode() {
  if (!selected.value) return
  // 编辑只在 markdown 视图,先确保切到 markdown
  viewMode.value = 'markdown'
  editBuffer.value = markdown.value
  isEditing.value = true
}

async function cancelEdit() {
  if (isDirty.value) {
    try {
      await ElMessageBox.confirm('有未保存的修改,确认放弃?', '提示', {
        type: 'warning',
        confirmButtonText: '放弃',
        cancelButtonText: '继续编辑',
      })
    } catch {
      return // 用户取消
    }
  }
  isEditing.value = false
  editBuffer.value = ''
}

async function saveEdit() {
  if (!selected.value || !isEditing.value) return
  saving.value = true
  try {
    const result = await saveRevision(selected.value, editBuffer.value)
    ElMessage.success(`已保存修订版: ${result.filename}`)
    isEditing.value = false
    editBuffer.value = ''
    // 刷新列表 + 选中新文件
    await loadList()
    await select(result.filename)
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function formatTime(ts: number) {
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
}

function displayName(name: string | null | undefined) {
  if (!name) return ''
  const base = name.replace(/\.md$/i, '')
  const ext = name.slice(base.length)
  const m = base.match(/^(\d{8}_\d{6})_(.+)$/)
  return m ? `${m[2]}_${m[1]}${ext}` : name
}

onMounted(async () => {
  await loadList()

  // 截图/演示深链: /report?tab=preview&mode=card&report=xxx
  // 正常使用不受影响；用于 PPT 自动截取时直接进入有内容的预览态。
  const params = new URLSearchParams(window.location.search)
  const tab = params.get('tab')
  const report = params.get('report')
  const mode = params.get('mode') as 'card' | 'markdown' | 'trace' | null

  if (report && reports.value.some(r => r.name === report)) {
    await select(report)
  }
  if (mode === 'card' || mode === 'markdown' || mode === 'trace') {
    viewMode.value = mode
  }
  if (tab === 'preview' && selected.value) {
    activeTab.value = 'preview'
  }
})
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 22px;
  font-weight: 700;
}
/* ReportPreview 两张主卡去框: 保留极轻底色和 hairline, 不画 border-radius 大框 */
.list-card, .preview-card { min-height: 600px; }
.list-card :deep(.el-card),
.preview-card :deep(.el-card) {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
.list-card :deep(.el-card)::before,
.preview-card :deep(.el-card)::before {
  display: none;
}
.list-card :deep(.el-card__header),
.preview-card :deep(.el-card__header) {
  padding: 0 0 14px 0 !important;
  border-bottom: 1px solid var(--border-line) !important;
  margin-bottom: 14px;
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 19px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--text-primary);
}
.list-card :deep(.el-card__body),
.preview-card :deep(.el-card__body) {
  padding: 0 !important;
}
/* 两列之间用一条竖向 hairline 分隔, 不再隔卡 */
.list-card { padding-right: 20px; border-right: 1px solid var(--border-line); }
.preview-card { padding-left: 20px; }
/* tabs 美化:让标签更醒目,撑满容器 */
.report-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }
.report-tabs :deep(.el-tabs__item) {
  font-size: 14px;
  padding: 0 18px;
  height: 44px;
  line-height: 44px;
  color: var(--text-secondary) !important;
  font-weight: 500;
  transition: color 0.18s ease;
}
.report-tabs :deep(.el-tabs__item:hover) {
  color: var(--text-primary) !important;
}
.report-tabs :deep(.el-tabs__item.is-active) {
  color: var(--text-primary) !important;
  font-weight: 600;
}
.report-tabs :deep(.el-tabs__item.is-disabled) {
  color: var(--text-muted) !important;
  opacity: 0.65;
}
.report-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--c-emerald) !important;
  height: 2px;
}
.tab-label { display: inline-flex; align-items: center; gap: 6px; }
.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 18px;
  padding: 0 7px;
  background: rgba(45, 212, 191, 0.14);
  border: 1px solid rgba(45, 212, 191, 0.28);
  color: var(--c-mint);
  border-radius: 10px;
  font-size: 11px;
  line-height: 1;
  font-weight: 600;
  letter-spacing: 0.2px;
}
/* 刷新按钮:与深色主题对齐,避免默认浅色底 */
.head .refresh-btn {
  background: rgba(45, 212, 191, 0.06) !important;
  border-color: rgba(45, 212, 191, 0.28) !important;
  color: var(--c-mint) !important;
}
.head .refresh-btn:hover {
  background: rgba(45, 212, 191, 0.14) !important;
  border-color: var(--c-emerald) !important;
  color: var(--c-emerald) !important;
}
.tab-current {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: normal;
  margin-left: 4px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  vertical-align: middle;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
/* 简报头操作区:5 个按钮统一翡翠 ghost 风格,主操作"导出 PPTX"用实底,删除用 rust ghost */
.head-actions .action-btn {
  height: 30px !important;
  padding: 0 12px !important;
  border-radius: 7px !important;
  background: rgba(45, 212, 191, 0.06) !important;
  border: 1px solid rgba(45, 212, 191, 0.28) !important;
  color: var(--c-mint) !important;
  font-weight: 500 !important;
  letter-spacing: 0.2px;
  box-shadow: none !important;
  transition: all 0.18s ease !important;
}
.head-actions .action-btn:hover:not(.is-disabled) {
  background: rgba(45, 212, 191, 0.14) !important;
  border-color: var(--c-emerald) !important;
  color: var(--c-emerald) !important;
  transform: none !important;
}
.head-actions .action-btn.action-btn--primary {
  background: linear-gradient(180deg, #2dd4bf 0%, #0e7c7b 100%) !important;
  border-color: rgba(45, 212, 191, 0.55) !important;
  color: #04161a !important;
  font-weight: 600 !important;
  box-shadow: 0 2px 10px rgba(45, 212, 191, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.18) !important;
}
.head-actions .action-btn.action-btn--primary:hover:not(.is-disabled) {
  filter: brightness(1.08);
  background: linear-gradient(180deg, #2dd4bf 0%, #0e7c7b 100%) !important;
  border-color: var(--c-emerald) !important;
  color: #04161a !important;
}
.head-actions .action-btn.action-btn--danger {
  background: rgba(217, 119, 87, 0.06) !important;
  border-color: rgba(217, 119, 87, 0.32) !important;
  color: var(--c-rust, #d97757) !important;
}
.head-actions .action-btn.action-btn--danger:hover:not(.is-disabled) {
  background: rgba(217, 119, 87, 0.14) !important;
  border-color: var(--c-rust, #d97757) !important;
  color: #f5a07f !important;
}
/* radio-group 与按钮高度对齐 */
.head-actions :deep(.el-radio-group) {
  display: inline-flex;
}
.head-actions :deep(.el-radio-button__inner) {
  height: 30px;
  line-height: 28px;
  padding: 0 12px;
}

/* 简报列表 tab: 行式索引列表 (像邮件 / 文件浏览器), 不再用卡片网格 */
.list-grid {
  display: flex;
  flex-direction: column;
  padding: 0;
  border-top: 1px solid var(--border-line);
}
.list-item {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto auto 36px;
  align-items: center;
  gap: 16px;
  padding: 14px 12px 14px 18px;
  border-bottom: 1px solid var(--border-line);
  background: transparent;
  cursor: pointer;
  transition: all var(--t-fast);
}
.list-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: transparent;
  transition: background var(--t-fast);
}
.list-item:hover {
  background: rgba(45, 212, 191, 0.04);
}
.list-item:hover::before {
  background: rgba(45, 212, 191, 0.4);
}
.list-item.active {
  background: rgba(45, 212, 191, 0.08);
}
.list-item.active::before {
  background: var(--c-emerald);
}

/* 删除按钮: 行末固定槽位, 默认 0.4 透明度, hover 时显完整 */
.item-delete {
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0.4;
  transition: all var(--t-fast);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.list-item:hover .item-delete { opacity: 1; }
.item-delete:hover {
  background: rgba(217, 119, 87, 0.10);
  border-color: rgba(217, 119, 87, 0.32);
  color: var(--c-rust);
}

.item-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.item-name {
  flex: 1;
  font-weight: 500;
  font-size: 13.5px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.2px;
  line-height: 1.5;
  min-width: 0;
}
.list-item.active .item-name {
  color: var(--c-emerald);
  font-weight: 600;
}
.item-tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.item-meta {
  color: var(--text-muted);
  font-size: 11.5px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 0.3px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  flex-shrink: 0;
}

.card-view {
  padding: 4px;
  overflow: visible;
}

.trace-view {
  padding: 8px 4px;
  overflow: visible;
}
.trace-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 16px;
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
  border-radius: 8px;
  margin-bottom: 18px;
}
.summary-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.summary-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}
.summary-value.mono {
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 12px;
  font-weight: 500;
}
.trace-timeline {
  padding-left: 4px;
}
.trace-step {
  background: rgba(180, 230, 225, 0.04);
  border: 1px solid var(--border-line);
  border-radius: 6px;
  padding: 10px 14px;
}
.trace-step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.trace-step-index {
  font-family: ui-monospace, monospace;
  color: var(--text-muted);
  font-size: 12px;
}
.trace-step-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}
.trace-step-name {
  font-family: ui-monospace, monospace;
  color: var(--text-muted);
  font-size: 11px;
}
.trace-step-desc {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 6px;
}
.trace-step-stats {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-muted);
}
.trace-step-stats b {
  color: var(--text-primary);
}
.trace-step-error {
  margin-top: 8px;
}
.trace-step-output {
  margin-top: 8px;
  font-size: 12px;
}
.trace-step-output summary {
  cursor: pointer;
  color: var(--c-emerald);
  user-select: none;
}
.trace-step-output pre {
  margin-top: 6px;
  padding: 10px 12px;
  background: var(--text-primary);
  color: var(--border-line);
  border-radius: 4px;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  line-height: 1.55;
}

.preview {
  padding: 16px 24px;
  overflow: visible;
  line-height: 1.8;
  font-size: 14px;
  color: var(--text-primary);
}
.preview :deep(h1) {
  color: var(--c-emerald);
  border-bottom: 3px solid var(--c-emerald);
  padding-bottom: 8px;
}
.preview :deep(h2) {
  color: var(--c-emerald);
  margin-top: 24px;
  border-left: 4px solid var(--c-moss);
  padding-left: 10px;
}
.preview :deep(h3) { color: var(--text-secondary); }
.preview :deep(ul), .preview :deep(ol) { padding-left: 24px; }
.preview :deep(li) { margin: 6px 0; }
.preview :deep(strong) { color: var(--text-primary); }
.preview :deep(blockquote) {
  border-left: 4px solid var(--border-line);
  padding: 8px 14px;
  background: rgba(180, 230, 225, 0.025);
  color: var(--text-secondary);
  margin: 12px 0;
}
.preview :deep(code) {
  background: rgba(180, 230, 225, 0.03);
  padding: 2px 6px;
  border-radius: 3px;
}

/* ─────────── P1-1 编辑修订模式 ─────────── */
.edit-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 4px;
}
.edit-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: rgba(45, 212, 191, 0.05);
  border: 1px solid rgba(45, 212, 191, 0.40);
  border-radius: 6px;
  color: var(--c-emerald);
  font-size: 13px;
}
.edit-banner-tag {
  background: var(--c-emerald-deep);
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.edit-banner-text {
  flex: 1;
}
.edit-dirty-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-rust);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.18);
  flex-shrink: 0;
}
.edit-textarea {
  width: 100%;
  min-height: 560px;
  height: calc(70vh - 60px);
  resize: vertical;
  padding: 14px 16px;
  border: 1px solid var(--border-line);
  border-radius: 6px;
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, "Courier New", monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  background: rgba(180, 230, 225, 0.04);
  outline: none;
  box-sizing: border-box;
}
.edit-textarea:focus {
  border-color: var(--c-emerald);
  background: rgba(180, 230, 225, 0.04);
  box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.12);
}
.edit-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

@media (max-width: 720px) {
  .head {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
  }

  .head .refresh-btn {
    width: 100%;
  }

  .report-tabs :deep(.el-tabs__item) {
    padding: 0 12px;
  }

  .list-item {
    grid-template-columns: 1fr 32px;
    gap: 8px;
  }

  .item-tags,
  .item-meta {
    grid-column: 1 / -1;
  }
}

</style>
