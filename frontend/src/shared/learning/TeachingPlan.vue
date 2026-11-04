<template>
  <section class="teaching-plan">
    <h2>个性化教学方案</h2>
    <p v-if="loading" role="status">正在读取教学方案…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!plan">暂无教学方案。</p>
    <template v-else>
      <p>{{ readable(plan.validity_label) || '方案依据暂未返回。' }}</p>
      <h3 v-if="plan.title">{{ readable(plan.title) }}</h3>
      <p>{{ readable(plan.summary) || '方案摘要暂未返回。' }}</p>
      <ol><li v-for="(item, index) in items" :key="index"><strong>{{ item.phase }} · {{ readable(item.title) }}</strong><span>{{ item.duration || '时长待定' }}</span><ul><li v-for="(action, i) in item.actions || []" :key="i">{{ readable(action) }}</li></ul></li></ol>
      <p class="note">方案是教学安排建议，不代表已完成练习或已掌握。</p>
    </template>
  </section>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ plan: { type: Object, default: null }, loading: Boolean, error: { type: String, default: '' } })
const items = computed(() => Array.isArray(props.plan?.plan_items) ? props.plan.plan_items : [])
const readable = value => typeof value === 'string' ? value.replaceAll('管理员评分', '教师评分').replaceAll('管理员备注', '教师备注').replaceAll('用户自评', '学生自评') : ''
</script>
<style scoped>
h2 { margin: 0 0 var(--space-2); font-size: var(--text-card); }
h3 { font-size: var(--text-card); }
p, span, ul, .note { color: var(--ink-secondary); }
ol { display: grid; gap: var(--space-2); padding-left: var(--space-3); }
ol > li { padding-left: var(--space-1); }
span { display: block; font-size: var(--text-caption); }
</style>
