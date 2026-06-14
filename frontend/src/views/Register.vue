<template>
  <div class="register-page">
    <div class="register-container">
      <div class="register-header">
        <h1 class="register-title">用户注册</h1>
        <p class="register-subtitle">加入在线学习平台，开始你的学习之旅</p>
      </div>

      <div class="register-form">
        <div class="form-group">
          <label class="form-label">用户名 *</label>
          <input
            v-model="form.username"
            type="text"
            class="input"
            placeholder="请输入用户名"
          />
        </div>

        <div class="form-group">
          <label class="form-label">密码 *</label>
          <input
            v-model="form.password"
            type="password"
            class="input"
            placeholder="请输入密码"
          />
        </div>

        <div class="form-group">
          <label class="form-label">确认密码 *</label>
          <input
            v-model="form.password2"
            type="password"
            class="input"
            placeholder="请再次输入密码"
          />
        </div>

        <div class="form-group">
          <label class="form-label">邮箱 *</label>
          <input
            v-model="form.email"
            type="email"
            class="input"
            placeholder="请输入邮箱"
          />
        </div>

        <div class="form-group">
          <label class="form-label">昵称</label>
          <input
            v-model="form.nickname"
            type="text"
            class="input"
            placeholder="请输入昵称（可选）"
          />
        </div>

        <button
          class="btn btn-primary btn-block btn-large"
          @click="handleRegister"
          :disabled="loading"
        >
          {{ loading ? '注册中...' : '注册' }}
        </button>

        <div class="form-footer">
          <span class="form-footer-text">已有账号？</span>
          <router-link to="/login" class="form-footer-link">立即登录</router-link>
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
  password: '',
  password2: '',
  email: '',
  nickname: '',
})

const loading = ref(false)
const error = ref('')

const handleRegister = async () => {
  if (!form.value.username || !form.value.password || !form.value.email) {
    error.value = '请填写必填项'
    return
  }

  if (form.value.password !== form.value.password2) {
    error.value = '两次输入的密码不一致'
    return
  }

  loading.value = true
  error.value = ''

  try {
    const result = await userStore.register(form.value)
    if (result.success) {
      router.push('/profile/setup')
    } else {
      error.value = result.message
    }
  } catch (err) {
    error.value = '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.register-container {
  width: 100%;
  max-width: 450px;
  background: white;
  padding: 40px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.register-header {
  text-align: center;
  margin-bottom: 32px;
}

.register-title {
  font-size: 24px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.register-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
}

.register-form {
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.role-selector {
  display: flex;
  gap: 12px;
}

.role-btn {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid var(--border-color);
  border-radius: 8px;
  background: white;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.role-btn:hover {
  border-color: #1890ff;
  background: #f5f5f5;
}

.role-btn.active {
  border-color: #1890ff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.role-icon {
  font-size: 24px;
}

.role-text {
  font-size: 13px;
  font-weight: 500;
}

.btn-large {
  padding: 12px 24px;
  font-size: 16px;
  margin-top: 8px;
}

.form-footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.form-footer-text {
  color: var(--text-secondary);
  font-size: 14px;
  margin-right: 6px;
}

.form-footer-link {
  color: #1890ff;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
}

.form-footer-link:hover {
  text-decoration: underline;
}

.error-message {
  padding: 12px 16px;
  background: #fee;
  border: 1px solid #fcc;
  border-radius: 8px;
  color: #c33;
  font-size: 14px;
  margin-top: 16px;
}

.input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.3s;
}

.input:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.btn {
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.btn-block {
  width: 100%;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.input-number-wide {
  width: 100%;
}
</style>
