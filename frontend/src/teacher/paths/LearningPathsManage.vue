<template>
  <PathManageEditor :key="route.fullPath" :api="pathApi" management-base="/teacher/learning-paths" :take-draft="takeKnowledgeDraft" />
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import PathManageEditor from '@/shared/paths/PathManageEditor.vue'
import pathApi from './api.js'
import { consumeTeachingTransfer, teachingIdentity } from '@/shared/knowledge/teachingTransfer.js'

const route = useRoute()
const userStore = useUserStore()
function takeKnowledgeDraft() {
  if (route.query.from !== 'knowledge' || userStore.userInfo?.role !== 'teacher' || !userStore.userInfo?.id) return null
  return consumeTeachingTransfer(teachingIdentity(userStore.userInfo), 'path')
}
</script>
