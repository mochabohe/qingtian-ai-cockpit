import { http } from './http'

// ============================================================================
// BriefingDoc 类型(与 backend/app/services/briefing_schema.py 保持一致)
// ============================================================================

// P0-3 洞察证据链:每条 KPI/section/action 关联的数据来源摘要
export interface Evidence {
  label: string         // 证据标识
  source: string        // 数据来源
  method: string        // 计算口径
  fields: string[]      // 关键字段
  record_count: number  // 命中记录数
  samples: string[]     // 原始样例
  note: string          // 附加说明
}

export interface KPI {
  label: string
  value: string
  delta?: string | null
  tone?: 'positive' | 'negative' | 'neutral'
  evidence?: Evidence[]
}

export interface ActionItem {
  owner: string
  action: string
  deadline: string
  priority: 'high' | 'medium' | 'low'
  evidence?: Evidence[]
}

export interface TrendDataPoint { x: string; y: number }
export interface TrendDelta { value: number | null; baseline: string }

export interface TrendSection {
  type: 'trend'
  title: string
  metric: string
  unit?: string | null
  data: TrendDataPoint[]
  delta?: TrendDelta | null
  insight: string
  evidence?: Evidence[]
}

export interface RankingSection {
  type: 'ranking'
  title: string
  columns: string[]
  rows: (string | number)[][]
  insight: string
  evidence?: Evidence[]
}

export interface DistributionDataPoint { label: string; value: number }
export interface DistributionSection {
  type: 'distribution'
  title: string
  data: DistributionDataPoint[]
  insight: string
  evidence?: Evidence[]
}

export interface AlertSection {
  type: 'alert'
  level: 'info' | 'warning' | 'high'
  title: string
  msg: string
  evidence_text?: string[]    // 旧字段名(LLM 输出的字符串证据列表)
  evidence?: Evidence[]
}

export interface TextSection {
  type: 'text'
  title: string
  body: string
  evidence?: Evidence[]
}

export type Section =
  | TrendSection
  | RankingSection
  | DistributionSection
  | AlertSection
  | TextSection

export interface Cover { headline: string; kpi_strip: KPI[] }
export interface Meta {
  title: string
  topic: string
  period: string
  generated_at: string
  audit_id: string
}
export interface Compliance {
  masked_field_count: number
  total_field_count: number
  findings: string[]
  mode?: 'dry_run' | 'production'   // 演示模式 / 生产模式(2026-05-08 加)
}

export interface BriefingDoc {
  meta: Meta
  cover: Cover
  executive_summary: string
  sections: Section[]
  actions: ActionItem[]
  compliance: Compliance
}

// ============================================================================
// 列表项(列表接口加 has_doc 标识是否有结构化版本)
// ============================================================================
export interface ReportItem {
  name: string
  size: number
  modified: number
  has_doc?: boolean
  has_trace?: boolean
}

// ============================================================================
// 全链路追溯(orchestrator 5 步执行轨迹)
// ============================================================================
export interface TraceStepTokens {
  prompt?: number | null
  completion?: number | null
  total?: number | null
}

export interface TraceStep {
  index: number
  name: string
  title: string
  desc: string
  started_at: string
  status: 'running' | 'done' | 'error'
  duration_s: number
  output: string
  output_len: number
  model?: string | null
  error?: string | null
  tokens?: TraceStepTokens
}

export interface ReportTrace {
  topic: string
  data_file?: string | null
  audit_id?: string | null
  generated_at: string
  steps: TraceStep[]
  totals: {
    n_steps: number
    duration_s: number
    tokens_prompt: number
    tokens_completion: number
  }
}

// ============================================================================
// API
// ============================================================================
export async function listReports(): Promise<ReportItem[]> {
  const { data } = await http.get('/report/list')
  return data.data || []
}

export async function getReportMarkdown(filename: string): Promise<string> {
  const { data } = await http.get(`/report/${encodeURIComponent(filename)}/markdown`)
  return data.data.markdown
}

export async function getReportDoc(filename: string): Promise<BriefingDoc> {
  const { data } = await http.get(`/report/${encodeURIComponent(filename)}/doc`)
  return data.data
}

export async function getReportTrace(filename: string): Promise<ReportTrace> {
  const { data } = await http.get(`/report/${encodeURIComponent(filename)}/trace`)
  return data.data
}

export async function saveReport(topic: string, markdown: string, filename?: string) {
  const { data } = await http.post('/report/save', { topic, markdown, filename })
  return data.data
}

export interface SaveRevisionResult {
  filename: string
  path: string
  size: number
  copied_siblings: string[]
  note: string
}

/**
 * P1-1 简报最小审阅:把 textarea 编辑后的正文保存为修订版。
 * 后端纯文件操作,不调 LLM。
 */
export async function saveRevision(
  originalFilename: string,
  markdown: string,
  note?: string,
): Promise<SaveRevisionResult> {
  const { data } = await http.post('/report/save-revision', {
    original_filename: originalFilename,
    markdown,
    note,
  })
  return data.data
}

export async function deleteReport(filename: string) {
  await http.delete(`/report/${encodeURIComponent(filename)}`)
}

export function getHtmlUrl(filename: string): string {
  return `/api/report/${encodeURIComponent(filename)}/html`
}

export function getPptxUrl(filename: string): string {
  return `/api/report/${encodeURIComponent(filename)}/pptx`
}

export function getJsonUrl(filename: string): string {
  return `/api/report/${encodeURIComponent(filename)}/json`
}
