<template>
  <header class="global-header">
    <div class="brand-group">
      <a-button v-if="staff && compact" type="text" aria-label="打开工作导航" @click="$emit('menu')"><icon-menu /></a-button>
      <router-link :to="user.isAuthenticated ? landingFor(role) : '/'" class="brand" aria-label="智航 · 网络安全学习">
        <span class="brand-mark"><icon-compass /></span><span>智航<span class="brand-caption">网络安全学习</span></span>
      </router-link>
    </div>
    <button type="button" class="search-trigger" :aria-label="role === 'admin' ? '搜索治理页面，快捷键 Ctrl K' : '搜索页面'" @click="searchOpen = true">
      <icon-search aria-hidden="true" /><span>{{ role === 'student' ? '找学习内容，或问智能体' : role === 'admin' ? '搜索治理页面' : '搜索页面' }}</span>
    </button>
    <div class="header-actions">
      <MessageCenter :key="user.userInfo?.id || role" />
      <a-dropdown v-if="user.isAuthenticated" trigger="click" @select="selectPersonal">
        <button type="button" class="personal-trigger" aria-label="个人区">
          <a-avatar class="personal-avatar">{{ user.userName.slice(0, 1) }}</a-avatar><span class="user-name">{{ user.userName }}</span><icon-down />
        </button>
        <template #content>
          <a-doption v-for="item in personalLinks.filter(item => item.roles.includes(role))" :key="item.key" :value="item.path">{{ item.label }}</a-doption>
          <a-doption value="recall-pet">{{ pet.preferences.hidden ? '重新开启智航伙伴' : '唤出智航伙伴' }}</a-doption>
          <a-doption value="logout" :disabled="loggingOut">{{ loggingOut ? '正在退出…' : '退出登录' }}</a-doption>
        </template>
      </a-dropdown>
      <router-link v-else to="/login" class="login-link">登录</router-link>
    </div>
    <a-modal v-model:visible="searchOpen" title="搜索" :footer="false" width="min(96vw, var(--search-width))" @open="searchInput?.focus()">
      <label class="search-label">{{ role === 'student' ? '输入页面名称或学习问题' : '输入页面名称' }}</label>
      <a-input ref="searchInput" v-model="query" placeholder="输入关键词" aria-label="搜索页面关键词" :input-attrs="{ 'aria-label': '搜索页面关键词' }" allow-clear @press-enter="runSearch" />
      <section v-if="role === 'admin' && !query.trim() && recent.length" class="recent-visits" aria-label="最近访问">
        <div class="recent-heading"><h3>最近访问</h3><a-button type="text" size="small" @click="recent = visits.clear()">清空</a-button></div>
        <div class="search-results">
          <router-link v-for="item in recent" :key="item.path" :to="item.path" @click="searchOpen = false"><component :is="item.icon" />{{ item.label }}<icon-arrow-right /></router-link>
        </div>
      </section>
      <div class="search-results" aria-label="页面搜索结果">
        <router-link v-for="item in results" :key="item.path" :to="item.path" @click="searchOpen = false"><component :is="item.icon" /><span>{{ item.label }}<small v-if="role === 'admin'">{{ item.group }}</small></span><icon-arrow-right /></router-link>
        <p v-if="!results.length" class="empty-search">没有找到匹配的页面。请换个关键词。</p>
        <a-button v-if="role === 'student' && query.trim()" long @click="ask">请智能体帮我学习“{{ query.trim() }}”</a-button>
      </div>
    </a-modal>
  </header>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createRecentVisits } from '../navigation/recentVisits.js'
import { useUserStore } from '@/store/user'
import { usePetStore } from '@/store/pet'
import { landingFor, personalLinks, searchEntries } from '../navigation/config.js'
import { openTutor } from '@/learning/agent/public.js'
import MessageCenter from './MessageCenter.vue'
import { clearTeachingTransfer } from '../knowledge/teachingTransfer.js'
defineProps({ compact: Boolean })
defineEmits(['menu'])
const user = useUserStore()
const pet = usePetStore()
const router = useRouter()
const route = useRoute()
let storage
try { storage = window.sessionStorage } catch { /* 受限浏览器使用内存记录。 */ }
const visits = createRecentVisits(storage)
const recent = ref([])
const role = computed(() => user.isAuthenticated ? user.userInfo?.role || 'guest' : 'guest')
const staff = computed(() => ['teacher', 'admin'].includes(role.value))
const searchOpen = ref(false)
const searchInput = ref(null)
const query = ref('')
const loggingOut = ref(false)
const results = computed(() => searchEntries(role.value, query.value))
watch(() => `${user.userInfo?.id}:${role.value}`, () => {
  clearTeachingTransfer()
  searchOpen.value = false
  query.value = ''
  recent.value = visits.account(user.userInfo?.id, role.value)
  if (role.value === 'admin') recent.value = visits.record(route.path)
}, { flush: 'sync', immediate: true })
watch(() => route.path, path => { recent.value = visits.record(path) })
function searchShortcut(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k') {
    event.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}
window.addEventListener('keydown', searchShortcut)
onBeforeUnmount(() => window.removeEventListener('keydown', searchShortcut))
async function selectPersonal(value) {
  if (value === 'recall-pet') { pet.reveal(); return }
  if (value !== 'logout') return router.push(value)
  loggingOut.value = true
  await user.logout()
  loggingOut.value = false
  await router.push('/login')
}
function ask() {
  searchOpen.value = false
  openTutor(router, { prompt: query.value, userId: user.userInfo?.id })
}
function runSearch() {
  if (results.value.length === 1) { router.push(results.value[0].path); searchOpen.value = false }
  else if (role.value === 'student' && query.value.trim()) ask()
}
</script>
<style scoped>
.global-header { min-height: var(--header-height); padding: var(--space-2) var(--page-gutter); display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); background: var(--surface); border-bottom: var(--stroke) solid var(--line); }
.brand-group, .brand, .header-actions, .personal-trigger { display: flex; align-items: center; gap: var(--space-1); }
.brand { color: var(--ink); font-size: var(--text-card); font-weight: var(--weight-strong); white-space: nowrap; }
.brand-mark { display: grid; place-items: center; width: var(--avatar-size); height: var(--avatar-size); color: var(--action); background: var(--action-soft); border-radius: var(--radius-control); font-size: var(--text-section); }
.brand-caption { margin-left: var(--space-2); font-size: var(--text-caption); font-weight: var(--weight-normal); color: var(--ink-secondary); }
.search-trigger { display: flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); width: min(var(--form-width), 40%); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface-page); color: var(--ink-secondary); cursor: pointer; text-align: left; }
.search-trigger:hover { border-color: var(--line-strong); }
.header-actions { flex-shrink: 0; gap: var(--space-2); }
.personal-trigger { border: 0; border-radius: var(--radius-control); background: transparent; color: var(--ink); min-height: var(--control-height); cursor: pointer; }
.personal-trigger:hover { background: var(--surface-muted); }
.personal-avatar { width: var(--avatar-size); height: var(--avatar-size); }
.user-name { max-width: var(--sidebar-width); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.login-link { padding: var(--space-1); }
.search-label { display: block; margin-bottom: var(--space-1); color: var(--ink-secondary); }
.search-results { display: grid; gap: var(--space-1); margin-top: var(--space-2); }
.search-results a { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); color: var(--ink); }
.search-results a svg:last-child { margin-left: auto; }
.search-results a:hover { background: var(--action-soft); }
.empty-search { padding: var(--space-2); color: var(--ink-secondary); }
.recent-visits { margin-top: var(--space-2); padding-bottom: var(--space-2); border-bottom: var(--stroke) solid var(--line); }
.recent-heading { display: flex; justify-content: space-between; align-items: center; }
.recent-heading h3 { margin: 0; font-size: var(--text-caption); color: var(--ink-secondary); }
.search-results small { display: block; font-size: var(--text-caption); color: var(--ink-muted); }
.search-results > a { min-width: 0; }
.search-results > a > span { min-width: 0; overflow-wrap: anywhere; }
.is-compact .brand-caption, .is-compact .user-name, .is-compact .search-trigger span { display: none; }
.is-compact .global-header { gap: var(--space-1); }
.is-compact .search-trigger { width: var(--control-height); justify-content: center; padding: var(--space-1); margin-left: auto; }
</style>
