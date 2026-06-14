import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export const useChallengeStore = defineStore('challenge', () => {
  // State
  const challenges = ref([])
  const categories = ref([])
  const currentChallenge = ref(null)
  const loading = ref(false)

  // Actions
  const fetchCategories = async () => {
    try {
      const response = await api.challenge.getCategories()
      categories.value = response.results || response
      return response
    } catch (error) {
      console.error('获取分类失败:', error)
      throw error
    }
  }

  const fetchChallenges = async (params = {}) => {
    loading.value = true
    try {
      const response = await api.challenge.getChallenges(params)
      challenges.value = response.results || response
      return response
    } catch (error) {
      console.error('获取题目失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const fetchChallengeDetail = async (id) => {
    loading.value = true
    try {
      const response = await api.challenge.getChallengeDetail(id)
      currentChallenge.value = response
      return response
    } catch (error) {
      console.error('获取题目详情失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const submitFlag = async (challengeId, flag) => {
    try {
      const response = await api.challenge.submitFlag(challengeId, flag)
      return { success: response.success, message: response.message, score: response.score }
    } catch (error) {
      return {
        success: false,
        message: error.response?.data?.message
          || error.response?.data?.non_field_errors?.[0]
          || error.response?.data?.flag?.[0]
          || '提交失败'
      }
    }
  }

  return {
    challenges,
    categories,
    currentChallenge,
    loading,
    fetchCategories,
    fetchChallenges,
    fetchChallengeDetail,
    submitFlag
  }
})
