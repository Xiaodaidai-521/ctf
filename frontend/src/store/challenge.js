import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import api from '@/api'
import { captureAccount, onAccountClear } from '@/shared/state/accountScope.js'

export const useChallengeStore = defineStore('challenge', () => {
  // State
  const challenges = ref([])
  const categories = ref([])
  const currentChallenge = ref(null)
  // 列表与详情分开加载/报错，避免打开一道题时把列表也置为忙碌或清空。
  const listLoading = ref(false)
  const detailLoading = ref(false)
  const listError = ref('')
  const detailError = ref('')
  const loading = computed(() => listLoading.value || detailLoading.value)
  let listRequest = 0
  let detailRequest = 0
  onAccountClear(() => {
    ++listRequest; ++detailRequest
    challenges.value = []; categories.value = []; currentChallenge.value = null
    listLoading.value = false; detailLoading.value = false
    listError.value = ''; detailError.value = ''
  })

  // Actions
  const fetchCategories = async () => {
    const account = captureAccount()
    try {
      const response = await api.challenge.getCategories()
      if (account.current()) categories.value = response.results || response
      return response
    } catch (error) {
      console.error('获取分类失败:', error)
      throw error
    }
  }

  const fetchChallenges = async (params = {}) => {
    const request = ++listRequest
    listLoading.value = true
    listError.value = ''
    try {
      const response = await api.challenge.getChallenges(params)
      if (request !== listRequest) return response
      challenges.value = response.results || response
      return response
    } catch (error) {
      if (request === listRequest) {
        listError.value = '题目暂时未能加载，请重试。'
        challenges.value = []
      }
      console.error('获取题目失败:', error)
      throw error
    } finally {
      if (request === listRequest) listLoading.value = false
    }
  }

  const fetchChallengeDetail = async (id) => {
    const request = ++detailRequest
    detailLoading.value = true
    detailError.value = ''
    try {
      const response = await api.challenge.getChallengeDetail(id)
      if (request !== detailRequest) return response
      currentChallenge.value = response
      return response
    } catch (error) {
      if (request === detailRequest) {
        detailError.value = '题目详情暂时未能读取，请重试。'
        currentChallenge.value = null
      }
      console.error('获取题目详情失败:', error)
      throw error
    } finally {
      if (request === detailRequest) detailLoading.value = false
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
    listLoading,
    detailLoading,
    listError,
    detailError,
    fetchCategories,
    fetchChallenges,
    fetchChallengeDetail,
    submitFlag
  }
})
