<template>
  <section class="exec-summary">
    <div class="head">
      <span class="icon">📌</span>
      <span class="title">摘要</span>
    </div>
    <div v-if="sentences.length" class="sentences">
      <p v-for="(s, i) in sentences" :key="i" class="sentence">
        <span class="step">{{ stepLabels[i] || i + 1 }}</span>
        <span class="text">{{ s }}</span>
      </p>
    </div>
    <div v-else class="empty">(暂无摘要)</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ summary: string }>()

const stepLabels = ['现状', '归因', '行动方向']

const sentences = computed(() => {
  if (!props.summary) return []
  return props.summary
    .split(/(?<=[。!?！?])\s*/)
    .map(s => s.trim())
    .filter(Boolean)
    .slice(0, 4)
})
</script>

<style scoped>
.exec-summary {
  border-radius: 16px;
  padding: 24px 28px;
  background: var(--bg-glass);
  border: 1px solid var(--border-line);
  border-left: 3px solid var(--c-emerald);
  box-shadow: var(--shadow-card), var(--shadow-inset-line);
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  letter-spacing: 1.6px;
  text-transform: uppercase;
}

.icon { font-size: 16px; }

.sentences {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sentence {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin: 0;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-primary);
}

/* 第一段(现状)首字下沉, 加杂志感 */
.sentence:first-child .text::first-letter {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: 2.6em;
  float: left;
  line-height: 0.92;
  margin: 4px 8px 0 0;
  color: var(--c-emerald);
  font-weight: 700;
}

.step {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 50px;
  height: 24px;
  padding: 0 10px;
  border-radius: 12px;
  background: linear-gradient(180deg, var(--c-emerald), var(--c-emerald-deep));
  color: #04161a;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
  margin-top: 3px;
}

.text { flex: 1; font-weight: 500; }

.empty { color: var(--text-muted); font-size: 13px; }
</style>
