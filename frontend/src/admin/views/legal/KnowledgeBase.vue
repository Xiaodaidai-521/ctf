<template>
  <LegalWorkspace
    title="知识库浏览"
    subtitle="浏览法规、条款、案例、模板与检索日志，支撑 RAG 合规分析。"
    table-title="法规文档"
    aside-title="知识检索"
    :metrics="metrics"
    :columns="columns"
    :rows="documents"
    :loading="loading"
    :row-actions="[{ key: 'ingest', label: '向量化' }]"
    :actions="[{ key: 'retrieve', label: retrieving ? '解析中...' : '检索', primary: true }]"
    @refresh="loadData"
    @action="retrieve"
    @row-action="handleRowAction"
  >
    <template #aside>
      <div class="quick-form">
        <textarea v-model="query" class="form-textarea" rows="5" placeholder="输入检索问题"></textarea>
        <div v-if="retrievalAnswer" class="rag-answer">
          <div class="rag-answer__header">
            <strong>模型解析</strong>
            <span v-if="retrievalProvider || retrievalModel">{{ retrievalProvider }} / {{ retrievalModel }}</span>
          </div>
          <p>{{ retrievalAnswer }}</p>
        </div>
        <div v-if="retrievalCitations.length" class="citation-list">
          <h4>引用依据</h4>
          <div v-for="item in retrievalCitations" :key="item.id || item.index" class="citation-item">
            <div class="citation-item__header">
              <strong>[{{ item.index }}] {{ item.title }}</strong>
              <span>{{ item.source_type }} · {{ item.score }}</span>
            </div>
            <p>{{ item.excerpt }}</p>
          </div>
        </div>
        <div v-if="retrievalResults.length" class="raw-results">
          <h4>原始召回</h4>
          <div v-for="item in retrievalResults" :key="item.id" class="retrieval-item">
            <strong>{{ item.title }}</strong>
            <span>{{ item.score }}</span>
            <p>{{ item.text?.slice(0, 120) }}</p>
          </div>
        </div>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

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
  { key: 'document_type', label: '类型', badge: true },
  { key: 'status', label: '状态', badge: true },
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
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(loadData)
</script>

<style scoped>
.quick-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.retrieval-item {
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 10px;
}

.retrieval-item span {
  float: right;
  color: #2563eb;
  font-weight: 700;
}

.retrieval-item p {
  color: #64748b;
  margin: 6px 0 0;
}

.rag-answer,
.citation-list,
.raw-results {
  border-top: 1px solid #e2e8f0;
  padding-top: 12px;
}

.rag-answer {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
}

.rag-answer__header,
.citation-item__header {
  align-items: flex-start;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.rag-answer__header span,
.citation-item__header span {
  color: #64748b;
  flex: 0 0 auto;
  font-size: 12px;
}

.rag-answer p {
  color: #334155;
  margin: 8px 0 0;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
}

.citation-list h4,
.raw-results h4 {
  color: #0f172a;
  font-size: 14px;
  margin: 0 0 8px;
}

.citation-item {
  border-bottom: 1px solid #e2e8f0;
  padding: 10px 0;
}

.citation-item p {
  color: #64748b;
  display: -webkit-box;
  margin: 6px 0 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}
</style>
