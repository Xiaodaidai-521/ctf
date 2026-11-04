import api from '@/api'
import { staffKnowledgeApi } from '@/shared/knowledge/staffApi.js'
import { listValue } from '../governance/data.js'
export const foundationApi = {
  documents: async (params, signal) => { const data = await staffKnowledgeApi.documents(params, signal); listValue(data); return data },
  jobs: async (params, signal) => { const data = await staffKnowledgeApi.jobs(params, signal); listValue(data); return data },
  clauses: async (params, signal) => { const data = await staffKnowledgeApi.clauses(params, signal); listValue(data); return data },
  embeddings: async (params, signal) => { const data = await staffKnowledgeApi.embeddings(params, signal); listValue(data); return data },
  logs: async (params, signal) => { const data = await staffKnowledgeApi.retrievalLogs(params, signal); listValue(data); return data },
  materials: async signal => { const data = await staffKnowledgeApi.materials(signal); listValue(data); return data },
  people: async () => {
    const data = await api.user.adminUsers({ page_size: 100 })
    return listValue(Array.isArray(data) ? data : data?.results ?? data?.users)
  },
  catalog: async () => {
    const data = await api.learningMap.teacherCatalog()
    if (!data?.version || !data?.label) throw new Error('Unreadable catalog')
    return data
  },
  documentDetail: (...args) => staffKnowledgeApi.documentDetail(...args),
  inspect: (...args) => staffKnowledgeApi.inspect(...args),
  retrieve: (...args) => staffKnowledgeApi.retrieve(...args),
  indexDocument: (...args) => staffKnowledgeApi.indexDocument(...args),
  grant: (...args) => staffKnowledgeApi.grant(...args),
}
