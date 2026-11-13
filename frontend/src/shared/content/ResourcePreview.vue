<template>
  <ContentDialog title="资源详情" @close="$emit('close')">
    <div class="resource-preview"><div class="resource-cover"><img v-if="resource.cover_url" :src="resource.cover_url" :alt="`${resource.title}封面`" /><AppIcon v-else :name="resourceIcon(resource.resource_type)" /></div><h3>{{ resource.title }}</h3><ProtectionBadge :status="resource.protection?.file" label="文件已加密保存" /><ProtectionBadge :status="resource.protection?.cover_image" label="封面已加密保存" /><div class="resource-meta"><span>{{ resourceTypeLabel(resource.resource_type) }}</span><span>{{ resource.category || '未分类' }}</span><span>{{ statusLabel(resource.status) }}</span></div><dl class="preview-fields"><dt>上传者</dt><dd>{{ resource.uploader_info?.username || '未提供' }}</dd><dt>上传时间</dt><dd>{{ formatDate(resource.created_at) }}</dd><dt>文件大小</dt><dd>{{ formatFileSize(resource.file_size) }}</dd><dt>查看</dt><dd>{{ resource.view_count ?? '未提供' }}</dd><dt>下载</dt><dd>{{ resource.download_count ?? '未提供' }}</dd></dl><h4>资源描述</h4><p class="resource-description">{{ resource.description }}</p><p v-if="resource.status !== 'approved'" class="content-note">原文仅供上传者和管理员审阅。</p><p v-if="error" class="content-error" role="alert">{{ error }}</p></div>
    <template #footer><button class="content-button" @click="$emit('close')">关闭</button><button class="content-button primary" :disabled="downloading" @click="$emit('download')">{{ downloading ? '下载中…' : '下载文件' }}</button></template>
  </ContentDialog>
</template>
<script setup>
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
import AppIcon from '../design/AppIcon.vue'
import ContentDialog from './ContentDialog.vue'
import { resourceIcon, resourceTypeLabel, statusLabel, formatDate, formatFileSize } from './presentation.js'
defineProps({ role: { type: String, required: true }, resource: { type: Object, required: true }, downloading: Boolean, error: String })
defineEmits(['close', 'download'])
</script>
<style scoped src="./content.css"></style>
