<!--
  简易 markdown → HTML 渲染,用于 Agent 输出的文本类内容(step 1 collector / step 3 compliance / step 5 publisher)。
  支持:### / ## / **bold** / - 列表 / 段落换行
  样式类(.sc-h3 / .sc-h4 / .sc-strong / .sc-ul / .sc-li)在 AgentConsole 全局样式里定义。
-->
<template>
  <div class="markdown-text" v-html="rendered"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ raw: string }>()

const rendered = computed(() => {
  if (!props.raw) return ''
  let html = props.raw
    .replace(/### (.*?)(?:\n|$)/g, '<h4 class="sc-h4">$1</h4>')
    .replace(/## (.*?)(?:\n|$)/g, '<h3 class="sc-h3">$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong class="sc-strong">$1</strong>')
    .replace(/^- (.*?)$/gm, '<li class="sc-li">$1</li>')

  // 把连续的 <li> 包进 <ul>
  html = html.replace(/(<li class="sc-li">[\s\S]*?<\/li>\s*)+/g, (match) => `<ul class="sc-ul">${match}</ul>`)

  // 段落换行 → <br>,但不在 ul/li 边界产生多余 br
  html = html.replace(/\n/g, '<br/>')
  html = html.replace(/<br\/>(?=<ul|<li|<\/ul|<\/li|<h[34])/g, '')
  html = html.replace(/(<\/ul>|<\/li>|<h[34]>.*?<\/h[34]>)(<br\/>)+/g, '$1')

  return html
})
</script>

<style scoped>
.markdown-text {
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-primary);
  letter-spacing: 0.2px;
}
.markdown-text :deep(p) {
  color: var(--text-secondary);
  margin: 6px 0;
}
.markdown-text :deep(code) {
  background: rgba(45, 212, 191, 0.10);
  color: var(--c-emerald);
  border: 1px solid rgba(45, 212, 191, 0.22);
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}
</style>
