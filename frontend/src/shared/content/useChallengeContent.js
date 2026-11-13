import { reactive } from 'vue'
import { onAccountClear } from '../state/accountScope.js'
import { uiSnapshot } from '../state/retention.js'
import { createContentApi, requireContentRole } from './api.js'
import { challengeForm, contentError, readList } from './presentation.js'

export function useChallengeContent(role, service = createContentApi(role)) {
  requireContentRole(role)
  const state = reactive({ items: [], total: null, hasNext: false, page: 1, pageSize: 20, loading: false, listError: '', categories: [], categoriesError: '', categoriesLoading: false, filters: { category: '', difficulty: '', is_active: '' }, editor: null, form: challengeForm(), editingId: null, busy: false, detailLoading: false, error: '', success: '' })
  const retention = uiSnapshot('content:challenges', role)
  const saved = retention.read()
  if (saved) { state.page = saved.page; state.filters = saved.filters }
  const remember = () => retention.write({ page: state.page, filters: { category: state.filters.category, difficulty: state.filters.difficulty, is_active: state.filters.is_active } })
  let listGeneration = 0, detailGeneration = 0, alive = true
  const unsubscribe = onAccountClear(destroy)
  async function loadCategories() {
    state.categoriesLoading = true
    state.categoriesError = ''
    try {
      const response = await service.categories()
      const items = Array.isArray(response) ? response : response?.results
      if (!Array.isArray(items)) throw new Error('Invalid categories')
      if (alive) state.categories = items
    } catch (error) { if (alive) state.categoriesError = contentError(error, role, '读取分类') }
    finally { if (alive) state.categoriesLoading = false }
  }
  async function load() {
    const generation = ++listGeneration
    state.loading = true
    state.listError = ''
    const params = { page: state.page, page_size: state.pageSize }
    for (const key of ['category', 'difficulty', 'is_active']) if (state.filters[key] !== '') params[key] = state.filters[key]
    try {
      const result = readList(await service.challenges(params))
      if (!alive || generation !== listGeneration) return
      state.items = result.items; state.total = result.total; state.hasNext = result.hasNext
    } catch (error) { if (alive && generation === listGeneration) state.listError = contentError(error, role, '读取题目') }
    finally { if (alive && generation === listGeneration) state.loading = false }
  }
  function filter() { state.page = 1; return load() }
  function changePage(page) { if (page < 1 || state.loading) return; state.page = page; return load() }
  function create() { ++detailGeneration; state.form = challengeForm(); state.editingId = null; state.editor = 'create'; state.error = ''; state.success = '' }
  async function edit(item) {
    const generation = ++detailGeneration
    state.detailLoading = true; state.error = ''; state.success = ''
    try {
      const detail = await service.challengeDetail(item.id)
      if (!alive || generation !== detailGeneration) return
      state.form = challengeForm(detail); state.form.flag = ''; state.editingId = item.id; state.editor = 'edit'
    } catch (error) { if (alive && generation === detailGeneration) state.error = contentError(error, role, '读取题目详情') }
    finally { if (alive && generation === detailGeneration) state.detailLoading = false }
  }
  function close() { if (!state.busy) { ++detailGeneration; state.editor = null; state.error = '' } }
  async function save() {
    if (state.busy || !state.editor) return
    state.error = ''; state.success = ''
    if (!state.form.title.trim() || (state.editor === 'create' && !state.form.flag.trim()) || state.form.category == null || !state.form.description.trim()) { state.error = state.editor === 'create' ? '请填写标题、分类、题目描述和答案。' : '请填写标题、分类和题目描述。'; return }
    state.busy = true
    try {
      const payload = challengeForm(state.form)
      if (state.editor === 'edit' && !payload.flag) delete payload.flag
      if (state.editor === 'edit') await service.updateChallenge(state.editingId, payload)
      else await service.createChallenge(payload)
      if (!alive) return
      state.success = '题目内容已保存，请另行核对答案是否生效。'; state.editor = null
      await load()
    } catch (error) { if (alive) state.error = contentError(error, role, '保存题目') }
    finally { if (alive) state.busy = false }
  }
  async function remove(item, confirmDelete = message => window.confirm(message)) {
    if (state.busy || !confirmDelete(`确定删除题目“${item.title}”吗？此操作不可恢复。`)) return
    state.busy = true; state.error = ''; state.success = ''
    try {
      await service.deleteChallenge(item.id)
      if (!alive) return
      state.success = '题目已删除。'
      if (state.items.length === 1 && state.page > 1) state.page--
      await load()
    } catch (error) { if (alive) state.error = contentError(error, role, '删除题目') }
    finally { if (alive) state.busy = false }
  }
  function destroy() {
    if (!alive) return
    remember(); alive = false; ++listGeneration; ++detailGeneration; unsubscribe()
    state.items = []; state.categories = []; state.form = challengeForm(); state.editor = null; state.editingId = null
    state.loading = false; state.detailLoading = false; state.busy = false
  }
  return { state, load, loadCategories, filter, changePage, create, edit, close, save, remove, destroy }
}
