<template>
  <ContentDialog :title="mode === 'edit' ? '编辑题目' : '新增题目'" :busy="busy" @close="$emit('close')">
    <form id="challenge-content-form" class="content-form" @submit.prevent="$emit('save')">
      <label>标题<input v-model="form.title" required :disabled="busy" placeholder="请输入题目标题" /></label>
      <label>分类<select v-model="form.category" required :disabled="busy || !categories.length"><option :value="null" disabled>请选择分类</option><option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option></select></label>
      <label>难度<select v-model="form.difficulty" :disabled="busy"><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
      <label>分数<input v-model.number="form.score" type="number" required min="0" :disabled="busy" /></label>
      <label class="full-width">题目描述<textarea v-model="form.description" rows="6" required :disabled="busy" placeholder="请输入题目描述"></textarea></label>
      <label class="full-width">{{ mode === 'edit' ? '替换答案（Flag，留空保留原答案）' : '答案（Flag）' }}<input v-model="form.flag" type="password" autocomplete="new-password" :required="mode === 'create'" :disabled="busy" :placeholder="mode === 'edit' ? '仅在需要替换答案时填写' : '请输入题目答案'" /><small v-if="mode === 'edit'">原答案不读取到页面；留空保存保留原答案。</small><small>保存后请用真实提交核对答案是否生效，再安排学生练习。</small></label>
      <label class="full-width">提示<textarea v-model="form.hint" rows="3" :disabled="busy" placeholder="请输入分级提示（可选）"></textarea></label>
      <label>状态<select v-model="form.is_active" :disabled="busy"><option :value="true">已激活</option><option :value="false">未激活</option></select></label>
      <h3 class="full-width">练习环境设置</h3>
      <label>环境镜像<input v-model="form.docker_image" :disabled="busy" placeholder="填写已有镜像名称" /><small>留空表示题目无需容器环境。</small></label>
      <label>服务端口<input v-model.number="form.redirect_port" type="number" min="1" max="65535" :disabled="busy" placeholder="例如：80" /></label>
      <label>访问方式<select v-model="form.redirect_type" :disabled="busy"><option value="">无代理</option><option value="http">子域名访问</option><option value="path">路径访问</option><option value="direct">直接访问</option></select></label>
      <p v-if="error" class="content-error full-width" role="alert">{{ error }}</p>
    </form>
    <template #footer><button class="content-button" :disabled="busy" @click="$emit('close')">取消</button><button class="content-button primary" type="submit" form="challenge-content-form" :disabled="busy || !categories.length">{{ busy ? '保存中…' : mode === 'edit' ? '保存' : '创建' }}</button></template>
  </ContentDialog>
</template>
<script setup>
import ContentDialog from './ContentDialog.vue'
import { difficulties } from './presentation.js'
defineProps({ role: { type: String, required: true }, mode: { type: String, required: true }, form: { type: Object, required: true }, categories: { type: Array, required: true }, busy: Boolean, error: String })
defineEmits(['save', 'close'])
</script>
<style scoped src="./content.css"></style>
