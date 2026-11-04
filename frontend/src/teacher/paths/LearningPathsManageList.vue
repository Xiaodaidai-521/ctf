<template>
  <PathManageList :api="pathApi" management-base="/teacher/learning-paths" home="/teacher" />
</template>

<script setup>
import PathManageList from '@/shared/paths/PathManageList.vue'
import pathApi from './api.js'
</script>
