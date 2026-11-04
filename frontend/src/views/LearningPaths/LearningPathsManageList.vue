<template>
  <PathManageList :api="pathApi" :management-base="managementBase" :home="home" />
</template>

<script setup>
// Compatibility entry: shared neutral management, never another role's page.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PathManageList from '@/shared/paths/PathManageList.vue'
import pathApi from '@/shared/paths/api.js'

const route = useRoute()
const managementBase = computed(() => route.path.startsWith('/teacher/') ? '/teacher/learning-paths' : '/learning-paths')
const home = computed(() => route.path.startsWith('/teacher/') ? '/teacher' : '/admin/dashboard')
</script>
