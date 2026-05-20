<template>
  <article class="ranking-card">
    <header class="head">
      <h3 class="title">
        <span class="emoji">🏆</span>
        {{ section.title }}
      </h3>
      <EvidenceTrigger :evidence="section.evidence" @open="onShowEvidence" />
    </header>
    <div v-if="hasRows" class="table-wrap">
      <table class="rank-table">
        <thead>
          <tr>
            <th class="rank-col">#</th>
            <th v-for="(c, i) in section.columns" :key="i">{{ c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in section.rows" :key="i" :class="{ 'top-row': i < 3 }">
            <td class="rank-col">
              <span class="rank-badge" :class="{ gold: i === 0, silver: i === 1, bronze: i === 2 }">
                {{ i + 1 }}
              </span>
            </td>
            <td v-for="(cell, j) in row" :key="j">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty">该周期暂无符合阈值的排名数据</div>
    <InsightLine v-if="section.insight" :text="section.insight" />
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RankingSection, Evidence } from '@/api/report'
import InsightLine from './InsightLine.vue'
import EvidenceTrigger from './EvidenceTrigger.vue'

const props = defineProps<{ section: RankingSection }>()
const emit = defineEmits<{
  (e: 'show-evidence', payload: { title: string; subtitle: string; evidence: Evidence[] }): void
}>()
const hasRows = computed(() => Array.isArray(props.section.rows) && props.section.rows.length > 0)

function onShowEvidence() {
  emit('show-evidence', {
    title:    `排名 · ${props.section.title}`,
    subtitle: `${props.section.rows?.length || 0} 项排名 · ${(props.section.columns || []).join(' / ')}`,
    evidence: props.section.evidence || [],
  })
}
</script>

<style scoped>
.ranking-card {
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
  margin-bottom: 14px;
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

.table-wrap {
  overflow-x: auto;
  margin: 0 -4px;
}

.rank-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}

.rank-table th {
  text-align: left;
  padding: 10px 12px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-muted);
  background: rgba(180, 230, 225, 0.04);
  border-bottom: 1px solid var(--border-line);
  letter-spacing: 0.4px;
}

.rank-table th:first-child { border-top-left-radius: var(--r-sm); }
.rank-table th:last-child  { border-top-right-radius: var(--r-sm); }

.rank-table td {
  padding: 10px 12px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-subtle);
}

.rank-col {
  width: 48px;
  text-align: center;
}

.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: rgba(180, 230, 225, 0.06);
  color: var(--text-secondary);
  font-weight: 700;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.rank-badge.gold {
  background: rgba(245, 158, 11, 0.18);
  color: var(--c-amber-warm);
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.25);
}
.rank-badge.silver {
  background: rgba(180, 230, 225, 0.10);
  color: var(--c-sand);
}
.rank-badge.bronze {
  background: rgba(217, 119, 87, 0.16);
  color: var(--c-rust);
}

.top-row td {
  font-weight: 500;
  background: rgba(45, 212, 191, 0.04);
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 36px 20px;
  text-align: center;
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
