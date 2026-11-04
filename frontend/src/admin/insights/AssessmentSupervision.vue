<template>
  <main class="governance-page" data-density="admin">
    <template v-if="allowed">
      <header class="governance-hero"><h1>{{ names.assessmentSupervision }}</h1><p class="governance-muted">只读核对测评来源、有效性与方案依据。真实评分录入和教学安排由教师负责。</p></header>
      <div class="governance-heading"><label>学生 <select v-model="selectedStudent" :disabled="rosterLoading"><option value="">请选择学生</option><option v-for="student in students" :key="student.id" :value="String(student.id)">{{ student.username || '学生姓名未提供' }}</option></select></label><button class="governance-primary" :disabled="loading || rosterLoading" @click="refresh">{{ loading || rosterLoading ? '正在读取…' : '刷新监督记录' }}</button></div>
      <p v-if="rosterSources.students.error" class="governance-error" role="alert">{{ rosterSources.students.error }}</p><p v-else-if="!rosterLoading && !students.length">暂无可读取的学生名单。</p>
      <p class="governance-notice">本页不提供评分录入、修改、生成或确认教学安排的操作。教师使用“动态评测”，管理员只核对记录。</p>
      <template v-if="selectedStudent">
        <section class="governance-panel"><h2>数据有效性与综合总评</h2><p v-if="sources.scores.loading" role="status">正在读取评分…</p><p v-else-if="sources.scores.error" class="governance-error" role="alert">{{ sources.scores.error }}</p><template v-else-if="sources.scores.data"><p>有效性规则：{{ rulesLabel }}</p><dl><dt>有效评分数量</dt><dd>{{ effectiveCount }}</dd><dt>学生自评</dt><dd>{{ scoreLabel(summary?.self_assessment?.score) }} · {{ weight(summary?.weights?.self_assessment) }}</dd><dt>最新有效教师评分</dt><dd>{{ scoreLabel(summary?.admin?.score) }} · {{ weight(summary?.weights?.admin) }}</dd><dt>实际测评日期</dt><dd>{{ summary?.admin?.measured_at || '未提供' }}</dd><dt>计算后总评</dt><dd>{{ scoreLabel(summary?.final_score) }}</dd><dt>总评状态</dt><dd>{{ summary?.status === 'ready' ? '已生成总评' : '待补齐数据' }}</dd></dl><p class="governance-muted">总评直接使用已有结果，缺少分数不补算。</p></template></section>
        <details class="governance-panel"><summary>历史评分趋势</summary><label>趋势方向 <select v-model="direction"><option value="total">总分</option><option v-for="item in directions" :key="item.key" :value="item.key">{{ item.label }}</option></select></label><TrendChart v-if="!sources.scores.error && !sources.scores.loading" :rows="trend" :title="trendTitle" :max="100" /></details>
        <section class="governance-panel"><h2>历史评分与责任记录</h2><p class="governance-muted">最多读取最近 100 条。评分人员、测评日期、六方向、标签和备注均保留；有效性以记录为准。</p><p v-if="sources.scores.loading" role="status">正在读取评分记录…</p><p v-else-if="!sources.scores.error && !rows.length">暂无评分记录。</p><div v-if="rows.length" class="governance-table-wrap"><table><thead><tr><th>实际日期</th><th>评分人员</th><th>总分</th><th v-for="item in directions" :key="item.key">{{ item.label }}</th><th>有效性</th><th>标签</th><th>关键备注</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><th>{{ row.measured_at || '未提供' }}</th><td>{{ row.scored_by_name || '人员信息未提供' }}</td><td>{{ scoreLabel(row.total_score) }}</td><td v-for="item in directions" :key="item.key">{{ scoreLabel(row.dimension_scores?.[item.key]) }}</td><td>{{ validityLabel(row.validity_status) }}</td><td>{{ Array.isArray(row.tags) ? row.tags.join('、') || '无' : '未提供' }}</td><td>{{ row.remark || '无' }}</td></tr></tbody></table></div></section>
        <details class="governance-panel"><summary>教学方案依据监督</summary><TeachingPlan :plan="sources.plan.data" :loading="sources.plan.loading" :error="sources.plan.error" /><p class="governance-muted">方案只供核对依据，不代表已完成安排或已掌握，也不由管理员代为执行。</p></details>
      </template>
    </template>
    <p v-else role="alert">评测监督仅供管理员使用。教师请从动态评测进入。</p>
  </main>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { names } from '@/shared/navigation/names.js'
import TeachingPlan from '@/shared/learning/TeachingPlan.vue'
import TrendChart from '@/shared/learning/TrendChart.vue'
import { assessmentSupervisionApi } from './api.js'
import { directions, scoreTrend, validityLabel } from './presentation.js'
import { countValue, listValue, numberValue, scoreLabel } from '../governance/data.js'
import { useGovernanceSources } from '../governance/useSources.js'
const route = useRoute(), selectedStudent = ref(''), direction = ref('total')
const roster = useGovernanceSources({ students: assessmentSupervisionApi.students })
const { allowed, user, sources: rosterSources, loading: rosterLoading } = roster
const selection = useGovernanceSources({ scores: () => selectedStudent.value ? assessmentSupervisionApi.scores(selectedStudent.value) : null, plan: () => selectedStudent.value ? assessmentSupervisionApi.plan(selectedStudent.value) : null })
const { sources, loading, load } = selection
const students = computed(() => rosterSources.students.data ? listValue(rosterSources.students.data) : [])
watch([() => route.query.student, students], ([id]) => { if (id && students.value.some(student => String(student.id) === String(id))) selectedStudent.value = String(id) }, { immediate: true })
watch(selectedStudent, () => { direction.value = 'total'; load() }, { flush: 'sync' })
watch(() => user.userInfo, () => { selectedStudent.value = ''; selection.clear() }, { deep: true, flush: 'sync' })
const rows = computed(() => sources.scores.data ? listValue(sources.scores.data) : [])
const summary = computed(() => sources.scores.data?.score_summary)
const effectiveCount = computed(() => Array.isArray(sources.scores.data?.effective_score_ids) ? `${sources.scores.data.effective_score_ids.length} 次` : '未提供')
const rulesLabel = computed(() => { const rules = sources.scores.data?.filter_rules; const days = countValue(rules?.valid_score_days), interval = countValue(rules?.min_interval_days); return days === null || interval === null ? '规则尚未提供，请核对评分记录的有效性。' : `近 ${days} 天内、间隔不少于 ${interval} 天的两次最新有效评分。` })
const weight = value => { const number = numberValue(value); return number !== null && number >= 0 && number <= 1 ? `占 ${Math.round(number * 100)}%` : '权重未提供' }
const trend = computed(() => scoreTrend(rows.value, direction.value))
const trendTitle = computed(() => direction.value === 'total' ? '历史总分' : `${directions.find(item => item.key === direction.value)?.label}历史评分`)
async function refresh() { await roster.load(); if (selectedStudent.value && !students.value.some(student => String(student.id) === selectedStudent.value)) { selectedStudent.value = ''; selection.clear() } else await load() }
</script>
<style scoped src="../governance/governance.css"></style>
