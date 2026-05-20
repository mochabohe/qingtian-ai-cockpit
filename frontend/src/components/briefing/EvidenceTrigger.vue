<template>
  <!--
    P0-3 证据按钮:嵌在 KPI/section/action 里,点击触发 EvidenceDrawer
    设计原则:无证据时不显示(避免空按钮);有证据时显示数量
  -->
  <button
    v-if="hasEvidence"
    class="evidence-trigger"
    :class="`size-${size}`"
    @click.stop="$emit('open')"
    :title="`查看 ${count} 条证据`"
  >
    <svg class="ev-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
    <span class="ev-text">查看证据</span>
    <span class="ev-count">{{ count }}</span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Evidence } from '@/api/report'

const props = withDefaults(defineProps<{
  evidence?: Evidence[]
  size?: 'small' | 'normal'
}>(), {
  evidence: () => [],
  size: 'normal',
})

defineEmits<{
  (e: 'open'): void
}>()

const count = computed(() => props.evidence?.length || 0)
const hasEvidence = computed(() => count.value > 0)
</script>

<style scoped>
.evidence-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  background: rgba(45, 212, 191, 0.10);
  border: 1px solid rgba(45, 212, 191, 0.28);
  border-radius: var(--r-pill);
  font-size: 11.5px;
  color: var(--c-emerald);
  cursor: pointer;
  transition: all var(--t-fast);
  font-weight: 500;
  white-space: nowrap;
}
.evidence-trigger:hover {
  background: rgba(45, 212, 191, 0.18);
  border-color: rgba(45, 212, 191, 0.5);
  transform: translateY(-1px);
}
.evidence-trigger.size-small {
  font-size: 10.5px;
  padding: 2px 7px;
  gap: 3px;
}
.ev-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}
.size-small .ev-icon {
  width: 10px;
  height: 10px;
}
.ev-text {
  letter-spacing: 0.2px;
}
.ev-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: var(--c-emerald);
  color: #04161a;
  border-radius: var(--r-sm);
  font-size: 10.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.size-small .ev-count {
  min-width: 14px;
  height: 14px;
  font-size: 9.5px;
}
</style>
