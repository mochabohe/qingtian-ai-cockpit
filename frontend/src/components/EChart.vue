<template>
  <div ref="chartRef" :style="{ width, height }"></div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  option: any
  width?: string
  height?: string
}>()

// 标准事件透传:让父组件能拿到 ECharts 的原生 click 回调,
// 不用各自再去 ref + getInstance。
const emit = defineEmits<{
  (e: 'click', params: any): void
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function resize() {
  chart?.resize()
}

onMounted(async () => {
  await nextTick()
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params) => emit('click', params))
    if (props.option) chart.setOption(props.option, true)
  }
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

watch(
  () => props.option,
  (val) => {
    if (chart && val) chart.setOption(val, true)
  },
  { deep: true },
)
</script>
