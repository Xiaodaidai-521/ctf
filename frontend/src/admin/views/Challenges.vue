<template>
  <section class="content-page admin-challenges" data-density="admin">
    <header class="content-header"><div><h1>题目管理</h1><p>维护题目内容、分类与练习环境。</p></div><div class="content-actions"><button class="content-button" :disabled="state.loading" @click="load">刷新</button><button class="content-button primary" :disabled="state.busy" @click="create">新增题目</button></div></header>
    <p v-if="state.success" class="content-success" role="status">{{ state.success }}</p>
    <p v-if="state.error && !state.editor" class="content-error" role="alert">{{ state.error }}</p>
    <div class="content-surface" :aria-busy="state.loading">
      <ChallengeFilters role="admin" :filters="state.filters" :categories="state.categories" :loading="state.loading" @apply="filter" />
      <p v-if="state.categoriesError" class="content-error" role="alert">{{ state.categoriesError }} <button class="content-button" :disabled="state.categoriesLoading" @click="loadCategories">重试分类</button></p>
      <div v-if="state.loading" class="content-state" role="status">正在读取题目…</div>
      <div v-else-if="state.listError" class="content-error" role="alert">{{ state.listError }} <button class="content-button" @click="load">重试</button></div>
      <template v-else><ChallengeTable v-if="state.items.length" role="admin" :items="state.items" :busy="state.busy || state.detailLoading" @edit="edit" @delete="remove" /><p v-else class="content-state">暂无符合筛选条件的题目。</p><ContentPagination :page="state.page" :total="state.total" :has-next="state.hasNext" :loading="state.loading" @change="changePage" /></template>
      <p v-if="state.detailLoading" class="content-note" role="status">正在读取题目详情…</p>
    </div>
    <ChallengeEditor v-if="state.editor" role="admin" :mode="state.editor" :form="state.form" :categories="state.categories" :busy="state.busy" :error="state.error" @close="close" @save="save" />
  </section>
</template>
<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import ChallengeFilters from '@/shared/content/ChallengeFilters.vue'
import ChallengeTable from '@/shared/content/ChallengeTable.vue'
import ChallengeEditor from '@/shared/content/ChallengeEditor.vue'
import ContentPagination from '@/shared/content/ContentPagination.vue'
import { useChallengeContent } from '@/shared/content/useChallengeContent.js'
const { state, load, loadCategories, filter, changePage, create, edit, close, save, remove, destroy } = useChallengeContent('admin')
onMounted(() => Promise.all([load(), loadCategories()]))
onBeforeUnmount(destroy)
</script>
<style scoped src="../../shared/content/content.css"></style>
