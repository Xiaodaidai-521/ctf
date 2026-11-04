<template>
  <main class="governance-page" data-density="admin">
    <template v-if="allowed">
      <header class="governance-hero"><h1>{{ names.globalInsights }}</h1><p class="governance-muted">只读核对平台使用与内容分布。教师学情、评分录入与教学反馈使用独立工作区。</p></header>
      <div class="governance-heading"><h2>平台概况</h2><button class="governance-primary" :disabled="loading" @click="load">{{ loading ? '正在读取…' : '刷新洞察' }}</button></div>
      <section class="governance-panel"><div class="governance-table-wrap"><table class="platform-overview"><thead><tr><th scope="col">统计项</th><th scope="col">当前值</th><th scope="col">范围与来源</th></tr></thead><tbody><tr v-for="metric in metrics" :key="metric.key"><th scope="row">{{ metric.label }}</th><td>{{ metric.loading ? '读取中…' : metric.value === null ? '未提供' : `${metric.value}${metric.unit || ''}` }}</td><td><p v-if="metric.error" class="governance-error" role="alert">{{ metric.error }}</p><p v-else>{{ metric.scope }}</p></td></tr></tbody></table></div><p class="governance-muted">新增人数、总分发放与平均分尚未提供，不补零也不推算。</p></section>
      <details class="governance-panel"><summary>题目分类与难度分布</summary><p class="governance-muted">仅按本次已读取题目计算，不代表完整题库。完整题目总数以治理列表为准。</p><p v-if="sources.challenges.loading" role="status">正在读取题目…</p><p v-else-if="sources.challenges.error" class="governance-error" role="alert">{{ sources.challenges.error }}</p><template v-else><section v-for="group in distributions" :key="group.title"><h2>{{ group.title }}</h2><p v-if="!group.rows.length">暂无已读取的分布数据。</p><div v-else class="governance-table-wrap"><table><thead><tr><th>分类</th><th>题目数量</th><th>当前占比</th></tr></thead><tbody><tr v-for="row in group.rows" :key="row.name"><th>{{ row.name }}</th><td>{{ row.count }} 题</td><td>{{ row.percentage }}%</td></tr></tbody></table></div></section></template></details>
      <details class="governance-panel"><summary>学生使用概况与只读记录</summary><p class="governance-muted">这里是学生名单的使用概况，不是全部平台用户。参考掌握度可能来自学生自评，不等于独立掌握证据；正确提交数不等于去重解题数。</p><p v-if="sources.students.loading" role="status">正在读取学生记录…</p><p v-else-if="sources.students.error" class="governance-error" role="alert">{{ sources.students.error }}</p><template v-else-if="sources.students.data"><dl><dt>学生人数</dt><dd>{{ summary.students }}</dd><dt>已完成引导</dt><dd>{{ summary.onboarded }} / {{ summary.onboardedSamples }} 人有状态</dd><dt>参考平均掌握度</dt><dd>{{ percentLabel(summary.averageMastery) }} · {{ summary.masterySamples }} 人有数据</dd><dt>学生正确提交总数</dt><dd>{{ summary.correctSubmissions === null ? '未提供' : summary.correctSubmissions }}</dd></dl>
        <div class="governance-actions"><label>查找学生 <input v-model="search" placeholder="输入学生姓名" /></label><label>排序 <select v-model="sort"><option value="recent">按自评时间</option><option value="mastery">按参考掌握度</option></select></label></div><p v-if="!students.length">当前没有符合筛选的学生记录。</p>
        <details v-for="student in students" :key="student.id"><summary>{{ student.username || '学生姓名未提供' }} · {{ student.onboarded === true ? '已完成引导' : student.onboarded === false ? '未完成引导' : '引导状态未提供' }} · 参考掌握度 {{ percentLabel(student.mastery) }}</summary><dl><dt>正确提交</dt><dd>{{ countLabel(student.solved_count) }}</dd><dt>累计积分</dt><dd>{{ countLabel(student.score) }}</dd><dt>学习目标</dt><dd>{{ student.goals || '未填写' }}</dd><dt>自评时间</dt><dd>{{ dateLabel(student.self_assessed_at) }}</dd><template v-for="direction in directions" :key="direction.key"><dt>{{ direction.label }}自评</dt><dd>{{ selfRatingLabel(student.skills?.[direction.key]) }}</dd></template></dl><h3>参考概念掌握度</h3><ul v-if="student.concepts?.length"><li v-for="(concept, index) in student.concepts" :key="index">{{ concept.name || '概念名称未提供' }} · {{ conceptLabel(concept.mastery) }}</li></ul><p v-else>暂无概念记录。</p><router-link :to="{ path: '/admin/learning-scores', query: { student: student.id } }">核对该学生评测记录</router-link><p class="governance-muted">教学建议与下一步安排由教师在学情洞察中处理，管理员不代替教师评分。</p></details>
      </template></details>
      <details class="governance-panel"><summary>最新解题动态</summary><p class="governance-muted">显示最近已读取的正确提交，不将每次提交当作首次解题或积分发放。</p><p v-if="sources.activities.loading" role="status">正在读取提交记录…</p><p v-else-if="sources.activities.error" class="governance-error" role="alert">{{ sources.activities.error }}</p><template v-else-if="sources.activities.data"><p v-if="!activities.length">暂无已读取的正确提交记录，不生成示例动态。</p><ul v-else><li v-for="row in activities" :key="row.id">{{ row.username || '用户姓名未提供' }} · {{ row.challenge_title || '题目名称未提供' }} · {{ dateLabel(row.created_at) }}</li></ul></template><router-link to="/admin/submissions">打开提交记录</router-link></details>
    </template>
    <p v-else role="alert">全局洞察仅供管理员使用，请使用与你身份相符的入口。</p>
  </main>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import { names } from '@/shared/navigation/names.js'
import { platformInsightsApi } from './api.js'
import { challengeDistributions, conceptLabel, directions, percentLabel, platformStats, selfRatingLabel, studentSummary } from './presentation.js'
import { countValue, dateLabel, listValue, numberValue } from '../governance/data.js'
import { useGovernanceSources } from '../governance/useSources.js'
const { allowed, user, sources, loading, load } = useGovernanceSources(platformInsightsApi)
const search = ref(''), sort = ref('recent')
usePageFilters('admin-global-insights', { sort })
if (!['recent', 'mastery'].includes(sort.value)) sort.value = 'recent'
watch(() => user.userInfo, () => { search.value = '' }, { deep: true, flush: 'sync' })
const stats = computed(() => platformStats(sources))
const metrics = computed(() => [
  ['totalUsers', '平台用户总数', 'users', '用户与权限，包含全部角色'],
  ['rankedUsers', '有积分的榜单用户', 'leaderboard', '已有排行榜，不等于总用户数'],
  ['totalChallenges', '本次已读取题目', 'challenges', '本次题目列表，不外推完整题库'],
  ['totalSubmissions', '平台总提交数', 'submissions', '全部平台提交记录'],
  ['successRate', '平台提交正确率', 'submissions', '全部提交中正确提交的比例', '%'],
].map(([key, label, source, scope, unit]) => ({ key, label, scope, unit, value: stats.value[key], error: sources[source].error, loading: sources[source].loading })))
const distributions = computed(() => { const result = challengeDistributions(sources.challenges.data); return [{ title: '题目分类分布', rows: result.categories }, { title: '题目难度分布', rows: result.difficulties }] })
const allStudents = computed(() => sources.students.data ? listValue(sources.students.data) : [])
const summary = computed(() => studentSummary(allStudents.value))
const time = row => { const value = row.self_assessed_at ? new Date(row.self_assessed_at).getTime() : 0; return Number.isFinite(value) ? value : 0 }
const students = computed(() => allStudents.value.filter(row => String(row.username || '').toLowerCase().includes(search.value.toLowerCase())).sort((a, b) => sort.value === 'mastery' ? (numberValue(b.mastery) ?? -1) - (numberValue(a.mastery) ?? -1) || time(b) - time(a) : time(b) - time(a)))
const activities = computed(() => sources.activities.data ? listValue(sources.activities.data).filter(row => row.is_correct === true) : [])
const countLabel = value => countValue(value) === null ? '未提供' : value
</script>
<style scoped src="../governance/governance.css"></style>
<style scoped>
@media (max-width: 768px) {
  .platform-overview, .platform-overview tbody { display: block; width: 100%; }
  .platform-overview thead { display: none; }
  .platform-overview tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-1); padding-block: var(--space-2); border-bottom: var(--stroke) solid var(--line); }
  .platform-overview th, .platform-overview td { min-width: 0; padding: 0; border: 0; white-space: normal; overflow-wrap: anywhere; }
  .platform-overview td:last-child { grid-column: 1 / -1; }
  .platform-overview p { margin: 0; }
}
</style>
