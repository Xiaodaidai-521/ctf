<template>
  <div class="exam-center-page">
    <header class="exam-heading">
      <div>
        <p class="exam-eyebrow">{{ names.exams }} · 正式测评</p>
        <h1>{{ names.exams }}</h1>
        <p class="exam-subtitle">理论 + 实战的综合测评；练习在靶场，题内辅导先讲思路再练习。</p>
      </div>
      <router-link :to="recordsPath" class="records-link">
        测评记录{{ recordCount === null ? '' : `（${recordCount}）` }}<AppIcon name="bi-chevron-right" />
      </router-link>
    </header>

    <div v-if="dataLoading" class="page-state" role="status">正在读取测评状态…</div>
    <div v-else-if="dataError" class="page-state is-error" role="alert">
      {{ dataError }}<button type="button" class="text-action" @click="loadData">重新加载</button>
    </div>

    <div class="exam-layout">
      <section class="exam-card" aria-labelledby="exam-card-heading">
        <header class="card-heading">
          <div>
            <h2 id="exam-card-heading">综合测试</h2>
            <p class="card-note">理论与实战各限时 180 分钟；完成理论后进入实战。</p>
          </div>
          <span class="status-badge" :class="`is-${statusKind}`">{{ statusLabel }}</span>
        </header>

        <dl class="exam-facts">
          <div>
            <dt>理论测试</dt>
            <dd>30 单选 + 20 多选 + 20 判断 · 180 分钟</dd>
          </div>
          <div>
            <dt>实战测试</dt>
            <dd>3 简单 + 2 中等 + 1 困难 · 180 分钟</dd>
          </div>
          <div>
            <dt>通过条件</dt>
            <dd>以理论卷及格线与后台判定为准</dd>
          </div>
        </dl>

        <div v-if="ongoingExamId" class="primary-actions">
          <button type="button" class="btn btn-primary btn-block" :disabled="loading" @click="continueExam">
            {{ loading ? '正在读取…' : '继续测评' }}
          </button>
          <button type="button" class="text-action danger" :disabled="loading" @click="abandonAndStartNew">
            放弃当前测评并重新开始
          </button>
          <p class="action-note">放弃不可恢复；仅保留已提交的答案。</p>
        </div>
        <div v-else class="primary-actions">
          <button type="button" class="btn btn-primary btn-block" :disabled="loading || !statusLoaded" @click="startExam">
            {{ loading ? '正在准备测评…' : '开始测评' }}
          </button>
          <p class="action-note">组卷由后台按题库条件完成；题库不足时不会生成不完整的测评。</p>
        </div>

        <p v-if="actionError" class="page-state is-error" role="alert">{{ actionError }}</p>
      </section>

      <aside class="exam-side" aria-labelledby="side-heading">
        <h2 id="side-heading" class="side-title">怎么用这块</h2>
        <ul class="side-list">
          <li><strong>待考/可开始</strong><span>点击“开始测评”，从理论部分进入正式答题。</span></li>
          <li><strong>进行中</strong><span>只显示“继续测评”，回到同一份卷子的已保存进度。</span></li>
          <li><strong>记录区</strong><span>全部历史、筛选、逐题结果与等级趋势，不在这里复制一份。</span></li>
        </ul>
        <p class="side-note">正式答题页不提供题内辅导入口；不做答案提示，也不绕过服务端防辅导策略。</p>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/shared/design/AppIcon.vue'
import { names } from '@/shared/navigation/names'
import { RECORDS_PATH, examsApi } from '@/learning/exams/api.js'

const router = useRouter()
const recordsPath = RECORDS_PATH
const loading = ref(false)
const dataLoading = ref(true)
const dataError = ref('')
const actionError = ref('')
const statusLoaded = ref(false)
const ongoingExamId = ref(null)
const recordCount = ref(null)

// 主操作只由真实进行中记录决定，不根据本地“点过开始”推断。
const statusKind = computed(() => ongoingExamId.value ? 'ongoing' : 'idle')
const statusLabel = computed(() => ongoingExamId.value ? '进行中' : statusLoaded.value ? '待考' : '状态未读取')

async function loadData() {
  dataLoading.value = true
  dataError.value = ''
  statusLoaded.value = false
  try {
    // 只读进行中记录；统计、趋势与最近记录在记录区读取。
    const [records, history] = await Promise.all([
      examsApi.records({ status: 'in_progress' }),
      examsApi.myHistory(),
    ])
    const list = Array.isArray(records?.results) ? records.results : []
    ongoingExamId.value = list[0]?.id ?? null
    recordCount.value = Array.isArray(history?.records) ? history.records.length : null
    statusLoaded.value = true
  } catch {
    dataError.value = '测评状态暂时未能读取，请重试；不会据此认为你没有进行中的测评。'
  } finally {
    dataLoading.value = false
  }
}

const continueExam = () => {
  if (ongoingExamId.value) router.push(`/exam-taking/${ongoingExamId.value}`)
}

// 放弃先显式确认；取消不写入任何状态。
const abandonAndStartNew = async () => {
  if (!confirm('确定要放弃当前测评吗？此操作无法撤销！')) return
  loading.value = true
  actionError.value = ''
  try {
    await examsApi.abandonComprehensive()
    ongoingExamId.value = null
    await startExam()
  } catch {
    actionError.value = '未能确认测评已放弃；请重新加载后再试，当前进行中记录不会被当作已完成。'
  } finally {
    loading.value = false
  }
}

const startExam = async () => {
  loading.value = true
  actionError.value = ''
  try {
    const res = await examsApi.startComprehensive()
    if (res?.theory_record?.id) {
      router.push(`/exam-taking/${res.theory_record.id}`)
    } else {
      actionError.value = '后台未返回可开始的测评记录，请刷新后重试。'
    }
  } catch (error) {
    const existingRecord = error?.response?.data?.exam_record_id
    if (existingRecord) {
      ongoingExamId.value = existingRecord
      actionError.value = '你还有进行中的测评，可以继续完成，或确认放弃后重新开始。'
    } else {
      actionError.value = '测评尚未创建成功。请稍后重试；若仍失败，请联系教师检查题库是否满足组卷条件。'
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
defineExpose({
  loadData, startExam, abandonAndStartNew, continueExam,
  loading, dataLoading, dataError, actionError, ongoingExamId, recordCount, statusLabel,
})
</script>
<style scoped>
.exam-center-page { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: 0 auto; padding: var(--space-3) 0 var(--space-6); color: var(--ink); }
.exam-heading { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-2); margin-bottom: var(--space-3); }
.exam-eyebrow { margin: 0 0 2px; color: var(--ink-secondary); font-size: var(--text-caption); }
.exam-heading h1 { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); }
.exam-subtitle { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.records-link { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); color: var(--action); font-size: var(--text-caption); text-decoration: none; }
.page-state { margin-bottom: var(--space-2); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.page-state.is-error { background: var(--negative-soft); color: var(--negative); }
.exam-layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: var(--space-2); align-items: start; }
.exam-card, .exam-side { min-width: 0; padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); }
.card-heading { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-2); margin-bottom: var(--space-2); }
.card-heading h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.card-note, .action-note, .side-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.status-badge { flex: none; padding: 2px var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.status-badge.is-idle { background: var(--action-soft); color: var(--action); }
.status-badge.is-ongoing { background: var(--warning-soft); color: var(--warning); }
.exam-facts { display: grid; gap: var(--space-1); margin: 0 0 var(--space-3); padding: var(--space-2) 0; border-top: var(--stroke) solid var(--line); border-bottom: var(--stroke) solid var(--line); }
.exam-facts div { display: grid; grid-template-columns: minmax(calc(var(--space-8) + var(--space-2)), auto) minmax(0, 1fr); gap: var(--space-2); }
.exam-facts dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.exam-facts dd { margin: 0; overflow-wrap: anywhere; }
.primary-actions { display: grid; gap: var(--space-1); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.btn-block { width: 100%; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:disabled { border-color: var(--line); background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.text-action { justify-self: start; padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.text-action.danger { color: var(--negative); }
.exam-side { display: grid; gap: var(--space-1); }
.side-title { margin: 0; font-size: var(--text-card); }
.side-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.side-list li { display: grid; gap: 2px; padding-top: var(--space-1); border-top: var(--stroke) solid var(--line); }
.side-list strong { font-size: var(--text-caption); }
.side-list span { color: var(--ink-secondary); font-size: var(--text-caption); }
.side-note { padding-top: var(--space-1); border-top: var(--stroke) solid var(--line); color: var(--ink-muted); }
.records-link:focus-visible, .btn:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.is-compact .exam-layout { grid-template-columns: minmax(0, 1fr); }
.is-compact .exam-facts div { grid-template-columns: minmax(0, 1fr); gap: 2px; }
</style>
