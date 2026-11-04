<template>
  <FoundationFrame current="health"><main class="governance-page">
    <header class="governance-hero"><h1>{{ names.foundation }} · {{ names.indexHealth }}</h1><p class="governance-muted">核对处理任务、可检索段落与检索记录，不将缺少记录当作运行正常。</p></header>
    <div class="governance-heading"><label>处理状态 <select v-model="filter"><option value="all">全部记录</option><option value="attention">需要核对</option><option value="ongoing">尚在处理</option></select></label><button class="governance-primary" :disabled="loading" @click="load">{{ loading ? '正在读取…' : '刷新记录' }}</button></div>
    <p class="governance-notice">这里显示已有处理记录。资料服务是否持续可用、全部来源的索引覆盖率与实时告警尚未提供，不能据此判断整个平台健康。</p>
    <section class="governance-panel"><h2>资料处理记录</h2><p v-if="sources.jobs.loading" role="status">正在读取处理记录…</p><p v-else-if="sources.jobs.error" class="governance-error" role="alert">{{ sources.jobs.error }}</p>
      <template v-else-if="sources.jobs.data"><p class="governance-muted">{{ listScope(sources.jobs.data) }}。筛选仅作用于本页记录。</p><p v-if="!jobs.length">当前已读取范围内没有符合筛选的处理记录。</p>
        <div v-else class="governance-table-wrap"><table class="governance-mobile-records"><thead><tr><th>资料</th><th>状态</th><th>段落</th><th>处理时间</th><th>核对</th></tr></thead><tbody><tr v-for="row in jobs" :key="row.id"><td data-label="资料">{{ row.document_title || '资料名称未提供' }}</td><td data-label="状态">{{ jobStatus(row.status) }}</td><td data-label="段落">{{ chunkLabel(row) }}</td><td data-label="处理时间">{{ dateLabel(row.completed_at || row.started_at || row.created_at) }}</td><td data-label="核对"><p v-if="indexIssue(row)">{{ indexIssue(row) }}</p><router-link v-if="row.document" :to="{ path: '/admin/legal/kb/tools', query: { document: row.document } }">核对文档</router-link><span v-else>关联文档未提供</span></td></tr></tbody></table></div>
        <div class="governance-actions"><button :disabled="page === 1 || loading" @click="changePage(-1)">上一页</button><span>第 {{ page }} 页</span><button :disabled="!sources.jobs.data.next || loading" @click="changePage(1)">下一页</button></div>
      </template>
    </section>
    <section class="governance-panel"><h2>已索引段落</h2><p v-if="sources.embeddings.loading" role="status">正在读取段落记录…</p><p v-else-if="sources.embeddings.error" class="governance-error" role="alert">{{ sources.embeddings.error }}</p><template v-else-if="sources.embeddings.data"><p class="governance-muted">{{ listScope(sources.embeddings.data) }}。只展示已有记录，不推算未索引资料的数量。</p><p v-if="!embeddings.length">暂无已读取的索引段落。</p><ul v-else><li v-for="row in embeddings" :key="row.id">{{ row.title || '资料名称未提供' }} · {{ dateLabel(row.updated_at) }}</li></ul></template></section>
    <section class="governance-panel"><h2>最近检索记录</h2><p v-if="sources.logs.loading" role="status">正在读取检索记录…</p><p v-else-if="sources.logs.error" class="governance-error" role="alert">{{ sources.logs.error }}</p><template v-else-if="sources.logs.data"><p class="governance-muted">{{ listScope(sources.logs.data) }}。查询内容不在这里展示；耗时不等于检索质量。</p><p v-if="!logs.length">暂无已读取的检索记录。</p><ul v-else><li v-for="row in logs" :key="row.id">{{ dateLabel(row.created_at) }} · {{ latencyLabel(row.latency_ms) }}</li></ul></template></section>
  </main></FoundationFrame>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { names } from '@/shared/navigation/names.js'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import FoundationFrame from './FoundationFrame.vue'
import { foundationApi } from './api.js'
import { chunkLabel, indexIssue, jobStatus } from './presentation.js'
import { countValue, dateLabel, listScope, listValue } from '../governance/data.js'
import { useGovernanceSources } from '../governance/useSources.js'
const route = useRoute(), page = ref(1), filter = ref('all')
usePageFilters('admin-index-health', { filter, page })
if (!['all', 'attention', 'ongoing'].includes(filter.value)) filter.value = 'all'
if (!Number.isSafeInteger(page.value) || page.value < 1) page.value = 1
watch(() => route.query.status, status => { if (status !== undefined) { filter.value = ['attention', 'ongoing'].includes(status) ? status : 'all'; page.value = 1 } }, { immediate: true })
const { sources, loading, load } = useGovernanceSources({
  jobs: signal => foundationApi.jobs({ page: page.value, page_size: 50 }, signal),
  embeddings: signal => foundationApi.embeddings({ page_size: 50 }, signal),
  logs: signal => foundationApi.logs({ page_size: 20 }, signal),
})
const rows = key => sources[key].data ? listValue(sources[key].data) : []
const jobs = computed(() => rows('jobs').filter(row => filter.value === 'attention' ? indexIssue(row) : filter.value === 'ongoing' ? ['pending', 'running'].includes(row.status) : true))
const embeddings = computed(() => rows('embeddings')), logs = computed(() => rows('logs'))
const latencyLabel = value => countValue(value) === null ? '耗时未提供' : `耗时 ${value} 毫秒`
async function changePage(delta) { page.value += delta; await load() }
</script>
<style scoped src="../governance/governance.css"></style>
