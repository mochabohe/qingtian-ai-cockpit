<template>
  <div v-if="text" class="insight-line">
    <span class="insight-icon">💡</span>
    <span class="insight-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<style scoped>
.insight-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  background: rgba(45, 212, 191, 0.06);
  border-left: 3px solid var(--c-emerald);
  border-radius: var(--r-sm);
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-primary);
}

.insight-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.insight-text {
  flex: 1;
  font-weight: 500;
}
</style>
