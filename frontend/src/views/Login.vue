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
    await router.push(userStore.userInfo?.role === 'teacher' ? '/teacher' : '/')
  } catch {
    error.value = '登录失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:linear-gradient(90deg,rgba(24,23,19,.045) 1px,transparent 1px) 0 0/44px 44px,linear-gradient(180deg,#faf7f0 0%,var(--bg-paper) 100%)}.login-container{width:100%;max-width:400px;padding:40px;border:1px solid var(--border-color);border-radius:var(--radius-lg);background:rgba(255,250,242,.86);box-shadow:14px 14px 0 var(--bg-paper-2)}.login-header{text-align:center;margin-bottom:32px}.login-title{margin:0 0 8px;font-size:32px;line-height:1.05;font-weight:950;color:var(--text-primary)}.login-subtitle{margin:0;color:var(--text-secondary);font-size:14px}.login-form{margin-bottom:24px}.form-group{display:block;margin-bottom:20px}.form-label{display:block;margin-bottom:8px;color:var(--text-primary);font-size:14px;font-weight:850}.btn-large{width:100%;margin-top:8px;padding:12px 24px;font-size:16px}.form-footer{margin-top:24px;padding-top:20px;border-top:1px solid #e8dfd2;text-align:center}.form-footer-text{color:var(--text-secondary);font-size:14px}.form-footer-link{margin-left:4px;color:var(--primary-color);font-size:14px;font-weight:850;text-decoration:none}.form-footer-link:hover{color:#8e2721}.error-message{margin:0;padding:12px;border:1px solid rgba(183,53,45,.28);border-radius:var(--radius-sm);background:rgba(183,53,45,.1);color:var(--error-color);font-size:14px;text-align:center}
</style>
