<template>
  <div class="kpi-badge" :class="`tone-${kpi.tone || 'neutral'}`">
    <div class="kpi-value">{{ kpi.value }}</div>
    <div class="kpi-label">{{ kpi.label }}</div>
    <div v-if="kpi.delta" class="kpi-delta">{{ kpi.delta }}</div>
    <EvidenceTrigger
      v-if="kpi.evidence && kpi.evidence.length"
      class="kpi-evidence"
      size="small"
      :evidence="kpi.evidence"
      @open="$emit('show-evidence')"
    />
  </div>
</template>

<script setup lang="ts">
import type { KPI } from '@/api/report'
import EvidenceTrigger from './EvidenceTrigger.vue'

defineProps<{ kpi: KPI }>()
defineEmits<{ (e: 'show-evidence'): void }>()
</script>

<style scoped>
.kpi-badge {
  border-radius: 12px;
  padding: 14px 16px;
  background: rgba(180, 230, 225, 0.05);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(180, 230, 225, 0.10);
  min-width: 130px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
}

.kpi-evidence {
  margin-top: 4px;
  align-self: flex-start;
}

.kpi-value {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 26px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.1;
  letter-spacing: 0.4px;
  font-variant-numeric: tabular-nums;
}

.kpi-label {
  font-size: 11.5px;
  color: var(--text-muted);
  font-weight: 500;
  letter-spacing: 0.3px;
}

.kpi-delta {
  font-size: 12px;
  font-weight: 600;
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}

.tone-positive .kpi-delta { color: var(--c-moss); }
.tone-negative .kpi-delta { color: var(--c-rust); }
.tone-neutral  .kpi-delta { color: var(--c-emerald); }

.tone-positive { border-left: 3px solid var(--c-moss); }
.tone-negative { border-left: 3px solid var(--c-rust); }
.tone-neutral  { border-left: 3px solid var(--c-emerald); }
.tone-positive .kpi-value { color: var(--c-moss); }
.tone-negative .kpi-value { color: var(--c-rust); }
</style>
