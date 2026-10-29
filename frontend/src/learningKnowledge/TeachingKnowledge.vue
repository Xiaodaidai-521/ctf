<template>
  <main class="lk-page">
    <header class="lk-header">
      <div>
        <p class="lk-eyebrow">模块三 · 教师审阅</p>
        <h1>教学材料审阅</h1>
        <p>检查原文、段落和任务映射，再提交独立审阅与发布。这里只展示服务器返回的可管理材料。</p>
      </div>
      <button type="button" :disabled="busy" @click="resumeAndLoad">重新加载列表</button>
    </header>

    <p class="lk-notice">教师路由不等于课程审阅授权。独立审阅人、当前修订、许可与发布范围均由服务器校验，不提供模拟学生预览。</p>
    <section v-if="paused" class="lk-panel" aria-live="polite">
      <h2>内容已清除</h2>
      <p>切换用户、离开页面、窗口失焦或进入后台会清除原文、表单和请求标识；返回后不会自动恢复。</p>
      <p>中断请求不代表服务器取消了写操作，请先重新加载核对结果。</p>
      <button v-if="sessionChanged" type="button" @click="privacy.reload">会话已在其他标签页变化，刷新页面</button>
      <button v-else type="button" @click="resumeAndLoad">重新读取当前会话的材料</button>
    </section>

    <p v-if="error" class="lk-error" role="alert">{{ error }}</p>
    <p v-if="message" class="lk-notice" role="status">{{ message }}</p>
    <p v-if="busy" role="status">正在请求服务器，请稍候……</p>

    <template v-if="!paused">
      <section class="lk-panel" aria-labelledby="material-list-title">
        <h2 id="material-list-title">材料列表</h2>
        <p v-if="!materials.length && !busy">暂无服务器授权的可管理材料。空列表不代表拥有登记或审阅权限。</p>
        <div v-if="materials.length" class="lk-table-wrap">
          <table>
            <thead><tr><th>标题 / 材料 ID</th><th>课程目录</th><th>分类</th><th>最新修订</th><th>状态</th><th>检查</th></tr></thead>
            <tbody>
              <tr v-for="row in materials" :key="row.material_id">
                <td>{{ row.title }}<small class="lk-id">{{ row.material_id }}</small></td>
                <td>{{ row.catalog_version }}</td><td>{{ classLabel(row.material_class) }}</td>
                <td>{{ row.revision }}</td><td>{{ statusLabel(row.review_status) }}</td>
                <td><button type="button" :disabled="busy" @click="inspect(row)">原文与段落</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="selectedId" class="lk-panel" aria-labelledby="inspection-title">
        <h2 id="inspection-title">原文与段落检查</h2>
        <form class="lk-actions" @submit.prevent="inspectSelected">
          <label>修订号（留空读取最新）<input v-model="revisionInput" type="number" min="1" step="1" :disabled="busy" /></label>
          <button type="submit" :disabled="busy">重新 GET 检查</button>
        </form>
        <template v-if="inspection">
          <h3>{{ inspection.title }}</h3>
          <dl class="lk-meta">
            <dt>材料 ID / 修订</dt><dd>{{ inspection.material_id }} / {{ inspection.revision }}</dd>
            <dt>课程目录版本</dt><dd>{{ selectedCatalog || '检查接口未返回课程版本，请刷新列表核对' }}</dd>
            <dt>来源机构 / 版本</dt><dd>{{ inspection.publisher }} / {{ inspection.source_version }}</dd>
            <dt>来源地址（仅文本）</dt><dd>{{ inspection.source_url || '未提供' }}</dd>
            <dt>来源日期 / 登记核验日期</dt><dd>{{ inspection.source_date }} / {{ inspection.verified_at }}</dd>
            <dt>来源快照 SHA-256</dt><dd>{{ inspection.source_hash }}</dd>
            <dt>解析器 / 复查期限</dt><dd>{{ inspection.parser_version }} / {{ inspection.recheck_due_at || '未设定' }}</dd>
            <dt>修订作者 / 审阅者</dt><dd>{{ inspection.author_id }} / {{ inspection.reviewer_id || '待审阅' }}</dd>
            <dt>适用范围 / 变更说明</dt><dd>{{ inspection.applicability }} / {{ inspection.change_note || '未提供' }}</dd>
            <dt>许可 / 许可地址</dt><dd>{{ inspection.license_id }} / {{ inspection.license_url || '未提供' }}</dd>
            <dt>署名要求</dt><dd>{{ inspection.attribution_text }}</dd>
            <dt>复用范围</dt><dd>{{ inspection.reuse_scope }}</dd>
            <dt>分类 / 提示等级</dt><dd>{{ classLabel(inspection.material_class) }} / {{ inspection.hint_level ?? '不适用' }}</dd>
            <dt>审阅 / 解析状态</dt><dd>{{ statusLabel(inspection.review_status) }} / {{ inspection.parse_status }}</dd>
            <dt>发布范围 / ACL 版本</dt><dd>{{ inspection.published_scope }} / {{ inspection.acl_version }}</dd>
            <dt>影响任务数（跨修订去重）</dt><dd>{{ inspection.affected_task_count }}</dd>
          </dl>
          <p class="lk-muted">登记核验日期不代表教师签收或法规现行性认证。请核实来源、许可和适用范围，新修订需提交完整元数据。</p>
          <p class="lk-notice">{{ inspection.preview_notice }}</p>

          <h3>课程任务映射</h3>
          <ul class="lk-list">
            <li v-for="(task, index) in inspection.tasks" :key="index">
              {{ task.task__task_key }} · 任务版本 {{ task.task__version }}
              <div>知识点：{{ task.knowledge_point_ids?.join('、') || '未返回' }}</div>
            </li>
          </ul>
          <p v-if="!inspection.tasks?.length" class="lk-warning">当前修订未返回任务映射，请勿推定适用范围。</p>

          <h3>完整原文（纯文本）</h3>
          <pre class="lk-source">{{ inspection.source_snapshot }}</pre>
          <h3>解析段落（{{ inspection.chunks?.length || 0 }}）</h3>
          <p v-if="!inspection.chunks?.length" class="lk-warning">没有可检查段落。服务器会拒绝不完整的审阅流程。</p>
          <article v-for="chunk in inspection.chunks" :key="chunk.chunk_ref" class="lk-card">
            <h4>{{ chunk.heading_path?.join(' / ') || '无标题路径' }}</h4>
            <p>段落引用：{{ chunk.chunk_ref }} · 定位：{{ formatLocator(chunk.locator) }}</p>
            <p v-if="!Object.keys(chunk.locator || {}).length || chunk.location_notice" class="lk-warning">{{ chunk.location_notice || '定位待人工补齐' }}</p>
            <pre class="lk-source">{{ chunk.text }}</pre>
          </article>

          <h3>审阅操作</h3>
          <p>approve 必须由非所有者、非本修订作者的独立教师完成。按钮不表示拥有操作权限，服务器决定是否接受。</p>
          <p class="lk-warning">withdraw 将撤回材料访问，影响任务数见上方；操作后必须重新读取状态。</p>
          <form class="lk-form" @submit.prevent="runAction">
            <label>操作
              <select v-model="action" :disabled="busy">
                <option value="submit">提交审阅（submit）</option><option value="approve">独立批准（approve）</option>
                <option value="publish">发布（publish）</option><option value="withdraw">撤回（withdraw）</option>
              </select>
            </label>
            <label>expected_revision（当前检查修订）<input :value="inspection.revision" readonly /></label>
            <label class="lk-full">理由（必填，最多 500 字）<textarea v-model="reason" required maxlength="500" rows="3" :disabled="busy" /></label>
            <label class="lk-full">幂等标识（发送时生成，最多 64 字；同一操作失败重试沿用）<input :value="pendingAction?.body.idempotency_key || ''" readonly maxlength="64" placeholder="尚未发送" /></label>
            <button type="submit" :disabled="busy || !reason.trim()">执行所选操作</button>
          </form>
        </template>
      </section>

      <section class="lk-panel" aria-labelledby="material-form-title">
        <h2 id="material-form-title">登记材料 / 新修订</h2>
        <p>使用严格 JSON，不接受未知字段。任务必须属于同一课程；task_ids 是数据库正整数 ID，不是上方任务键。</p>
        <p>新修订只接受 task_ids 与完整 metadata，不修改材料分类或课程；检查 API 不返回全部字段，因此不自动复制为新修订。</p>
        <p class="lk-warning">登记和新修订 API 没有幂等参数。网络中断后先核对列表，避免重复创建。页面失焦也会清空尚未提交的 JSON。</p>
        <form class="lk-form" @submit.prevent="saveMaterial">
          <label>表单类型
            <select v-model="formMode" :disabled="busy" @change="draft = ''">
              <option value="register">登记新材料</option><option value="revise">所选材料的新修订</option>
            </select>
          </label>
          <p v-if="formMode === 'revise'">目标材料：{{ selectedId || '请先从列表检查一份材料' }}</p>
          <details class="lk-full">
            <summary>查看完整 JSON 示例与枚举</summary>
            <p>以下仅为格式示例，请替换课程、任务 ID、日期、来源和许可，不可当作真实材料直接发布。</p>
            <p>material_class：lesson / hint / student_analysis / teacher_answer / grading_secret；仅 hint 需要 hint_level（1–4）。分类不授予读写权限。</p>
            <p>source_type：teacher_authored / article / resource / knowledge_concept / legal_clause；关联现有来源时填真实 source_object_id。</p>
            <p>source_snapshot 最多 100000 字；空行分段。recheck_due_at 可为 null 或 ISO 日期时间。可选字段仅为示例中的可选源地址、许可地址、变更说明、复查日期、冲突组及登记来源设置。</p>
            <pre class="lk-source">{{ materialExample(formMode) }}</pre>
            <button type="button" :disabled="busy" @click="draft = materialExample(formMode)">用示例替换输入（需修改）</button>
          </details>
          <label class="lk-full">请求 JSON<textarea v-model="draft" class="lk-json" rows="18" required spellcheck="false" autocomplete="off" :disabled="busy" /></label>
          <button type="submit" :disabled="busy || (formMode === 'revise' && !selectedId)">{{ formMode === 'register' ? '登记并解析' : '创建并解析新修订' }}</button>
        </form>
      </section>
    </template>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { knowledgeApi, errorMessage } from './api.js'
import { materialExample, parseMaterialForm } from './materialForm.js'
import { requestKey } from './requestGeneration.js'
import { usePrivatePage } from './usePrivatePage.js'
import './learningKnowledge.css'

const materials = ref([])
const inspection = ref(null)
const selectedId = ref('')
const selectedCatalog = ref('')
const revisionInput = ref('')
const action = ref('submit')
const reason = ref('')
const pendingAction = ref(null)
const formMode = ref('register')
const draft = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')

function clearContent() {
  materials.value = []
  inspection.value = null
  selectedId.value = ''
  selectedCatalog.value = ''
  revisionInput.value = ''
  action.value = 'submit'
  reason.value = ''
  pendingAction.value = null
  formMode.value = 'register'
  draft.value = ''
  busy.value = false
  error.value = ''
  message.value = ''
}
const privacy = usePrivatePage(clearContent)
const { paused, sessionChanged } = privacy

const classLabel = value => ({ lesson: '学习材料', hint: '分级提示', student_analysis: '学生解析', teacher_answer: '教师答案', grading_secret: '评分密钥' }[value] || value)
const statusLabel = value => ({ draft: '草稿', in_review: '审阅中', approved: '已批准', published: '已发布', withdrawn: '已撤回' }[value] || value)
const formatLocator = locator => Object.keys(locator || {}).length ? JSON.stringify(locator) : '定位待人工补齐'

function failure(err) {
  if ([401, 403, 404, 503].includes(err.response?.status)) clearContent()
  error.value = errorMessage(err)
}

async function loadList() {
  const ticket = privacy.begin()
  if (!ticket) return
  clearContent()
  busy.value = true
  try {
    const result = await knowledgeApi.materials(ticket.signal)
    if (ticket.isCurrent()) materials.value = result.results
  } catch (err) {
    if (ticket.isCurrent()) failure(err)
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}
function resumeAndLoad() {
  if (privacy.resume()) loadList()
}

async function inspect(row, revision = row.revision) {
  const ticket = privacy.begin()
  if (!ticket) return
  inspection.value = null
  draft.value = ''
  reason.value = ''
  pendingAction.value = null
  selectedId.value = row.material_id
  selectedCatalog.value = row.catalog_version || ''
  revisionInput.value = revision || ''
  error.value = ''
  message.value = ''
  busy.value = true
  try {
    const result = await knowledgeApi.inspect(row.material_id, revision, ticket.signal)
    if (ticket.isCurrent()) inspection.value = result
  } catch (err) {
    if (ticket.isCurrent()) failure(err)
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}
function inspectSelected() {
  const number = revisionInput.value === '' ? undefined : Number(revisionInput.value)
  if (number !== undefined && (!Number.isSafeInteger(number) || number < 1)) {
    error.value = '修订号必须是正整数，或留空读取最新修订。'
    return
  }
  inspect({ material_id: selectedId.value, catalog_version: selectedCatalog.value }, number)
}

async function refreshAfterWrite(ticket, id, revision) {
  const [list, detail] = await Promise.all([
    knowledgeApi.materials(ticket.signal), knowledgeApi.inspect(id, revision, ticket.signal),
  ])
  if (!ticket.isCurrent()) return
  materials.value = list.results
  inspection.value = detail
  selectedId.value = id
  selectedCatalog.value = list.results.find(row => row.material_id === id)?.catalog_version || ''
  revisionInput.value = detail.revision
}

async function runAction() {
  if (busy.value || !inspection.value || !reason.value.trim()) return
  const ticket = privacy.begin()
  if (!ticket) return
  const id = inspection.value.material_id
  const selectedAction = action.value
  const fields = { expected_revision: inspection.value.revision, reason: reason.value.trim() }
  const fingerprint = JSON.stringify([id, selectedAction, fields])
  if (pendingAction.value?.fingerprint !== fingerprint) {
    pendingAction.value = { fingerprint, body: { ...fields, idempotency_key: requestKey() } }
  }
  const body = { ...pendingAction.value.body }
  busy.value = true
  error.value = ''
  message.value = ''
  let confirmed = false
  try {
    await knowledgeApi.transition(id, selectedAction, body, ticket.signal)
    if (!ticket.isCurrent()) return
    confirmed = true
    pendingAction.value = null
    reason.value = ''
    inspection.value = null
    message.value = '服务器已接受操作，正在重新读取状态。'
    await refreshAfterWrite(ticket, id, fields.expected_revision)
    if (ticket.isCurrent()) message.value = '操作已被服务器接受，列表与修订已重新读取。'
  } catch (err) {
    if (ticket.isCurrent()) {
      if (confirmed) inspection.value = null
      failure(err)
      if (confirmed) message.value = '操作已被服务器接受，但重新读取失败；请重新加载，不要重复执行。'
    }
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}

async function saveMaterial() {
  if (busy.value || (formMode.value === 'revise' && !selectedId.value)) return
  let body
  try { body = parseMaterialForm(draft.value, formMode.value) } catch (err) {
    error.value = err.message
    return
  }
  const ticket = privacy.begin()
  if (!ticket) return
  busy.value = true
  error.value = ''
  message.value = ''
  let confirmed = false
  try {
    const result = formMode.value === 'register'
      ? await knowledgeApi.register(body, ticket.signal)
      : await knowledgeApi.revise(selectedId.value, body, ticket.signal)
    if (!ticket.isCurrent()) return
    confirmed = true
    draft.value = ''
    reason.value = ''
    pendingAction.value = null
    inspection.value = null
    message.value = `服务器已创建修订 ${result.revision}，正在读取段落。`
    await refreshAfterWrite(ticket, result.material_id, result.revision)
    if (ticket.isCurrent()) message.value = '材料已登记 / 修订并解析。请检查原文与段落，再提交审阅。'
  } catch (err) {
    if (ticket.isCurrent()) {
      failure(err)
      if (confirmed) message.value = '修订已创建，但重新读取失败；请刷新列表，不要重复创建。'
    }
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}

onMounted(resumeAndLoad)
</script>
