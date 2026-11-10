import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

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

  // Getters
  const isAuthenticated = computed(() => !!userInfo.value)
  const userName = computed(() => userInfo.value?.nickname || userInfo.value?.username || '')

  // Actions
  const login = async (credentials) => {
    try {
      await api.auth.csrf()
      const response = await api.auth.login(credentials)
      userInfo.value = response.user
      localStorage.setItem(USER_INFO_STORAGE_KEY, JSON.stringify(response.user))
      return { success: true, message: response.message }
    } catch (error) {
      console.error('登录失败:', error)
      return { success: false, message: error.response?.data?.error || error.response?.data?.detail || '登录失败' }
    }
  }

  const register = async (data) => {
    try {
      await api.auth.csrf()
      const response = await api.auth.register(data)
      const pendingApproval = data.role === 'teacher' || response.approval_status === 'pending' || response.user?.approval_status === 'pending'
      if (!pendingApproval) {
        userInfo.value = response.user
        localStorage.setItem(USER_INFO_STORAGE_KEY, JSON.stringify(response.user))
      }
      return { success: true, message: response.message, pendingApproval }
    } catch (error) {
      return { success: false, message: error.response?.data?.username?.[0] || error.response?.data?.error || '注册失败' }
    }
  }

  const logout = async () => {
    try {
      await api.auth.csrf()
      await api.auth.logout()
    } catch (error) {
      console.warn('Logout request failed:', error)
    } finally {
      userInfo.value = null
      localStorage.removeItem(USER_INFO_STORAGE_KEY)
    }
  }

  const fetchProfile = async () => {
    try {
      const response = await api.user.profile()
      userInfo.value = response
      localStorage.setItem(USER_INFO_STORAGE_KEY, JSON.stringify(response))
      return response
    } catch (error) {
      logout()
      throw error
    }
  }

  const updateProfile = async (data) => {
    try {
      const response = await api.user.updateProfile(data)
      userInfo.value = response.user
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


