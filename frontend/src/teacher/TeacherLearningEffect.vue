<template>
  <section class="teacher-panel">
    <header><p>学习画像 / 数据快照</p><h1>学习效果分析</h1><span>选择学生后展示八项学习指标；无学习记录时使用默认零值。</span></header>
    <label>查看学生<select v-model="studentId" @change="loadMetrics"><option v-for="student in students" :key="student.id" :value="student.id">{{ student.username }}</option></select></label>
    <p v-if="message" class="message">{{ message }}</p>
    <div class="metric-grid"><article v-for="item in metrics" :key="item.key"><span>{{ item.label }}</span><strong>{{ item.value.toFixed(2) }}<small>{{ item.unit }}</small></strong><p>{{ item.status }}</p></article></div>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import api from '@/api'
const students = ref([])
const studentId = ref('')
const message = ref('')
const metricDefinitions = [
  ['time_score', '学习时长', '小时'], ['completion_score', '课程完成率', '%'], ['mastery_score', '知识掌握度', '分'], ['retention_score', '记忆保持度', '%'], ['consistency_score', '学习连续性', '%'], ['efficiency_score', '学习效率', '分'], ['engagement_score', '学习参与度', '%'], ['focus_score', '学习专注度', '分'],
]
const metrics = ref(metricDefinitions.map(([key, label, unit]) => ({ key, label, unit, value: 0, status: '暂无学习记录' })))
const applyDimensions = (dimensions, effectiveSeconds = 0) => { metrics.value = metricDefinitions.map(([key, label, unit]) => { const score = Number(dimensions?.[key]); const value = key === 'time_score' ? Math.max(0, Number(effectiveSeconds) || 0) / 3600 : (Number.isFinite(score) ? score : 0); return { key, label, unit, value, status: score >= 80 ? '表现优秀' : score >= 60 ? '状态良好' : score > 0 ? '建议关注' : '暂无学习记录' } }) }
const loadMetrics = async () => { if (!studentId.value) { applyDimensions(); return }; try { const response = await api.analytics.learningEffectSummary(studentId.value, 90); applyDimensions(response?.snapshot?.dimensions, response?.snapshot?.sample_description?.effective_learning_seconds); message.value = response?.snapshot ? '' : '该学生暂无学习记录，已展示默认指标。' } catch { applyDimensions(); message.value = '数据暂时不可用，已展示默认指标。' } }
onMounted(async () => { try { students.value = await api.analytics.teacherStudentReport() || []; studentId.value = students.value.find(item => item.username === '126')?.id || students.value[0]?.id || ''; await loadMetrics() } catch { message.value = '学生列表暂时不可用，已展示默认指标。' } })
</script>
<style scoped>
.teacher-panel{min-height:100vh;padding:42px 36px;background:#faf7f0;color:#1e1c18}.teacher-panel header p{margin:0 0 8px;color:#b42318;font-size:12px;font-weight:800}.teacher-panel h1{margin:0;font-size:40px}.teacher-panel header span{display:block;margin-top:10px;color:#6b6256}.teacher-panel label{display:grid;gap:7px;width:260px;margin:24px 0;font-weight:700}.teacher-panel select{height:42px;padding:0 10px;border:1px solid #a78b63;border-radius:5px;background:#fffaf2}.message{color:#6b6256}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.metric-grid article{min-height:148px;padding:18px;border:1px solid #d9cfbe;border-radius:8px;background:#fffaf2}.metric-grid span,.metric-grid p{color:#6b6256;font-size:13px;font-weight:700}.metric-grid strong{display:block;margin:20px 0 0;font-size:30px}.metric-grid small{margin-left:4px;font-size:13px;color:#6b6256}@media(max-width:900px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.teacher-panel{padding:28px 16px}.metric-grid{grid-template-columns:1fr}}
</style>


