<template>
  <section v-if="role" class="resource-workbench" aria-label="学习工作台">
    <button class="workbench-card dashboard-card" @click="goDashboard">
      <span class="workbench-kicker">{{ role === 'student' ? 'PERSONAL LEARNING' : 'RESOURCE OPERATIONS' }}</span>
      <i class="bi bi-graph-up-arrow card-icon"></i>
      <strong>{{ dashboardTitle }}</strong>
      <span class="dashboard-summary">{{ summary }}</span>
      <span class="dashboard-stat"><b>{{ primary }}</b>{{ primaryLabel }}<b>{{ secondary }}</b>{{ secondaryLabel }}</span>
      <span class="card-action">查看完整{{ role === 'student' ? '分析' : '看板' }} <i class="bi bi-arrow-right"></i></span>
    </button>

    <div class="workbench-links">
      <button class="workbench-card link-card" @click="goPath">
        <i class="bi bi-signpost-split card-icon"></i>
        <span class="workbench-kicker">LEARNING PATH</span>
        <strong>{{ role === 'student' ? '学习路径' : '学习路径管理' }}</strong>
        <small>{{ pathSummary }}</small>
        <span class="card-action">进入 <i class="bi bi-arrow-right"></i></span>
      </button>
      <button class="workbench-card link-card" @click="goResources">
        <i class="bi bi-folder2-open card-icon"></i>
        <span class="workbench-kicker">RESOURCE CENTER</span>
        <strong>{{ role === 'student' ? '资源中心' : role === 'teacher' ? '教学资源中心' : '资源审核中心' }}</strong>
        <small>{{ resourceSummary }}</small>
        <span class="card-action">{{ role === 'student' ? '浏览资源' : '进入工作区' }} <i class="bi bi-arrow-right"></i></span>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import api from '@/api'
import '@/assets/resource-workbench.css'

const emit = defineEmits(['resource-clicked'])
const router = useRouter()
const user = useUserStore()
const plan = ref({})
const paths = ref([])
const students = ref([])
const role = computed(() => user.userInfo?.role)
const currentPath = computed(() => paths.value.find(item => !item.completed_at) || paths.value[0])
const lowCount = computed(() => students.value.filter(item => Number(item.mastery || 0) < 60).length)
const focusCategory = computed(() => {
  const categoryMap = { web: 'Web安全', reverse: '逆向工程', crypto: '密码学', pwn: '网络安全', misc: '网络安全' }
  const skills = plan.value?.self_assessment_snapshot || {}
  const weakest = Object.entries(skills)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .sort(([, left], [, right]) => Number(left) - Number(right))[0]?.[0]
  return categoryMap[weakest] || ''
})
const dashboardTitle = computed(() => role.value === 'student' ? '学习概览' : role.value === 'teacher' ? '教学概览' : '资源概览')
const summary = computed(() => role.value === 'student'
  ? (plan.value.summary || '系统结合你的学习记录，生成下一步学习建议。')
  : role.value === 'teacher' ? `已汇总 ${students.value.length} 名学生的学习状态，便于安排教学资源。` : `已汇总 ${students.value.length} 名学生的资源与学习数据。`)
const primary = computed(() => role.value === 'student' ? paths.value.filter(item => !item.completed_at).length : students.value.length)
const primaryLabel = computed(() => role.value === 'student' ? ' 条进行中的路径' : ' 个学生样本')
const secondary = computed(() => role.value === 'student' ? `${Math.round(paths.value.reduce((total, item) => total + (item.progress_percentage || 0), 0) / Math.max(paths.value.length, 1))}%` : lowCount.value)
const secondaryLabel = computed(() => role.value === 'student' ? ' 平均完成度' : ' 项重点关注')
const pathSummary = computed(() => role.value === 'student'
  ? (currentPath.value ? `${currentPath.value.path_title} · 已完成 ${currentPath.value.completed_modules || 0}/${currentPath.value.total_modules || 0} 个模块` : '从一条学习路径开始，逐步完成安全训练。')
  : `已发布 ${paths.value.length} 条学习路径，可继续维护课程结构。`)
const resourceSummary = computed(() => role.value === 'student'
  ? (focusCategory.value ? `已为你定位 ${focusCategory.value} 相关训练资料。` : '按学习目标搜索和筛选训练资料。')
  : role.value === 'teacher' ? '进入资源审核与教学资料工作区。' : '处理资源审核与运营管理工作。')

function goDashboard () { router.push(role.value === 'student' ? '/dashboard' : role.value === 'teacher' ? '/teacher' : '/admin/dashboard') }
function goPath () { router.push(role.value === 'student' ? '/learning-paths' : role.value === 'teacher' ? '/teacher/learning-paths' : '/learning-paths/manage') }
function goResources () { emit('resource-clicked', { category: role.value === 'student' ? focusCategory.value : '' }) }

onMounted(async () => {
  if (role.value === 'student') {
    const [planResult, pathsResult] = await Promise.allSettled([api.analytics.teachingPlan(), api.learningPaths.my()])
    if (planResult.status === 'fulfilled') plan.value = planResult.value || {}
    if (pathsResult.status === 'fulfilled') paths.value = Array.isArray(pathsResult.value) ? pathsResult.value : []
  } else if (role.value === 'teacher' || role.value === 'admin') {
    const [studentsResult, pathsResult] = await Promise.allSettled([
      role.value === 'teacher' ? api.analytics.teacherStudentReport() : api.analytics.adminStudentReport(),
      api.learningPaths.list({ page_size: 100 })
    ])
    if (studentsResult.status === 'fulfilled') students.value = Array.isArray(studentsResult.value) ? studentsResult.value : []
    if (pathsResult.status === 'fulfilled') paths.value = Array.isArray(pathsResult.value) ? pathsResult.value : (pathsResult.value?.results || [])
  }
})
</script>
