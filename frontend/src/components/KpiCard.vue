<template>
  <div class="kpi-card" :style="{ '--accent': color || '#2dd4bf' }">
    <div class="kpi-glow"></div>
    <div class="kpi-meta">
      <div class="kpi-pulse"></div>
      <div class="kpi-title">{{ title }}</div>
    </div>
    <div class="kpi-value">
      <span class="value-num">{{ value }}</span>
      <span v-if="unit" class="kpi-unit">{{ unit }}</span>
    </div>
    <div class="kpi-bar"></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  value: string | number
  unit?: string
  color?: string
}>()
</script>

<style scoped>
/* 去框 stat: 不再当卡片用, 是 stat-band 里的一格. 仅靠数字大小 + 翡翠脉冲点 + 流光底线建立视觉, 没有外框/背景/阴影 */
.kpi-card {
  position: relative;
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 4px 0;
  overflow: visible;
  transition: opacity var(--t-fast);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
.kpi-card::before { display: none; }
.kpi-card:hover { opacity: 0.9; }
.kpi-card:hover .kpi-glow { opacity: 0.6; transform: scale(1.1); }

/* 角落微光保留, 但调到极弱 */
.kpi-glow {
  position: absolute;
  top: -30px;
  right: -30px;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: radial-gradient(closest-side, color-mix(in srgb, var(--accent) 22%, transparent), transparent 70%);
  opacity: 0.32;
  filter: blur(12px);
  transition: all var(--t-base);
  pointer-events: none;
}

.kpi-meta {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 1;
}
.kpi-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent);
  animation: kpi-pulse 2s ease-in-out infinite;
}
@keyframes kpi-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}
.kpi-title {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.4px;
  text-transform: uppercase;
}
.kpi-value {
  position: relative;
  margin-top: 12px;
  display: flex;
  align-items: baseline;
  gap: 6px;
  z-index: 1;
}
/* 数字层级:超大衬线, 真正的视觉锚点 */
.value-num {
  font-family: 'Cormorant Garamond', 'Source Han Serif SC', Georgia, serif;
  font-size: clamp(28px, 4.4vw, 38px);
  font-weight: 600;
  letter-spacing: 0.4px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  line-height: 1;
}
.kpi-unit {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  letter-spacing: 0.4px;
}
.kpi-bar {
  position: relative;
  margin-top: 12px;
  height: 1px;
  border-radius: 0;
  background: var(--border-line);
  overflow: hidden;
}
.kpi-bar::after {
  content: '';
  position: absolute;
  top: 0; left: 0; bottom: 0;
  width: 50%;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  animation: kpi-bar-slide 3s ease-in-out infinite;
  opacity: 0.7;
}
@keyframes kpi-bar-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(220%); }
}
</style>
