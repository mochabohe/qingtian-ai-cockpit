<template>
  <article class="alert-card" :class="`level-${section.level || 'warning'}`">
    <div class="head">
      <span class="emoji">{{ levelEmoji }}</span>
      <h3 class="title">{{ section.title }}</h3>
      <span class="level-tag">{{ (section.level || 'warning').toUpperCase() }}</span>
      <EvidenceTrigger :evidence="section.evidence" @open="onShowEvidence" />
    </div>
    <p class="msg">{{ section.msg }}</p>
    <div v-if="section.evidence_text && section.evidence_text.length" class="evidence">
      <div class="evidence-head">证据链</div>
      <ul class="evidence-list">
        <li v-for="(e, i) in section.evidence_text" :key="i">{{ e }}</li>
      </ul>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AlertSection, Evidence } from '@/api/report'
import EvidenceTrigger from './EvidenceTrigger.vue'

const props = defineProps<{ section: AlertSection }>()
const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()

const levelEmoji = computed(() => {
  return ({ high: '🔴', warning: '🟠', info: '🔵' } as const)[props.section.level] || '🟠'
})

function onShowEvidence() {
  emit('show-evidence', {
    title:    `预警 · ${props.section.title}`,
    subtitle: `级别 ${(props.section.level || 'warning').toUpperCase()}`,
    evidence: props.section.evidence || [],
  })
}
</script>

<style scoped>
.alert-card {
  border-radius: 16px;
  padding: 20px 22px;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  border-left-width: 4px;
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
  color: var(--text-primary);
}

.level-high    { border-left-color: var(--c-rust); background: linear-gradient(135deg, rgba(217, 119, 87, 0.10) 0%, rgba(16, 32, 40, 0.72) 30%); }
.level-warning { border-left-color: var(--c-amber-warm); background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(16, 32, 40, 0.72) 30%); }
.level-info    { border-left-color: var(--c-emerald); background: linear-gradient(135deg, rgba(45, 212, 191, 0.08) 0%, rgba(16, 32, 40, 0.72) 30%); }

.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.emoji { font-size: 16px; }

.title {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.3px;
  margin: 0;
}

.level-tag {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 1.2px;
  padding: 3px 10px;
  border-radius: var(--r-pill);
  background: rgba(180, 230, 225, 0.06);
  border: 1px solid var(--border-line);
  color: var(--text-secondary);
}

.level-high    .level-tag { background: rgba(217, 119, 87, 0.14); color: var(--c-rust); border-color: rgba(217, 119, 87, 0.32); }
.level-warning .level-tag { background: rgba(245, 158, 11, 0.14); color: var(--c-amber-warm); border-color: rgba(245, 158, 11, 0.32); }
.level-info    .level-tag { background: rgba(45, 212, 191, 0.10); color: var(--c-emerald); border-color: rgba(45, 212, 191, 0.28); }

.msg {
  margin: 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-primary);
  font-weight: 500;
}

.evidence {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-line);
}

.evidence-head {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 1.2px;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.evidence-list {
  margin: 0;
  padding-left: 22px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.75;
}

.evidence-list li { margin: 2px 0; }
</style>
