<template>
  <main class="teacher-growth">
    <header class="page-head"><h1>成长图谱 · 教师视角</h1><p>{{ student?.username || '选择学生' }} · 只展示该学生的可读取记录，缺少的成长分区单独说明。</p></header>
    <div class="filters"><label>学生<select :value="state.studentId" :disabled="state.rosterLoading" @change="model.selectStudent($event.target.value)"><option value="">选择学生</option><option v-for="item in state.students" :key="item.id" :value="item.id">{{ item.username || '学生姓名暂不可用' }}</option></select></label><label>学习活动窗口<select :value="state.days" @change="model.loadEffect(Number($event.target.value))"><option v-for="days in ACTIVITY_WINDOWS" :key="days" :value="days">近 {{ days }} 天</option></select></label><button :disabled="state.rosterLoading" @click="reload">重新读取</button></div>
    <p v-if="state.rosterLoading" role="status">正在读取学生名单…</p><p v-else-if="state.rosterError" role="alert">{{ state.rosterError }}</p><p v-else-if="requested && !student">该学生不在当前可读取名单中，未读取其他人的成长记录。</p>
    <nav v-if="student" class="section-links" aria-label="成长分区"><a v-for="section in GROWTH_SECTIONS" :key="section.key" :href="`#teacher-growth-${section.key}`" @click.prevent="goSection(section.key)">{{ section.title }}</a></nav>
    <div v-if="student" class="growth-sections">
      <section id="teacher-growth-overview" class="panel">
        <details class="length-disclosure" :open="expandedSections.overview" @toggle="onSectionToggle('overview', $event)">
          <summary class="length-disclosure__summary">成长总览</summary>
          <div class="length-disclosure__body">
            <h2>成长总览</h2><p>{{ student.goals || '该学生尚未提供学习目标。' }}</p><dl class="summary-grid"><div><dt>参考掌握度</dt><dd>{{ formatPercent(reportMastery(student)) }}</dd></div><div><dt>正确提交次数</dt><dd>{{ countText(student.solved_count) }}</dd></div><div><dt>累计积分</dt><dd>{{ countText(student.score) }}</dd></div></dl><p class="note">参考掌握度可能包含自评，正确提交次数可含重复提交。模块完成率、个人画像与学习航线进度暂未提供，不能据此视为完整成长报告。</p>
          </div>
        </details>
      </section>
      <section id="teacher-growth-activity" class="panel">
        <details class="length-disclosure" :open="expandedSections.activity" @toggle="onSectionToggle('activity', $event)">
          <summary class="length-disclosure__summary">学习活动</summary>
          <div class="length-disclosure__body">
            <h2>学习活动</h2><p v-if="state.effectLoading" role="status">正在读取近 {{ state.days }} 天学习活动…</p><p v-else-if="state.effectError" role="alert">{{ state.effectError }}<button @click="model.loadEffect()">重试</button></p><template v-else-if="state.effect"><ActivityFacts :effect="state.effect" /><TrendChart v-if="state.effect.hasDaily" :rows="activityRows" title="每日学习分钟" unit="分钟" :show-table="false" /><p v-else>这一时间窗暂无学习日数据，不生成曲线或累计学习天数。</p><dl class="metric-grid"><div v-for="metric in metrics" :key="metric.key"><dt>{{ metric.label }}</dt><dd>{{ metricText(metric.value) }}</dd></div></dl><p class="note">八项数值是学习效果指数，不是实际小时或独立测评分。实际有效学习时长：{{ formatMinutes(secondsToMinutes(state.rawEffect?.snapshot?.sample_description?.effective_learning_seconds)) }}。</p></template>
          </div>
        </details>
      </section>
      <section id="teacher-growth-mastery" class="panel">
        <details class="length-disclosure" :open="expandedSections.mastery" @toggle="onSectionToggle('mastery', $event)">
          <summary class="length-disclosure__summary">掌握与能力</summary>
          <div class="length-disclosure__body">
            <h2>掌握与能力</h2><h3>六方向自评</h3><dl class="metric-grid"><div v-for="direction in DIRECTIONS" :key="direction.key"><dt>{{ direction.label }}</dt><dd>{{ rating(student.skills?.[direction.key]) }}</dd></div></dl><h3>报表概念参考值</h3><p class="note">此报表可能由自评回退生成，不能作为独立能力通过的结论。</p><ul v-if="student.concepts?.length"><li v-for="(concept, index) in student.concepts" :key="index">{{ concept.name }} · {{ formatPercent(percentFromRatio(concept.mastery)) }}</li></ul><p v-else>暂无概念参考记录。</p><p>该学生的动态方向成长、能力探索与练习事实暂未提供，目前无法在此核对这些记录。</p>
          </div>
        </details>
      </section>
      <section id="teacher-growth-recommendations" class="panel">
        <details class="length-disclosure" :open="expandedSections.recommendations" @toggle="onSectionToggle('recommendations', $event)">
          <summary class="length-disclosure__summary">推荐与航线</summary>
          <div class="length-disclosure__body">
            <h2>推荐与航线</h2><ul v-if="state.effect?.recommendations.length"><li v-for="(item, index) in state.effect.recommendations" :key="index"><strong>{{ item.action_text || item.title || '学习建议' }}</strong><p>{{ item.reason || '本条教学理由暂未提供。' }}</p><p v-if="item.content">{{ item.content }}</p></li></ul><p v-else>暂无该学生的活动建议。</p><p class="note">活动建议来自本次学习快照；个体题目推荐与在学航线明细暂未提供。</p>
          </div>
        </details>
      </section>
      <section id="teacher-growth-reviews" class="panel">
        <details class="length-disclosure" :open="expandedSections.reviews" @toggle="onSectionToggle('reviews', $event)">
          <summary class="length-disclosure__summary">复习提醒</summary>
          <div class="length-disclosure__body">
            <h2>复习提醒</h2><p>该学生的到期复习清单、记忆概率与完成复习记录暂未提供。教师视角不能代替学生标记完成复习。</p>
          </div>
        </details>
      </section>
      <section id="teacher-growth-results" class="panel">
        <details class="length-disclosure" :open="expandedSections.results" @toggle="onSectionToggle('results', $event)">
          <summary class="length-disclosure__summary">结果与复盘</summary>
          <div class="length-disclosure__body">
            <h2>结果与复盘</h2><p>该学生的完整测评结果、提交复盘、复测与争议明细暂未提供。原任务统计仍可在学情洞察展开；此处不以累计积分代替测评成绩。</p>
          </div>
        </details>
      </section>
      <section id="teacher-growth-report" class="panel">
        <details class="length-disclosure" :open="expandedSections.report" @toggle="onSectionToggle('report', $event)">
          <summary class="length-disclosure__summary">学习结论与报告</summary>
          <div class="length-disclosure__body">
            <h2>学习结论与报告</h2><p class="note">该学生的周报与个人学习报告暂未提供；以下教学方案不冒充完整学习报告。</p><TeachingPlan :plan="state.plan" :loading="state.planLoading" :error="state.planError" /><button :disabled="state.planLoading" @click="model.loadPlan">重新读取方案</button>
          </div>
        </details>
      </section>
    </div>
  </main>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import '@/shared/layout/disclosure.css'
import { useUserStore } from '@/store/user'
import api from './insights/api.js'
import { createInsightsState } from './insights/state.js'
import { GROWTH_SECTIONS, countText, metricRows, metricText, reportMastery } from './insights/presentation.js'
import { DIRECTIONS } from './assessment/presentation.js'
import { ACTIVITY_WINDOWS, finite, formatDate, formatMinutes, formatPercent, percentFromRatio, secondsToMinutes } from '@/shared/learning/presentation.js'
import ActivityFacts from '@/shared/learning/ActivityFacts.vue'
import TeachingPlan from '@/shared/learning/TeachingPlan.vue'
import TrendChart from '@/shared/learning/TrendChart.vue'
const props = defineProps({ studentId: { type: [String, Number], default: '' } })
const route = useRoute(), router = useRouter(), user = useUserStore()
const requested = computed(() => props.studentId || route.params.studentId || '')
const model = createInsightsState({ api, wrap: reactive }), state = model.state
const student = computed(() => state.students.find(item => String(item.id) === String(state.studentId)))
const metrics = computed(() => metricRows(state.rawEffect))
const activityRows = computed(() => (state.effect?.dailyStats || []).map(row => ({ date: row.date, value: row.minutes })))
const rating = value => { const number = finite(value); return number === null || number < 0 || number > 5 ? '未自评' : `${number} / 5` }
const defaultExpandedSections = () => Object.fromEntries(GROWTH_SECTIONS.map(section => [section.key, section.key === 'overview']))
const expandedSections = ref(defaultExpandedSections())
const sectionKey = hash => GROWTH_SECTIONS.find(section => `#teacher-growth-${section.key}` === hash)?.key
function onSectionToggle(key, event) {
  expandedSections.value[key] = event.currentTarget.open
}
function scrollToSection(key) {
  if (!student.value || !expandedSections.value[key]) return
  const element = typeof document !== 'undefined' ? document.getElementById(`teacher-growth-${key}`) : null
  element?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}
function goSection(key) {
  if (!student.value || !GROWTH_SECTIONS.some(section => section.key === key)) return
  expandedSections.value[key] = true
  router.replace({ query: route.query, hash: `#teacher-growth-${key}` })
  nextTick(() => scrollToSection(key))
}
function applyHash() {
  const key = sectionKey(route.hash)
  if (!key || !student.value) return
  expandedSections.value[key] = true
  nextTick(() => scrollToSection(key))
}
// 首次书签可直达分区；之后换学生/账号不继承上一人的展开选择。
let firstStudent = true
watch(() => state.studentId, id => {
  expandedSections.value = defaultExpandedSections()
  if (id && firstStudent) { firstStudent = false; applyHash() }
}, { flush: 'sync' })
watch(() => route.hash, applyHash)
let reloadGeneration = 0
async function reload() {
  const generation = ++reloadGeneration
  const previous = state.studentId
  await model.loadStudents()
  if (generation !== reloadGeneration) return
  await model.selectStudent(requested.value || previous || state.students[0]?.id)
}
watch(() => user.userInfo?.role === 'teacher' && user.userInfo?.id ? `teacher:${user.userInfo.id}` : null, account => { reloadGeneration++; model.setAccount(account); if (account) reload() }, { immediate: true, flush: 'sync' })
watch(requested, id => {
  model.selectStudent(id)
  // An in-flight roster load finishes against the latest route, never its old captured student.
}, { flush: 'sync' })
onBeforeUnmount(model.dispose)
</script>
<style scoped src="./insights/learning.css"></style>
