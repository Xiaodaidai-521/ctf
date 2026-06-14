<template>
  <nav class="navbar">
    <div class="navbar-left">
      <div class="navbar-brand">
        <router-link to="/" class="brand-logo">EDU</router-link>
      </div>
      <div class="navbar-menu">
        <router-link to="/" class="nav-item" active-class="active">
          首页
        </router-link>
        <router-link to="/challenges" class="nav-item" active-class="active">
          题库练习
        </router-link>
        <router-link to="/dashboard" class="nav-item" active-class="active" v-if="userStore.isAuthenticated">
          学习看板
        </router-link>
        <router-link to="/multi-agent?mode=learning" class="nav-item" active-class="active">
          学习中心
        </router-link>
        <router-link to="/learning-paths" class="nav-item" active-class="active">
          学习路径
        </router-link>
        <router-link to="/resources" class="nav-item" active-class="active">
          资源中心
        </router-link>
        <router-link to="/community" class="nav-item" active-class="active">
          社区
        </router-link>
        <router-link to="/exam-center" class="nav-item" active-class="active">
          测试中心
        </router-link>
        <router-link v-if="userStore.userInfo?.role === 'teacher' || userStore.userInfo?.role === 'admin'" to="/admin/dashboard" class="nav-item" active-class="active">
          管理中心
        </router-link>
      </div>
    </div>

    <div class="navbar-right">
      <div v-if="userStore.isAuthenticated" class="user-menu">
        <div class="user-avatar-container" @click="toggleUserDropdown">
          <img
            v-if="userStore.userInfo?.avatar_url"
            :src="userStore.userInfo.avatar_url"
            class="user-avatar-img"
            alt="用户头像"
          />
          <div v-else class="user-avatar-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="role-badge" :class="'role-' + userStore.userInfo?.role">
            {{ getRoleText(userStore.userInfo?.role) }}
          </div>
        </div>

        <div class="user-dropdown" :class="{ show: showUserDropdown }">
          <div class="dropdown-header">
            <div class="dropdown-avatar">
              <img
                v-if="userStore.userInfo?.avatar_url"
                :src="userStore.userInfo.avatar_url"
                class="dropdown-avatar-img"
                alt="用户头像"
              />
              <div v-else class="dropdown-avatar-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
                  <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  <circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
            <div class="dropdown-info">
              <div class="dropdown-name">{{ userStore.userName }}</div>
              <div class="dropdown-role">{{ getRoleText(userStore.userInfo?.role) }}</div>
              <div class="dropdown-score">积分: {{ userStore.userInfo?.score || 0 }}</div>
            </div>
          </div>
          <div class="dropdown-divider"></div>
          <div class="dropdown-menu">
            <router-link to="/dashboard" class="dropdown-item">
              <span class="dropdown-icon">📊</span>
              <span>学习看板</span>
            </router-link>
            <router-link to="/profile" class="dropdown-item">
              <span class="dropdown-icon">👤</span>
              <span>个人中心</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role !== 'admin'" to="/analytics" class="dropdown-item">
              <span class="dropdown-icon">📈</span>
              <span>学习分析</span>
            </router-link>
            <router-link to="/multi-agent?mode=learning" class="dropdown-item">
              <span class="dropdown-icon">🧠</span>
              <span>学习中心</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'admin'" to="/learning-paths/manage" class="dropdown-item">
              <span class="dropdown-icon">🎯</span>
              <span>学习路径管理</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'teacher'" to="/learning-paths/manage" class="dropdown-item">
              <span class="dropdown-icon">🎯</span>
              <span>学习路径管理</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'admin'" to="/admin/dashboard" class="dropdown-item">
              <span class="dropdown-icon">⚙️</span>
              <span>管理后台</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'teacher'" to="/admin/dashboard" class="dropdown-item">
              <span class="dropdown-icon">📚</span>
              <span>教师中心</span>
            </router-link>
            <div class="dropdown-divider"></div>
            <button @click="handleLogout" class="dropdown-item dropdown-item-danger">
              <span class="dropdown-icon">🚪</span>
              <span>退出登录</span>
            </button>
          </div>
        </div>
      </div>
      <div v-else class="auth-buttons">
        <router-link to="/login" class="btn btn-outline">登录</router-link>
        <router-link to="/register" class="btn btn-outline">注册</router-link>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { ref } from 'vue'
import { useUserStore } from '@/store/user'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()

const showUserDropdown = ref(false)

const getRoleText = (role) => {
  const map = {
    'student': '用户',
    'teacher': '教师',
    'admin': '管理员'
  }
  return map[role] || '用户'
}

const toggleUserDropdown = () => {
  showUserDropdown.value = !showUserDropdown.value
}

const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}

// 点击外部关闭下拉菜单
document.addEventListener('click', (e) => {
  if (!e.target.closest('.user-menu')) {
    showUserDropdown.value = false
  }
})
</script>

<style scoped>
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 64px;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0;
}

.navbar-left {
  display: flex;
  align-items: center;
  padding-left: 24px;
  gap: 40px;
}

.navbar-brand {
  display: block;
}

.brand-logo {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-primary);
  text-decoration: none;
}

.navbar-menu {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.nav-item {
  padding: 10px 20px;
  color: var(--color-text-1);
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.3s;
  font-size: 14px;
  font-weight: 500;
}

.nav-item:hover {
  color: var(--color-primary);
  background: var(--color-fill-1);
}

.nav-item.active {
  color: var(--color-primary);
  background: var(--color-primary-light-1);
}

.nav-item.highlight {
  background: linear-gradient(135deg, rgb(var(--primary-6)) 0%, rgb(var(--purple-6)) 100%);
  color: #fff;
  font-weight: 600;
}

.nav-item.highlight:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(var(--primary-6), 0.3);
}

.nav-item.highlight.active {
  background: linear-gradient(135deg, rgb(var(--primary-6)) 0%, rgb(var(--purple-6)) 100%);
  box-shadow: 0 4px 12px rgba(var(--primary-6), 0.3);
}

.navbar-right {
  display: flex;
  align-items: center;
  padding-right: 24px;
}

.user-menu {
  position: relative;
}

.user-avatar-container {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 20px;
  transition: background 0.3s;
}

.user-avatar-container:hover {
  background: var(--color-fill-1);
}

.user-avatar-img {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}

.user-avatar-empty {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-fill-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-2);
}

.role-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}

.role-student {
  background: #e6f7ff;
  color: #1890ff;
}

.role-teacher {
  background: #fff7e6;
  color: #faad14;
}

.role-admin {
  background: #fff1f0;
  color: #ff4d4f;
}

.user-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  width: 280px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  opacity: 0;
  visibility: hidden;
  transform: translateY(-8px);
  transition: all 0.2s ease;
}

.user-dropdown.show {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

.dropdown-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  border-bottom: 1px solid var(--color-border);
}

.dropdown-avatar-img {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
}

.dropdown-avatar-empty {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-fill-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-2);
}

.dropdown-info {
  flex: 1;
}

.dropdown-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-1);
  margin-bottom: 4px;
}

.dropdown-role {
  font-size: 14px;
  color: var(--color-text-2);
  margin-bottom: 2px;
}

.dropdown-score {
  font-size: 12px;
  color: var(--color-text-3);
}

.dropdown-divider {
  height: 1px;
  background: var(--color-border);
}

.dropdown-menu {
  padding: 8px 0;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  color: var(--color-text-1);
  text-decoration: none;
  transition: background 0.2s;
  border: none;
  background: none;
  width: 100%;
  text-align: left;
  cursor: pointer;
  font-size: 14px;
}

.dropdown-item:hover {
  background: var(--color-fill-1);
}

.dropdown-item-danger {
  color: var(--color-error);
}

.dropdown-item-danger:hover {
  background: #fff1f0;
}

.dropdown-icon {
  font-size: 16px;
}

.auth-buttons {
  display: flex;
  gap: 12px;
}

.btn {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  text-decoration: none;
  display: inline-block;
}

.btn-outline {
  background: var(--color-bg-light);
  border: 1px solid var(--color-border);
  color: var(--color-text-1);
}

.btn-outline:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: #40a9ff;
}
</style>
