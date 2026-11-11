<template>
  <main class="learning-insights-page">
    <TeacherLearningDashboard />
    <details id="task-evidence" class="evaluation-section" :open="route.hash === '#task-evidence'"><summary>任务评估统计与运行记录</summary><EvaluationStatistics /></details>
  </main>
</template>
<script setup>
import { useRoute } from 'vue-router'
import TeacherLearningDashboard from './TeacherLearningDashboard.vue'
import EvaluationStatistics from './insights/EvaluationStatistics.vue'
const route = useRoute()
</script>
<style scoped>
.learning-insights-page { min-width: 0; background: var(--surface-page); }
.evaluation-section { margin: var(--space-2); background: var(--surface); border-radius: var(--radius-panel); }
summary { cursor: pointer; padding: var(--space-2); color: var(--ink); font-size: var(--text-card); font-weight: var(--weight-strong); }
summary:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
