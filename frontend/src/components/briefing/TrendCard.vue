<template>
  <article class="trend-card">
    <header class="head">
      <h3 class="title">
        <span class="emoji">📈</span>
        {{ section.title }}
      </h3>
      <div class="head-right">
        <span v-if="deltaText" class="delta-badge" :class="deltaTone">
          {{ deltaText }}
        </span>
        <EvidenceTrigger :evidence="section.evidence" @open="onShowEvidence" />
      </div>
    </header>
    <div class="metric">
      <span class="metric-label">指标</span>
      <strong class="metric-value">{{ section.metric }}</strong>
      <span v-if="section.unit" class="metric-unit">({{ section.unit }})</span>
    </div>
    <EChart v-if="hasData" :option="option" height="260px" />
    <div v-else class="empty-chart">该周期暂无符合阈值的趋势数据</div>
    <InsightLine v-if="section.insight" :text="section.insight" />
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TrendSection, Evidence } from '@/api/report'
import EChart from '@/components/EChart.vue'
import InsightLine from './InsightLine.vue'
import EvidenceTrigger from './EvidenceTrigger.vue'
import { trendColor, axisStyle, tooltipStyle } from '@/utils/chartPalette'

const props = defineProps<{ section: TrendSection }>()
const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()

function onShowEvidence() {
  emit('show-evidence', {
    title:    `趋势 · ${props.section.title}`,
    subtitle: `指标 ${props.section.metric}${props.section.unit ? ' (' + props.section.unit + ')' : ''}`,
    evidence: props.section.evidence || [],
  })
}

const hasData = computed(() => Array.isArray(props.section.data) && props.section.data.length > 0)

const deltaText = computed(() => {
  const d = props.section.delta
  if (!d || d.value == null || isNaN(Number(d.value))) return ''
  const sign = d.value > 0 ? '↑' : d.value < 0 ? '↓' : '·'
  const abs = Math.abs(d.value).toFixed(1)
  return `${sign} ${d.baseline || ''} ${abs}%`
})

const deltaTone = computed(() => {
  const v = props.section.delta?.value
  if (v == null) return 'neutral'
  if (v > 0) return 'positive'
  if (v < 0) return 'negative'
  return 'neutral'
})

const lineColor = computed(() => trendColor(props.section.delta?.value))

const option = computed(() => ({
  grid: { left: 40, right: 28, top: 24, bottom: 36 },
  tooltip: { trigger: 'axis', ...tooltipStyle },
  xAxis: {
    type: 'category',
    data: props.section.data.map(p => p.x),
    ...axisStyle,
  },
  yAxis: {
    type: 'value',
    ...axisStyle,
  },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      data: props.section.data.map(p => p.y),
      lineStyle: { color: lineColor.value, width: 2.5 },
      itemStyle: { color: lineColor.value, borderColor: 'rgba(5, 13, 17, 0.85)', borderWidth: 1.5 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: hexToRgba(lineColor.value, 0.28) },
            { offset: 1, color: hexToRgba(lineColor.value, 0.02) },
          ],
        },
      },
      label: {
        show: true,
        position: 'top',
        color: lineColor.value,
        fontSize: 11,
        fontWeight: 600,
      },
    },
  ],
}))

function hexToRgba(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return hex
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
</script>

<style scoped>
.trend-card {
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
  margin-bottom: 12px;
}

.head-right {
  display: flex;
  align-items: center;
  gap: 8px;
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

.delta-badge {
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.3px;
  font-variant-numeric: tabular-nums;
}

.delta-badge.positive { background: rgba(132, 204, 22, 0.14); color: var(--c-moss); border: 1px solid rgba(132, 204, 22, 0.28); }
.delta-badge.negative { background: rgba(217, 119, 87, 0.14); color: var(--c-rust); border: 1px solid rgba(217, 119, 87, 0.32); }
.delta-badge.neutral  { background: rgba(45, 212, 191, 0.10); color: var(--c-emerald); border: 1px solid rgba(45, 212, 191, 0.28); }

.metric {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}

.metric-label {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.3px;
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.metric-unit {
  font-size: 12px;
  color: var(--text-muted);
}

.empty-chart {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  background: rgba(180, 230, 225, 0.02);
  border: 1px dashed var(--border-line);
  border-radius: var(--r-md);
  color: var(--text-muted);
  font-size: 13px;
  gap: 6px;
}
.empty-chart::before {
  content: '—';
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 36px;
  color: var(--text-dim);
  line-height: 1;
}
</style>
