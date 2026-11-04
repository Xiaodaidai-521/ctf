<template>
  <PathManageEditor :key="route.fullPath" :api="pathApi" :management-base="managementBase" />
</template>

<script setup>
// Compatibility entry: keep the old restricted admin routes operational.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PathManageEditor from '@/shared/paths/PathManageEditor.vue'
import pathApi from '@/shared/paths/api.js'

const route = useRoute()
const managementBase = computed(() => route.path.startsWith('/teacher/') ? '/teacher/learning-paths' : '/learning-paths/manage')
</script>
