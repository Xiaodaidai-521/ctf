<template>
  <TutorHost v-if="isStudent" :mode="'page'" />
  <LegacyMultiAgentChat v-else v-bind="$attrs" />
</template>
<script setup>
import { computed } from 'vue'
import { useUserStore } from '@/store/user'
import TutorHost from '@/learning/agent/components/TutorHost.vue'
import LegacyMultiAgentChat from './legacy/LegacyMultiAgentChat.vue'

// 兼容装配：学生走统一教学对话，教师/管理员保留原显式协作视图。
defineOptions({ inheritAttrs: false })
const user = useUserStore()
const isStudent = computed(() => (user.userInfo?.role || 'student') === 'student')
</script>
<style scoped>
</style>
