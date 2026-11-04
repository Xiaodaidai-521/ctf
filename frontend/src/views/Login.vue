<template>
  <div class="login-page">
    <div class="login-container">
      <header class="login-header">
        <h1 class="login-title">用户登录</h1>
        <p class="login-subtitle">欢迎回到在线学习平台</p>
      </header>

      <form class="login-form" @submit.prevent="handleLogin">
        <label class="form-group">
          <span class="form-label">用户名</span>
          <input v-model.trim="form.username" type="text" class="input" autocomplete="username" placeholder="请输入用户名" />
        </label>
        <label class="form-group">
          <span class="form-label">密码</span>
          <input v-model="form.password" type="password" class="input" autocomplete="current-password" placeholder="请输入密码" />
        </label>
        <button class="btn btn-primary btn-block btn-large" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登录' }}
        </button>
        <div class="form-footer">
          <span class="form-footer-text">还没有账号？</span>
          <router-link to="/register" class="form-footer-link">立即注册</router-link>
        </div>
      </form>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { landingFor } from '@/shared/navigation/names.js'

const userStore = useUserStore()
const router = useRouter()
const form = ref({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    error.value = '请填写用户名和密码。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await userStore.login(form.value)
    if (!result.success) {
      error.value = result.message
      return
    }
    await router.push(landingFor(userStore.userInfo?.role))
  } catch {
    error.value = '登录失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: calc(100vh - var(--header-height) - var(--nav-height)); display: grid; place-items: center; padding: var(--page-gutter); }
.login-container { width: 100%; max-width: var(--form-width); padding: var(--space-4); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.login-header { margin-bottom: var(--space-4); }
.login-title { margin-bottom: var(--space-1); font-size: var(--text-page); }
.login-subtitle, .form-footer-text { color: var(--ink-secondary); }
.form-group { display: block; margin-bottom: var(--space-3); }
.form-label { display: block; margin-bottom: var(--space-1); font-weight: var(--weight-medium); }
.btn-large { width: 100%; }
.form-footer { margin-top: var(--space-3); text-align: center; }
.form-footer-link { margin-left: var(--space-1); }
.error-message { margin: var(--space-2) 0 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--negative-soft); color: var(--negative); }
</style>
