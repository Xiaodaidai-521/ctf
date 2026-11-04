<template>
  <form class="content-filters" @submit.prevent="$emit('apply')">
    <label>分类<select v-model="filters.category" :disabled="loading"><option value="">全部分类</option><option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option></select></label>
    <label>难度<select v-model="filters.difficulty"><option value="">全部难度</option><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
    <label>状态<select v-model="filters.is_active"><option value="">全部状态</option><option value="true">已激活</option><option value="false">未激活</option></select></label>
    <button class="content-button" type="submit" :disabled="loading">筛选</button>
  </form>
  <p v-if="role === 'teacher'" class="content-note">这里显示你有权查看的题目；未激活题目的可见范围由账号权限决定。</p>
</template>
<script setup>
import { difficulties } from './presentation.js'
defineProps({ role: { type: String, required: true }, filters: { type: Object, required: true }, categories: { type: Array, required: true }, loading: Boolean })
defineEmits(['apply'])
</script>
<style scoped src="./content.css"></style>
