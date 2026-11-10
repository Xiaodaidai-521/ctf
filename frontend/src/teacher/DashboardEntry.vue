<template><TeacherLearningDashboard v-if="isTeacher" /><StudentDashboard v-else /></template>
<script setup>
import { computed } from 'vue'
import { useUserStore } from '@/store/user'
import StudentDashboard from '@/views/StudentDashboard.vue'
import TeacherLearningDashboard from './TeacherLearningDashboard.vue'
const userStore = useUserStore()
const isTeacher = computed(() => userStore.userInfo?.role === 'teacher')
</script>

