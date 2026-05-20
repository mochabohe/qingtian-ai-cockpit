<template>
  <article class="dist-card">
    <header class="head">
      <h3 class="title">
        <span class="emoji">🎯</span>
        {{ section.title }}
      </h3>
      <EvidenceTrigger :evidence="section.evidence" @open="onShowEvidence" />
    </header>
    <EChart v-if="hasData" :option="option" height="280px" />
    <div v-else class="empty">该周期暂无符合阈值的分布数据</div>
    <InsightLine v-if="section.insight" :text="section.insight" />
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DistributionSection, Evidence } from '@/api/report'
import EChart from '@/components/EChart.vue'
import InsightLine from './InsightLine.vue'
import EvidenceTrigger from './EvidenceTrigger.vue'
import { BRIEFING_PALETTE, tooltipStyle } from '@/utils/chartPalette'

const props = defineProps<{ section: DistributionSection }>()
const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()
const hasData = computed(() => Array.isArray(props.section.data) && props.section.data.length > 0)

function onShowEvidence() {
  emit('show-evidence', {
    title:    `分布 · ${props.section.title}`,
    subtitle: `${props.section.data?.length || 0} 个分类`,
    evidence: props.section.evidence || [],
  })
}

const option = computed(() => ({
  color: BRIEFING_PALETTE,
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)', ...tooltipStyle },
  legend: {
    orient: 'vertical',
    right: 8,
    top: 'middle',
    icon: 'circle',
    itemWidth: 8,
    itemHeight: 8,
    textStyle: { fontSize: 12, color: '#a8c0bd' },
  },
  series: [
    {
      type: 'pie',
      radius: ['48%', '72%'],
      center: ['38%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderColor: 'rgba(5, 13, 17, 0.85)',
        borderWidth: 2,
      },
      label: {
        show: true,
        formatter: '{b}\n{d}%',
        fontSize: 11,
        color: '#e6f1f0',
      },
      labelLine: {
        show: true,
        length: 8,
        length2: 8,
        lineStyle: { color: 'rgba(180, 230, 225, 0.24)' },
      },
      data: props.section.data.map(p => ({ name: p.label, value: p.value })),
    },
  ],
}))
</script>

<style scoped>
.dist-card {
  border-radius: 16px;
  padding: 20px 22px;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
  color: var(--text-primary);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
  margin: 0;
}

.emoji { font-size: 16px; }

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 240px;
  color: var(--text-muted);
  font-size: 13px;
  background: rgba(180, 230, 225, 0.02);
  border: 1px dashed var(--border-line);
  border-radius: var(--r-md);
}
.empty::before {
  content: '—';
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 36px;
  color: var(--text-dim);
  line-height: 1;
}
</style>
