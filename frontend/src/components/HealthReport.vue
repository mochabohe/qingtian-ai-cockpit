<template>
  <!--
    P0-2 数据体检中心(单数据集视图)
    展示:总分(0-100) + 4 维度雷达 + 风险列表 + 字段角色矩阵
    使用方式:<HealthReport :dataset-key="key" :dataset-name="name" />
  -->
  <div class="health-report" v-loading="loading">
    <div v-if="!report && !loading" class="empty-state">
      <el-button type="primary" @click="loadReport">运行体检</el-button>
    </div>

    <template v-if="report">
      <!-- 顶部:总分 + 4 维度 -->
      <div class="header-row">
        <div class="score-circle" :class="scoreClass">
          <div class="score-num">{{ report.score }}</div>
          <div class="score-label">健康评分</div>
        </div>
        <div class="dim-grid">
          <div v-for="d in report.dimensions" :key="d.name" class="dim-card">
            <div class="dim-head">
              <span class="dim-label">{{ d.label }}</span>
              <span class="dim-score" :class="dimColor(d.score)">{{ d.score }}</span>
            </div>
            <div class="dim-bar">
              <div class="dim-bar-fill" :class="dimColor(d.score)"
                   :style="{ width: d.score + '%' }"></div>
            </div>
            <div class="dim-detail">{{ d.detail }}</div>
          </div>
        </div>
      </div>

      <!-- 风险提示 -->
      <div v-if="report.risks.length" class="risks-section">
        <div class="section-title">⚠️ 风险提示 ({{ report.risks.length }})</div>
        <div class="risk-list">
          <div v-for="(r, i) in report.risks" :key="i" class="risk-item" :class="`risk-${r.level}`">
            <el-tag :type="riskTagType(r.level)" size="small">
              {{ riskLevelLabel(r.level) }}
            </el-tag>
            <div class="risk-msg">
              <div>{{ r.message }}</div>
              <div v-if="r.affected_fields && r.affected_fields.length" class="risk-fields">
                影响字段:
                <span v-for="f in r.affected_fields.slice(0, 6)" :key="f" class="aff-tag">{{ f }}</span>
                <span v-if="r.affected_fields.length > 6" class="aff-more">
                  +{{ r.affected_fields.length - 6 }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="risks-empty">
        ✅ 未发现风险,数据可直接进入分析流程
      </div>

      <!-- 字段角色矩阵 -->
      <div class="fields-section">
        <div class="section-title">
          🔍 字段角色识别
          <span class="section-meta">{{ report.n_rows.toLocaleString() }} 行 × {{ report.n_cols }} 列</span>
        </div>
        <div class="field-grid">
          <div v-for="f in report.field_summary" :key="f.name"
               class="field-cell" :class="`role-${f.role}`">
            <div class="field-head">
              <span class="field-name">{{ f.name }}</span>
              <el-tag size="small" :type="roleTagType(f.role)" effect="light">
                {{ f.role_label }}
              </el-tag>
            </div>
            <div class="field-meta-row">
              <span class="conf-bar">
                <span class="conf-label">置信度</span>
                <span class="conf-bar-track">
                  <span class="conf-bar-fill" :class="dimColor(f.role_confidence)"
                        :style="{ width: f.role_confidence + '%' }"></span>
                </span>
                <span class="conf-num">{{ f.role_confidence }}</span>
              </span>
            </div>
            <div class="field-stats">
              <span :class="{ 'stat-warn': f.null_ratio >= 0.3 }">
                空值 {{ (f.null_ratio * 100).toFixed(1) }}%
              </span>
              <span>· {{ f.n_unique.toLocaleString() }} 唯一值</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/api/http'
import { readCache, writeCache } from '@/utils/sessionCache'

interface Dimension {
  name:    string
  label:   string
  score:   number
  weight:  number
  detail:  string
}
interface Risk {
  level:           'high' | 'medium' | 'low'
  code:            string
  message:         string
  affected_fields: string[]
}
interface FieldSummary {
  name:            string
  role:            string
  role_label:      string
  role_confidence: number
  null_ratio:      number
  n_unique:        number
  unique_ratio:    number
  dtype:           string
}
interface Report {
  score:         number
  dimensions:    Dimension[]
  risks:         Risk[]
  n_rows:        number
  n_cols:        number
  field_summary: FieldSummary[]
}

const props = defineProps<{
  datasetKey: string
  datasetName?: string
  autoLoad?: boolean
}>()

const loading = ref(false)
const report  = ref<Report | null>(null)

const scoreClass = computed(() => {
  if (!report.value) return ''
  const s = report.value.score
  if (s >= 90) return 'score-excellent'
  if (s >= 75) return 'score-good'
  if (s >= 60) return 'score-fair'
  return 'score-poor'
})

function dimColor(score: number) {
  if (score >= 90) return 'col-green'
  if (score >= 70) return 'col-blue'
  if (score >= 50) return 'col-yellow'
  return 'col-red'
}

function riskTagType(level: string) {
  return ({ high: 'danger' as const, medium: 'warning' as const, low: 'info' as const })[level as 'high' | 'medium' | 'low']
}
function riskLevelLabel(level: string) {
  return ({ high: '高', medium: '中', low: '低' })[level as 'high' | 'medium' | 'low']
}
function roleTagType(role: string) {
  const m: Record<string, any> = {
    time:    'primary',
    id:      'success',
    metric:  'warning',
    dim:     'info',
    text:    '',
    unknown: 'info',
  }
  return m[role] ?? ''
}

async function loadReport(opts: { force?: boolean } = {}) {
  if (!props.datasetKey) return
  const cacheKey = `health:${props.datasetKey}`
  if (!opts.force) {
    const cached = readCache<Report>(cacheKey)
    if (cached) {
      report.value = cached
      return
    }
  }
  loading.value = true
  try {
    const { data } = await http.get(`/data/datasets/${encodeURIComponent(props.datasetKey)}/health`)
    report.value = data.data
    writeCache(cacheKey, data.data)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '体检失败')
    report.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.datasetKey, () => {
  if (props.autoLoad) loadReport()
}, { immediate: true })

defineExpose({ loadReport })
</script>

<style scoped>
.health-report {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 300px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

/* 顶部分数 + 维度 */
.header-row {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 24px;
  align-items: start;
}
.score-circle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, rgba(45, 212, 191, 0.18) 0%, rgba(10, 22, 28, 0.6) 75%);
  border: 4px solid rgba(45, 212, 191, 0.45);
  box-shadow: 0 0 28px rgba(45, 212, 191, 0.18), inset 0 0 18px rgba(45, 212, 191, 0.08);
  position: relative;
}
.score-circle.score-excellent {
  border-color: var(--c-moss);
  background: radial-gradient(circle at 50% 50%, rgba(132, 204, 22, 0.20) 0%, rgba(10, 22, 28, 0.6) 75%);
  box-shadow: 0 0 28px rgba(132, 204, 22, 0.22), inset 0 0 18px rgba(132, 204, 22, 0.08);
}
.score-circle.score-good {
  border-color: var(--c-emerald);
  background: radial-gradient(circle at 50% 50%, rgba(45, 212, 191, 0.18) 0%, rgba(10, 22, 28, 0.6) 75%);
}
.score-circle.score-fair {
  border-color: var(--c-amber-warm);
  background: radial-gradient(circle at 50% 50%, rgba(245, 158, 11, 0.16) 0%, rgba(10, 22, 28, 0.6) 75%);
  box-shadow: 0 0 28px rgba(245, 158, 11, 0.18), inset 0 0 18px rgba(245, 158, 11, 0.06);
}
.score-circle.score-poor {
  border-color: var(--c-rust);
  background: radial-gradient(circle at 50% 50%, rgba(217, 119, 87, 0.22) 0%, rgba(10, 22, 28, 0.6) 75%);
  box-shadow: 0 0 28px rgba(217, 119, 87, 0.22), inset 0 0 18px rgba(217, 119, 87, 0.08);
}
.score-num {
  font-size: 56px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.score-label {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 1px;
  margin-top: 6px;
}

.dim-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.dim-card {
  padding: 12px 14px;
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
  border-radius: 8px;
}
.dim-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.dim-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.dim-score {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.dim-bar {
  height: 6px;
  background: var(--border-line);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 6px;
}
.dim-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width .35s ease;
}
.dim-detail {
  font-size: 11.5px;
  color: var(--text-muted);
}

.col-green  { color: var(--c-moss); }
.col-green.dim-bar-fill,
.col-green.conf-bar-fill { background: linear-gradient(90deg, #22c55e, var(--c-moss)); }
.col-blue   { color: var(--c-emerald); }
.col-blue.dim-bar-fill,
.col-blue.conf-bar-fill  { background: linear-gradient(90deg, var(--c-emerald), var(--c-mint)); }
.col-yellow { color: var(--c-amber-warm); }
.col-yellow.dim-bar-fill,
.col-yellow.conf-bar-fill { background: linear-gradient(90deg, var(--c-amber-warm), var(--c-rust)); }
.col-red    { color: var(--c-rust); }
.col-red.dim-bar-fill,
.col-red.conf-bar-fill   { background: linear-gradient(90deg, var(--c-rust), var(--c-rust)); }

/* 风险列表 */
.risks-section {
  background: rgba(45, 212, 191, 0.05);
  border: 1px solid rgba(45, 212, 191, 0.10);
  border-radius: 8px;
  padding: 14px 16px;
}
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-meta {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
}
.risk-list { display: flex; flex-direction: column; gap: 8px; }
.risk-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  background: rgba(180, 230, 225, 0.04);
  border-radius: 6px;
  border-left: 3px solid var(--c-emerald);
}
.risk-item.risk-high { border-left-color: var(--c-rust); }
.risk-item.risk-low  { border-left-color: var(--text-muted); }
.risk-msg { flex: 1; font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.risk-fields { font-size: 11.5px; color: var(--text-muted); margin-top: 4px; }
.aff-tag {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 6px;
  background: rgba(180, 230, 225, 0.06);
  border: 1px solid var(--border-line);
  border-radius: 3px;
  color: var(--text-secondary);
  font-family: ui-monospace, monospace;
}
.aff-more {
  margin-left: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.risks-empty {
  padding: 12px 16px;
  background: rgba(132, 204, 22, 0.06);
  border: 1px solid rgba(132, 204, 22, 0.30);
  border-radius: 8px;
  font-size: 13px;
  color: var(--c-moss);
  font-weight: 600;
}

/* 字段角色矩阵 */
.fields-section { }
.field-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.field-cell {
  padding: 10px 12px;
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
  border-radius: 6px;
  border-left: 3px solid var(--border-line);
}
.field-cell.role-time    { border-left-color: var(--c-emerald); }
.field-cell.role-id      { border-left-color: var(--c-moss); }
.field-cell.role-metric  { border-left-color: var(--c-emerald); }
.field-cell.role-dim     { border-left-color: var(--c-sand); }
.field-cell.role-text    { border-left-color: var(--c-amber-warm); }
.field-cell.role-unknown { border-left-color: var(--text-muted); opacity: .75; }

.field-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
  gap: 8px;
}
.field-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
  flex: 1;
}
.field-meta-row { margin-bottom: 4px; }
.conf-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
.conf-label { width: 40px; flex-shrink: 0; }
.conf-bar-track {
  flex: 1;
  height: 4px;
  background: var(--border-line);
  border-radius: 2px;
  overflow: hidden;
}
.conf-bar-fill {
  display: block;
  height: 100%;
  border-radius: 2px;
}
.conf-num {
  font-variant-numeric: tabular-nums;
  width: 24px;
  text-align: right;
}
.field-stats {
  font-size: 11.5px;
  color: var(--text-muted);
}
.stat-warn { color: var(--c-amber-warm); font-weight: 600; }

@media (max-width: 900px) {
  .header-row { grid-template-columns: 1fr; }
  .score-circle { margin: 0 auto; }
  .dim-grid { grid-template-columns: 1fr; }
}
</style>
