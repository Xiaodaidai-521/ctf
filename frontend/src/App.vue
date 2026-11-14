<template>
  <div class="app-shell" :class="{ 'is-compact': compact }" :data-density="role">
    <a href="#page-content" class="skip-link">跳到页面内容</a>
    <GlobalHeader :compact="compact" @menu="menuOpen = true" />
    <div v-if="!staff" class="student-navigation"><RoleNavigation :role="role" /></div>
    <div class="workspace" :class="{ 'staff-workspace': staff && !compact }">
      <aside v-if="staff && !compact" class="workspace-sidebar"><RoleNavigation :role="role" /></aside>
      <a-drawer v-if="staff && compact" v-model:visible="menuOpen" title="工作导航" placement="left" :footer="false" width="var(--menu-width)">
        <RoleNavigation :role="role" @navigate="menuOpen = false" />
      </a-drawer>
      <main id="page-content" class="page-content" tabindex="-1">
        <StateRouteView :key="`${user.userInfo?.id || 'guest'}:${role}`" />
      </main>
    </div>
    <TutorDrawer v-if="role === 'student' && !examPage" :key="`drawer:${accountScope.epoch}`" />
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import StateRouteView from '@/shared/state/StateRouteView.vue'
import { accountScope, syncStateAccount } from '@/shared/state/accountScope.js'
import { useUserStore } from '@/store/user'
import GlobalHeader from '@/shared/layout/GlobalHeader.vue'
import RoleNavigation from '@/shared/layout/RoleNavigation.vue'
import TutorDrawer from '@/learning/agent/components/TutorDrawer.vue'
import { signOutAgent, syncAgentAccount } from '@/learning/agent/runtime.js'
import { breakpoints } from '@/shared/design/breakpoints.js'
const route = useRoute()
const user = useUserStore()
const role = computed(() => user.isAuthenticated ? user.userInfo?.role || 'guest' : 'guest')
const examPage = computed(() => route.path.startsWith('/exam-taking'))
// 账号切换清理本端会话；退出登录作废在途响应，旧账号数据不落入新状态。
watch(() => [user.userInfo?.id, role.value], () => {
  syncStateAccount(user.isAuthenticated ? user.userInfo : null)
}, { immediate: true, flush: 'sync' })
watch(() => accountScope.value, () => {
  signOutAgent()
  if (user.isAuthenticated) syncAgentAccount(user.userInfo?.id)
}, { immediate: true, flush: 'sync' })
const staff = computed(() => ['teacher', 'admin'].includes(role.value))
const media = window.matchMedia(`(max-width: ${breakpoints.compact}px)`)
const compact = ref(media.matches)
const menuOpen = ref(false)
const resize = () => { compact.value = media.matches; menuOpen.value = false }
media.addEventListener('change', resize)
onBeforeUnmount(() => media.removeEventListener('change', resize))
watch(() => `${user.userInfo?.id}:${role.value}`, () => { menuOpen.value = false })
</script>
<style scoped>
.app-shell { min-height: 100vh; background: var(--surface-page); }
.student-navigation { background: var(--surface); border-bottom: var(--stroke) solid var(--line); }
.workspace { min-height: calc(100vh - var(--header-height) - var(--nav-height)); }
.staff-workspace { display: grid; grid-template-columns: var(--sidebar-width) minmax(0, 1fr); min-height: calc(100vh - var(--header-height)); }
.workspace-sidebar { background: var(--surface); border-right: var(--stroke) solid var(--line); }
.page-content { min-width: 0; padding-bottom: var(--space-10); }
.skip-link { position: fixed; left: var(--space-2); top: var(--space-2); transform: translateY(-200%); padding: var(--space-1) var(--space-2); z-index: var(--z-overlay); color: var(--on-action); background: var(--action); }
.skip-link:focus { transform: none; }
</style>
