<template>
  <main v-if="managing" class="knowledge-library">
    <header class="library-header">
      <div>
        <h1>{{ user.userInfo?.role === 'admin' ? names.foundation : names.knowledge }}</h1>
        <p class="library-subtitle">查找资料，核对出处与原文。</p>
      </div>
      <div class="library-actions">
        <router-link :to="resourcePath" class="library-link">返回{{ names.resourceReview }}</router-link>
        <template v-if="managing">
          <router-link :to="user.userInfo?.role === 'teacher' ? '/teacher/materials' : '/admin/legal/kb/authorization'" class="library-link">{{ user.userInfo?.role === 'teacher' ? names.materials : '授权监督' }}</router-link>
          <a-button :disabled="state.busy || paused" @click="state.uploadOpen = !state.uploadOpen">上传文档入库</a-button>
        </template>
      </div>
    </header>

    <ContentAreaNav v-if="user.userInfo?.role === 'teacher'" />
    <!-- Keep the picker mounted while a native file dialog blurs the window. Only a fresh
         selection may resume the cleared page; old forms and requests are never restored. -->
    <input v-if="managing" ref="fileInput" class="library-file-input" type="file"
      accept=".md,.markdown,.txt,.text,.html,.htm,.csv,.json,.log,.docx,.pdf,.pptx,.xlsx" @change="chooseFile" />

    <a-alert v-if="paused" type="warning" class="library-notice">
      <template #title>请重新加载资料</template>
      未提交的内容已清空，请重新填写。
      <div class="library-actions library-notice-actions">
        <a-button v-if="sessionChanged" size="small" @click="privacy.reload">刷新页面</a-button>
        <a-button v-else size="small" @click="resume">重新加载</a-button>
      </div>
    </a-alert>
    <a-alert v-if="state.error" type="error" class="library-notice" role="alert">{{ libraryError(state.error) }}</a-alert>

    <section v-if="managing && !paused && state.uploadOpen" class="library-panel library-upload" aria-labelledby="upload-heading">
      <div class="library-section-heading">
        <div><h2 id="upload-heading">上传文档入库</h2><p>上传后可在“法律库”的“上传文档”中查找。</p></div>
        <a-button type="text" :disabled="state.busy" @click="closeUpload">收起</a-button>
      </div>
      <a-alert type="info">如需向学生发布课程材料，请使用“{{ names.materials }}”。</a-alert>
      <form class="library-upload-form" @submit.prevent="controller.upload">
        <div class="library-file-row">
          <a-button :disabled="state.busy" @click="fileInput?.click()">选择文档</a-button>
          <span>{{ state.file ? `${state.file.name} · ${(state.file.size / 1024).toFixed(1)} KB` : '尚未选择文件' }}</span>
        </div>
        <label>文档标题<a-input v-model="state.uploadTitle" :max-length="300" placeholder="留空使用文件名" :disabled="state.busy" /></label>
        <label>可见范围
          <a-select v-model="state.uploadVisibility" :disabled="state.busy">
            <a-option value="internal">内部资料（不向学生开放）</a-option>
            <a-option value="learner">学习资料（发布后按课程开放）</a-option>
            <a-option v-if="user.userInfo?.role === 'admin'" value="staff">仅后台人员</a-option>
          </a-select>
        </label>
        <p class="library-muted library-full">支持文本文档、PDF、Office 等，不支持视频；文件大小默认上限 20 MB。</p>
        <a-button html-type="submit" type="primary" :loading="state.busy" :disabled="!state.file">上传文档</a-button>
      </form>
      <a-alert v-if="state.uploadResult" :type="state.uploadResult.status === 'completed' ? 'success' : 'error'" class="library-notice" role="status">
        <template #title>{{ state.uploadResult.status === 'completed' ? '文档已入库' : '文档入库未完成' }}</template>
        <p>{{ state.uploadResult.title }}</p>
        <p v-if="state.uploadResult.error_message">{{ libraryError(state.uploadResult.error_message) }}</p>
        <a-button v-if="state.uploadResult.status === 'completed'" size="small" @click="changeGroup('legal')">查看已上传资料</a-button>
      </a-alert>
      <p class="library-muted">上传中断时，请先核对资料列表，避免重复上传。</p>
    </section>

    <p v-if="deletionState.message" class="library-muted" role="status">{{ deletionState.message }} <a-button v-if="deletionState.uncertain" @click="resume">重新加载</a-button></p>
    <MaterialDeleteDialog v-if="deletionState.target && !paused" :state="deletionState" @close="deletion.close" @confirm="deletion.confirm" @reload="resume" />
    <section class="library-panel library-browser" aria-label="按来源浏览知识资料">
      <a-tabs :active-key="state.group" @change="changeGroup">
        <a-tab-pane key="teaching" title="教学材料" />
        <a-tab-pane key="legal" title="法律库" />
        <a-tab-pane key="platform" title="平台资料" />
      </a-tabs>
      <div class="library-browser-body">
        <div class="library-section-heading">
          <div><h2>{{ groupTitle }}</h2><p>{{ groupDescription }}</p></div>
          <router-link v-if="user.userInfo?.role === 'admin' && state.group === 'legal'" to="/admin/legal/kb/tools" class="library-link">法律库管理</router-link>
        </div>
        <template v-if="!paused">
          <form class="library-search" @submit.prevent="controller.search()">
            <label class="library-query">{{ state.group === 'teaching' ? '标题或正文关键词' : '关键词' }}
              <a-input v-model="state.query" :disabled="state.busy" :max-length="500" allow-clear autocomplete="off"
                placeholder="输入标题或关键词查找资料" />
            </label>
            <label v-if="managing && state.group !== 'teaching'" class="library-source-filter">来源类型
              <a-select v-model="state.sourceType" :disabled="state.busy">
                <a-option value="">全部来源</a-option>
                <template v-if="state.group === 'legal'">
                  <a-option value="legal_document">法律文档</a-option><a-option value="document">上传文档</a-option>
                </template>
                <template v-else>
                  <a-option value="article">文章</a-option><a-option value="resource">资源</a-option><a-option value="knowledge_concept">知识点</a-option>
                </template>
              </a-select>
            </label>
            <a-button :type="state.uploadOpen ? 'secondary' : 'primary'" html-type="submit" :loading="state.busy">搜索资料</a-button>
            <a-button v-if="managing" :disabled="state.busy" @click="resetSearch">重置</a-button>
          </form>
          <div class="library-results-heading" aria-live="polite">
            <span v-if="state.busy">正在加载，请稍候…</span>
            <span v-else-if="state.searched">搜索结果 · {{ state.count }} 项<span v-if="managing && state.group !== 'teaching'"> · 第 {{ state.page }} 页</span></span>
            <span v-else>请选择来源或输入关键词</span>
          </div>
          <div class="library-content" :class="{ 'library-content-split': state.detail }">
            <div class="library-result-list" :aria-busy="state.busy">
              <a-empty v-if="!state.rows.length && !state.busy" :description="emptyNotice" />
              <article v-for="row in state.rows" :key="row.id || row.material_id" class="library-result">
                <div class="library-result-tags">
                  <a-tag size="small">{{ row.source_label || classLabel(row.material_class) || '教学材料' }}</a-tag>
                  <span v-if="state.group === 'teaching'" class="library-muted">{{ statusLabel(row.review_status) }}</span>
                  <span v-if="row.chunk_count !== undefined" class="library-muted">{{ row.chunk_count }} {{ row.source_type === 'legal_document' ? '条条款' : '个段落' }}</span>
                </div>
                <h3><button class="library-title-button" type="button" :disabled="state.busy" @click="controller.inspect(row)">{{ row.title }}</button></h3>
                <p v-if="row.excerpt" class="library-excerpt">{{ sourceText(row.excerpt, row.source_type) }}</p>
                <p v-if="state.group === 'teaching' && Number.isSafeInteger(row.revision)" class="library-provenance">第 {{ row.revision }} 版</p>
                <p v-else-if="formatLocator(row.locator)" class="library-provenance">{{ formatLocator(row.locator) }}</p>
                <div class="library-result-footer">
                  <a-button size="small" type="text" :disabled="state.busy || deletionState.busy" @click="controller.inspect(row)">查看出处与段落</a-button>
                  <a-button v-if="state.group === 'teaching'" size="small" type="text" status="danger" :disabled="state.busy || deletionState.busy || deletionState.uncertain" @click="deletion.open(row)">删除材料</a-button>
                </div>
              </article>
              <div v-if="managing && state.group !== 'teaching' && state.searched" class="library-pagination">
                <a-button :disabled="state.busy || !state.previous" @click="controller.search(state.page - 1)">上一页</a-button>
                <span>第 {{ state.page }} 页</span>
                <a-button :disabled="state.busy || !state.next" @click="controller.search(state.page + 1)">下一页</a-button>
              </div>
            </div>

            <section v-if="state.detail" class="library-detail" aria-label="资料详情" tabindex="0">
              <div class="library-section-heading">
                <div><h2>{{ state.detail.title }}</h2></div>
                <a-button size="small" @click="state.detail = null">关闭详情</a-button>
              </div>
              <template v-if="managing">
                <dl class="library-meta">
                  <dt>来源类型</dt><dd>{{ state.detail.source_label || classLabel(state.detail.material_class) }}</dd>
                  <template v-if="state.group === 'teaching'">
                    <template v-if="Number.isSafeInteger(state.detail.revision)"><dt>材料版本</dt><dd>第 {{ state.detail.revision }} 版</dd></template>
                    <dt>来源机构 / 版本</dt><dd>{{ state.detail.publisher }} / {{ state.detail.source_version }}</dd>
                    <dt>适用范围</dt><dd>{{ state.detail.applicability || '未提供' }}</dd>
                    <dt>许可 / 署名</dt><dd>{{ state.detail.license_id }} / {{ state.detail.attribution_text }}</dd>
                  </template>
                  <template v-else-if="formatLocator(state.detail.locator)">
                    <dt>所在章节 / 段落</dt><dd>{{ formatLocator(state.detail.locator) }}</dd>
                  </template>
                </dl>
                <div class="library-actions">
                  <router-link v-if="internalSourcePath" :to="internalSourcePath" class="library-link">查看原文</router-link>
                  <a v-if="externalSourceUrl" :href="externalSourceUrl" target="_blank" rel="noopener noreferrer" class="library-link">查看外部来源</a>
                  <router-link v-if="state.group === 'teaching'" :to="user.userInfo?.role === 'teacher' ? '/teacher/materials' : '/admin/legal/kb/authorization'" class="library-link">{{ user.userInfo?.role === 'teacher' ? names.materials : '授权监督' }}</router-link>
                </div>
                <div v-if="user.userInfo?.role === 'teacher'" class="library-actions teaching-actions">
                  <a-button :disabled="!canTransfer" @click="prepareMaterial">加入材料草稿</a-button>
                  <a-button :disabled="!canTransfer" @click="preparePath">准备学习任务</a-button>
                  <p class="library-muted">先核对原文与许可，再补充教学目标、练习和检验；不会直接向学生发布。只有段落时会标明摘录，不当作完整原文。</p>
                </div>
                <p v-if="transferMessage" class="library-muted" role="status">{{ transferMessage }}</p>
                <details v-if="state.detail.full_text || state.detail.source_snapshot" class="library-chunk">
                  <summary>完整原文</summary>
                  <pre class="library-source">{{ state.detail.full_text || state.detail.source_snapshot }}</pre>
                </details>
                <h3 class="library-chunks-title">{{ state.detail.source_type === 'legal_document' ? '条款' : '段落' }} · {{ state.detail.chunks?.length || 0 }}</h3>
                <p v-if="!state.detail.chunks?.length" class="library-muted">暂无可查看的段落。</p>
                <details v-for="(chunk, index) in state.detail.chunks" :key="chunk.id || chunk.chunk_ref" class="library-chunk" :open="index === 0">
                  <summary>{{ formatLocator({ heading_path: chunk.heading_path }) || formatLocator(chunk.locator) || `段落 ${index + 1}` }}</summary>
                  <pre class="library-source">{{ sourceText(chunk.text, state.detail.source_type) }}</pre>
                </details>
              </template>
            </section>
          </div>
        </template>
      </div>
    </section>
  </main>
</template>

<script setup>
import { names } from '@/shared/navigation/names'

import { computed, onMounted, reactive, ref } from 'vue'
import { useUserStore } from '@/store/user'
import { useRouter } from 'vue-router'
import ContentAreaNav from '@/shared/knowledge/ContentAreaNav.vue'
import MaterialDeleteDialog from '@/shared/knowledge/MaterialDeleteDialog.vue'
import { createMaterialDeletion, initialMaterialDeletion } from '@/shared/knowledge/materialDeletion.js'
import { prepareTeachingTransfer, teachingSource } from '@/shared/knowledge/teachingTransfer.js'
import { staffKnowledgeApi as knowledgeApi } from '@/shared/knowledge/staffApi.js'
import { usePrivatePage } from './usePrivatePage.js'
import { canManageLibrary, classLabel, createLibraryController, formatLocator, initialLibraryState, libraryError, safeSourceLink, sourceText, statusLabel } from './libraryController.js'
import './learningKnowledge.css'

const user = useUserStore()
const router = useRouter()
const transferMessage = ref('')
const canTransfer = computed(() => Boolean(teachingSource(state.detail)))
function transfer(kind, path) {
  try {
    prepareTeachingTransfer(user.userInfo, kind, state.detail)
    router.push({ path, query: { from: 'knowledge' } })
  } catch (error) { transferMessage.value = error.message }
}
const prepareMaterial = () => transfer('material', '/teacher/materials')
const preparePath = () => transfer('path', '/teacher/learning-paths/new')
const state = reactive(initialLibraryState())
const deletionState = reactive(initialMaterialDeletion())
const fileInput = ref(null)
const managing = computed(() => canManageLibrary(user.userInfo?.role))
const resourcePath = computed(() => user.userInfo?.role === 'teacher' ? '/teacher/resources' : user.userInfo?.role === 'admin' ? '/admin/resources' : '/resources')
const privacy = usePrivatePage(() => {
  controller.clear()
  deletion.clear()
  if (fileInput.value) fileInput.value.value = ''
})
const { paused, sessionChanged } = privacy
const controller = createLibraryController({ state, privacy, api: knowledgeApi, getRole: () => user.userInfo?.role })
const deletion = createMaterialDeletion({ state: deletionState, privacy, api: knowledgeApi, getRole: () => user.userInfo?.role,
  reload: async (ticket, id) => {
    state.detail = null
    const result = await knowledgeApi.materialSearch(state.query.trim(), ticket.signal)
    if (!ticket.isCurrent()) return
    if (!Array.isArray(result.results) || result.results.some(row => row.material_id === id)) throw new Error('列表尚未更新')
    state.rows = result.results; state.count = result.results.length; state.searched = true
  },
})
const groupTitle = computed(() => ({ teaching: '课程材料', legal: '法律文档与上传资料', platform: '文章、资源与知识点' }[state.group]))
const groupDescription = computed(() => ({
  teaching: '查找课程材料，查看版本与出处。',
  legal: '查找法律条款或已上传的文档。',
  platform: '查找平台资料，打开原文核对。',
}[state.group]))
const emptyNotice = computed(() => state.searched ? '没有找到相关资料，请调整关键词或来源。' : '选择来源后搜索资料')
const internalSourcePath = computed(() => {
  if (!managing.value) return ''
  const path = safeSourceLink(state.detail?.source_path)
  return path.startsWith('/') ? path : ''
})
const externalSourceUrl = computed(() => {
  if (!managing.value) return ''
  const url = safeSourceLink(state.detail?.source_url)
  return /^https?:/.test(url) ? url : ''
})

function resume() {
  if (!managing.value || !privacy.resume()) return
  controller.search()
}
function changeGroup(group) {
  if (!managing.value || !['teaching', 'legal', 'platform'].includes(group)) return
  if (!privacy.resume()) return
  state.group = group
  controller.search()
}
function resetSearch() {
  deletion.clear()
  state.query = ''
  state.sourceType = ''
  controller.search()
}
function closeUpload() {
  state.uploadOpen = false
  state.file = null
  state.uploadTitle = ''
  state.uploadVisibility = 'internal'
  state.uploadResult = null
  if (fileInput.value) fileInput.value.value = ''
}
function chooseFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !managing.value || sessionChanged.value) return
  if (paused.value && !privacy.resume()) return
  state.uploadOpen = true
  state.file = file
  state.uploadResult = null
  state.error = ''
}
onMounted(resume)
</script>

<style scoped>
.knowledge-library { max-width:var(--page-width); margin:0 auto; padding:var(--space-4); color:var(--text-primary, var(--ink)); }
.library-header, .library-section-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:var(--space-2); }
.library-header { margin-bottom:var(--space-3); }
.library-header h1 { font-size:var(--text-section); letter-spacing:-.04em; margin:calc(var(--space-1) / 2) 0 var(--space-1); }
.library-eyebrow { margin:0; color:var(--action); font-size:var(--text-caption); font-weight: var(--weight-strong); letter-spacing:.09em; }
.library-subtitle, .library-section-heading p { color:var(--text-secondary, var(--ink-secondary)); line-height:1.75; margin:calc(var(--space-1) / 2) 0 0; }
.library-actions { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-1); }
.library-header > .library-actions { padding-top:var(--space-1); justify-content:flex-end; }
.library-link { color:var(--action); font-size:var(--text-caption); font-weight: var(--weight-strong); text-decoration:none; }
.library-link:hover { text-decoration:underline; }
.library-panel { background:var(--bg-card, var(--surface)); border:var(--stroke) solid var(--border-color, var(--line)); border-radius:var(--radius-control); }
.library-browser { overflow:hidden; }
.library-browser :deep(.arco-tabs-nav) { padding:calc(var(--space-1) / 2) var(--space-2) 0; background:var(--surface-muted); }
.library-browser :deep(.arco-tabs-content) { display:none; }
.library-browser-body, .library-upload { padding:var(--space-3); }
.library-section-heading h2 { font-size:var(--text-card); margin:0 0 calc(var(--space-1) / 2); line-height:1.5; overflow-wrap:anywhere; }
.library-section-heading { margin-bottom:var(--space-2); }
.library-notice { margin-bottom:var(--space-2); }
.library-notice-actions { margin-top:var(--space-1); }
.library-search { display:flex; align-items:flex-end; flex-wrap:wrap; gap:var(--space-1); }
.library-search label, .library-upload-form label { display:grid; gap:calc(var(--space-1) / 2); font-size:var(--text-caption); font-weight: var(--weight-strong); }
.library-query { flex:1; min-width:var(--row-value-width); }
.library-source-filter { width:var(--row-value-width); }
.library-muted { color:var(--text-secondary, var(--ink-secondary)); font-size:var(--text-caption); line-height:1.7; overflow-wrap:anywhere; }
.library-results-heading { display:flex; justify-content:space-between; flex-wrap:wrap; gap:var(--space-1); margin-top:var(--space-3); padding:var(--space-2) 0; border-top:var(--stroke) solid var(--border-color, var(--line)); font-size:var(--text-caption); }
.library-content { display:grid; grid-template-columns:minmax(0, 1fr); gap:var(--space-3); }
.library-content-split { grid-template-columns:minmax(var(--menu-width), 2fr) minmax(0, 3fr); }
.library-result-list { min-width:0; }
.library-result { padding:var(--space-2) 0; border-bottom:var(--stroke) solid var(--border-color, var(--line)); }
.library-result:first-of-type { padding-top:calc(var(--space-1) / 2); }
.library-result h3 { margin:var(--space-1) 0 var(--space-1); line-height:1.6; }
.library-title-button { border:0; padding:0; background:none; font:inherit; font-size:var(--text-body); color:inherit; cursor:pointer; text-align:left; overflow-wrap:anywhere; }
.library-title-button:hover { color:var(--action); }
.library-title-button:focus-visible { outline:calc(var(--stroke) * 2) solid var(--action); outline-offset:calc(var(--space-1) / 2); }
.library-result-tags { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-1); }
.library-excerpt { line-height:1.8; font-size:var(--text-caption); color:var(--text-secondary, var(--ink-secondary)); white-space:pre-wrap; overflow-wrap:anywhere; }
.library-provenance { font-size:var(--text-caption); line-height:1.7; color:var(--text-secondary, var(--ink-secondary)); overflow-wrap:anywhere; }
.library-result-footer { display:flex; justify-content:space-between; align-items:center; gap:var(--space-1); }
.library-source-text { color:var(--text-muted, var(--ink-secondary)); font-size:var(--text-caption); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.library-result-footer :deep(.arco-btn) { flex-shrink:0; }
.library-pagination { display:flex; align-items:center; justify-content:flex-end; gap:var(--space-1); padding-top:var(--space-2); font-size:var(--text-caption); }
.library-detail { min-width:0; border:var(--stroke) solid var(--border-color, var(--line)); background:var(--bg-paper, var(--surface)); border-radius:var(--radius-control); padding:var(--space-2); max-height:78vh; overflow:auto; position:sticky; top:var(--space-2); align-self:start; }
.library-detail .library-section-heading { gap:var(--space-1); }
.library-meta { display:grid; grid-template-columns:var(--row-label-width) minmax(0, 1fr); gap:var(--space-1); margin:var(--space-2) 0; font-size:var(--text-caption); line-height:1.7; }
.library-meta dt { color:var(--text-secondary, var(--ink-secondary)); }
.library-meta dd { margin:0; overflow-wrap:anywhere; }
.library-chunks-title { font-size:var(--text-caption); margin:var(--space-3) 0 var(--space-1); }
.library-chunk { border:var(--stroke) solid var(--border-color, var(--line)); background:var(--bg-card, var(--surface)); border-radius:var(--radius-control); margin-top:var(--space-1); padding:var(--space-2); }
.library-chunk summary { cursor:pointer; font-size:var(--text-caption); font-weight: var(--weight-strong); line-height:1.6; overflow-wrap:anywhere; }
.library-source { white-space:pre-wrap; overflow-wrap:anywhere; font-family: var(--font-family); font-size:var(--text-caption); line-height:1.9; margin-bottom:0; }
.library-upload { margin-bottom:var(--space-3); }
.library-upload-form { display:grid; grid-template-columns:minmax(0, 2fr) minmax(0, 1fr); gap:var(--space-2); margin:var(--space-2) 0; }
.library-file-row, .library-full { grid-column:1 / -1; }
.library-file-row { display:flex; align-items:center; gap:var(--space-1); font-size:var(--text-caption); overflow-wrap:anywhere; }
.library-upload-form > :deep(.arco-btn) { justify-self:start; }
.library-file-input { display:none; }
.library-error-text { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; }
.library-privacy { color:var(--text-muted, var(--ink-secondary)); font-size:var(--text-caption); text-align:center; margin:var(--space-2) 0 0; }
.library-detail :deep(.lk-card) { background:transparent; padding:0; border:0; }
.library-detail :deep(.lk-meta) { grid-template-columns:var(--row-label-width) minmax(0, 1fr); font-size:var(--text-caption); }
@media (max-width: 1120px) { .library-header { flex-direction:column; }.library-header > .library-actions { padding:0; }.library-content-split { grid-template-columns:minmax(0, 1fr); }.library-detail { position:static; max-height:none; } }
@media (max-width: 768px) { .knowledge-library { padding:var(--space-2) var(--space-1); }.library-browser-body, .library-upload { padding:var(--space-2); }.library-header h1 { font-size:var(--text-section); }.library-section-heading { flex-wrap:wrap; }.library-upload-form { grid-template-columns:minmax(0, 1fr); }.library-source-filter { width:100%; }.library-meta { grid-template-columns:var(--row-label-width) minmax(0, 1fr); }.library-detail { padding:var(--space-2); }.library-result-footer { align-items:flex-start; flex-direction:column; }.library-source-text { max-width:100%; } }
</style>
