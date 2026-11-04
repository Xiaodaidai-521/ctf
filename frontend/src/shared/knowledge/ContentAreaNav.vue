<template>
  <nav class="content-area" aria-label="内容与资料">
    <router-link v-for="item in items" :key="item.path" :to="item.path" :aria-current="route.path === item.path ? 'page' : undefined">
      <strong>{{ item.label }}</strong><span>{{ item.description }}</span>
    </router-link>
  </nav>
</template>
<script setup>
import { useRoute } from 'vue-router'
import { names } from '@/shared/navigation/names.js'
const route = useRoute()
const items = [
  { path: '/teacher/resources', label: names.resourceReview, description: '把关给学生使用的成品' },
  { path: '/teacher/knowledge', label: names.knowledge, description: '查原文、核出处，资料只在这里入库' },
  { path: '/teacher/materials', label: names.materials, description: '生产、审阅与发布教学材料' },
]
</script>
<style scoped>
.content-area { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--density-gap); margin-bottom: var(--space-3); }
.content-area a { display: grid; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink); text-decoration: none; }
.content-area a[aria-current] { background: var(--action-soft); }
.content-area a:hover { background: var(--surface-hover); }
.content-area span { color: var(--ink-secondary); font-size: var(--text-caption); }
.content-area a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 768px) { .content-area { grid-template-columns: minmax(0, 1fr); } }
</style>
