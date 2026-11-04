<template>
  <section v-if="allowed" class="foundation-domain" data-density="admin">
    <nav class="foundation-nav" aria-label="基座治理"><router-link v-for="item in entries" :key="item.key" :to="item.path" :aria-current="current === item.key ? 'page' : undefined">{{ item.label }}</router-link></nav>
    <slot />
  </section>
  <p v-else class="governance-page" role="alert">基座治理仅供管理员使用。教师请从知识基座进入，学生请使用任务内的资料入口。</p>
</template>
<script setup>
import { computed } from 'vue'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names.js'
defineProps({ current: { type: String, required: true } })
const user = useUserStore()
const allowed = computed(() => user.isAuthenticated && user.userInfo?.role === 'admin')
const entries = [
  { key: 'library', path: '/admin/legal/kb', label: '资料库' },
  { key: 'tools', path: '/admin/legal/kb/tools', label: names.indexTools },
  { key: 'health', path: '/admin/legal/kb/health', label: names.indexHealth },
  { key: 'authorization', path: '/admin/legal/kb/authorization', label: names.authorizationSupervision },
]
</script>
<style scoped>
.foundation-nav { display: flex; flex-wrap: wrap; gap: var(--density-gap); max-width: var(--page-width); margin: var(--space-2) auto 0; padding-inline: var(--page-gutter); }
.foundation-nav a { display: inline-flex; align-items: center; min-height: var(--control-height); padding: var(--space-1) var(--space-2); color: var(--ink-secondary); text-decoration: none; border-radius: var(--radius-control); }
.foundation-nav a[aria-current='page'] { background: var(--action-soft); color: var(--action); font-weight: var(--weight-strong); }
.foundation-nav a:hover { background: var(--surface-hover); }
.foundation-nav a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
