<!--
  简报合成 Agent 输出 JSON 渲染:
    - cover.headline: 大字主标语
    - executive_summary: 三句话摘要段落
    - actions: 行动项列表(高/中/低优先级颜色徽章)
  数据 schema 见 backend/app/services/agents.py 的 WRITER_PROMPT。
-->
<template>
  <div class="writer-card">
    <!-- Headline -->
    <div v-if="data.cover?.headline" class="headline">
      <span class="quote-mark">「</span>
      {{ data.cover.headline }}
      <span class="quote-mark">」</span>
    </div>

    <!-- Executive Summary -->
    <p v-if="data.executive_summary" class="exec-summary">
      {{ data.executive_summary }}
    </p>

    <!-- Actions -->
    <div v-if="data.actions?.length" class="actions">
      <div class="actions-title">📋 行动项 ({{ data.actions.length }})</div>
      <div
        v-for="(action, i) in data.actions"
        :key="i"
        class="action-row"
        :class="`prio-${action.priority || 'medium'}`"
      >
        <span class="prio-badge">{{ priorityLabel(action.priority) }}</span>
        <div class="action-body">
          <div class="action-text">{{ action.action }}</div>
          <div class="action-meta">
            <span v-if="action.owner" class="meta-owner">👤 {{ action.owner }}</span>
            <span v-if="action.deadline" class="meta-deadline">📅 {{ action.deadline }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ data: any }>()

function priorityLabel(p?: string) {
  return ({ high: '高', medium: '中', low: '低' } as any)[p || ''] || '中'
}
</script>

<style scoped>
.writer-card { display: flex; flex-direction: column; gap: 14px; }

.headline {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.5;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(45, 212, 191, 0.08);
  border: 1px solid rgba(45, 212, 191, 0.22);
  border-left: 4px solid var(--c-emerald);
}
.quote-mark { color: var(--c-emerald); font-size: 18px; }

.exec-summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-secondary);
  padding: 0 4px;
}

.actions { display: flex; flex-direction: column; gap: 8px; }
.actions-title { font-size: 12px; font-weight: 600; color: var(--c-mint); margin-bottom: 2px; letter-spacing: 0.3px; }

.action-row {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-line);
  background: rgba(180, 230, 225, 0.04);
  align-items: flex-start;
}
.action-row.prio-high { border-left: 3px solid var(--c-rust); background: rgba(217, 119, 87, 0.10); }
.action-row.prio-medium { border-left: 3px solid #f59e0b; background: rgba(245, 158, 11, 0.08); }
.action-row.prio-low { border-left: 3px solid var(--c-moss); background: rgba(132, 204, 22, 0.08); }

.prio-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
  margin-top: 1px;
}
.prio-high .prio-badge { background: rgba(217, 119, 87, 0.16); color: var(--c-rust); }
.prio-medium .prio-badge { background: rgba(245, 158, 11, 0.14); color: #f59e0b; }
.prio-low .prio-badge { background: rgba(132, 204, 22, 0.14); color: var(--c-moss); }

.action-body { flex: 1; }
.action-text { font-size: 13px; line-height: 1.5; color: var(--text-primary); font-weight: 500; }
.action-meta { display: flex; gap: 12px; margin-top: 6px; font-size: 11.5px; color: var(--text-muted); }
</style>
