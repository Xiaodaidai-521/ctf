<template>
  <PathManageList :api="pathApi" management-base="/learning-paths" home="/admin/dashboard" />
</template>

<script setup>
import PathManageList from '@/shared/paths/PathManageList.vue'
import pathApi from '@/shared/paths/api.js'
</script>
