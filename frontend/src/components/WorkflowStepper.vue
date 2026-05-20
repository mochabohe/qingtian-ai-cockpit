<template>
  <!--
    经营分析工作流进度条(全局,仅工作流 4 页显示)
    数据来自 mission store,4 个节点点击跳转,当前页节点高亮 + 脉冲动画
  -->
  <div class="workflow-stepper">
    <div
      v-for="(step, i) in steps"
      :key="step.path"
      class="step"
      :class="[`status-${step.status}`, { 'is-current': step.isCurrent }]"
      @click="$router.push(step.path)"
    >
      <div class="step-circle">
        <span v-if="step.status === 'done'" class="check-icon">✓</span>
        <span v-else class="step-num">{{ i + 1 }}</span>
      </div>
      <div class="step-text">
        <div class="step-title">{{ step.title }}</div>
        <div class="step-desc">{{ step.desc }}</div>
      </div>
      <div v-if="i < steps.length - 1" class="connector" :class="`status-${step.status}`"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useMissionStore } from '@/stores/mission'

const route = useRoute()
const mission = useMissionStore()

interface Step {
  path: string
  title: string
  desc: string
  status: 'done' | 'current' | 'pending'
  isCurrent: boolean
}

const steps = computed<Step[]>(() => {
  const path = route.path
  const dataReady = mission.dataReady >= mission.dataTotal && mission.dataTotal > 0
  const briefReady = !!mission.briefFilename
  const videoReady = !!mission.videoTaskId

  function pickStatus(stepPath: string, doneFlag: boolean): Step['status'] {
    if (doneFlag) return 'done'
    if (path === stepPath) return 'current'
    return 'pending'
  }

  return [
    {
      path: '/upload',
      title: '数据接入',
      desc: dataReady
        ? `${mission.dataReady}/${mission.dataTotal} 已就绪`
        : `${mission.dataReady}/${mission.dataTotal} 待就绪`,
      status: pickStatus('/upload', dataReady),
      isCurrent: path === '/upload',
    },
    {
      path: '/agent',
      title: 'Agent 分析',
      desc: briefReady ? '已产出简报' : (path === '/agent' ? '正在配置' : '待执行'),
      status: pickStatus('/agent', briefReady),
      isCurrent: path === '/agent',
    },
    {
      path: '/report',
      title: '简报预览',
      desc: briefReady ? mission.briefFilename!.slice(0, 18) + '…' : '待生成',
      status: pickStatus('/report', briefReady && path !== '/report'),
      isCurrent: path === '/report',
    },
    {
      path: '/video',
      title: 'AI 视频',
      desc: videoReady ? '已生成' : '待生成',
      status: pickStatus('/video', videoReady && path !== '/video'),
      isCurrent: path === '/video',
    },
  ]
})
</script>

<style scoped>
.workflow-stepper {
  display: flex;
  align-items: stretch;
  background: rgba(45, 212, 191, 0.06);
  border: 1px solid var(--border-line);
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 14px;
  position: relative;
}

.step {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all .2s;
  position: relative;
  min-width: 0;
  padding: 4px 6px;
  border-radius: 10px;
}
.step:hover {
  background: rgba(180, 230, 225, 0.04);
}

/* 节点圆环 */
.step-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
  transition: all .25s;
  border: 2px solid;
}

.step.status-pending .step-circle {
  background: rgba(180, 230, 225, 0.04);
  border-color: var(--border-line);
  color: var(--text-muted);
}
.step.status-current .step-circle,
.step.is-current .step-circle {
  background: linear-gradient(135deg, var(--c-emerald), var(--c-mint));
  border-color: transparent;
  color: #04161a;
  box-shadow: 0 0 0 5px rgba(45, 212, 191, 0.20);
  animation: stepper-pulse 1.6s ease-in-out infinite;
}
.step.status-done .step-circle {
  background: linear-gradient(135deg, var(--c-moss), var(--c-teal));
  border-color: transparent;
  color: #04161a;
  box-shadow: 0 4px 12px rgba(132, 204, 22, 0.25);
}
.check-icon { font-size: 16px; font-weight: 900; }

@keyframes stepper-pulse {
  0%, 100% { box-shadow: 0 0 0 5px rgba(45, 212, 191, 0.20); }
  50%      { box-shadow: 0 0 0 10px rgba(45, 212, 191, 0.06); }
}

/* 节点文字 */
.step-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.step-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step.status-pending .step-title {
  color: var(--text-muted);
}
.step.is-current .step-title {
  color: var(--c-emerald-deep);
}
.step-desc {
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step.status-done .step-desc {
  color: var(--c-moss);
}
.step.is-current .step-desc {
  color: var(--c-emerald);
  font-weight: 600;
}

/* 连接线:从节点圆环延伸到下一节点圆环, 默认渐隐淡出, 不抢主体 */
.connector {
  position: absolute;
  right: -8px;
  top: 50%;
  max-width: 32px;
  width: 16px;
  height: 2px;
  background: linear-gradient(90deg,
    var(--border-line) 0%,
    var(--border-line) 70%,
    transparent 100%);
  transform: translateY(-50%);
  pointer-events: none;
}
.connector.status-done {
  background: linear-gradient(90deg,
    var(--c-moss) 0%,
    rgba(132, 204, 22, 0.4) 70%,
    transparent 100%);
}

@media (max-width: 900px) {
  .workflow-stepper {
    flex-direction: column;
    gap: 12px;
  }
  .connector { display: none; }
  .step { padding: 6px 8px; }
}
</style>
