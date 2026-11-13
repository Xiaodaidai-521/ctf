<template>
  <PathManageEditor :key="route.fullPath" :api="pathApi" management-base="/learning-paths" list-path="/learning-paths/manage" />
</template>

<script setup>
import { useRoute } from 'vue-router'
import PathManageEditor from '@/shared/paths/PathManageEditor.vue'
import pathApi from '@/shared/paths/api.js'
const route = useRoute()
</script>
