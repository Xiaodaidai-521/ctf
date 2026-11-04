<template>
  <section class="teacher-overview">
    <header><p class="overview-label">教学工作区</p><h1>{{ names.teacher }}</h1><p>先处理待办，再把资料与学情转成下一步教学安排。</p></header>
    <div class="cockpit-heading"><div><h2>今日教学待办</h2><p>各项按自己的范围显示，不合并成一个总数。</p></div><button class="btn btn-primary" :disabled="loading" @click="load">{{ loading ? '正在读取…' : '刷新待办' }}</button></div>
    <div class="todo-grid">
      <router-link v-for="tile in tiles" :key="tile.key" :to="tile.href" class="todo-tile">
        <span>{{ tile.title }}</span><strong>{{ tile.loading ? '…' : tile.count === null ? '—' : tile.count }}</strong>
        <p :class="{ 'read-error': tile.error }">{{ tile.loading ? '正在读取待办' : tile.error || (tile.count === null ? '数量暂未提供，可打开工作页核对。' : tile.description) }}</p>
        <small v-if="tile.scope">{{ tile.scope }}</small><span class="tile-open">打开处理 <icon-arrow-right /></span>
      </router-link>
    </div>
    <section class="priority-list" aria-labelledby="priority-heading">
      <h2 id="priority-heading">优先反馈</h2>
      <p v-if="sources.feedback.loading" role="status">正在读取反馈…</p>
      <p v-else-if="sources.feedback.error" role="alert">{{ sources.feedback.error }}</p>
      <ul v-else-if="priorities.length"><li v-for="(item, index) in priorities" :key="index"><router-link :to="item.href"><div><strong>{{ item.title }}</strong><p>{{ item.student }} · {{ item.reason }}</p></div><icon-arrow-right /></router-link></li></ul>
      <p v-else>当前已读取的优先反馈中没有待处理项。</p>
    </section>
    <section class="content-block"><h2>内容与资料</h2><ContentAreaNav /></section>
    <section class="work-links"><h2>教学工作入口</h2><div class="teaching-links"><router-link v-for="item in entries" :key="item.path" :to="item.path"><component :is="item.icon" /><div><h3>{{ item.title }}</h3><p>{{ item.description }}</p></div><icon-arrow-right /></router-link></div></section>
    <section class="collaboration-console"><div class="console-heading"><icon-message /><h2>教学协作</h2></div><p>在协作对话中梳理教学问题，关键教学决定由你核对。</p><router-link class="text-link" to="/multi-agent">打开协作对话 →</router-link></section>
  </section>
</template>
<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names.js'
import ContentAreaNav from '@/shared/knowledge/ContentAreaNav.vue'
import { cockpitApi } from './cockpit/api.js'
import { cockpitError, cockpitPriorities, cockpitTiles } from './cockpit/model.js'
const user = useUserStore()
const keys = Object.keys(cockpitApi)
const sources = reactive(Object.fromEntries(keys.map(key => [key, { data: null, error: '', loading: true }])))
const loading = ref(false)
const tiles = computed(() => cockpitTiles(sources))
const priorities = computed(() => cockpitPriorities(sources))
let generation = 0
async function load() {
  const token = ++generation
  loading.value = true
  for (const key of keys) Object.assign(sources[key], { data: null, error: '', loading: true })
  await Promise.all(keys.map(async key => {
    try { const data = await cockpitApi[key](); if (token === generation) sources[key].data = data }
    catch (error) { if (token === generation) sources[key].error = cockpitError(error) }
    finally { if (token === generation) sources[key].loading = false }
  }))
  if (token === generation) loading.value = false
}
watch(() => `${user.userInfo?.id}:${user.userInfo?.role}`, () => {
  ++generation
  for (const key of keys) Object.assign(sources[key], { data: null, error: '', loading: false })
  loading.value = false
})
onMounted(load)
onUnmounted(() => { ++generation })
const entries = [
  { path: '/teacher/learning-paths', title: names.paths, icon: 'icon-branch', description: '创建与维护课程航线、章节和实验。' },
  { path: '/teacher/challenges', title: '题目管理', icon: 'icon-code', description: '维护练习题目与实验环境。' },
  { path: '/teacher/learning-scores', title: names.assessment, icon: 'icon-edit', description: '录入学生测评，生成教学方案。' },
  { path: '/teacher/learning-effect', title: names.insights, icon: 'icon-bar-chart', description: '了解学习变化，下钻学生成长记录。' },
  { path: '/teacher/teaching-actions', title: '教学安排', icon: 'icon-check-square', description: '依据学情创建、确认或调整教学安排。' },
  { path: '/teacher/feedback/reconciliation', title: names.eventReconciliation, icon: 'icon-history', description: '单独核对处理事件，不与反馈决策混在一起。' },
]
</script>
<style scoped>
.teacher-overview { max-width: var(--page-width); padding: var(--space-4) var(--page-gutter); margin-inline: auto; }
header { margin-bottom: var(--space-4); text-align: center; }
header h1 { margin-bottom: var(--space-2); font-size: clamp(var(--text-page), 5vw, var(--student-hero-size)); background: var(--student-hero-gradient); background-clip: text; -webkit-background-clip: text; color: transparent; }
header p, .cockpit-heading p, .todo-tile p, .teaching-links p, .priority-list p, .collaboration-console p { color: var(--ink-secondary); margin: var(--space-1) 0 0; }
.overview-label { font-size: var(--text-caption); }
h2 { font-size: var(--text-section); margin: 0 0 var(--space-2); }
.cockpit-heading { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
.todo-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--density-gap); }
.todo-tile { display: grid; gap: var(--space-1); padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); color: var(--ink); text-decoration: none; }
.todo-tile:first-child { grid-column: span 2; }
.todo-tile strong { font-size: var(--text-page); }
.todo-tile p, .todo-tile small { font-size: var(--text-caption); }
.todo-tile small { color: var(--ink-muted); }
.tile-open { display: flex; align-items: center; gap: var(--space-1); margin-top: var(--space-1); font-size: var(--text-caption); }
.todo-tile .read-error { color: var(--negative); }
.priority-list, .content-block, .work-links, .collaboration-console { margin-top: var(--space-4); }
.priority-list ul { padding: 0; list-style: none; }
.priority-list a { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); padding: var(--space-2) 0; border-bottom: var(--stroke) solid var(--line); color: var(--ink); text-decoration: none; }
.teaching-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--density-gap); }
.teaching-links a { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-control); color: var(--ink); background: var(--surface); text-decoration: none; }
.teaching-links a > svg:last-child { margin-left: auto; }
.teaching-links h3 { margin: 0; font-size: var(--text-card); }
.collaboration-console { padding: var(--space-3); border-radius: var(--student-console-radius); background: var(--surface); box-shadow: var(--shadow-raised); }
.console-heading { display: flex; align-items: center; gap: var(--space-1); }
.console-heading h2 { margin: 0; font-size: var(--text-card); }
.text-link { display: inline-flex; align-items: center; min-height: var(--control-height); color: var(--action); }
a:hover { background: var(--surface-hover); }
a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 1120px) { .todo-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 768px) { .todo-grid, .teaching-links { grid-template-columns: minmax(0, 1fr); } .todo-tile:first-child { grid-column: auto; } .cockpit-heading { align-items: flex-start; flex-direction: column; } }
</style>
