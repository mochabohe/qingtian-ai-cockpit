<template>
  <footer class="compliance-footer" :class="`mode-${mode}`">
    <div class="left">
      <span class="lock">🔒</span>
      <span class="text">
        合规审查 · {{ modeLabel }}
        <strong>{{ compliance.masked_field_count }}</strong>
        /
        <strong>{{ compliance.total_field_count }}</strong>
        字段
      </span>
      <span v-if="mode === 'dry_run'" class="mode-tag" :title="modeTooltip">
        演示模式
      </span>
    </div>
    <div v-if="auditId" class="right">
      <span class="audit-label">审计 ID</span>
      <code class="audit-id">{{ auditId }}</code>
    </div>
    <div v-if="compliance.findings && compliance.findings.length" class="findings">
      <details>
        <summary>{{ summaryLabel }} ({{ compliance.findings.length }})</summary>
        <ul>
          <li v-for="(f, i) in compliance.findings" :key="i">{{ f }}</li>
        </ul>
      </details>
    </div>
    <div v-if="mode === 'dry_run'" class="dry-run-note">
      ⓘ 当前为演示模式:已识别风险点但未修改原文(项目数据本就脱敏)。
      生产环境可切 <code>COMPLIANCE_DRY_RUN=false</code> 启用真实脱敏。
    </div>
  </footer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Compliance } from '@/api/report'

const props = defineProps<{
  compliance: Compliance
  auditId?: string
}>()

// mode 是后端 P0 修订后新增字段,旧简报缺失时降级为 production(保持旧文案)
const mode = computed(() => (props.compliance as any).mode || 'production')

const modeLabel = computed(() =>
  mode.value === 'dry_run' ? '已识别风险' : '已脱敏'
)
const summaryLabel = computed(() =>
  mode.value === 'dry_run' ? '风险点清单' : '已脱敏字段清单'
)
const modeTooltip = '演示模式只识别不修改;生产模式会真实脱敏文本'
</script>

<style scoped>
.compliance-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: var(--r-md);
  background: rgba(180, 230, 225, 0.025);
  border: 1px dashed var(--border-line);
  font-size: 13px;
  color: var(--text-secondary);
}

.compliance-footer.mode-dry_run {
  background: rgba(245, 158, 11, 0.06);
  border-color: rgba(245, 158, 11, 0.32);
  border-style: solid;
}

.mode-tag {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(245, 158, 11, 0.18);
  color: var(--c-amber-warm);
  border: 1px solid rgba(245, 158, 11, 0.32);
  font-size: 11px;
  font-weight: 700;
  border-radius: var(--r-sm);
  letter-spacing: 0.4px;
  margin-left: 4px;
  cursor: help;
}

.dry-run-note {
  flex-basis: 100%;
  margin-top: 6px;
  padding: 8px 12px;
  background: rgba(245, 158, 11, 0.08);
  border-left: 3px solid var(--c-amber-warm);
  border-radius: var(--r-sm);
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.dry-run-note code {
  background: rgba(245, 158, 11, 0.10);
  border: 1px solid rgba(245, 158, 11, 0.24);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  color: var(--c-amber-warm);
}

.left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.lock {
  font-size: 14px;
}

.text strong {
  color: var(--text-primary);
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  font-weight: 700;
  margin: 0 2px;
}

.right {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.audit-label {
  color: var(--text-muted);
  font-weight: 500;
}

.audit-id {
  background: rgba(45, 212, 191, 0.08);
  border: 1px solid rgba(45, 212, 191, 0.24);
  padding: 2px 8px;
  border-radius: var(--r-sm);
  font-size: 11px;
  color: var(--c-emerald);
  font-family: 'JetBrains Mono', monospace;
}

.findings {
  flex-basis: 100%;
}

.findings details {
  margin-top: 4px;
}

.findings summary {
  cursor: pointer;
  color: var(--text-muted);
  font-size: 12px;
  user-select: none;
}

.findings ul {
  margin: 8px 0 0;
  padding-left: 24px;
  font-size: 12px;
  color: var(--text-secondary);
}

.findings li { margin: 4px 0; }
</style>
