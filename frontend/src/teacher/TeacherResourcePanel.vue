<template>
  <section class="content-page teacher-resources" data-density="teacher">
    <ContentAreaNav />
    <header class="content-header"><div><h1>{{ names.resourceReview }}</h1><p>资源审阅由管理员负责，教师不参与审阅。可上传成品等待管理员审核；备课资料在知识基座，教学内容制作在材料工坊。</p></div><div class="content-actions"><router-link class="content-button" to="/teacher/knowledge">{{ names.knowledge }}</router-link><router-link class="content-button" to="/teacher/materials">{{ names.materials }}</router-link><button class="content-button" :disabled="state.loading" @click="refresh">刷新</button><button class="content-button primary" :disabled="state.busy" @click="openUpload">上传资源</button></div></header>
    <p v-if="state.success" class="content-success" role="status">{{ state.success }}</p>
    <p v-if="state.error && !state.review && !state.uploadOpen && !state.preview" class="content-error" role="alert">{{ state.error }}</p>
    <p v-if="state.selectionLoading" class="content-note" role="status">正在查找所选资源…</p>
    <p v-if="state.selectionError" class="content-error" role="alert">{{ state.selectionError }} <button class="content-button" @click="applyQuery(route.query)">重试所选资源</button></p>
    <div class="content-surface" :aria-busy="state.loading">
      <ResourceFilters role="teacher" :status="state.status" :filters="state.filters" :counts="state.counts" :loading="state.loading" @status="selectStatus" @apply="filter" />
      <p v-if="state.countsError && !state.listError" class="content-error" role="alert">{{ state.countsError }} <button class="content-button" @click="loadCounts">重试数量</button></p>
      <div v-if="state.loading" class="content-state" role="status">正在读取资源…</div>
      <div v-else-if="state.listError" class="content-error" role="alert">{{ state.listError }} <button class="content-button" @click="refresh">重试</button></div>
      <template v-else><p class="content-note">资源审阅列表目前仅向管理员开放。如需了解审核进度，请联系管理员；已通过的成品可在智库查看。</p><ResourceReviewList v-if="state.items.length" role="teacher" :items="state.items" :busy="state.busy" @preview="preview" /><p v-else class="content-state">{{ state.status === 'pending' ? '暂无符合筛选条件的待审核资源。' : '暂无符合筛选条件的资源。' }}</p><ContentPagination :page="state.page" :total="state.total" :has-next="state.hasNext" :loading="state.loading" @change="changePage" /></template>
    </div>
    <p class="content-note">教师端不提供审阅提交。请联系管理员处理审核，或前往 <router-link to="/resources">智库</router-link> 查看已通过的资源。</p>
    <ResourcePreview v-if="state.preview" role="teacher" :resource="state.preview" :downloading="state.downloading" :error="state.error" @close="state.preview = null" @download="download" />
    <ResourceUploadForm v-if="state.uploadOpen" role="teacher" :busy="state.busy" :error="state.error" @close="closeUpload" @upload="upload" />
  </section>
</template>
<script setup>
import { watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import ContentAreaNav from '@/shared/knowledge/ContentAreaNav.vue'
import { names } from '@/shared/navigation/names'
import ResourceFilters from '@/shared/content/ResourceFilters.vue'
import ResourceReviewList from '@/shared/content/ResourceReviewList.vue'
import ResourcePreview from '@/shared/content/ResourcePreview.vue'
import ResourceUploadForm from '@/shared/content/ResourceUploadForm.vue'
import ContentPagination from '@/shared/content/ContentPagination.vue'
import { useResourceContent } from '@/shared/content/useResourceContent.js'
const route = useRoute()
const { state, refresh, applyQuery, loadCounts, filter, selectStatus, changePage, upload, download, destroy } = useResourceContent('teacher')
function preview(item) { state.error = ''; state.preview = item }
function openUpload() { state.error = ''; state.uploadOpen = true }
function closeUpload() { if (!state.busy) { state.uploadOpen = false; state.error = '' } }
watch(() => [route.query.status, route.query.resource], () => applyQuery(route.query), { immediate: true })
onBeforeUnmount(destroy)
</script>
<style scoped src="../shared/content/content.css"></style>
