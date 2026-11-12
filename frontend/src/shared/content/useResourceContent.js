import { reactive } from 'vue'
import { onAccountClear } from '../state/accountScope.js'
import { uiSnapshot } from '../state/retention.js'
import { createContentApi, requireContentRole } from './api.js'
import { contentError, readList, saveResourceFile } from './presentation.js'

export function useResourceContent(role, service = createContentApi(role), saveFile = saveResourceFile) {
  requireContentRole(role)
  const state = reactive({ items: [], total: null, hasNext: false, page: 1, pageSize: 20, status: 'pending', counts: {}, countsError: '', filters: { search: '', resource_type: '', category: '', ordering: '-created_at' }, loading: false, listError: '', error: '', success: '', review: null, note: '', preview: null, uploadOpen: false, busy: false, downloading: false, selectionLoading: false, selectionError: '' })
  const retention = uiSnapshot('content:resources', role)
  const saved = retention.read()
  if (saved) { state.page = saved.page; state.status = saved.status; state.filters = saved.filters }
  const remember = () => retention.write({ page: state.page, status: state.status, filters: { search: state.filters.search, resource_type: state.filters.resource_type, category: state.filters.category, ordering: state.filters.ordering } })
  let generation = 0, countsGeneration = 0, selectionGeneration = 0, alive = true
  const unsubscribe = onAccountClear(destroy)
  async function load() {
    const current = ++generation
    ++countsGeneration
    state.loading = true; state.listError = ''
    const params = { page: state.page, page_size: state.pageSize, ...Object.fromEntries(Object.entries(state.filters).filter(([, value]) => value !== '')) }
    if (state.status !== 'all') params.status = state.status
    try {
      const result = readList(await service.resources(params))
      if (!alive || current !== generation) return false
      state.items = result.items; state.total = result.total; state.hasNext = result.hasNext
      return true
    } catch (error) {
      if (alive && current === generation) { state.listError = contentError(error, role, '读取资源'); state.counts = {} }
      return false
    } finally { if (alive && current === generation) state.loading = false }
  }
  async function loadCounts() {
    const current = ++countsGeneration
    state.countsError = ''
    try {
      const values = await Promise.all(['pending', 'approved', 'rejected', 'all'].map(async status => {
        const params = { page: 1, page_size: 1 }
        if (status !== 'all') params.status = status
        return [status, readList(await service.resources(params)).total]
      }))
      if (alive && current === countsGeneration) state.counts = Object.fromEntries(values)
    } catch (error) { if (alive && current === countsGeneration) { state.counts = {}; state.countsError = contentError(error, role, '读取资源数量') } }
  }
  async function refresh() { const loaded = await load(); if (loaded) await loadCounts(); return loaded }
  async function applyQuery(query = {}) {
    const current = ++selectionGeneration
    const status = Array.isArray(query.status) ? query.status[0] : query.status
    if (Object.hasOwn(query, 'status')) {
      const nextStatus = ['pending', 'approved', 'rejected', 'all'].includes(status) ? status : 'pending'
      if (nextStatus !== state.status) state.page = 1
      state.status = nextStatus
    }
    if (Object.hasOwn(query, 'resource')) state.page = 1
    state.preview = null; state.selectionError = ''; state.selectionLoading = false
    const target = Array.isArray(query.resource) ? query.resource[0] : query.resource
    const loaded = await refresh()
    if (!alive || current !== selectionGeneration || !target) return
    if (!loaded) { state.selectionError = '暂时无法查看所选资源，请先恢复列表访问后重试。'; return }
    state.selectionLoading = true
    try {
      let items = state.items, hasNext = state.hasNext, page = 1
      while (alive && current === selectionGeneration) {
        const match = items.find(item => String(item.id) === String(target))
        if (match) { state.preview = match; return }
        if (!hasNext) { state.selectionError = '所选资源不在当前审核状态的可访问列表中，请核对筛选或联系管理员。'; return }
        if (page >= 50) { state.selectionError = '所选资源尚未在已读取的列表中找到，请继续翻页查找。'; return }
        const params = { page: ++page, page_size: state.pageSize, ...Object.fromEntries(Object.entries(state.filters).filter(([, value]) => value !== '')) }
        if (state.status !== 'all') params.status = state.status
        const result = readList(await service.resources(params))
        items = result.items; hasNext = result.hasNext
      }
    } catch (error) { if (alive && current === selectionGeneration) state.selectionError = contentError(error, role, '查看所选资源') }
    finally { if (alive && current === selectionGeneration) state.selectionLoading = false }
  }
  function filter() { ++selectionGeneration; state.selectionLoading = false; state.selectionError = ''; state.page = 1; return load() }
  function selectStatus(status) { state.status = status; return filter() }
  function changePage(page) { if (page < 1 || state.loading) return; state.page = page; return load() }
  function review(item, action) { if (role !== 'admin') return; state.review = { item, action }; state.note = ''; state.error = ''; state.success = '' }
  function closeReview() { if (!state.busy) { state.review = null; state.error = '' } }
  async function confirmReview() {
    if (role !== 'admin' || state.busy || !state.review) return
    state.error = ''; state.success = ''
    if (state.review.action === 'rejected' && !state.note.trim()) { state.error = '请输入拒绝原因。'; return }
    state.busy = true
    try {
      await service.reviewResource(state.review.item.id, state.review.action, state.note)
      if (!alive) return
      state.success = '审核已完成。'; state.review = null
      if (state.items.length === 1 && state.page > 1) state.page--
      await refresh()
    } catch (error) { if (alive) state.error = contentError(error, role, '审核资源') }
    finally { if (alive) state.busy = false }
  }
  async function upload(data) {
    if (state.busy) return
    state.busy = true; state.error = ''; state.success = ''
    try {
      const uploaded = await service.uploadResource(data)
      if (!alive) return
      state.success = uploaded?.resource?.protection?.file?.storage === 'encrypted' ? '资源文件已加密保存，等待管理员审核。' : '资源已上传，等待管理员审核。'; state.uploadOpen = false
      await refresh()
    } catch (error) { if (alive) state.error = contentError(error, role, '上传资源') }
    finally { if (alive) state.busy = false }
  }
  async function download() {
    if (!state.preview || state.downloading) return
    const item = state.preview
    state.downloading = true; state.error = ''; state.success = ''
    try {
      const response = await service.downloadResource(item.id)
      if (!alive || state.preview !== item) return
      saveFile(response, item)
      state.success = '文件已开始下载。'
    } catch (error) { if (alive) state.error = contentError(error, role, '下载资源') }
    finally { if (alive) state.downloading = false }
  }
  function destroy() {
    if (!alive) return
    remember(); alive = false; ++generation; ++countsGeneration; ++selectionGeneration; unsubscribe()
    state.items = []; state.counts = {}; state.preview = null; state.review = null; state.note = ''; state.uploadOpen = false
    state.loading = false; state.busy = false; state.downloading = false; state.selectionLoading = false
  }
  return { state, refresh, applyQuery, load, loadCounts, filter, selectStatus, changePage, review, closeReview, confirmReview, upload, download, destroy }
}
