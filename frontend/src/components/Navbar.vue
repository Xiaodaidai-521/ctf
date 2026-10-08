<template>
  <nav class="navbar">
    <div class="navbar-left">
      <div class="navbar-brand">
        <router-link to="/" class="brand-logo">
          <span class="brand-mark"><i class="bi bi-shield-lock"></i></span>
          <span>SECURITY LEARNING</span>
        </router-link>
      </div>
      <div class="navbar-menu">
        <router-link to="/" class="nav-item" active-class="active">
          首页
        </router-link>
        <router-link to="/challenges" class="nav-item" active-class="active">
          题库练习
        </router-link>
        <router-link v-if="userStore.userInfo?.role !== 'teacher' && userStore.userInfo?.role !== 'admin'" to="/multi-agent?mode=learning" class="nav-item" active-class="active">
          智能辅导
        </router-link>
        <router-link to="/resources" class="nav-item" active-class="active">
          资源中心
        </router-link>
        <router-link to="/community" class="nav-item" active-class="active">
          社区
        </router-link>
        <router-link v-if="userStore.userInfo?.role !== 'teacher'" to="/exam-center" class="nav-item" active-class="active">
          测试中心
        </router-link>
        <router-link v-if="userStore.userInfo?.role === 'teacher'" to="/teacher" class="nav-item" active-class="active">
          教师中心
        </router-link>
        <router-link v-if="userStore.userInfo?.role === 'admin'" to="/admin/dashboard" class="nav-item" active-class="active">
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
            <router-link v-if="userStore.userInfo?.role !== 'teacher'" to="/dashboard" class="dropdown-item">
              <span class="dropdown-icon">📊</span>
              <span>学习看板</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role !== 'teacher'" to="/profile" class="dropdown-item">
              <span class="dropdown-icon">👤</span>
              <span>个人中心</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role !== 'teacher'" to="/analytics" class="dropdown-item">
              <span class="dropdown-icon">📈</span>
              <span>学习分析</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role !== 'teacher' && userStore.userInfo?.role !== 'admin'" to="/multi-agent?mode=learning" class="dropdown-item">
              <span class="dropdown-icon">🧠</span>
              <span>智能辅导</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'admin'" to="/learning-paths/manage" class="dropdown-item">
              <span class="dropdown-icon">🎯</span>
              <span>学习路径管理</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'admin'" to="/admin/dashboard" class="dropdown-item">
              <span class="dropdown-icon">⚙️</span>
              <span>管理后台</span>
            </router-link>
            <router-link v-if="userStore.userInfo?.role === 'teacher'" to="/teacher" class="dropdown-item">
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
  background: rgba(250, 247, 240, 0.92);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border-color);
  box-shadow: none;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
}

.navbar-left {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 28px;
}

.navbar-brand {
  display: block;
}

.brand-logo {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 950;
  text-decoration: none;
  white-space: nowrap;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--text-primary);
  border-radius: 50%;
  color: var(--primary-color);
  background: rgba(255, 250, 242, 0.6);
}

.navbar-menu {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: none;
}

.navbar-menu::-webkit-scrollbar {
  display: none;
}

.nav-item {
  padding: 8px 12px;
  color: var(--text-secondary);
  text-decoration: none;
  border-radius: 4px;
  transition: all 0.2s ease;
  font-size: 14px;
  font-weight: 850;
  white-space: nowrap;
}

.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-paper-2);
}

.nav-item.active {
  color: var(--text-primary);
  background: var(--bg-paper-2);
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
  flex-shrink: 0;
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
  border-radius: 4px;
  border: 1px solid transparent;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.user-avatar-container:hover {
  background: var(--bg-paper-2);
  border-color: var(--border-color);
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
  background: var(--bg-paper-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-2);
}

.role-badge {
  padding: 2px 8px;
  border-radius: 2px;
  font-size: 12px;
  font-weight: 850;
}

.role-student {
  background: rgba(183, 53, 45, 0.1);
  color: var(--primary-color);
}

.role-teacher {
  background: rgba(239, 196, 107, 0.35);
  color: #785313;
}

.role-admin {
  background: var(--text-primary);
  color: #fbf7ef;
}

.user-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  width: 280px;
  background: rgba(255, 250, 242, 0.98);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 10px 10px 0 rgba(24, 23, 19, 0.1);
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
  border-bottom: 1px solid var(--border-color);
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
  background: var(--bg-paper-2);
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
  color: var(--text-primary);
  margin-bottom: 4px;
}

.dropdown-role {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 2px;
}

.dropdown-score {
  font-size: 12px;
  color: var(--text-muted);
}

.dropdown-divider {
  height: 1px;
  background: var(--border-color);
}

.dropdown-menu {
  padding: 8px 0;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  color: var(--text-primary);
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
  background: var(--bg-paper-2);
}

.dropdown-item-danger {
  color: var(--error-color);
}

.dropdown-item-danger:hover {
  background: rgba(183, 53, 45, 0.1);
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
  border-radius: 4px;
  font-size: 14px;
  font-weight: 850;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  text-decoration: none;
  display: inline-block;
}

.btn-outline {
  background: rgba(255, 250, 242, 0.68);
  border: 1px solid var(--text-primary);
  color: var(--text-primary);
}

.btn-outline:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.btn-primary {
  background: var(--text-primary);
  color: #fbf7ef;
}

.btn-primary:hover {
  background: #2a2823;
}

@media (max-width: 980px) {
  .navbar {
    padding: 0 16px;
  }

  .navbar-left {
    gap: 16px;
  }

  .brand-logo span:last-child {
    display: none;
  }
}

@media (max-width: 720px) {
  .navbar-menu {
    max-width: calc(100vw - 152px);
  }

  .auth-buttons {
    gap: 8px;
  }

  .btn {
    padding: 7px 12px;
  }
}
</style>
