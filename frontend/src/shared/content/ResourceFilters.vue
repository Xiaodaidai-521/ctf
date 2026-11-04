<template>
  <div class="content-actions" aria-label="审核状态筛选"><button v-for="item in statuses" :key="item.value" class="content-button" :aria-pressed="status === item.value" @click="$emit('status', item.value)">{{ item.label }}<span v-if="counts[item.value] !== undefined">（{{ counts[item.value] }}）</span></button></div>
  <form class="content-filters" @submit.prevent="$emit('apply')">
    <label>搜索<input v-model="filters.search" type="search" placeholder="搜索标题、描述或标签" /></label>
    <label>类型<select v-model="filters.resource_type"><option value="">全部类型</option><option v-for="item in resourceTypes" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
    <label>分类<select v-model="filters.category"><option value="">全部分类</option><option v-for="category in resourceCategories" :key="category" :value="category">{{ category }}</option></select></label>
    <label>排序<select v-model="filters.ordering"><option value="-created_at">最新上传</option><option value="created_at">最早上传</option><option value="-download_count">下载最多</option><option value="-view_count">查看最多</option></select></label>
    <button class="content-button" type="submit" :disabled="loading">筛选</button>
  </form>
</template>
<script setup>
import { statuses, resourceTypes, resourceCategories } from './presentation.js'
defineProps({ role: { type: String, required: true }, filters: { type: Object, required: true }, status: { type: String, required: true }, counts: { type: Object, required: true }, loading: Boolean })
defineEmits(['apply', 'status'])
</script>
<style scoped src="./content.css"></style>
