<template>
  <main class="teacher-assessment">
    <header class="page-head"><h1>动态评测</h1><p>录入真实测评，生成下一阶段教学安排。学情洞察在独立页面查看。</p></header>
    <div class="filters"><label>学生<select :value="state.studentId" :disabled="state.rosterLoading || state.saving" @change="model.selectStudent($event.target.value)"><option value="">选择学生</option><option v-for="student in state.students" :key="student.id" :value="student.id">{{ student.username || '学生姓名暂不可用' }}</option></select></label><button :disabled="state.rosterLoading || state.saving" @click="model.loadStudents">重新读取名单</button><button :disabled="!state.studentId || state.loading || state.saving" @click="model.readSelection">重新读取评分与方案</button></div>
    <p v-if="state.rosterLoading" role="status">正在读取学生名单…</p>
    <p v-if="state.rosterError" role="alert">{{ state.rosterError }}</p>
    <p v-else-if="!state.rosterLoading && !state.students.length">暂无可查看的学生。</p>
    <template v-if="state.studentId">
      <p v-if="state.message" role="status">{{ state.message }}</p>
      <div class="work-grid">
        <section class="panel form-panel"><h2>录入评分</h2><form @submit.prevent="model.save"><fieldset :disabled="state.saving || state.needsReconciliation"><div class="field-grid"><label>实际测评日期<input v-model="state.form.measured_at" type="date" :max="today" required /></label><label>总分<input v-model="state.form.total_score" type="number" min="0" max="100" step="0.01" required /></label><label v-for="direction in DIRECTIONS" :key="direction.key">{{ direction.label }}<input v-model="state.form.dimension_scores[direction.key]" type="number" min="0" max="100" step="0.01" required /></label></div><label>标签<input v-model="state.form.tagsText" placeholder="用逗号分隔，如基础巩固、专项提升" /></label><label>关键备注<textarea v-model="state.form.remark" rows="3" placeholder="记录错因、观察与建议" /></label><button class="primary" :disabled="state.saving || state.needsReconciliation" type="submit">{{ state.saving ? '正在保存…' : '保存评分并生成方案' }}</button></fieldset></form></section>
        <section class="panel"><h2>数据有效性</h2><p>仅使用近 {{ state.rules?.valid_score_days ?? 90 }} 天内、间隔不少于 {{ state.rules?.min_interval_days ?? 7 }} 天的两次最新有效评分。</p><p>当前有效评分：{{ state.loading || state.scoresError ? '—' : `${state.effectiveIds.length} 次` }}</p><TeachingPlan :plan="state.plan" :loading="state.planLoading" :error="state.planError" /></section>
        <section class="panel wide"><h2>综合总评</h2><p v-if="state.loading" role="status">正在读取评分…</p><p v-else-if="state.scoresError" role="alert">{{ state.scoresError }}</p><template v-else><p>{{ state.summary?.status === 'ready' ? '已生成总评' : '待补齐自评或有效教师评分' }}</p><dl class="summary-grid"><div><dt>学生自评</dt><dd>{{ scoreText(state.summary?.self_assessment?.score) }}</dd></div><div><dt>最新有效教师评分</dt><dd>{{ scoreText(state.summary?.admin?.score) }}</dd><small>{{ state.summary?.admin?.measured_at || '暂无测评日期' }}</small></div><div><dt>计算后总评</dt><dd>{{ scoreText(state.summary?.final_score) }}</dd></div></dl><p>自评 {{ weight(state.summary?.weights?.self_assessment) }}，教师评分 {{ weight(state.summary?.weights?.admin) }}；总评直接使用已返回的结果，不补算缺失分数。</p></template></section>
        <section class="panel wide"><div class="section-head"><h2>历史评分趋势</h2><label>趋势方向<select v-model="trendMode"><option value="total">总分</option><option v-for="direction in DIRECTIONS" :key="direction.key" :value="direction.key">{{ direction.label }}</option></select></label></div><TrendChart :rows="trend" :title="trendTitle" :max="100" /></section>
        <section class="panel wide"><h2>历史评分</h2><p>最多读取最近 100 条评分；有效性由评分记录给出。</p><p v-if="!state.loading && !state.scoresError && !state.rows.length">暂无评分记录。</p><div class="table-scroll" v-if="state.rows.length"><table><caption>评分记录（保留六方向、标签和备注）</caption><thead><tr><th>实际日期</th><th>总分</th><th v-for="direction in DIRECTIONS" :key="direction.key">{{ direction.label }}</th><th>有效性</th><th>标签</th><th>关键备注</th></tr></thead><tbody><tr v-for="row in state.rows" :key="row.id"><th>{{ row.measured_at }}</th><td>{{ scoreText(row.total_score) }}</td><td v-for="direction in DIRECTIONS" :key="direction.key">{{ scoreText(row.dimension_scores?.[direction.key]) }}</td><td>{{ validityLabel(row.validity_status) }}</td><td>{{ (row.tags || []).join('、') || '无' }}</td><td>{{ row.remark || '无' }}</td></tr></tbody></table></div></section>
      </div>
    </template>
  </main>
</template>
<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useUserStore } from '@/store/user'
import api from './api.js'
import { createAssessmentState } from './state.js'
import { DIRECTIONS, localToday, scoreText, trendRows, validityLabel } from './presentation.js'
import { finite } from '@/shared/learning/presentation.js'
import TeachingPlan from '@/shared/learning/TeachingPlan.vue'
import TrendChart from '@/shared/learning/TrendChart.vue'
const user = useUserStore()
const today = localToday()
const model = createAssessmentState({ api, wrap: reactive, today })
const state = model.state
const trendMode = ref('total')
const trend = computed(() => trendRows(state.rows, trendMode.value))
const trendTitle = computed(() => trendMode.value === 'total' ? '总分趋势' : `${DIRECTIONS.find(item => item.key === trendMode.value)?.label}趋势`)
const weight = value => finite(value) === null ? '权重未提供' : `占 ${Math.round(finite(value) * 100)}%`
watch(() => user.userInfo?.role === 'teacher' && user.userInfo?.id ? `teacher:${user.userInfo.id}` : null, account => { model.setAccount(account); if (account) model.loadStudents() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(model.dispose)
</script>
<style scoped src="../insights/learning.css"></style>
