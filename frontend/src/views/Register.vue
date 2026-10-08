<template>
  <div class="register-page">
    <div class="register-container">
      <div v-if="!applicationSubmitted">
        <div class="register-header"><h1 class="register-title">Create an account</h1><p class="register-subtitle">Join the learning platform.</p></div>
        <div class="register-form">
          <div class="form-group"><label class="form-label">Account type *</label><div class="role-selector"><button type="button" class="role-btn" :class="{ active: form.role === 'student' }" @click="form.role = 'student'">Student</button><button type="button" class="role-btn" :class="{ active: form.role === 'teacher' }" @click="form.role = 'teacher'">Teacher</button></div><p v-if="form.role === 'teacher'" class="approval-notice">Teacher registrations require administrator approval. You can use teacher features only after approval.</p></div>
          <div class="form-group"><label class="form-label">Username *</label><input v-model="form.username" type="text" class="input" placeholder="Enter username" /></div>
          <div class="form-group"><label class="form-label">Password *</label><input v-model="form.password" type="password" class="input" placeholder="Enter password" /></div>
          <div class="form-group"><label class="form-label">Confirm password *</label><input v-model="form.password2" type="password" class="input" placeholder="Enter password again" /></div>
          <div class="form-group"><label class="form-label">Email *</label><input v-model="form.email" type="email" class="input" placeholder="Enter email" /></div>
          <div class="form-group"><label class="form-label">Display name</label><input v-model="form.nickname" type="text" class="input" placeholder="Optional" /></div>
          <button class="btn btn-primary btn-block btn-large" @click="handleRegister" :disabled="loading">{{ loading ? 'Submitting...' : form.role === 'teacher' ? 'Submit teacher application' : 'Register' }}</button>
          <div class="form-footer"><span class="form-footer-text">Already have an account?</span><router-link to="/login" class="form-footer-link">Sign in</router-link></div>
        </div>
        <div v-if="error" class="error-message">{{ error }}</div>
      </div>
      <div v-else class="pending-state"><div class="pending-icon">⌛</div><h1 class="register-title">Application submitted</h1><p class="register-subtitle">Your teacher application is waiting for administrator approval.</p><p class="pending-detail">You will not be signed in as a teacher until your application is approved.</p><router-link to="/login" class="btn btn-primary btn-block btn-large">Back to sign in</router-link></div>
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
  if (!form.value.username || !form.value.password || !form.value.email) { error.value = 'Please complete all required fields.'; return }
  if (form.value.password !== form.value.password2) { error.value = 'Passwords do not match.'; return }
  loading.value = true
  error.value = ''
  try {
    const result = await userStore.register(form.value)
    if (!result.success) error.value = result.message
    else if (result.pendingApproval) applicationSubmitted.value = true
    else router.push('/profile/setup')
  } catch { error.value = 'Registration failed. Please try again.' }
  finally { loading.value = false }
}
</script>

<style scoped>
.register-page { min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; background:linear-gradient(90deg,rgba(24,23,19,.045) 1px,transparent 1px) 0 0/44px 44px,linear-gradient(180deg,#faf7f0 0%,var(--bg-paper) 100%); }.register-container { width:100%; max-width:450px; background:rgba(255,250,242,.86); padding:40px; border:1px solid var(--border-color); border-radius:var(--radius-lg); box-shadow:14px 14px 0 var(--bg-paper-2); }.register-header,.pending-state { text-align:center; }.register-header { margin-bottom:32px; }.register-title { margin:0 0 8px; font-size:32px; line-height:1.05; font-weight:950; color:var(--text-primary); }.register-subtitle,.pending-detail { font-size:14px; color:var(--text-secondary); }.form-group { margin-bottom:16px; }.form-label { display:block; margin-bottom:8px; font-size:14px; font-weight:850; color:var(--text-primary); }.role-selector { display:flex; gap:12px; }.role-btn { flex:1; padding:12px; border:2px solid var(--border-color); border-radius:4px; background:rgba(255,250,242,.78); cursor:pointer; font-weight:850; }.role-btn.active { border-color:var(--text-primary); background:var(--text-primary); color:#fbf7ef; }.approval-notice { margin:10px 0 0; padding:10px 12px; border-left:3px solid var(--primary-color); background:var(--bg-paper-2); color:var(--text-secondary); font-size:13px; line-height:1.5; }.input { box-sizing:border-box; width:100%; padding:10px 14px; border:1px solid var(--border-color); border-radius:4px; font-size:14px; }.input:focus { outline:none; border-color:var(--primary-color); box-shadow:0 0 0 3px rgba(183,53,45,.12); }.btn { box-sizing:border-box; border:1px solid var(--text-primary); border-radius:4px; padding:10px 20px; font-size:14px; font-weight:850; cursor:pointer; text-align:center; text-decoration:none; }.btn-primary { background:var(--text-primary); color:#fbf7ef; }.btn-block { display:block; width:100%; }.btn-large { padding:12px 24px; font-size:16px; }.btn:disabled { opacity:.6; cursor:not-allowed; }.form-footer { margin-top:24px; padding-top:16px; border-top:1px solid var(--border-color); text-align:center; }.form-footer-text { color:var(--text-secondary); font-size:14px; margin-right:6px; }.form-footer-link { color:var(--primary-color); font-size:14px; font-weight:850; text-decoration:none; }.error-message { margin-top:16px; padding:12px 16px; border:1px solid rgba(183,53,45,.28); border-radius:4px; background:rgba(183,53,45,.1); color:var(--error-color); font-size:14px; }.pending-state { padding:20px 0; }.pending-icon { display:grid; place-items:center; width:62px; height:62px; margin:0 auto 20px; border:1px solid var(--border-color); border-radius:50%; background:var(--bg-paper-2); font-size:30px; }.pending-detail { margin:18px 0 24px; line-height:1.6; }
</style>
