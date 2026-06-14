<template>
  <div class="admin-layout">
    <!-- 移动端遮罩层 -->
    <div v-if="sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false"></div>

    <!-- 侧边栏 -->
    <aside class="admin-sidebar" :class="{ open: sidebarOpen }">
      <div class="sidebar-logo">
        <div class="sidebar-logo-icon">EDU</div>
        <span>管理后台</span>
      </div>
      <nav class="sidebar-menu">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="menu-item"
          :class="{ active: $route.path === item.path }"
        >
          <span class="menu-icon">{{ item.icon }}</span>
          <span>{{ item.title }}</span>
        </router-link>
      </nav>
    </aside>

    <!-- 主内容区 -->
    <main class="admin-main">
      <!-- 顶部栏 -->
      <header class="admin-header">
        <div class="header-left">
          <button class="header-action" @click="toggleSidebar">
            ☰
          </button>
          <h1 class="header-title">{{ pageTitle }}</h1>
        </div>

        <div class="header-right">
          <button class="header-action" @click="goBackToFront">🏠 返回前台</button>
          <button class="header-action" @click="handleRefresh">
            🔄
          </button>
          <button class="header-action" @click="handleLogout">
            🚪 退出
          </button>
          <div class="user-dropdown" @click="goToProfile">
            <div class="admin-avatar">{{ userStore.userName.charAt(0) }}</div>
            <div class="user-info">
              <span class="user-name">{{ userStore.userName }}</span>
              <span class="user-role">管理员</span>
            </div>
          </div>
        </div>
      </header>

      <!-- 内容区 -->
      <div class="admin-content">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const sidebarOpen = ref(false)

const menuItems = [
  {
    path: '/admin/dashboard',
    title: '仪表盘',
    icon: '📊'
  },
  {
    path: '/admin/student-learning',
    title: '用户学习报表',
    icon: '📋'
  },
  {
    path: '/admin/learning-scores',
    title: '动态评分管理',
    icon: '📈'
  },
  {
    path: '/admin/users',
    title: '用户管理',
    icon: '👥'
  },
  {
    path: '/admin/challenges',
    title: '题目管理',
    icon: '📝'
  },
  {
    path: '/admin/submissions',
    title: '提交记录',
    icon: '📋'
  },
  {
    path: '/admin/categories',
    title: '分类管理',
    icon: '🏷️'
  },
  {
    path: '/admin/resources',
    title: '资源审核',
    icon: '📦'
  },
  {
    path: '/admin/articles',
    title: '文章审核',
    icon: '📰'
  },
  {
    path: '/admin/announcements',
    title: '公告管理',
    icon: '📢'
  }
]

const pageTitle = computed(() => {
  const item = menuItems.find(i => route.path.startsWith(i.path))
  return item ? item.title : '管理后台'
})

const toggleSidebar = () => {
  sidebarOpen.value = !sidebarOpen.value
}

const handleRefresh = () => {
  window.location.reload()
}

const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}

const goToProfile = () => {
  router.push('/profile')
}

const goBackToFront = () => {
  router.push('/')
}

onMounted(() => {
  // 检查管理员权限
  if (userStore.userInfo?.role !== 'admin') {
    router.push('/')
  }
})
</script>

<style scoped>
@import '../assets/admin.css';
</style>
