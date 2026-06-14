<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <h1 class="login-title">用户登录</h1>
        <p class="login-subtitle">欢迎回到在线学习平台</p>
      </div>

      <div class="login-form">
        <div class="form-group">
          <label class="form-label">用户名</label>
          <input
            v-model="form.username"
            type="text"
            class="input"
            placeholder="请输入用户名"
            @keyup.enter="handleLogin"
          />
        </div>

        <div class="form-group">
          <label class="form-label">密码</label>
          <input
            v-model="form.password"
            type="password"
            class="input"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </div>

        <button
          class="btn btn-primary btn-block btn-large"
          @click="handleLogin"
          :disabled="loading"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>

        <div class="form-footer">
          <span class="form-footer-text">还没有账号？</span>
          <router-link to="/register" class="form-footer-link">立即注册</router-link>
        </div>
      </div>

      <div v-if="error" class="error-message">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useUserStore } from '@/store/user'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()

const form = ref({
  username: '',
  password: ''
})

const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  console.log('点击登录按钮', form.value)
  if (!form.value.username || !form.value.password) {
    error.value = '请填写用户名和密码'
    return
  }

  loading.value = true
  error.value = ''

  try {
    console.log('调用userStore.login')
    const result = await userStore.login(form.value)
    console.log('登录结果:', result)
    if (result.success) {
      console.log('准备跳转到首页')
      await router.push('/')
      console.log('跳转完成')
    } else {
      error.value = result.message
    }
  } catch (err) {
    console.error('登录异常:', err)
    error.value = '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-container {
  width: 100%;
  max-width: 400px;
  background: white;
  padding: 40px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-title {
  font-size: 24px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
}

.login-form {
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.btn-large {
  padding: 12px 24px;
  font-size: 16px;
  margin-top: 8px;
  width: 100%;
}

.form-footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.form-footer-text {
  color: var(--text-secondary);
  font-size: 14px;
}

.form-footer-link {
  color: #1890ff;
  font-size: 14px;
  margin-left: 4px;
  text-decoration: none;
  transition: color 0.3s;
  font-weight: 500;
}

.form-footer-link:hover {
  color: #40a9ff;
}

.error-message {
  padding: 12px;
  background: #fff2f0;
  border: 1px solid #ffccc7;
  color: #ff4d4f;
  border-radius: var(--radius-sm);
  font-size: 14px;
  text-align: center;
  margin-bottom: 16px;
}
</style>
