<template>
  <div class="register-page">
    <div class="register-container">
      <div v-if="!applicationSubmitted">
        <div class="register-header"><h1 class="register-title">创建账号</h1><p class="register-subtitle">加入平台，开启学习旅程。</p></div>
        <div class="register-form">
          <div class="form-group"><label class="form-label">账号类型 *</label><div class="role-selector"><button type="button" class="role-btn" :class="{ active: form.role === 'student' }" @click="form.role = 'student'">学生</button><button type="button" class="role-btn" :class="{ active: form.role === 'teacher' }" @click="form.role = 'teacher'">教师</button></div><p v-if="form.role === 'teacher'" class="approval-notice">教师注册需要管理员审核，通过后方可使用教师功能。</p></div>
          <div class="form-group"><label class="form-label">用户名 *</label><input v-model="form.username" type="text" class="input" placeholder="请输入用户名" /></div>
          <div class="form-group"><label class="form-label">密码 *</label><input v-model="form.password" type="password" class="input" placeholder="请输入密码" /></div>
          <div class="form-group"><label class="form-label">确认密码 *</label><input v-model="form.password2" type="password" class="input" placeholder="请再次输入密码" /></div>
          <div class="form-group"><label class="form-label">邮箱 *</label><input v-model="form.email" type="email" class="input" placeholder="请输入邮箱" /></div>
          <div class="form-group"><label class="form-label">昵称</label><input v-model="form.nickname" type="text" class="input" placeholder="选填" /></div>
          <button class="btn btn-primary btn-block btn-large" @click="handleRegister" :disabled="loading">{{ loading ? '提交中…' : form.role === 'teacher' ? '提交教师申请' : '注册' }}</button>
          <div class="form-footer"><span class="form-footer-text">已有账号？</span><router-link to="/login" class="form-footer-link">登录</router-link></div>
        </div>
        <div v-if="error" class="error-message">{{ error }}</div>
      </div>
      <div v-else class="pending-state"><div class="pending-icon"><AppIcon aria-hidden="true" name="bi-clock" /></div><h1 class="register-title">申请已提交</h1><p class="register-subtitle">你的教师申请正在等待管理员审核。</p><p class="pending-detail">审核通过后才能以教师身份登录。</p><router-link to="/login" class="btn btn-primary btn-block btn-large">返回登录</router-link></div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useUserStore } from '@/store/user'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()
const form = ref({ username: '', password: '', password2: '', email: '', nickname: '', role: 'student' })
const loading = ref(false)
const error = ref('')
const applicationSubmitted = ref(false)

const handleRegister = async () => {
  if (!form.value.username || !form.value.password || !form.value.email) { error.value = '请填写所有必填项。'; return }
  if (form.value.password !== form.value.password2) { error.value = '两次输入的密码不一致。'; return }
  loading.value = true
  error.value = ''
  try {
    const result = await userStore.register(form.value)
    if (!result.success) error.value = result.message
    else if (result.pendingApproval) applicationSubmitted.value = true
    else router.push('/profile/setup')
  } catch { error.value = '注册失败，请重试。' }
  finally { loading.value = false }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-3) var(--page-gutter);
  background: var(--surface-page);
  color: var(--ink);
  font-family: var(--font-family);
  font-size: var(--text-body);
  line-height: var(--leading-body);
}

.register-container {
  box-sizing: border-box;
  width: 100%;
  max-width: var(--form-width);
  padding: var(--space-5);
  background: var(--surface);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-panel);
}

.register-header, .pending-state { text-align: center; }
.register-header { margin-bottom: var(--space-4); }
.register-title { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); font-weight: var(--weight-strong); }
.register-subtitle, .pending-detail { color: var(--ink-secondary); }
.register-subtitle { margin: 0; }
.form-group { margin-bottom: var(--space-2); }
.form-label { display: block; margin-bottom: var(--space-1); font-size: var(--text-caption); font-weight: var(--weight-medium); }
.role-selector { display: flex; gap: var(--space-2); }
.role-btn { flex: 1; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); cursor: pointer; font: inherit; font-weight: var(--weight-medium); }
.role-btn:hover { background: var(--surface-hover); }
.role-btn.active { border-color: var(--action); background: var(--action-soft); color: var(--action); }
.approval-notice { margin: var(--space-2) 0 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.input { box-sizing: border-box; width: 100%; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; }
.input::placeholder { color: var(--ink-muted); }
.input:hover { border-color: var(--line-strong); }
.input:focus { border-color: var(--action); }
.btn { box-sizing: border-box; min-height: var(--control-height); border: var(--stroke) solid transparent; border-radius: var(--radius-control); padding: var(--space-1) var(--space-3); font: inherit; font-weight: var(--weight-medium); cursor: pointer; text-align: center; text-decoration: none; }
.btn-primary { background: var(--action); color: var(--on-action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); }
.btn-primary:active:not(:disabled) { background: var(--action-pressed); }
.btn-block { display: block; width: 100%; }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.form-footer { display: flex; justify-content: center; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-3); padding-top: var(--space-2); border-top: var(--stroke) solid var(--line); font-size: var(--text-caption); }
.form-footer-text { color: var(--ink-secondary); }
.form-footer-link { color: var(--action); font-weight: var(--weight-medium); text-decoration: none; }
.form-footer-link:hover { color: var(--action-hover); text-decoration: underline; }
.error-message { margin-top: var(--space-2); padding: var(--space-2); border: var(--stroke) solid var(--negative); border-radius: var(--radius-control); background: var(--negative-soft); color: var(--negative); font-size: var(--text-caption); }
.pending-state { padding: var(--space-3) 0; }
.pending-icon { display: grid; place-items: center; width: var(--space-8); height: var(--space-8); margin: 0 auto var(--space-3); border-radius: var(--radius-pill); background: var(--surface-muted); font-size: var(--text-page); }
.pending-detail { margin: var(--space-2) 0 var(--space-3); }
.role-btn, .input, .btn, .form-footer-link { transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease); }
.register-page :is(button, input, a):focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }

@media (max-width: 768px) {
  .register-container { padding: var(--space-3); }
}
</style>
