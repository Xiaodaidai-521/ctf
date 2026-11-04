<template>
  <div data-retain-scroll class="table-container" tabindex="0" aria-label="题目列表，可横向滚动">
    <table class="content-table">
      <thead><tr><th>标题</th><th>分类</th><th>难度</th><th>分数</th><th>练习环境</th><th>解决人数</th><th>状态</th><th>操作</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.id">
        <td><strong>{{ item.title }}</strong></td><td>{{ item.category_name || '未分类' }}</td><td>{{ difficultyLabel(item.difficulty) }}</td><td>{{ item.score ?? '未提供' }}</td>
        <td><template v-if="item.docker_image"><span>{{ item.docker_image }}</span><small v-if="item.redirect_port">端口：{{ item.redirect_port }} · {{ redirectLabel(item.redirect_type) }}</small></template><span v-else>无需环境</span></td>
        <td>{{ item.solve_count ?? '未提供' }}</td><td>{{ item.is_active ? '已激活' : '未激活' }}</td>
        <td><div class="content-actions"><button class="content-button" :disabled="busy" @click="$emit('edit', item)">编辑</button><button class="content-button danger" :disabled="busy" @click="$emit('delete', item)">删除</button></div></td>
      </tr></tbody>
    </table>
  </div>
</template>
<script setup>
import { difficultyLabel, redirectLabel } from './presentation.js'
defineProps({ role: { type: String, required: true }, items: { type: Array, required: true }, busy: Boolean })
defineEmits(['edit', 'delete'])
</script>
<style scoped src="./content.css"></style>
