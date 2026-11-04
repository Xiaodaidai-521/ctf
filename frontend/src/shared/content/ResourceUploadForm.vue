<template>
  <ContentDialog title="上传学习资源" :busy="busy" @close="$emit('close')">
    <form id="content-upload-form" class="content-form" @submit.prevent="submit">
      <label class="full-width">资源标题<input v-model="form.title" required :disabled="busy" /></label>
      <label>资源类型<select v-model="form.resource_type" required :disabled="busy"><option value="" disabled>请选择类型</option><option v-for="item in resourceTypes" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
      <label>分类<select v-model="form.category" required :disabled="busy"><option value="" disabled>请选择分类</option><option v-for="item in resourceCategories" :key="item" :value="item">{{ item }}</option></select></label>
      <label class="full-width">资源描述<textarea v-model="form.description" rows="6" required :disabled="busy"></textarea></label>
      <label class="full-width">标签<input v-model="form.tags" :disabled="busy" placeholder="多个标签用逗号分隔" /></label>
      <label class="full-width">资源文件<input ref="fileInput" type="file" required :disabled="busy" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.rar,.7z,.mp4,.avi,.mkv" @change="file = $event.target.files[0] || null" /><small>支持文档、压缩包和视频，最大 500MB。</small></label>
      <label class="full-width">封面图片（可选）<input type="file" accept="image/*" :disabled="busy" @change="cover = $event.target.files[0] || null" /></label>
      <p v-if="localError || error" class="content-error full-width" role="alert">{{ localError || error }}</p>
    </form>
    <template #footer><button class="content-button" :disabled="busy" @click="$emit('close')">取消</button><button class="content-button primary" form="content-upload-form" type="submit" :disabled="busy">{{ busy ? '上传中…' : '提交审核' }}</button></template>
  </ContentDialog>
</template>
<script setup>
import { reactive, ref } from 'vue'
import ContentDialog from './ContentDialog.vue'
import { resourceTypes, resourceCategories } from './presentation.js'
defineProps({ role: { type: String, required: true }, busy: Boolean, error: String })
const emit = defineEmits(['close', 'upload'])
const form = reactive({ title: '', resource_type: '', category: '', description: '', tags: '' })
const file = ref(null), cover = ref(null), localError = ref(''), fileInput = ref(null)
function submit() {
  localError.value = ''
  if (!file.value) { localError.value = '请选择资源文件。'; return }
  if (file.value.size > 500 * 1024 * 1024) { localError.value = '文件大小不能超过 500MB。'; return }
  if (cover.value && !cover.value.type.startsWith('image/')) { localError.value = '封面请选择图片文件。'; return }
  const data = new FormData()
  for (const key of ['title', 'resource_type', 'category', 'description', 'tags']) data.append(key, form[key])
  data.append('file', file.value)
  if (cover.value) data.append('cover_image', cover.value)
  emit('upload', data)
}
</script>
<style scoped src="./content.css"></style>
