<template>
  <section class="content-page admin-resources" data-density="admin">
    <ResourceSidebar @resource-clicked="focusReviewList" />
    <header class="content-header"><div><h1>{{ names.resourceReview }}</h1><p>审核学生可用的成品资源，核对内容与文件。</p></div><div class="content-actions"><router-link class="content-button" to="/admin/legal/kb">{{ names.foundation }}</router-link><button class="content-button" :disabled="state.loading" @click="refresh">刷新</button><button class="content-button primary" :disabled="state.busy" @click="openUpload">上传资源</button></div></header>
    <p v-if="state.success" class="content-success" role="status">{{ state.success }}</p>
    <p v-if="state.error && !state.review && !state.uploadOpen && !state.preview" class="content-error" role="alert">{{ state.error }}</p>
    <p v-if="state.selectionLoading" class="content-note" role="status">正在查找所选资源…</p>
    <p v-if="state.selectionError" class="content-error" role="alert">{{ state.selectionError }} <button class="content-button" @click="applyQuery(route.query)">重试所选资源</button></p>
    <div ref="reviewList" class="content-surface" :aria-busy="state.loading">
      <ResourceFilters role="admin" :status="state.status" :filters="state.filters" :counts="state.counts" :loading="state.loading" @status="selectStatus" @apply="filter" />
      <p v-if="state.countsError && !state.listError" class="content-error" role="alert">{{ state.countsError }} <button class="content-button" @click="loadCounts">重试数量</button></p>
      <div v-if="state.loading" class="content-state" role="status">正在读取资源…</div>
      <div v-else-if="state.listError" class="content-error" role="alert">{{ state.listError }} <button class="content-button" @click="refresh">重试</button></div>
      <template v-else><p class="content-note">{{ state.status === 'pending' ? '只有待审核资源可以通过或拒绝。' : '已审核资源不能再次审核，请切换到待审核资源。' }}</p><ResourceReviewList v-if="state.items.length" role="admin" :items="state.items" :busy="state.busy" @review="review" @preview="preview" /><p v-else class="content-state">{{ state.status === 'pending' ? '暂无符合筛选条件的待审核资源。' : '暂无符合筛选条件的资源。' }}</p><ContentPagination :page="state.page" :total="state.total" :has-next="state.hasNext" :loading="state.loading" @change="changePage" /></template>
    </div>
    <ResourceReviewDialog v-if="state.review" role="admin" :resource="state.review.item" :action="state.review.action" v-model:note="state.note" :busy="state.busy" :error="state.error" @close="closeReview" @confirm="confirmReview" />
    <ResourcePreview v-if="state.preview" role="admin" :resource="state.preview" :downloading="state.downloading" :error="state.error" @close="state.preview = null" @download="download" />
    <ResourceUploadForm v-if="state.uploadOpen" role="admin" :busy="state.busy" :error="state.error" @close="closeUpload" @upload="upload" />
  </section>
</template>
<script setup>
import { watch, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { names } from '@/shared/navigation/names'
import ResourceSidebar from '@/components/ResourceSidebar.vue'
import ResourceFilters from '@/shared/content/ResourceFilters.vue'
import ResourceReviewList from '@/shared/content/ResourceReviewList.vue'
import ResourceReviewDialog from '@/shared/content/ResourceReviewDialog.vue'
import ResourcePreview from '@/shared/content/ResourcePreview.vue'
import ResourceUploadForm from '@/shared/content/ResourceUploadForm.vue'
import ContentPagination from '@/shared/content/ContentPagination.vue'
import { useResourceContent } from '@/shared/content/useResourceContent.js'
const route = useRoute()
const { state, refresh, applyQuery, loadCounts, filter, selectStatus, changePage, review, closeReview, confirmReview, upload, download, destroy } = useResourceContent('admin')
const reviewList = ref(null)
function focusReviewList() { reviewList.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
function preview(item) { state.error = ''; state.preview = item }
function openUpload() { state.error = ''; state.uploadOpen = true }
function closeUpload() { if (!state.busy) { state.uploadOpen = false; state.error = '' } }
watch(() => [route.query.status, route.query.resource], () => applyQuery(route.query), { immediate: true })
onBeforeUnmount(destroy)
</script>
<style scoped src="../../shared/content/content.css"></style>
