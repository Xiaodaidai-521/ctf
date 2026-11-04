import axios from 'axios'

// Staff-only governance transport. No redirects, local storage or student evidence API changes.
const client = axios.create({ baseURL: '/api', timeout: 30000, withCredentials: true,
  xsrfCookieName: 'csrftoken', xsrfHeaderName: 'X-CSRFToken' })
const segment = value => encodeURIComponent(String(value))
const get = async (path, params, signal) => (await client.get(path, { params, signal })).data
async function post(path, body, signal, timeout = 30000) {
  await get('/users/csrf/', undefined, signal)
  return (await client.post(path, body, { signal, timeout })).data
}
export const governanceKnowledgeApi = {
  documents: (params, signal) => get('/legal-kb/documents/', params, signal),
  documentDetail: (id, signal) => get(`/legal-kb/documents/${segment(id)}/`, undefined, signal),
  clauses: (params, signal) => get('/legal-kb/clauses/', params, signal),
  jobs: (params, signal) => get('/legal-kb/ingestion-jobs/', params, signal),
  embeddings: (params, signal) => get('/legal-kb/embeddings/', params, signal),
  retrievalLogs: (params, signal) => get('/legal-kb/retrieval-logs/', params, signal),
  retrieve: (body, signal) => post('/legal-kb/retrieve/', body, signal),
  indexDocument: (id, signal) => post(`/legal-kb/documents/${segment(id)}/ingest/`, {}, signal, 180000),
  grant: (body, signal) => post('/teaching-knowledge/grants/', body, signal),
  deleteMaterial: async (id, body, signal) => {
    await get('/users/csrf/', undefined, signal)
    return (await client.delete(`/teaching-knowledge/materials/${segment(id)}/`, { data: body, signal })).data
  },
}
