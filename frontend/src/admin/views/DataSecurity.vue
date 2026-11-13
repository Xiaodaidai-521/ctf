<template>
  <div class="security-page">
    <section class="page-card" aria-labelledby="policy-title">
      <div class="page-header">
        <h3 id="policy-title" class="page-title">数据保护策略</h3>
        <button class="action-btn btn-default" :disabled="loading" @click="loadPolicy">刷新</button>
      </div>
      <p>默认遮蔽敏感内容。本页只管理策略与查看申请，不展示原文、读取密钥或导出数据。</p>
      <p v-if="error" role="alert" class="error-message">{{ error }}</p>
      <p v-if="loading" role="status">正在读取策略…</p>
      <template v-if="metadata">
        <dl>
          <dt>当前版本</dt><dd>{{ metadata.policy.version }}</dd>
          <dt>状态</dt><dd>{{ statusLabel[metadata.policy.status] || '不可用' }}</dd>
          <dt>内容摘要</dt><dd class="digest">{{ metadata.policy.content_hash }}</dd>
          <dt>生效时间</dt><dd>{{ metadata.policy.effective_at }}</dd>
          <dt>到期时间</dt><dd>{{ metadata.policy.expires_at }}</dd>
        </dl>
        <div class="table-scroll">
          <table>
            <caption>当前策略规则</caption>
            <thead><tr><th>类别</th><th>出口</th><th>角色</th><th>用途</th><th>处理</th></tr></thead>
            <tbody>
              <tr v-for="(rule, index) in metadata.policy.rules" :key="index">
                <td>{{ categoryLabel[rule.category] || rule.category }}</td>
                <td>{{ outletLabel[rule.outlet] || rule.outlet }}</td>
                <td>{{ roleLabel[rule.role] || rule.role }}</td>
                <td>{{ purposeLabel[rule.purpose] || rule.purpose }}</td>
                <td>{{ algorithmLabel[rule.action.algorithm] || rule.action.algorithm }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <details>
          <summary>密钥引用信息</summary>
          <p>引用仅标识用途和版本，不赋予读取密钥的权限。实际可用性以密钥服务为准。</p>
          <ul><li v-for="key in metadata.keys" :key="key.key_ref">{{ key.key_ref }} · {{ key.version }} · {{ keyPurposeLabel[key.purpose] || key.purpose }}</li></ul>
        </details>
      </template>
    </section>

    <section class="page-card" aria-labelledby="preview-title">
      <h3 id="preview-title" class="page-title">合成示例预览</h3>
      <p>只使用服务器生成的示例，不接收或保存真实正文。预览不会更改当前策略。</p>
      <form @submit.prevent="runPreview">
        <label for="sample-case">示例类型</label>
        <select id="sample-case" v-model="sampleCase" :disabled="previewing">
          <option value="email">邮箱</option>
          <option value="ipv4">IPv4 地址</option>
          <option value="card">银行卡候选</option>
          <option value="mixed">组合示例</option>
        </select>
        <button class="action-btn btn-primary" :disabled="previewing || !metadata">{{ previewing ? '处理中…' : '预览保护结果' }}</button>
      </form>
      <p v-if="previewError" role="alert" class="error-message">{{ previewError }}</p>
      <div v-if="result" aria-live="polite">
        <p>使用版本：{{ result.policy_version }}</p>
        <pre>{{ result.output }}</pre>
      </div>
    </section>

    <section class="page-card" aria-labelledby="request-title">
      <div class="page-header">
        <h3 id="request-title" class="page-title">原文查看申请</h3>
        <button class="action-btn btn-default" :disabled="requestsLoading || requestSubmitting || requestAction" @click="loadRequests(requestOffset)">刷新申请</button>
      </div>
      <p>状态：{{ capabilityLabel[requestState] || '状态待确认' }}</p>
      <p id="request-scope-note">申请与批准必须由不同账号完成，双方都须有资料访问权。批准最长有效 15 分钟，只能查看一次，管理员也不例外。</p>
      <p>本页只管理申请和审批，不展示原文。申请理由会先遮蔽敏感内容，再保存为保护后的说明。</p>
      <p v-if="requestState === 'disabled'">原文查看尚未开放，暂不能提交或审批。</p>
      <p v-if="requestError" role="alert" class="error-message">{{ requestError }}</p>
      <p v-if="requestNotice" role="status">{{ requestNotice }}</p>
      <p v-if="requestsLoading" role="status">正在读取申请…</p>
      <p v-if="requestAction" role="status">正在处理申请…</p>
      <template v-if="['enabled-unverified', 'accepted'].includes(requestState)">
        <form class="request-form" aria-describedby="request-scope-note" autocomplete="off" @submit.prevent="submitRequest">
          <h4>提交查看申请</h4>
          <div class="request-fields">
            <label for="request-source-id">资料编号
              <input id="request-source-id" v-model.number="requestDraft.sourceId" type="number" min="1" step="1" required :disabled="requestSubmitting || sourceLoading" placeholder="请输入资料列表中的编号">
            </label>
            <label for="request-field">查看内容
              <select id="request-field" v-model="requestDraft.field" :disabled="requestSubmitting || sourceLoading">
                <option v-for="(field, key) in revealFields" :key="key" :value="key">{{ field.label }}</option>
              </select>
            </label>
            <label for="request-course">课程编号（如适用）
              <input id="request-course" v-model.number="requestDraft.courseId" type="number" min="1" step="1" :disabled="requestSubmitting || sourceLoading" placeholder="跨账号访问须使用已授权课程">
            </label>
            <label for="request-object">资料标识
              <input id="request-object" v-model="requestDraft.objectRef" readonly placeholder="核对资料后自动填入">
            </label>
            <label for="request-version">资料版本
              <input id="request-version" v-model="requestDraft.version" readonly placeholder="核对资料后自动填入">
            </label>
          </div>
          <div><button type="button" class="action-btn btn-default" :disabled="sourceLoading || requestSubmitting || requestAction || requestDraft.sourceId === ''" @click="lookupSource">{{ sourceLoading ? '核对中…' : '核对资料' }}</button></div>
          <p>申请用途：调查取证。资料编号来自已有资料列表；邮箱使用用户编号。核对只定位已获准访问的资料，不代表原文查看已获批准。</p>
          <label for="request-reason">申请理由</label>
          <textarea id="request-reason" v-model="requestDraft.reason" required rows="3" :disabled="requestSubmitting" placeholder="请说明查看的必要性，不要填写密码或密钥"></textarea>
          <div><button class="action-btn btn-primary" :disabled="requestSubmitting || requestAction || sourceLoading || !requestDraft.objectRef">{{ requestSubmitting ? '提交中…' : '提交申请' }}</button></div>
        </form>
        <div class="table-scroll">
          <table>
            <caption>当前账号有权访问的申请</caption>
            <thead><tr><th>资料</th><th>申请账号</th><th>保护后的理由</th><th>申请时间</th><th>状态</th><th>批准有效至</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="request in requests" :key="request.id">
                <td class="request-id">{{ request.fields.map(([, reference]) => revealFieldLabel[reference] || '不支持的资料').join('、') }}<br>{{ request.object_ref }}<br>版本：{{ request.object_version }}</td>
                <td>{{ request.requested_by.replace('user/', '账号 ') }}</td>
                <td class="request-reason">{{ request.reason }}</td>
                <td>{{ formatTime(request.requested_at) }}</td>
                <td>{{ requestStatusLabel[request.state] || '未知状态' }}</td>
                <td>{{ request.expires_at ? formatTime(request.expires_at) : '—' }}</td>
                <td>
                  <div class="request-actions">
                    <template v-if="request.state === 'pending'">
                      <button class="action-btn btn-primary" :disabled="requestAction || requestSubmitting" @click="changeRequest(request, 'approve')">批准</button>
                      <button class="action-btn btn-default" :disabled="requestAction || requestSubmitting" @click="changeRequest(request, 'reject')">不批准</button>
                    </template>
                    <button v-if="request.state === 'approved'" class="action-btn btn-default" :disabled="requestAction || requestSubmitting" @click="changeRequest(request, 'revoke')">撤销批准</button>
                    <span v-if="!['pending', 'approved'].includes(request.state)">—</span>
                  </div>
                </td>
              </tr>
              <tr v-if="!requests.length"><td colspan="7">当前没有可查看的申请。</td></tr>
            </tbody>
          </table>
        </div>
        <div class="request-actions">
          <button class="action-btn btn-default" :disabled="requestsLoading || requestAction || requestSubmitting || requestOffset === 0" @click="loadRequests(requestOffset - requestLimit)">上一页</button>
          <span>第 {{ Math.floor(requestOffset / requestLimit) + 1 }} 页</span>
          <button class="action-btn btn-default" :disabled="requestsLoading || requestAction || requestSubmitting || requests.length < requestLimit" @click="loadRequests(requestOffset + requestLimit)">下一页</button>
        </div>
      </template>
    </section>
    <section class="page-card statistics-card" aria-labelledby="statistics-title" :aria-busy="statisticsLoading">
      <div class="page-header">
        <h3 id="statistics-title" class="page-title">数据处理统计</h3>
        <button class="action-btn btn-default" :disabled="statisticsLoading" @click="loadStatistics(statisticsOffset)">刷新统计</button>
      </div>
      <p>状态：{{ capabilityLabel[statisticsState] || '状态待确认' }}</p>
      <p>不同报告、计量单位和版本分别列示，不合并为全平台覆盖率。报告核对只确认留存记录的完整性，不代表已交付或已验收。</p>
      <p v-if="statisticsLoading" role="status">正在读取统计…</p>
      <p v-if="statisticsError" role="alert" class="error-message">{{ statisticsError }}</p>
      <p v-if="statisticsState === 'disabled'">处理统计尚未启用。</p>
      <template v-if="statistics">
        <p>读取时间：{{ formatTime(statistics.observed_at) }}</p>
        <details>
          <summary>查看保护功能状态</summary>
          <ul><li v-for="item in statistics.capabilities" :key="item.capability">{{ statisticsSourceLabel[item.capability] || '其他保护功能' }}：{{ capabilityLabel[item.state] || '状态待确认' }}</li></ul>
        </details>
        <h4>尚无完整统计的范围</h4>
        <ul>
          <li v-for="item in statistics.unknown_sources" :key="item.source">
            {{ statisticsSourceLabel[item.source] || '其他范围' }}（{{ unitLabel[item.unit] || '单位待确认' }}）：
            {{ item.reason === 'BASELINE_UNVERIFIED' ? '应保护范围与验收结果尚待核对，暂不计算覆盖率。' : '暂无可核对的完整处理总量，暂不计算比例。' }}
          </li>
        </ul>
        <p v-if="statistics.unknown_records">本页有 {{ statistics.unknown_records }} 份报告尚未核对，无法确认其应处理量，未纳入处理比例。</p>
        <p v-if="!statistics.items.length">当前没有处理报告可统计，暂不计算处理覆盖率。</p>
        <article v-for="item in statistics.items" :key="item.id" class="statistics-record">
          <h4>记录 {{ item.id }} · {{ item.integrity === 'verified' ? '报告已核对' : '报告尚未核对' }}</h4>
          <p v-if="item.integrity !== 'verified'">{{ statisticsReasonLabel[item.reason] || '暂不能核对这份报告，处理量与比例未知。' }}</p>
          <template v-else>
            <p>报告时间：{{ formatTime(item.created_at) }} · {{ item.source_trust === 'synthetic' ? '合成数据' : '来源待确认' }}</p>
            <div class="table-scroll" tabindex="0" role="region" :aria-labelledby="`statistics-caption-${item.id}`">
              <table class="statistics-table">
                <caption :id="`statistics-caption-${item.id}`">记录 {{ item.id }} 的处理与复扫结果</caption>
                <thead><tr><th scope="col">阶段</th><th scope="col">单位</th><th scope="col">总量</th><th scope="col">成功／应处理</th><th scope="col">排除</th><th scope="col">失败</th><th scope="col">未知</th><th scope="col">未扫描</th><th scope="col">处理比例</th><th scope="col">统计版本</th></tr></thead>
                <tbody>
                  <tr v-for="metric in item.measurements" :key="metric.stage">
                    <th scope="row">{{ metric.stage === 'processing' ? '原处理' : '复扫' }}</th>
                    <td>{{ unitLabel[metric.unit] || '单位待确认' }}</td>
                    <td class="number">{{ metric.total }}</td>
                    <td class="number">{{ metric.numerator }}／{{ metric.denominator }}</td>
                    <td class="number">{{ metric.excluded }}</td><td class="number">{{ metric.failed }}</td>
                    <td class="number">{{ metric.unknown }}</td><td class="number">{{ metric.unscanned }}</td>
                    <td>{{ metric.ratio === null ? (metric.zero_reason === 'NO_ELIGIBLE_UNITS' ? '未计算（无应处理单位）' : '未知') : percentFormat.format(metric.ratio) }}</td>
                    <td>{{ metric.version }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <details>
              <summary>查看版本信息</summary>
              <dl>
                <dt>资料版本</dt><dd>{{ item.versions.asset }}</dd>
                <dt>保护策略</dt><dd>{{ item.versions.policy_binding.protection_version }}</dd>
                <dt>风险策略</dt><dd>{{ item.versions.policy_binding.risk_version }}</dd>
                <dt>数据格式</dt><dd>{{ item.versions.policy_binding.contract_version }}</dd>
                <dt>保护算法</dt><dd>{{ item.versions.algorithms.join('、') || '无' }}</dd>
                <dt>处理版本</dt><dd>{{ item.versions.adapter }}</dd>
                <dt>来源版本</dt><dd>{{ item.versions.source }}</dd>
                <dt>认证密钥版本</dt><dd>{{ item.versions.audit_key.version }}</dd>
              </dl>
            </details>
          </template>
        </article>
        <div class="request-actions">
          <button class="action-btn btn-default" :disabled="statisticsLoading || statisticsOffset === 0" @click="loadStatistics(statisticsOffset - statistics.limit)">上一页统计</button>
          <span>第 {{ Math.floor(statisticsOffset / statistics.limit) + 1 }} 页</span>
          <button class="action-btn btn-default" :disabled="statisticsLoading || statistics.next_offset === null" @click="loadStatistics(statistics.next_offset)">下一页统计</button>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import api from '@/api'

const metadata = ref(null)
const loading = ref(false)
const error = ref('')
const sampleCase = ref('mixed')
const previewing = ref(false)
const previewError = ref('')
const result = ref(null)
const requests = ref([])
const requestState = ref(null)
const requestsLoading = ref(false)
const sourceLoading = ref(false)
const requestSubmitting = ref(false)
const requestAction = ref('')
const requestError = ref('')
const requestNotice = ref('')
const requestOffset = ref(0)
const requestLimit = 20
const statistics = ref(null)
const statisticsState = ref(null)
const statisticsLoading = ref(false)
const statisticsError = ref('')
const statisticsOffset = ref(0)
const percentFormat = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 2 })
const statisticsSourceLabel = { 'field-protection': '字段保护', 'text-rag': '知识库文本', 'enabled-outlets': '已启用保护范围', 'reveal-requests': '原文查看申请', 'resource-export': '资料导出', 'private-files': '私有文件' }
const unitLabel = { field: '字段', text: '文本', cell: '单元格', record: '记录', outlet: '出口' }
const statisticsReasonLabel = {
  REPORT_NOT_AVAILABLE: '尚无可核对的处理报告，处理量与比例未知。',
  DELIVERY_UNKNOWN: '处理报告暂不可用，处理量与比例未知。',
  KEY_UNAVAILABLE: '报告验证暂不可用，处理量与比例未知。',
  REPORT_MISMATCH: '报告未通过完整性核对，不纳入处理统计。',
  SCOPE_INCOMPLETE: '报告未提供完整的处理结果，不纳入处理统计。',
}
const requestDraft = reactive({ sourceId: '', objectRef: '', version: '', field: 'email', courseId: '', reason: '' })
watch(() => [requestDraft.sourceId, requestDraft.field, requestDraft.courseId], () => {
  requestDraft.objectRef = ''
  requestDraft.version = ''
  requestNotice.value = ''
})
const revealFields = {
  email: { category: 'email', reference: 'users.ctfuser/email', label: '邮箱' },
  evidence: { category: 'evidence', reference: 'legal.legalanalysistask/input_text', label: '法审材料' },
  report: { category: 'report', reference: 'legal.legalreport/content', label: '法审报告' },
}
const revealFieldLabel = Object.fromEntries(Object.values(revealFields).map(field => [field.reference, field.label]))
const capabilityLabel = { disabled: '未启用', 'enabled-unverified': '已启用，尚未验收', accepted: '已验收' }
const requestStatusLabel = { pending: '待审批', approved: '已批准', rejected: '未批准', consumed: '已查看', revoked: '已撤销' }
const revealErrorLabel = {
  AUTHORIZATION_DENIED: '当前账号缺少所需资料权限，或这项操作不符合申请条件。',
  AUTHORIZATION_EXPIRED: '批准已到期，请重新申请。',
  POLICY_NOT_APPROVED: '保护策略暂不可用，本次操作未完成。',
  SOURCE_NOT_APPROVED: '资料暂不能申请原文查看。',
  UNSUPPORTED_SCOPE: '该内容不支持原文查看。',
  AUDIT_UNAVAILABLE: '操作未完成，请稍后重试。',
  INVALID_TYPE: '请检查申请信息后重试。',
  UNKNOWN_FIELD: '请检查申请信息后重试。',
  MISSING_FIELD: '请补全申请信息。',
}
const decisionPrompt = {
  approve: '确认批准这项申请？双方须有资料访问权，批准最长有效 15 分钟，只能查看一次。',
  reject: '确认不批准这项申请？',
  revoke: '确认撤销这项批准？撤销后不能再用此次批准查看原文。',
}
const decisionNotice = { approve: '申请已批准。', reject: '申请未获批准。', revoke: '批准已撤销。' }
const formatTime = value => new Date(value).toLocaleString('zh-CN', { hour12: false })
const statusLabel = { draft: '草稿', approved: '已批准', retired: '已撤销' }
const categoryLabel = { email_address: '邮箱', ip_address: 'IPv4 地址', payment_card_candidate: '银行卡候选', secret_credential: '显式凭据保护' }
const outletLabel = { model: '模型调用', embedding: '向量化', log: '日志记录', audit: '审计', api: '接口调用', export: '数据导出', rag: '知识库检索' }
const roleLabel = { student: '学生', teacher: '教师', admin: '管理员', service: '系统服务' }
const purposeLabel = { display: '页面展示', teaching: '教学', analysis: '分析处理', delivery: '对外交付', retrieval: '检索', security_audit: '安全审计', storage: '存储', investigation: '调查取证' }
const algorithmLabel = { drop: '删除', replace: '替换遮蔽', mask: '掩码处理', truncate: '截断', hmac: '哈希索引', pseudonym: '假名化', generalize: '泛化' }
const keyPurposeLabel = { 'enc-data': '数据加密', 'mask-link': '关联遮蔽', 'mask-pseudonym': '假名遮蔽', 'query-index': '查询索引', 'audit-auth': '审计鉴权', provider: '厂商调用', 'framework-signing': '框架签名', 'export-authority': '导出授权', 'share-pepper': '共享校验', 'backup-recipient': '备份接收', 'backup-identity': '备份身份' }

async function loadPolicy() {
  loading.value = true
  error.value = ''
  metadata.value = null
  result.value = null
  try {
    metadata.value = await api.dataSecurity.policies()
  } catch {
    error.value = '策略暂不可用或当前账号无权访问。请检查配置后重试。'
  } finally {
    loading.value = false
  }
}

async function runPreview() {
  previewing.value = true
  previewError.value = ''
  result.value = null
  try {
    result.value = await api.dataSecurity.preview(sampleCase.value)
  } catch {
    previewError.value = '预览未完成，未返回未经保护的内容。'
  } finally {
    previewing.value = false
  }
}

async function loadRequests(offset = 0) {
  requestsLoading.value = true
  requestError.value = ''
  requestState.value = null
  requests.value = []
  try {
    const response = await api.dataSecurity.revealRequests({ offset, limit: requestLimit })
    requests.value = response.items
    requestOffset.value = offset
    requestState.value = response.state
  } catch (failure) {
    requestState.value = failure.response?.data?.state || null
    requestError.value = revealErrorLabel[failure.response?.data?.code] || '申请服务暂不可用，请稍后重试。'
  } finally {
    requestsLoading.value = false
  }
}

async function lookupSource() {
  sourceLoading.value = true
  requestError.value = ''
  requestNotice.value = ''
  requestDraft.objectRef = ''
  requestDraft.version = ''
  try {
    const field = revealFields[requestDraft.field]
    const response = await api.dataSecurity.revealSource({
      source_id: requestDraft.sourceId, field: field.category, field_ref: field.reference,
      ...(requestDraft.courseId !== '' ? { course_id: requestDraft.courseId } : {}),
    })
    requestDraft.objectRef = response.object_ref
    requestDraft.version = response.object_version
    requestNotice.value = '资料已核对，请填写查看理由后提交申请。'
  } catch (failure) {
    requestError.value = revealErrorLabel[failure.response?.data?.code] || '资料暂不能核对，请稍后重试。'
  } finally {
    sourceLoading.value = false
  }
}

async function submitRequest() {
  requestSubmitting.value = true
  requestError.value = ''
  requestNotice.value = ''
  try {
    const field = revealFields[requestDraft.field]
    await api.dataSecurity.createRevealRequest({
      object_ref: requestDraft.objectRef.trim(), object_version: requestDraft.version.trim(),
      fields: [[field.category, field.reference]], purpose: 'investigation', reason: requestDraft.reason,
      ...(requestDraft.courseId !== '' ? { course_id: requestDraft.courseId } : {}),
    })
    requestDraft.reason = ''
    requestNotice.value = '申请已提交。列表中仅显示保护后的理由。'
    await loadRequests()
  } catch (failure) {
    requestError.value = revealErrorLabel[failure.response?.data?.code] || '申请未提交，请稍后重试。'
  } finally {
    requestSubmitting.value = false
  }
}

async function changeRequest(request, action) {
  if (!window.confirm(decisionPrompt[action])) return
  requestAction.value = request.id
  requestError.value = ''
  requestNotice.value = ''
  try {
    await api.dataSecurity.decideRevealRequest(request.id, action)
    requestNotice.value = decisionNotice[action]
    await loadRequests(requestOffset.value)
  } catch (failure) {
    requestError.value = revealErrorLabel[failure.response?.data?.code] || '操作未完成，请稍后重试。'
  } finally {
    requestAction.value = ''
  }
}

async function loadStatistics(offset = 0) {
  statisticsLoading.value = true
  statisticsError.value = ''
  try {
    const response = await api.dataSecurity.statistics({ offset })
    statistics.value = response
    statisticsOffset.value = response.offset
    statisticsState.value = response.state
  } catch (failure) {
    statistics.value = null
    statisticsState.value = failure.response?.data?.state === 'disabled' ? 'disabled' : null
    statisticsError.value = failure.response?.data?.code === 'AUTHORIZATION_DENIED'
      ? '当前账号无权查看处理统计。'
      : '处理统计暂不可用，请稍后重试。'
  } finally {
    statisticsLoading.value = false
  }
}

onMounted(() => {
  loadPolicy()
  loadRequests()
  loadStatistics()
})
</script>

<style scoped>
.security-page { display: grid; gap: 24px; }
.page-card { padding: 24px; border-radius: 12px; background: #fff; color: #253248; }
.page-header, form { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.page-header { justify-content: space-between; }
.page-title { margin: 0 0 12px; }
dl { display: grid; grid-template-columns: minmax(90px, 120px) minmax(0, 1fr); gap: 10px; }
dd { margin: 0; overflow-wrap: anywhere; }
.digest, pre { font-family: monospace; }
.table-scroll { overflow-x: auto; margin: 20px 0; }
table { width: 100%; border-collapse: collapse; text-align: left; }
caption { text-align: left; font-weight: 600; margin-bottom: 8px; }
th, td { padding: 10px; border-bottom: 1px solid #dbe2eb; white-space: nowrap; }
select { padding: 8px; border: 1px solid #8996a8; border-radius: 6px; background: #fff; }
pre { padding: 16px; background: #f2f5f9; white-space: pre-wrap; overflow-wrap: anywhere; }
.request-form { display: grid; align-items: start; gap: 12px; margin: 20px 0; }
.request-form h4, .request-form p { margin: 0; }
.request-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.request-fields label { display: grid; gap: 6px; }
.request-form input, .request-form textarea { box-sizing: border-box; width: 100%; padding: 8px; border: 1px solid #8996a8; border-radius: 6px; background: #fff; color: #253248; }
.request-form textarea { resize: vertical; }
.request-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.request-id { min-width: 160px; white-space: normal; overflow-wrap: anywhere; }
.request-reason { min-width: 160px; max-width: 320px; white-space: pre-wrap; overflow-wrap: anywhere; }
.statistics-card { min-width: 0; }
.statistics-record { padding: 16px 0; border-top: 1px solid #dbe2eb; }
.statistics-table .number { text-align: right; font-variant-numeric: tabular-nums; }
.error-message { color: #9d2020; }
summary { cursor: pointer; }
button:disabled { opacity: .6; cursor: not-allowed; }
@media (max-width: 600px) { .page-card { padding: 16px; } dl { grid-template-columns: 1fr; gap: 6px; } dd { margin-bottom: 8px; } }
</style>
