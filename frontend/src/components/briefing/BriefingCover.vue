<template>
  <section class="briefing-cover">
    <div class="cover-meta">
      <span class="badge">东风汽车 · 智汇车联</span>
      <span class="period">{{ meta.period }}</span>
    </div>
    <h1 class="cover-headline">{{ cover.headline }}</h1>
    <div class="cover-subline">
      <span>主题:{{ meta.topic }}</span>
      <span class="dot">·</span>
      <span>生成于 {{ formattedDate }}</span>
      <span v-if="meta.audit_id" class="dot">·</span>
      <span v-if="meta.audit_id" class="audit">审计 {{ meta.audit_id }}</span>
    </div>
    <div v-if="cover.kpi_strip && cover.kpi_strip.length" class="kpi-strip">
      <KpiBadge
        v-for="(k, i) in cover.kpi_strip"
        :key="i"
        :kpi="k"
        @show-evidence="onKpiEvidence(k)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BriefingDoc, KPI, Evidence } from '@/api/report'
import KpiBadge from './KpiBadge.vue'

const props = defineProps<{
  cover: BriefingDoc['cover']
  meta: BriefingDoc['meta']
}>()

const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()

function onKpiEvidence(k: KPI) {
  emit('show-evidence', {
    title:    `KPI · ${k.label}`,
    subtitle: `指标值 ${k.value}${k.delta ? ' · ' + k.delta : ''}`,
    evidence: k.evidence || [],
  })
}

const formattedDate = computed(() => {
  if (!props.meta.generated_at) return ''
  const d = new Date(props.meta.generated_at)
  if (isNaN(d.getTime())) return props.meta.generated_at.slice(0, 10)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})
</script>

<style scoped>
/* 报纸头版式 cover: 不再用 16~20px 圆角的"卡片", 改成 0 圆角无背景的"专题封面",
 * 顶/底用粗 + 细两条 hairline 模拟报纸头版分隔, 标题撑满版面, 极弱光晕做氛围 */
.briefing-cover {
  position: relative;
  border-radius: 0;
  border: 0;
  padding: 36px 0 40px;
  background: transparent;
  color: var(--text-primary);
  overflow: visible;
  box-shadow: none;
  border-top: 2px solid var(--c-emerald);
  border-bottom: 1px solid var(--border-line);
}

/* 上方在 c-emerald 粗线下再叠一条细 hairline, 模拟报纸双线 */
.briefing-cover::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 4px;
  height: 1px;
  background: var(--border-line);
  pointer-events: none;
}

/* 极弱右上翡翠光晕, 拉氛围 */
.briefing-cover::after {
  content: '';
  position: absolute;
  top: -40px;
  right: -40px;
  width: 360px;
  height: 220px;
  background: radial-gradient(closest-side, rgba(45, 212, 191, 0.10), transparent 70%);
  filter: blur(20px);
  pointer-events: none;
  z-index: 0;
}

.cover-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  position: relative;
  z-index: 1;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(45, 212, 191, 0.14);
  border: 1px solid rgba(45, 212, 191, 0.32);
  color: var(--c-emerald);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.4px;
  text-transform: uppercase;
}

.period {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 0.4px;
}

.cover-headline {
  position: relative;
  z-index: 1;
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 36px;
  line-height: 1.22;
  margin: 0 0 14px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: var(--text-primary);
}

.cover-subline {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 22px;
}

.cover-subline .dot {
  color: var(--text-dim);
  opacity: 0.7;
}

.cover-subline .audit {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  color: var(--text-muted);
}

.kpi-strip {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

@media (max-width: 768px) {
  .briefing-cover { padding: 24px; border-radius: 16px; }
  .cover-headline { font-size: 26px; }
  .kpi-strip { grid-template-columns: repeat(2, 1fr); gap: 12px; }
}
</style>
