<template>
  <div class="briefing-doc">
    <!-- 报刊报头: VOL + 期数 + audit_id, 营造杂志感 -->
    <header v-if="doc.meta" class="briefing-masthead">
      <span class="masthead-vol">VOL · {{ formatPeriod(doc.meta.period) }}</span>
      <span class="masthead-id">№ {{ (doc.meta.audit_id || '').slice(0, 12) || '—' }}</span>
    </header>

    <BriefingCover :cover="doc.cover" :meta="doc.meta" @show-evidence="openEvidence" />

    <ExecutiveSummary v-if="doc.executive_summary" :summary="doc.executive_summary" />

    <div v-if="doc.sections && doc.sections.length" class="sections">
      <component
        v-for="(s, i) in doc.sections"
        :key="i"
        :is="resolveCardComponent(s)"
        :section="s"
        @show-evidence="openEvidence"
      />
    </div>

    <ActionList
      v-if="doc.actions && doc.actions.length"
      :actions="doc.actions"
      @show-evidence="openEvidence"
    />

    <ComplianceFooter
      v-if="doc.compliance"
      :compliance="doc.compliance"
      :audit-id="doc.meta.audit_id"
    />

    <EvidenceDrawer
      v-model="evidenceOpen"
      :title="evidenceTitle"
      :subtitle="evidenceSubtitle"
      :evidence="evidenceItems"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { BriefingDoc as BriefingDocType, Section, Evidence } from '@/api/report'
import BriefingCover from './BriefingCover.vue'
import ExecutiveSummary from './ExecutiveSummary.vue'
import TrendCard from './TrendCard.vue'
import RankingCard from './RankingCard.vue'
import DistributionCard from './DistributionCard.vue'
import AlertCard from './AlertCard.vue'
import TextCard from './TextCard.vue'
import ActionList from './ActionList.vue'
import ComplianceFooter from './ComplianceFooter.vue'
import EvidenceDrawer from './EvidenceDrawer.vue'

defineProps<{ doc: BriefingDocType }>()

const SECTION_MAP = {
  trend: TrendCard,
  ranking: RankingCard,
  distribution: DistributionCard,
  alert: AlertCard,
  text: TextCard,
}

function resolveCardComponent(s: Section) {
  return (SECTION_MAP as any)[s.type] || TextCard
}

// 抽屉状态
const evidenceOpen     = ref(false)
const evidenceTitle    = ref('')
const evidenceSubtitle = ref('')
const evidenceItems    = ref<Evidence[]>([])

function openEvidence(payload: { title: string; subtitle?: string; evidence: Evidence[] }) {
  evidenceTitle.value    = payload.title
  evidenceSubtitle.value = payload.subtitle || ''
  evidenceItems.value    = payload.evidence || []
  evidenceOpen.value     = true
}

// 报头期数格式化: "2026-05" → "2026 · MAY"
function formatPeriod(p?: string): string {
  if (!p) return ''
  const m = /^(\d{4})-(\d{2})/.exec(p)
  if (!m) return p
  const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
  return `${m[1]} · ${months[Number(m[2]) - 1] || m[2]}`
}
</script>

<style scoped>
.briefing-doc {
  display: flex;
  flex-direction: column;
  gap: 32px;
  position: relative;
}

/* 报头 (VOL + audit_id), 与 ::before 翡翠下划线一起做出杂志感 */
.briefing-masthead {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--c-emerald);
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  letter-spacing: 0.4px;
}
.briefing-masthead .masthead-vol {
  font-size: 13px;
  letter-spacing: 3px;
  color: var(--c-emerald);
  font-weight: 600;
  text-transform: uppercase;
}
.briefing-masthead .masthead-id {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 1px;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 40px;
}

/* ============================================================
 * 杂志扁平化 — 子组件强制去框
 * 进 BriefingDoc 之后, 所有 trend/ranking/dist/alert/text/action/exec 卡片
 * 都丢掉外框/背景/阴影, 只保留排版与色彩对比, 像一份真正的杂志稿
 * ============================================================ */
.briefing-doc :deep(.trend-card),
.briefing-doc :deep(.ranking-card),
.briefing-doc :deep(.dist-card),
.briefing-doc :deep(.alert-card),
.briefing-doc :deep(.text-card),
.briefing-doc :deep(.action-list),
.briefing-doc :deep(.exec-summary),
.briefing-doc :deep(.compliance-footer) {
  background: transparent !important;
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}

/* 摘要保留左侧翡翠竖线作为视觉锚点(杂志报道首段) */
.briefing-doc :deep(.exec-summary) {
  padding-left: 18px !important;
  border-left: 2px solid var(--c-emerald) !important;
  border-radius: 0 !important;
}

/* alert 还要保留左侧色条用于警示分级 */
.briefing-doc :deep(.alert-card) {
  padding: 4px 0 4px 18px !important;
  border-left: 3px solid var(--border-strong) !important;
}
.briefing-doc :deep(.alert-card.level-high)    { border-left-color: var(--c-rust) !important; }
.briefing-doc :deep(.alert-card.level-warning) { border-left-color: var(--c-amber-warm) !important; }
.briefing-doc :deep(.alert-card.level-info)    { border-left-color: var(--c-emerald) !important; }

/* 标题视觉提级: 从子组件的 .head .title 16px 升到 22px serif, 形成报道感 */
.briefing-doc :deep(.trend-card .title),
.briefing-doc :deep(.ranking-card .title),
.briefing-doc :deep(.dist-card .title),
.briefing-doc :deep(.alert-card .title),
.briefing-doc :deep(.text-card .title),
.briefing-doc :deep(.action-list .title) {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif !important;
  font-size: 22px !important;
  font-weight: 600 !important;
  letter-spacing: 0.4px !important;
  color: var(--text-primary) !important;
}

/* 章节间用粗 + 细两条 hairline 替代卡片边框 */
.sections > * + * {
  position: relative;
  padding-top: 32px;
}
.sections > * + *::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 56px;
  height: 2px;
  background: var(--c-emerald);
  opacity: 0.7;
  pointer-events: none;
}
.sections > * + *::after {
  content: '';
  position: absolute;
  top: 0;
  left: 56px;
  right: 0;
  height: 1px;
  background: var(--border-line);
  pointer-events: none;
}

/* ActionList / ComplianceFooter 与上方 sections 也加分隔 */
.briefing-doc > .action-list,
.briefing-doc > .compliance-footer,
.briefing-doc :deep(.action-list),
.briefing-doc :deep(.compliance-footer) {
  position: relative;
}

@media print {
  .briefing-doc > * {
    page-break-inside: avoid;
  }
}
</style>
