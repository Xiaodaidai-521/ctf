import client from '@/api'

// Keep endpoint ownership in the existing client. Read every authorised page;
// an incomplete response fails rather than becoming an empty management list.
export async function collectManagementRows(read, params = {}) {
  const rows = []
  for (let page = 1; page <= 100; page++) {
    const payload = await read({ ...params, page })
    const items = Array.isArray(payload) ? payload : payload?.results
    if (!Array.isArray(items)) throw new Error('航线资料尚未完整读取。')
    rows.push(...items)
    if (Array.isArray(payload) || !payload.next) return rows
    if (!items.length) throw new Error('航线资料尚未完整读取。')
  }
  throw new Error('航线资料过多，尚未完整读取。')
}

export function createPathManagementApi(service = client) {
  return {
    list: params => collectManagementRows(p => service.learningPaths.list(p), params),
    detail: id => service.learningPaths.detail(id),
    modules: id => collectManagementRows(p => service.pathModules.list(p), { learning_path: id }),
    challenges: () => collectManagementRows(p => service.challenge.getChallenges(p), { is_active: true }),
    categories: () => collectManagementRows(p => service.challenge.getCategories(p)),
    delete: id => service.learningPaths.delete(id),
    create: data => service.learningPaths.create(data),
    update: (id, data) => service.learningPaths.update(id, data),
    createModule: data => service.pathModules.create(data),
    updateModule: (id, data) => service.pathModules.update(id, data),
  }
}

export default createPathManagementApi()
