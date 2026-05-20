<!--
  Step done 状态下的结论渲染路由组件:
    - 尝试 JSON.parse(output)
    - 命中 sections   → AnalyzerCard (step 2 analyzer)
    - 命中 actions    → WriterCard   (step 4 writer)
    - 否则             → MarkdownText (step 1 / 3 / 5 文本类输出)
-->
<template>
  <div class="step-conclusion">
    <AnalyzerCard v-if="kind === 'analyzer'" :data="parsed" />
    <WriterCard v-else-if="kind === 'writer'" :data="parsed" />
    <MarkdownText v-else :raw="raw" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AnalyzerCard from './AnalyzerCard.vue'
import WriterCard from './WriterCard.vue'
import MarkdownText from './MarkdownText.vue'

const props = defineProps<{ raw: string }>()

const parsed = computed<any>(() => {
  if (!props.raw) return null
  const trimmed = props.raw.trim()
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return null
  try {
    return JSON.parse(trimmed)
  } catch {
    return null
  }
})

const kind = computed<'analyzer' | 'writer' | 'markdown'>(() => {
  const p = parsed.value
  if (p && Array.isArray(p.sections)) return 'analyzer'
  if (p && Array.isArray(p.actions)) return 'writer'
  return 'markdown'
})
</script>

<style scoped>
.step-conclusion { width: 100%; }
</style>
