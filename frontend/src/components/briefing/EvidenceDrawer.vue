<template>
  <!--
    P0-3 洞察证据链抽屉
    点击 KPI/section/action 旁的"查看证据"按钮 → 抽屉弹出
    用户追问"这个数字哪来的"时直接打开,展示数据来源 / 口径 / 字段 / 样例
  -->
  <el-drawer
    v-model="open"
    :title="title"
    size="540px"
    direction="rtl"
    :destroy-on-close="false"
    class="evidence-drawer-root"
  >
    <template #header="{ titleId }">
      <div class="ed-head">
        <h4 :id="titleId" class="ed-title">
          <span class="ed-icon">🔍</span>
          {{ title }}
        </h4>
        <p class="ed-desc">{{ subtitle }}</p>
      </div>
    </template>

    <div class="ed-body" v-if="evidence && evidence.length">
      <div v-for="(ev, i) in evidence" :key="i" class="ed-card">
        <div class="ed-row-head">
          <span class="ed-label">{{ ev.label }}</span>
          <el-tag size="small" type="info" effect="light">{{ ev.source }}</el-tag>
        </div>

        <div class="ed-meta-row">
          <div class="ed-meta-item">
            <span class="ed-meta-key">📐 计算口径</span>
            <span class="ed-meta-val">{{ ev.method || '—' }}</span>
          </div>
          <div class="ed-meta-item">
            <span class="ed-meta-key">📊 命中记录</span>
            <span class="ed-meta-val ed-count">{{ ev.record_count.toLocaleString() }} 条</span>
          </div>
        </div>

        <div class="ed-fields" v-if="ev.fields && ev.fields.length">
          <span class="ed-meta-key">关键字段:</span>
          <el-tag v-for="f in ev.fields" :key="f" size="small" effect="plain">{{ f }}</el-tag>
        </div>

        <div class="ed-samples" v-if="ev.samples && ev.samples.length">
          <div class="ed-section-title">原始样例 ({{ ev.samples.length }} 条)</div>
          <ul class="ed-sample-list">
            <li v-for="(s, j) in ev.samples" :key="j">{{ s }}</li>
          </ul>
        </div>

        <div class="ed-note" v-if="ev.note">
          💡 {{ ev.note }}
        </div>
      </div>
    </div>

    <div class="ed-empty" v-else>
      <el-empty description="该结论暂未关联到证据池" />
      <p class="ed-empty-tip">
        通常发生在 LLM 输出的文案与算法计算的关键字未命中时,
        但简报本身的数字仍来自真实数据(可参考 .trace.json 全链路追溯)。
      </p>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Evidence } from '@/api/report'

const props = defineProps<{
  modelValue: boolean
  title?: string
  subtitle?: string
  evidence?: Evidence[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})
</script>

<!--
  本组件不带 <style>:
  el-drawer 默认 :teleported="true" 会把内容挂到 document.body 之下,
  组件内的 <style scoped> 通过 [data-v-xxx] 属性匹配,teleport 后属性丢失
  → 抽屉里所有元素无样式 → 文字默认黑色与黑底重合 → 看上去"点开后是空的"。
  样式已迁移至 frontend/src/style.css 的 .evidence-drawer-root 命名空间。
-->
