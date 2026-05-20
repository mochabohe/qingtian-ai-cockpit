/**
 * 简报组件群统一图表色板. 与全站翡翠青主题对齐, 引入暖色 accent 给关键负面信号锚定.
 * 用法:
 *   import { BRIEFING_PALETTE, trendColor, axisStyle } from '@/utils/chartPalette'
 *   option.color = BRIEFING_PALETTE
 *   series.lineStyle.color = trendColor(delta)
 */

// 8 色, 翡翠青为主, 后续依次暖色 / 警示 / 中性补
export const BRIEFING_PALETTE = [
  '#2dd4bf',  // 翡翠青 - 主
  '#84cc16',  // 橄榄绿 - 正向
  '#f59e0b',  // 琥珀金 - 关注 / 暖
  '#d97757',  // 砖橘 - 警示
  '#fb7185',  // 玫红 - 负向 / 高危
  '#06b6d4',  // 天青 - 中性补
  '#a78bfa',  // 紫 - 长尾
  '#94d8d4',  // 月白银
]

/**
 * 根据 delta 百分比挑趋势色:
 *   > +5%: 绿 (向好)
 *   < -5%: 砖橘 (向坏)
 *   其余: 银白 (中性)
 */
export function trendColor(delta?: number | null): string {
  if (delta == null || isNaN(Number(delta))) return '#94d8d4'
  if (delta > 0.05 || delta > 5) return '#84cc16'
  if (delta < -0.05 || delta < -5) return '#d97757'
  return '#94d8d4'
}

/** ECharts 通用暗色坐标轴样式 */
export const axisStyle = {
  axisTick:  { show: false },
  axisLine:  { lineStyle: { color: 'rgba(180, 230, 225, 0.16)' } },
  axisLabel: { color: '#a8c0bd', fontSize: 11 },
  splitLine: { lineStyle: { color: 'rgba(180, 230, 225, 0.06)' } },
}

/** ECharts 通用暗色 tooltip 样式 */
export const tooltipStyle = {
  backgroundColor: 'rgba(16, 32, 40, 0.96)',
  borderColor: 'rgba(180, 230, 225, 0.16)',
  borderWidth: 1,
  textStyle: { color: '#e6f1f0', fontSize: 12 },
  extraCssText: 'backdrop-filter: blur(14px); border-radius: 8px;',
}
