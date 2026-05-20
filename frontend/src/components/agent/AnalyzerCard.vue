<!--
  双路分析 Agent 输出 JSON 渲染:
    - kpi_strip: 横排 KPI 卡片
    - sections: 4 种 type(trend / ranking / distribution / alert)各自简洁渲染
  数据 schema 见 backend/app/services/agents.py 的 ANALYZER_PROMPT。
-->
<template>
  <div class="analyzer-card">
    <!-- KPI Strip -->
    <div class="kpi-strip" v-if="data.kpi_strip?.length">
      <div
        v-for="(kpi, i) in data.kpi_strip"
        :key="i"
        class="kpi-pill"
        :class="`tone-${kpi.tone || 'neutral'}`"
      >
        <div class="kpi-label">{{ kpi.label }}</div>
        <div class="kpi-value">{{ kpi.value }}</div>
        <div class="kpi-delta" v-if="kpi.delta">{{ kpi.delta }}</div>
      </div>
    </div>

    <!-- Sections -->
    <div class="sections" v-if="data.sections?.length">
      <div
        v-for="(sec, i) in data.sections"
        :key="i"
        class="section"
        :class="`section-${sec.type}`"
      >
        <div class="section-head">
          <span class="section-type-tag" :class="`tag-${sec.type}`">{{ typeLabel(sec.type) }}</span>
          <h4 class="section-title">{{ sec.title }}</h4>
          <span v-if="sec.type === 'alert'" class="alert-level" :class="`level-${sec.level}`">
            {{ levelLabel(sec.level) }}
          </span>
        </div>

        <!-- trend: data 是 [{x, y}] -->
        <div v-if="sec.type === 'trend' && sec.data?.length" class="trend-mini">
          <span class="trend-metric">{{ sec.metric }}</span>
          <span class="trend-data">
            {{ sec.data[0].x }} {{ sec.data[0].y }}
            <span v-if="sec.data.length > 1">→ {{ sec.data[sec.data.length - 1].x }} {{ sec.data[sec.data.length - 1].y }}</span>
          </span>
          <span v-if="sec.delta" class="trend-delta">
            ({{ sec.delta.baseline }} {{ sec.delta.value > 0 ? '+' : '' }}{{ sec.delta.value }}%)
          </span>
        </div>

        <!-- ranking: columns / rows -->
        <table v-else-if="sec.type === 'ranking' && sec.rows?.length" class="ranking-table">
          <thead>
            <tr><th v-for="c in sec.columns" :key="c">{{ c }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, r) in sec.rows" :key="r">
              <td v-for="(cell, c) in row" :key="c">{{ cell }}</td>
            </tr>
          </tbody>
        </table>

        <!-- distribution: data 是 [{label, value}] -->
        <div v-else-if="sec.type === 'distribution' && sec.data?.length" class="distribution-list">
          <div v-for="(item, j) in sec.data" :key="j" class="dist-row">
            <span class="dist-label">{{ item.label }}</span>
            <div class="dist-bar-wrap">
              <div class="dist-bar" :style="{ width: distRatio(item.value, sec.data) + '%' }"></div>
            </div>
            <span class="dist-value">{{ item.value }}</span>
          </div>
        </div>

        <!-- alert: msg + evidence -->
        <div v-else-if="sec.type === 'alert'" class="alert-body">
          <p class="alert-msg">{{ sec.msg }}</p>
          <ul v-if="sec.evidence?.length" class="alert-evidence">
            <li v-for="(e, j) in sec.evidence" :key="j">{{ e }}</li>
          </ul>
        </div>

        <!-- Insight -->
        <div v-if="sec.insight" class="insight">
          💡 {{ sec.insight }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ data: any }>()

function typeLabel(t: string) {
  return ({ trend: '趋势', ranking: '排行', distribution: '分布', alert: '预警' } as any)[t] || t
}
function levelLabel(l?: string) {
  return ({ info: '提示', warning: '警告', high: '高危' } as any)[l || ''] || l || ''
}
function distRatio(v: number, arr: any[]) {
  const max = Math.max(...arr.map((x) => Number(x.value) || 0))
  if (max <= 0) return 0
  return Math.round((Number(v) / max) * 100)
}
</script>

<style scoped>
.analyzer-card { display: flex; flex-direction: column; gap: 14px; }

.kpi-strip { display: flex; flex-wrap: wrap; gap: 8px; }
.kpi-pill {
  flex: 1 1 110px;
  border-radius: 12px;
  padding: 10px 12px;
  background: rgba(180, 230, 225, 0.025);
  border: 1px solid var(--border-line);
}
.kpi-pill.tone-positive { background: rgba(132, 204, 22, 0.10); border-color: rgba(132, 204, 22, 0.45); }
.kpi-pill.tone-negative { background: rgba(217, 119, 87, 0.12); border-color: rgba(217, 119, 87, 0.45); }
.kpi-pill.tone-neutral { background: rgba(45, 212, 191, 0.06); }

.kpi-label { font-size: 11px; color: var(--text-muted); }
.kpi-value { font-size: 16px; font-weight: 700; color: var(--text-primary); margin: 4px 0 2px; }
.kpi-delta { font-size: 11px; color: var(--text-secondary); }

.sections { display: flex; flex-direction: column; gap: 12px; }
.section {
  border-radius: 12px;
  padding: 12px 14px;
  background: rgba(180, 230, 225, 0.03);
  border: 1px solid var(--border-line);
}
.section-alert { background: rgba(217, 119, 87, 0.08); border-color: rgba(217, 119, 87, 0.36); }

.section-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.section-type-tag {
  font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
  background: rgba(45, 212, 191, 0.10); color: var(--c-emerald);
  border: 1px solid rgba(45, 212, 191, 0.30);
}
.tag-trend { background: rgba(45, 212, 191, 0.10); color: var(--c-emerald); border-color: rgba(45, 212, 191, 0.30); }
.tag-ranking { background: rgba(45, 212, 191, 0.10); color: var(--c-emerald); border-color: rgba(45, 212, 191, 0.30); }
.tag-distribution { background: rgba(78, 205, 196, 0.10); color: var(--c-mint); border-color: rgba(78, 205, 196, 0.30); }
.tag-alert { background: rgba(217, 119, 87, 0.14); color: var(--c-rust); border-color: rgba(217, 119, 87, 0.36); }

.section-title { margin: 0; font-size: 13px; font-weight: 600; color: var(--text-primary); flex: 1; }
.alert-level { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(217, 119, 87, 0.12); color: var(--c-rust); }
.alert-level.level-warning { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
.alert-level.level-info { background: rgba(45, 212, 191, 0.10); color: var(--c-teal); }

.trend-mini { font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.trend-metric { font-weight: 600; color: var(--text-primary); margin-right: 8px; }
.trend-delta { color: var(--c-moss); margin-left: 8px; font-weight: 600; }

.ranking-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.ranking-table th { text-align: left; padding: 6px 8px; background: rgba(45, 212, 191, 0.06); color: var(--c-mint); font-weight: 600; }
.ranking-table td { padding: 6px 8px; border-top: 1px solid var(--border-line); color: var(--text-secondary); }

.distribution-list { display: flex; flex-direction: column; gap: 6px; }
.dist-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.dist-label { width: 80px; color: var(--text-secondary); flex-shrink: 0; }
.dist-bar-wrap { flex: 1; height: 8px; background: rgba(180, 230, 225, 0.06); border-radius: 999px; overflow: hidden; }
.dist-bar { height: 100%; background: linear-gradient(90deg, var(--c-emerald), var(--c-mint)); border-radius: 999px; transition: width 0.4s; }
.dist-value { font-weight: 600; color: var(--text-primary); }

.alert-body { color: var(--text-primary); }
.alert-msg { margin: 0 0 6px; font-size: 12.5px; line-height: 1.6; color: var(--text-primary); }
.alert-evidence { margin: 0; padding-left: 18px; font-size: 12px; color: var(--text-muted); }
.alert-evidence li { margin-bottom: 2px; }

.insight {
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(45, 212, 191, 0.08);
  border: 1px solid rgba(45, 212, 191, 0.22);
  font-size: 12px;
  color: var(--c-emerald);
}
</style>
