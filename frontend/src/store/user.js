import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(
    localStorage.getItem('userInfo')
      ? JSON.parse(localStorage.getItem('userInfo'))
      : null
  )

  // Getters
  const isAuthenticated = computed(() => !!token.value)
  const userName = computed(() => userInfo.value?.nickname || userInfo.value?.username || '')

  // Actions
  const login = async (credentials) => {
    try {
      const response = await api.auth.login(credentials)
      token.value = response.token
      userInfo.value = response.user
      localStorage.setItem('token', response.token)
      localStorage.setItem('userInfo', JSON.stringify(response.user))
      return { success: true, message: response.message }
    } catch (error) {
      console.error('登录失败:', error)
      return { success: false, message: error.response?.data?.error || error.response?.data?.detail || '登录失败' }
    }
  }

  const register = async (data) => {
    try {
      const response = await api.auth.register(data)
      token.value = response.token
      userInfo.value = response.user
      localStorage.setItem('token', response.token)
      localStorage.setItem('userInfo', JSON.stringify(response.user))
      return { success: true, message: response.message }
    } catch (error) {
      return { success: false, message: error.response?.data?.username?.[0] || error.response?.data?.error || '注册失败' }
    }
  }

  const logout = () => {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  const fetchProfile = async () => {
    try {
      const response = await api.user.profile()
      userInfo.value = response
      localStorage.setItem('userInfo', JSON.stringify(response))
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
      localStorage.setItem('userInfo', JSON.stringify(response.user))
      return { success: true, message: response.message }
    } catch (error) {
      return { success: false, message: '更新失败' }
    }
  }

  return {
    token,
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
