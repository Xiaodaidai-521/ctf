<template>
  <section class="teacher-learning-dashboard">
    <StudentLearning />
  </section>
</template>

<script setup>
import StudentLearning from '@/admin/views/StudentLearning.vue'
</script>

<style scoped>
.teacher-learning-dashboard {
  min-height: 100vh;
  padding: 44px 36px;
  background-color: #faf7f0;
  background-image: linear-gradient(#e9e1d4 1px, transparent 1px), linear-gradient(90deg, #e9e1d4 1px, transparent 1px);
  background-size: 38px 38px;
}
.teacher-learning-dashboard :deep(.page-header-bar) { display: block; margin-bottom: 24px; }
.teacher-learning-dashboard :deep(.page-header-bar::before) { content: '学习画像 / 能力报告'; display: block; margin-bottom: 8px; color: #b42318; font-size: 12px; font-weight: 800; letter-spacing: .02em; }
.teacher-learning-dashboard :deep(.page-header-bar h2) { font-size: 42px; font-weight: 900; letter-spacing: -.05em; color: #1e1c18; }
.teacher-learning-dashboard :deep(.toolbar) { margin-top: 22px; }
.teacher-learning-dashboard :deep(.summary-row) { gap: 16px; }
.teacher-learning-dashboard :deep(.summary-card) { border: 1px solid #d9cfbe; border-radius: 8px; background: rgba(250,247,240,.94); box-shadow: none; padding: 20px; }
.teacher-learning-dashboard :deep(.s-num) { color: #1e1c18; font-size: 34px; }
.teacher-learning-dashboard :deep(.s-label) { color: #6b6256; font-size: 13px; }
.teacher-learning-dashboard :deep(.arco-table) { border: 1px solid #d9cfbe; border-radius: 8px; overflow: hidden; background: rgba(250,247,240,.94); }
.teacher-learning-dashboard :deep(.arco-table-th) { background: #e9dfcf; color: #1e1c18; font-weight: 800; }
.teacher-learning-dashboard :deep(.arco-table-td) { background: rgba(250,247,240,.94); border-color: #ded4c6; }
.teacher-learning-dashboard :deep(.arco-progress-line-bar) { background: #1e1c18; }
@media (max-width: 720px) { .teacher-learning-dashboard { padding: 28px 16px; } .teacher-learning-dashboard :deep(.page-header-bar h2) { font-size: 32px; } .teacher-learning-dashboard :deep(.summary-row) { flex-wrap: wrap; } .teacher-learning-dashboard :deep(.summary-card) { min-width: 42%; } }
</style>

