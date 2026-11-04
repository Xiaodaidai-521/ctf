import axios from 'axios'

// Existing read-only catalog endpoint; no grant expansion or task-key-to-ID guess.
// Keep cancellation and the private page's error handling, without redirect/storage
// side effects from the general-purpose API client.
const client = axios.create({ baseURL: '/api', timeout: 30000, withCredentials: true })
export async function readMaterialCatalog(version, signal) {
  const { data } = await client.get('/learning-map/catalog/', { params: version ? { version } : {}, signal })
  return typeof data.version === 'string' && typeof data.label === 'string' && data.label.trim()
    ? { value: data.version, label: data.label } : null
}

export async function readMaterialTaskNames(version, signal) {
  // This endpoint intentionally keeps its course-owner permission. A 403 is
  // an unavailable name lookup, never a reason to try a broader/student route.
  const { data } = await client.get('/learning-map/teacher/catalog/', { params: { version }, signal })
  if (data.version !== version) return []
  return (data.capabilities || []).flatMap(capability => capability.tasks || [])
    .filter(task => typeof task.title === 'string' && task.title.trim())
    .map(task => ({ key: task.task_key, version: task.version, label: task.title }))
}
