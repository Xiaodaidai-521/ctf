import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'
import { captureAccount, syncStateAccount } from '@/shared/state/accountScope.js'

const USER_INFO_STORAGE_KEY = 'userInfo'
const LEGACY_TEACHER_USERNAME = 'teacher_li'
const TEACHER_USERNAME = 'Teacher_\u674e'
const TEACHER_DISPLAY_NAME = '\u674e\u8001\u5e08'

const normalizeUserInfo = (user) => {
  if (!user || user.role !== 'teacher') return user
  if (user.username === LEGACY_TEACHER_USERNAME) return null
  if (user.username === TEACHER_USERNAME) return { ...user, nickname: TEACHER_DISPLAY_NAME }
  return user
}
const loadStoredUserInfo = () => {
  try {
    const storedUserInfo = localStorage.getItem(USER_INFO_STORAGE_KEY)
    return storedUserInfo ? normalizeUserInfo(JSON.parse(storedUserInfo)) : null
  } catch {
    localStorage.removeItem(USER_INFO_STORAGE_KEY)
    return null
  }
}

export const useUserStore = defineStore('user', () => {
  // State
  const userInfo = ref(loadStoredUserInfo())
  syncStateAccount(userInfo.value)
  let authGeneration = 0
  let authQueue = Promise.resolve()
  // Cookie-changing requests in this tab finish in action order, including slow logout.
  function authRequest(task) {
    const pending = authQueue.then(task, task)
    authQueue = pending.catch(() => {})
    return pending
  }
  function installUser(user) {
    const sameAccount = userInfo.value?.id === user?.id && userInfo.value?.role === user?.role
    userInfo.value = user
    syncStateAccount(user, { force: sameAccount })
    if (user) localStorage.setItem(USER_INFO_STORAGE_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_INFO_STORAGE_KEY)
  }
  // The session cookie is shared between tabs. Do not trust the other tab's payload.
  if (typeof window !== 'undefined') window.addEventListener('storage', event => {
    if (event.key === USER_INFO_STORAGE_KEY || event.key === null) {
      ++authGeneration
      userInfo.value = null
      syncStateAccount(null, { force: true })
    }
  })

  // Getters
  const isAuthenticated = computed(() => !!userInfo.value)
  const userName = computed(() => userInfo.value?.nickname || userInfo.value?.username || '')

  // Actions
  const login = async (credentials) => {
    const generation = ++authGeneration
    try {
      const response = await authRequest(async () => {
        await api.auth.csrf()
        return generation === authGeneration ? api.auth.login(credentials) : null
      })
      if (generation !== authGeneration) return { success: false, message: '登录状态已变化，请重新登录。' }
      installUser(response.user)
      return { success: true, message: response.message }
    } catch (error) {
      console.error('登录失败:', error)
      return { success: false, message: error.response?.data?.error || error.response?.data?.detail || '登录失败' }
    }
  }

  const register = async (data) => {
    const generation = ++authGeneration
    try {
      const response = await authRequest(async () => {
        await api.auth.csrf()
        return generation === authGeneration ? api.auth.register(data) : null
      })
      if (generation !== authGeneration) return { success: false, message: '登录状态已变化，请重新登录。' }
      const pendingApproval = data.role === 'teacher' || response.approval_status === 'pending' || response.user?.approval_status === 'pending'
      if (!pendingApproval) installUser(response.user)
      return { success: true, message: response.message, pendingApproval }
    } catch (error) {
      return { success: false, message: error.response?.data?.username?.[0] || error.response?.data?.error || '注册失败' }
    }
  }

  const logout = async () => {
    ++authGeneration
    // Clear locally before waiting on the network: no old account survives a slow logout.
    installUser(null)
    try {
      await authRequest(async () => { await api.auth.csrf(); await api.auth.logout() })
    } catch (error) {
      console.warn('Logout request failed:', error)
    }
  }

  const fetchProfile = async () => {
    const account = captureAccount()
    try {
      const response = await api.user.profile()
      if (!account.current()) return null
      if (userInfo.value?.id != null && String(response?.id) !== String(userInfo.value.id)) {
        installUser(null)
        throw new Error('Account changed')
      }
      userInfo.value = response
      syncStateAccount(response)
      localStorage.setItem(USER_INFO_STORAGE_KEY, JSON.stringify(response))
      return response
    } catch (error) {
      if (account.current()) logout()
      throw error
    }
  }

  const updateProfile = async (data) => {
    const account = captureAccount()
    try {
      const response = await api.user.updateProfile(data)
      if (!account.current()) return { success: false, message: '账号已变化，请重新读取资料。' }
      if (userInfo.value?.id != null && String(response.user?.id) !== String(userInfo.value.id)) {
        installUser(null)
        return { success: false, message: '账号已变化，请重新登录。' }
      }
      userInfo.value = response.user
      syncStateAccount(response.user)
      localStorage.setItem(USER_INFO_STORAGE_KEY, JSON.stringify(response.user))
      return { success: true, message: response.message }
    } catch (error) {
      return { success: false, message: '更新失败' }
    }
  }

  return {
    userInfo,
    isAuthenticated,
    userName,
    login,
    register,
    logout,
    fetchProfile,
    updateProfile
  }
})


