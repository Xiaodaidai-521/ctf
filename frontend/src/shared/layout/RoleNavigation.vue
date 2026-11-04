<template>
  <nav class="role-navigation" :class="{ 'is-student': isStudent }" :aria-label="isStudent ? '学习导航' : '工作导航'">
    <div v-for="group in groupsFor(role)" :key="group.label" class="nav-group">
      <p v-if="!isStudent" class="group-label">{{ group.label }}</p>
      <router-link v-for="item in group.items" :key="item.key" :to="item.path" class="role-link"
        :aria-current="activeEntry(role, route.path) === item.key ? 'page' : undefined" @click="$emit('navigate')">
        <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span>
      </router-link>
    </div>
    <router-link v-if="isStudent" to="/exam-center" class="exam-link" :aria-current="route.path.startsWith('/exam-') ? 'page' : undefined">
      <icon-trophy aria-hidden="true" /> {{ names.exams }}<span class="exam-caption">正式测评</span>
    </router-link>
  </nav>
</template>
<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { groupsFor, activeEntry } from '../navigation/config.js'
import { names } from '../navigation/names.js'
const props = defineProps({ role: { type: String, default: 'guest' } })
defineEmits(['navigate'])
const route = useRoute()
const isStudent = computed(() => !['teacher', 'admin'].includes(props.role))
</script>
<style scoped>
.role-navigation { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-2); }
.nav-group { display: flex; flex-direction: column; gap: var(--space-1); }
.group-label { margin: 0; padding-inline: var(--space-2); font-size: var(--text-caption); color: var(--ink-muted); }
.role-link, .exam-link { display: flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); color: var(--ink-secondary); border-radius: var(--radius-control); font-weight: var(--weight-medium); white-space: nowrap; }
.role-link svg, .exam-link svg { font-size: var(--icon-size); }
.role-link:hover, .exam-link:hover { background: var(--surface-hover); color: var(--ink); }
[aria-current='page'] { background: var(--action-soft); color: var(--action); }
.is-student { flex-direction: row; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-1) var(--page-gutter); min-height: var(--nav-height); max-width: var(--page-width); margin-inline: auto; overflow-x: auto; }
.is-student .nav-group { flex-direction: row; gap: var(--space-1); }
.exam-link { border-left: var(--stroke) solid var(--line); border-radius: 0; }
.exam-caption { font-size: var(--text-caption); color: var(--ink-muted); }
.is-compact .is-student { flex-direction: column; align-items: stretch; gap: 0; }
.is-compact .is-student .nav-group { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.is-compact .is-student .role-link { justify-content: center; padding-inline: var(--space-1); }
.is-compact .is-student .role-link svg { display: none; }
.is-compact .exam-link { align-self: flex-end; border-left: 0; }
</style>
