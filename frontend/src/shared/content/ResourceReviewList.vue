<template>
  <div class="resource-list">
    <article v-for="item in items" :key="item.id" class="resource-item">
      <div class="resource-cover"><img v-if="item.cover_url" :src="item.cover_url" :alt="`${item.title}封面`" /><AppIcon v-else :name="resourceIcon(item.resource_type)" /></div>
      <div class="resource-info"><div class="resource-header"><h3 class="resource-title">{{ item.title }}</h3><span class="content-badge" :class="['pending', 'approved', 'rejected'].includes(item.status) ? item.status : ''">{{ statusLabel(item.status) }}</span></div><p>{{ item.description }}</p><div class="resource-meta"><strong>{{ item.uploader_info?.username || '上传者未提供' }}</strong><span>{{ item.category || '未分类' }}</span><span>{{ resourceTypeLabel(item.resource_type) }}</span><span>{{ formatDate(item.created_at) }}</span></div></div>
      <div class="resource-actions"><template v-if="role === 'admin' && item.status === 'pending'"><button class="content-button" :disabled="busy" @click="$emit('review', item, 'approved')">通过</button><button class="content-button danger" :disabled="busy" @click="$emit('review', item, 'rejected')">拒绝</button></template><span v-else class="content-note">{{ item.status === 'pending' ? '等待管理员审核' : '已审核' }}</span><button class="content-button" @click="$emit('preview', item)">查看</button></div>
    </article>
  </div>
</template>
<script setup>
import AppIcon from '../design/AppIcon.vue'
import { resourceIcon, resourceTypeLabel, statusLabel, formatDate } from './presentation.js'
defineProps({ role: { type: String, required: true }, items: { type: Array, required: true }, busy: Boolean })
defineEmits(['review', 'preview'])
</script>
<style scoped src="./content.css"></style>
