<template>
  <article class="text-card">
    <header class="head">
      <h3 class="title">
        <span class="dot"></span>
        {{ section.title }}
      </h3>
      <EvidenceTrigger :evidence="section.evidence" @open="onShowEvidence" />
    </header>
    <p class="body">{{ section.body }}</p>
  </article>
</template>

<script setup lang="ts">
import type { TextSection, Evidence } from '@/api/report'
import EvidenceTrigger from './EvidenceTrigger.vue'

const props = defineProps<{ section: TextSection }>()
const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()

function onShowEvidence() {
  emit('show-evidence', {
    title:    `${props.section.title}`,
    subtitle: '文本卡片',
    evidence: props.section.evidence || [],
  })
}
</script>

<style scoped>
.text-card {
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

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  background: var(--c-emerald);
  border-radius: 50%;
  box-shadow: 0 0 6px rgba(45, 212, 191, 0.6);
}

.body {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.85;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
