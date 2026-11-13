<template>
  <main class="exam-center-page">
    <header><h1>试炼场</h1><p>参加正式理论与实战测评，以服务端记录核对结果。</p></header>
    <p v-if="dataLoading" role="status">正在读取测评状态…</p>
    <p v-else-if="dataError" role="alert">{{ dataError }} <button @click="loadData">重读状态</button></p>
    <p v-if="actionError" role="alert">{{ actionError }}</p>
    <section class="exam-entry" aria-label="正式测评入口">
      <h2>综合测试 · {{ statusLabel }}</h2>
      <p>理论阶段完成后进入实战阶段。题目、时间限制与评分以本场试卷及服务端记录为准。</p>
      <template v-if="ongoingExamId">
        <button class="primary" :disabled="loading || dataLoading" @click="continueExam">继续进行中的考试</button>
        <button :disabled="loading || dataLoading" @click="abandonAndStartNew">放弃当前考试并开始新考试</button>
      </template>
      <button v-else class="primary" :disabled="loading || dataLoading || !!dataError" @click="startExam">{{ loading ? '正在准备考试…' : '开始测试' }}</button>
      <router-link :to="recordsPath">查看全部考试记录（{{ recordCount ?? '数量待确认' }}）</router-link>
    </section>
    <ExamOverview :records="recentRecords" />
  </main>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { examsApi, RECORDS_PATH } from '@/learning/exams/api.js'
import ExamOverview from '@/learning/exams/components/ExamOverview.vue'
import { createAccountGuard } from '@/shared/state/accountScope.js'

const router = useRouter(), guard = createAccountGuard(), recordsPath = RECORDS_PATH
const loading = ref(false), dataLoading = ref(true), dataError = ref(''), actionError = ref('')
const ongoingExamId = ref(null), recentRecords = ref([]), recordCount = ref(null)
const statusLabel = computed(() => dataLoading.value || dataError.value ? '状态待确认' : ongoingExamId.value ? '进行中' : '待考')
let generation = 0
const loadData = async () => {
  const reading = ++generation
  dataLoading.value = true; dataError.value = ''
  try {
    const [records, history] = await Promise.all([
      examsApi.records({ status: 'in_progress' }), examsApi.myHistory(),
    ])
    if (!guard.current() || reading !== generation) return
    ongoingExamId.value = (Array.isArray(records) ? records : records.results || [])[0]?.id ?? null
    const all = Array.isArray(history) ? history : history.records || history.results || []
    recentRecords.value = all
    recordCount.value = Number.isFinite(history.count) ? history.count : all.length
  } catch {
    if (guard.current() && reading === generation) {
      dataError.value = '测评状态暂时无法读取，不会据此认为你没有进行中的测评，请重试。'
      recentRecords.value = []; recordCount.value = null
    }
  } finally {
    if (guard.current() && reading === generation) dataLoading.value = false
  }
}
const continueExam = () => {
  if (ongoingExamId.value) router.push(`/exam-taking/${ongoingExamId.value}`)
}
const startExam = async () => {
  if (loading.value) return
  loading.value = true; actionError.value = ''
  try {
    const response = await examsApi.startComprehensive()
    if (!guard.current()) return
    const id = response.theory_record?.id ?? response.practice_record?.id
    if (id == null) { actionError.value = '测评尚未创建成功，服务未返回可打开的考试记录。'; return }
    router.push(`/exam-taking/${id}`)
  } catch (error) {
    if (!guard.current()) return
    const existing = error.response?.data?.exam_record_id
    if (existing != null) { ongoingExamId.value = existing; actionError.value = '已有进行中的测评，请先继续或核对原记录。' }
    else actionError.value = '测评尚未创建成功，请稍后重试或联系教师。'
  } finally {
    if (guard.current()) loading.value = false
  }
}
const abandonAndStartNew = async () => {
  if (loading.value || !confirm('确定放弃当前考试吗？此操作无法撤销。')) return
  loading.value = true; actionError.value = ''
  try {
    await examsApi.abandonComprehensive()
    if (!guard.current()) return
    const records = await examsApi.records({ status: 'in_progress' })
    if (!guard.current()) return
    const active = (Array.isArray(records) ? records : records.results || [])[0]?.id ?? null
    if (active != null) { ongoingExamId.value = active; actionError.value = '未能确认放弃已生效，请核对原记录后重试。'; return }
    ongoingExamId.value = null
    loading.value = false
    await startExam()
  } catch {
    if (guard.current()) actionError.value = '未能确认放弃已生效，请核对原记录后重试。'
  } finally {
    if (guard.current()) loading.value = false
  }
}
onMounted(loadData)
onUnmounted(guard.dispose)
</script>

<style scoped>
.exam-center-page { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: auto; padding: var(--space-3) 0; color: var(--ink); }
h1 { font-size: var(--text-page); } h2 { font-size: var(--text-section); }
.exam-entry { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3); margin-bottom: var(--space-3); background: var(--surface); border-radius: var(--radius-panel); }
.exam-entry h2, .exam-entry p { flex-basis: 100%; margin: 0; }
button { min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
button.primary { background: var(--button-primary); color: var(--on-action); }
button:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: default; }
button:focus-visible, a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
a { color: var(--action); }
</style>
