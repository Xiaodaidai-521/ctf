<template>
  <TeacherLearningDashboard v-if="isTeacher" />
  <GrowthView v-else-if="isStudent" />
  <StudentDashboard v-else />
</template>
<script setup>
// This shared route-composition boundary is the only role dispatcher.
import { computed, defineAsyncComponent } from 'vue'
import { useUserStore } from '@/store/user'
const StudentDashboard = defineAsyncComponent(() => import('@/views/StudentDashboard.vue'))
const GrowthView = defineAsyncComponent(() => import('@/learning/growth/GrowthView.vue'))
const TeacherLearningDashboard = defineAsyncComponent(() => import('@/teacher/TeacherLearningDashboard.vue'))
const userStore = useUserStore()
const isTeacher = computed(() => userStore.userInfo?.role === 'teacher')
const isStudent = computed(() => !userStore.userInfo?.role || userStore.userInfo?.role === 'student')
</script>
