<template>
  <FoundationFrame current="tools">
    <main class="governance-page">
      <header class="governance-hero"><h1>{{ names.foundation }} · {{ names.indexTools }}</h1><p class="governance-muted">维护法规资料索引，核对条款、段落与检索出处。</p></header>
      <div class="governance-heading"><p class="governance-muted">更新索引不会改变课程权限，也不发布教学材料。</p><button :disabled="loading || busy" @click="reload">刷新记录</button></div>
      <p v-if="paused" class="governance-notice" role="status">资料已收起，请重新读取。<button @click="reload">重新读取</button></p>
      <p v-if="uncertain" class="governance-notice" role="alert">上次更新的结果尚未确认，已暂停重复更新。请先到索引健康核对记录。</p>
      <p v-if="error" class="governance-error" role="alert">{{ error }}</p><p v-if="message" class="governance-notice" role="status">{{ message }}</p>
      <section class="governance-panel"><h2>法规文档</h2><p v-if="sources.documents.loading" role="status">正在读取文档…</p><p v-else-if="sources.documents.error" class="governance-error" role="alert">{{ sources.documents.error }}</p>
        <template v-else-if="sources.documents.data"><p class="governance-muted">{{ listScope(sources.documents.data) }}</p><p v-if="!documents.length">暂无可读取的法规文档。</p>
          <div v-else class="governance-table-wrap"><table class="governance-mobile-records"><thead><tr><th>文档</th><th>类型</th><th>状态</th><th>版本</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="row in documents" :key="row.id"><td data-label="文档">{{ row.title || '未命名文档' }}</td><td data-label="类型">{{ documentType(row.document_type) }}</td><td data-label="状态">{{ documentStatus(row.status) }}</td><td data-label="版本">{{ row.version_label || '未提供' }}</td><td data-label="更新时间">{{ dateLabel(row.updated_at) }}</td><td data-label="操作"><button :disabled="busy || paused" @click="selectDocument(row)">核对条款</button><button :disabled="busy || paused || uncertain" @click="pendingDocument = row">更新索引</button></td></tr></tbody></table></div>
          <div class="governance-actions"><button :disabled="page === 1 || busy || loading" @click="changePage(-1)">上一页</button><span>第 {{ page }} 页</span><button :disabled="!sources.documents.data.next || busy || loading" @click="changePage(1)">下一页</button></div>
        </template>
      </section>
      <section v-if="pendingDocument" class="governance-panel" aria-label="确认更新索引"><h2>更新“{{ pendingDocument.title }}”的索引？</h2><p>将重新处理已有法规文档。请先确认来源与版本正确。</p><div class="governance-actions"><button class="governance-primary" :disabled="busy" @click="updateIndex">{{ busy ? '正在更新…' : '确认更新' }}</button><button :disabled="busy" @click="pendingDocument = null">取消</button></div></section>
      <section v-if="selectedDocument" class="governance-panel"><h2>{{ selectedDocument.title }} · 条款</h2><p v-if="clausesLoading" role="status">正在读取条款…</p><p v-else-if="!clauses.length">当前没有已读取条款。</p><article v-for="row in clauses" :key="row.id"><h3>{{ [row.chapter, row.article_number, row.title].filter(Boolean).join(' · ') || '条款' }}</h3><p>{{ row.text }}</p></article><p class="governance-muted">每次最多读取 50 条，完整资料可到资料库核对。</p></section>
      <section class="governance-panel"><h2>检索核对</h2><form class="governance-form" @submit.prevent="retrieve"><label>检索问题<textarea v-model="query" maxlength="500" rows="3" :disabled="busy || paused" placeholder="输入需要核对的资料问题"></textarea></label><button v-if="!pendingDocument" class="governance-primary" :disabled="busy || paused || !query.trim()">{{ busy ? '正在检索…' : '检索资料' }}</button></form>
        <template v-if="retrieved"><p v-if="answer">{{ answer }}</p><p v-if="!hits.length">本次未检索到匹配资料。</p><article v-for="(hit, index) in hits" :key="index"><h3>{{ hit.title || '资料出处' }}</h3><p class="governance-muted">{{ retrievalScore(hit.score) }}</p><p>{{ hit.excerpt || hit.text }}</p></article></template>
      </section>
    </main>
  </FoundationFrame>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { names } from '@/shared/navigation/names.js'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import { usePrivatePage } from '@/learningKnowledge/usePrivatePage.js'
import FoundationFrame from './FoundationFrame.vue'
import { foundationApi } from './api.js'
import { documentStatus, documentType, jobStatus, retrievalScore } from './presentation.js'
import { dateLabel, governanceError, listScope, listValue } from '../governance/data.js'
import { useGovernanceSources } from '../governance/useSources.js'
const route = useRoute()
const page = ref(1), query = ref(''), selectedDocument = ref(null), pendingDocument = ref(null), clauses = ref([])
usePageFilters('admin-index-tools', { page })
if (!Number.isSafeInteger(page.value) || page.value < 1) page.value = 1
const clausesLoading = ref(false), busy = ref(false), uncertain = ref(false), error = ref(''), message = ref('')
const retrieved = ref(false), answer = ref(''), hits = ref([]), mutationPending = ref(false)
const { sources, loading, load, clear } = useGovernanceSources({ documents: signal => foundationApi.documents({ page: page.value, page_size: 30 }, signal) })
const documents = computed(() => sources.documents.data ? listValue(sources.documents.data) : [])
const privacy = usePrivatePage(() => { if (mutationPending.value) uncertain.value = true; mutationPending.value = false; clear(); query.value = ''; selectedDocument.value = null; pendingDocument.value = null; clauses.value = []; busy.value = false; clausesLoading.value = false; error.value = ''; message.value = ''; retrieved.value = false; answer.value = ''; hits.value = [] })
const { paused } = privacy
async function reload() {
  if (!privacy.resume()) return
  await load()
  if (!route.query.document) return
  let row = documents.value.find(item => String(item.id) === String(route.query.document))
  if (!row) {
    const request = privacy.begin(); if (!request) return
    try { const data = await foundationApi.documentDetail(route.query.document, request.signal); if (request.isCurrent()) row = data }
    catch (cause) { if (request.isCurrent()) error.value = governanceError(cause) }
    finally { request.finish() }
  }
  if (row) await selectDocument(row)
}
async function changePage(delta) { page.value += delta; await reload() }
async function selectDocument(row) {
  const request = privacy.begin(); if (!request) return
  selectedDocument.value = row; clauses.value = []; clausesLoading.value = true; error.value = ''
  try { const data = await foundationApi.clauses({ document: row.id, page_size: 50 }, request.signal); if (request.isCurrent()) clauses.value = listValue(data) }
  catch (cause) { if (request.isCurrent()) error.value = governanceError(cause) }
  finally { if (request.isCurrent()) clausesLoading.value = false; request.finish() }
}
async function updateIndex() {
  if (busy.value || uncertain.value || !pendingDocument.value) return
  const request = privacy.begin(); if (!request) return
  busy.value = true; mutationPending.value = true; error.value = ''; message.value = ''; const row = pendingDocument.value
  try { const result = await foundationApi.indexDocument(row.id, request.signal); if (request.isCurrent()) {
    if (!['pending', 'running', 'completed', 'failed'].includes(result?.status)) { uncertain.value = true; error.value = '未能确认处理状态，请到索引健康核对后再操作。' }
    else { message.value = `“${row.title}”：${jobStatus(result.status)}。请到索引健康核对处理记录。`; pendingDocument.value = null }
  } } catch (cause) { if (request.isCurrent()) { error.value = governanceError(cause, true); uncertain.value = ![400, 401, 403, 404, 409].includes(cause.response?.status) } }
  finally { if (request.isCurrent()) { busy.value = false; mutationPending.value = false }; request.finish() }
}
async function retrieve() {
  if (!query.value.trim() || busy.value) return
  const request = privacy.begin(); if (!request) return
  busy.value = true; error.value = ''; retrieved.value = false; answer.value = ''; hits.value = []
  try { const result = await foundationApi.retrieve({ query: query.value.trim(), top_k: 5 }, request.signal); if (request.isCurrent()) {
    const results = Array.isArray(result?.citations) ? result.citations : listValue(result)
    hits.value = results; answer.value = typeof result?.answer === 'string' ? result.answer : ''; retrieved.value = true
  } } catch (cause) { if (request.isCurrent()) error.value = governanceError(cause) }
  finally { if (request.isCurrent()) busy.value = false; request.finish() }
}
onMounted(reload)
</script>
<style scoped src="../governance/governance.css"></style>
