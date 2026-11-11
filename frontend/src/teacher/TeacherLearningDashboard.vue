<template>
  <section class="teacher-insights" aria-label="学情洞察">
    <header class="page-head"><h1>学情洞察</h1><p>只读跟踪学习记录，下钻查看学生成长；评分与布置在独立动作页完成。</p></header>
    <div class="filters"><label>搜索学生<input v-model="query" type="search" placeholder="学生姓名" /></label><label>排序<select v-model="sort"><option value="self_assessed_at">最近自评</option><option value="mastery">报表参考掌握度</option></select></label><button :disabled="state.rosterLoading" @click="model.loadStudents">重新读取</button></div>
    <p v-if="state.rosterLoading" role="status">正在读取学生名单…</p><p v-else-if="state.rosterError" role="alert">{{ state.rosterError }}</p>
    <template v-else><p class="note">本次已读取 {{ state.students.length }} 名学生。参考掌握度可能包含方向自评；正确提交次数可含重复提交，不等同于独立解题数。</p><p v-if="!rows.length">{{ state.students.length ? '没有符合筛选的学生。' : '暂无可查看的学生。' }}</p><div v-else class="table-scroll"><table><caption>已读取学生学习报表</caption><thead><tr><th scope="col">学生</th><th scope="col">引导状态</th><th scope="col">参考掌握度</th><th scope="col">正确提交次数</th><th scope="col">自评更新时间</th><th scope="col">成长图谱</th></tr></thead><tbody><tr v-for="student in rows" :key="student.id"><th scope="row">{{ student.username || '学生姓名暂不可用' }}</th><td>{{ student.onboarded === true ? '已完成引导' : student.onboarded === false ? '未完成引导' : '未提供' }}</td><td>{{ formatPercent(reportMastery(student)) }}</td><td>{{ countText(student.solved_count) }}</td><td>{{ formatDate(student.self_assessed_at) }}</td><td><router-link :to="`/teacher/students/${encodeURIComponent(student.id)}/growth`">查看成长图谱<span class="note"> · {{ student.username }}</span></router-link></td></tr></tbody></table></div></template>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useUserStore } from '@/store/user'
import api from './insights/api.js'
import { createInsightsState } from './insights/state.js'
import { countText, filterStudents, reportMastery } from './insights/presentation.js'
import { formatDate, formatPercent } from '@/shared/learning/presentation.js'
const user = useUserStore()
const model = createInsightsState({ api, wrap: reactive })
const state = model.state
const query = ref(''), sort = ref('self_assessed_at')
const rows = computed(() => filterStudents(state.students, query.value, sort.value))
watch(() => user.userInfo?.role === 'teacher' && user.userInfo?.id ? `teacher:${user.userInfo.id}` : null, account => { model.setAccount(account); query.value = ''; if (account) model.loadStudents() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(model.dispose)
</script>
<style scoped src="./insights/learning.css"></style>
