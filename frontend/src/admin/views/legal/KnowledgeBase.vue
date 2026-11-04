<template>
  <LegalWorkspace
    :title="`${names.foundation} · 索引工具`"
    subtitle="浏览法规、条款、案例与模板，维护资料索引并核对检索结果。"
    table-title="法规文档"
    aside-title="知识检索"
    :metrics="metrics"
    :columns="columns"
    :rows="documents"
    :loading="loading"
    :row-actions="[{ key: 'ingest', label: '更新索引' }]"
    :actions="[{ key: 'retrieve', label: retrieving ? '解析中...' : '检索', primary: true }]"
    @refresh="loadData"
    @action="retrieve"
    @row-action="handleRowAction"
  >
    <template #aside>
      <div class="quick-form">
        <router-link to="/admin/legal/kb">返回{{ names.foundation }}</router-link>
        <textarea v-model="query" class="form-textarea" rows="5" placeholder="输入检索问题"></textarea>
        <div v-if="retrievalAnswer" class="rag-answer">
          <div class="rag-answer__header">
            <strong>检索说明</strong>
            <span v-if="retrievalProvider || retrievalModel">由{{ retrievalProviderLabel }}</span>
          </div>
          <p>{{ retrievalAnswer }}</p>
        </div>
        <div v-if="retrievalCitations.length" class="citation-list">
          <h4>引用依据</h4>
          <div v-for="item in retrievalCitations" :key="item.id || item.index" class="citation-item">
            <div class="citation-item__header">
              <strong>[{{ item.index }}] {{ item.title }}</strong>
              <span>{{ legalLabel('source', item.source_type) }} · 相关度 {{ item.score }}</span>
            </div>
            <p>{{ item.excerpt }}</p>
          </div>
        </div>
        <div v-if="retrievalResults.length" class="raw-results">
          <h4>检索结果</h4>
          <div v-for="item in retrievalResults" :key="item.id" class="retrieval-item">
            <strong>{{ item.title }}</strong>
            <span>相关度 {{ item.score }}</span>
            <p>{{ item.text?.slice(0, 120) }}</p>
          </div>
        </div>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { names } from '@/shared/navigation/names'

import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'
import { legalLabel } from './displayLabels.js'

const loading = ref(false)
const documents = ref([])
const clauses = ref([])
const jobs = ref([])
const query = ref('')
const retrieving = ref(false)
const retrievalAnswer = ref('')
const retrievalCitations = ref([])
const retrievalProvider = ref('')
const retrievalModel = ref('')
const retrievalResults = ref([])

const columns = [
  { key: 'title', label: '文档' },
  { key: 'document_type', label: '类型', labelKey: 'documentType', badge: true },
  { key: 'status', label: '状态', labelKey: 'documentStatus', badge: true },
  { key: 'jurisdiction', label: '法域' },
  { key: 'updated_at', label: '更新时间', formatter: formatDate },
]

const metrics = computed(() => [
  { label: '文档', value: documents.value.length, hint: '当前页' },
  { label: '条款', value: clauses.value.length, hint: '当前页' },
  { label: '导入任务', value: jobs.value.length, hint: '当前页' },
])

async function loadData() {
  loading.value = true
  try {
    const [documentRes, clauseRes, jobRes] = await Promise.all([
      api.legalKb.documents({ page_size: 30 }),
      api.legalKb.clauses({ page_size: 50 }),
      api.legalKb.ingestionJobs({ page_size: 20 }),
    ])
    documents.value = normalizeList(documentRes)
    clauses.value = normalizeList(clauseRes)
    jobs.value = normalizeList(jobRes)
  } finally {
    loading.value = false
  }
}

async function retrieve() {
  if (!query.value.trim()) return
  retrieving.value = true
  try {
    const response = await api.legalKb.retrieve({ query: query.value, top_k: 5 })
    const results = Array.isArray(response?.results)
      ? response.results
      : Array.isArray(response)
        ? response
        : []
    retrievalAnswer.value = response?.answer || ''
    retrievalProvider.value = response?.provider || ''
    retrievalModel.value = response?.model || ''
    retrievalCitations.value = Array.isArray(response?.citations)
      ? response.citations
      : results.map((item, index) => ({
          index: index + 1,
          id: item.id,
          source_type: item.source_type,
          object_id: item.object_id,
          title: item.title,
          score: item.score,
          excerpt: item.excerpt || item.text?.slice(0, 600),
          metadata: item.metadata || {},
        }))
    retrievalResults.value = results
  } finally {
    retrieving.value = false
  }
}

async function handleRowAction(key, row) {
  if (key === 'ingest') {
    await api.legalKb.ingestDocument(row.id)
    await loadData()
  }
}

function normalizeList(response) {
  return response?.results || response || []
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

const retrievalProviderLabel = computed(() => retrievalProvider.value ? '平台检索服务' : '本地检索')

onMounted(loadData)
</script>

<style scoped>
.quick-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.form-textarea {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.retrieval-item {
  border-bottom: var(--stroke) solid var(--line);
  padding-bottom: var(--space-1);
}

.retrieval-item span {
  float: right;
  color: var(--action);
  font-weight: var(--weight-strong);
}

.retrieval-item p {
  color: var(--ink-secondary);
  margin: var(--space-1) 0 0;
}

.rag-answer,
.citation-list,
.raw-results {
  border-top: var(--stroke) solid var(--line);
  padding-top: var(--space-2);
}

.rag-answer {
  background: var(--surface-muted);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-panel);
  padding: var(--space-2);
}

.rag-answer__header,
.citation-item__header {
  align-items: flex-start;
  display: flex;
  gap: var(--space-1);
  justify-content: space-between;
}

.rag-answer__header span,
.citation-item__header span {
  color: var(--ink-secondary);
  flex: 0 0 auto;
  font-size: var(--text-caption);
}

.rag-answer p {
  color: var(--ink-secondary);
  margin: var(--space-1) 0 0;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
}

.citation-list h4,
.raw-results h4 {
  color: var(--ink);
  font-size: var(--text-caption);
  margin: 0 0 var(--space-1);
}

.citation-item {
  border-bottom: var(--stroke) solid var(--line);
  padding: var(--space-1) 0;
}

.citation-item p {
  color: var(--ink-secondary);
  display: -webkit-box;
  margin: var(--space-1) 0 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}
</style>
