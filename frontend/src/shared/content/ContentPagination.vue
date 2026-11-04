<template>
  <nav v-if="total !== null && (page > 1 || hasNext)" class="content-pagination" aria-label="列表分页">
    <span>共 {{ total }} 条记录 · 第 {{ page }} 页</span>
    <div class="content-actions"><button class="content-button" :disabled="loading || page === 1" @click="$emit('change', page - 1)">上一页</button><button class="content-button" :disabled="loading || !hasNext" @click="$emit('change', page + 1)">下一页</button></div>
  </nav>
</template>
<script setup>
defineProps({ total: { type: Number, default: null }, page: { type: Number, required: true }, hasNext: Boolean, loading: Boolean })
defineEmits(['change'])
</script>
<style scoped src="./content.css"></style>
