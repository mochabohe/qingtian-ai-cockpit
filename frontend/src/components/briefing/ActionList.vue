<template>
  <section class="action-list">
    <div class="head">
      <span class="icon">✅</span>
      <span class="title">行动项</span>
      <span class="count">{{ actions.length }} 项</span>
    </div>
    <div v-if="actions.length" class="items">
      <div v-for="(a, i) in actions" :key="i" class="item" :class="`p-${a.priority}`">
        <input type="checkbox" class="check" disabled />
        <span class="prio">{{ priorityLabel(a.priority) }}</span>
        <span class="owner">{{ a.owner }}</span>
        <span class="action">{{ a.action }}</span>
        <EvidenceTrigger
          class="action-evidence"
          size="small"
          :evidence="a.evidence"
          @open="onShowEvidence(a)"
        />
        <span class="deadline" v-if="a.deadline">{{ a.deadline }}</span>
        <span class="deadline-empty" v-else>—</span>
      </div>
    </div>
    <div v-else class="empty">(暂无行动项)</div>
  </section>
</template>

<script setup lang="ts">
import type { ActionItem, Evidence } from '@/api/report'
import EvidenceTrigger from './EvidenceTrigger.vue'

defineProps<{ actions: ActionItem[] }>()
const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()

function priorityLabel(p: 'high' | 'medium' | 'low'): string {
  return ({ high: 'HIGH', medium: 'MID', low: 'LOW' } as const)[p] || p
}

function onShowEvidence(a: ActionItem) {
  emit('show-evidence', {
    title:    `行动项 · ${a.owner}`,
    subtitle: a.action,
    evidence: a.evidence || [],
  })
}
</script>

<style scoped>
.action-list {
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
  gap: 10px;
  margin-bottom: 14px;
}

.icon { font-size: 16px; }
.title { font-size: 16px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.3px; }
.count {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--text-muted);
  background: rgba(180, 230, 225, 0.06);
  border: 1px solid var(--border-line);
  padding: 3px 10px;
  border-radius: var(--r-pill);
  letter-spacing: 0.4px;
}

.items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  display: grid;
  grid-template-columns: 22px 60px 110px 1fr auto 100px;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: var(--r-md);
  background: rgba(180, 230, 225, 0.03);
  border: 1px solid var(--border-line);
  font-size: 13px;
  transition: all var(--t-fast);
}

.action-evidence {
  flex-shrink: 0;
}

.item:hover {
  background: rgba(45, 212, 191, 0.05);
  border-color: rgba(45, 212, 191, 0.18);
}

.check {
  margin: 0;
  width: 16px;
  height: 16px;
  accent-color: var(--c-emerald);
}

.prio {
  font-size: 11px;
  font-weight: 700;
  text-align: center;
  padding: 3px 8px;
  border-radius: var(--r-sm);
  letter-spacing: 0.5px;
}

.p-high .prio { background: rgba(217, 119, 87, 0.14); color: var(--c-rust); border: 1px solid rgba(217, 119, 87, 0.32); }
.p-medium .prio { background: rgba(245, 158, 11, 0.12); color: var(--c-amber-warm); border: 1px solid rgba(245, 158, 11, 0.32); }
.p-low .prio { background: rgba(45, 212, 191, 0.10); color: var(--c-emerald); border: 1px solid rgba(45, 212, 191, 0.28); }

.owner {
  font-weight: 600;
  color: var(--text-primary);
}

.action {
  color: var(--text-secondary);
  line-height: 1.55;
}

.deadline {
  font-size: 12px;
  color: var(--text-muted);
  text-align: right;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.deadline-empty {
  color: var(--text-dim);
  text-align: right;
  font-size: 12px;
}

.empty { color: var(--text-muted); font-size: 13px; padding: 20px; text-align: center; }

@media (max-width: 768px) {
  .item {
    grid-template-columns: 22px 60px 1fr;
    grid-template-rows: auto auto;
    row-gap: 4px;
  }
  .owner, .action, .deadline {
    grid-column: 3 / 4;
  }
  .deadline { text-align: left; }
}
</style>
