<template>
  <div class="security-page">
    <section class="page-card" aria-labelledby="policy-title">
      <div class="page-header">
        <h3 id="policy-title" class="page-title">数据保护策略</h3>
        <button class="action-btn btn-default" :disabled="loading" @click="loadPolicy">刷新</button>
      </div>
      <p>默认遮蔽敏感内容。此页面不提供原文查看、密钥读取或数据导出。</p>
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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '@/api'

const metadata = ref(null)
const loading = ref(false)
const error = ref('')
const sampleCase = ref('mixed')
const previewing = ref(false)
const previewError = ref('')
const result = ref(null)
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

onMounted(loadPolicy)
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
.error-message { color: #9d2020; }
summary { cursor: pointer; }
button:disabled { opacity: .6; cursor: not-allowed; }
@media (max-width: 600px) { .page-card { padding: 16px; } dl { grid-template-columns: 1fr; gap: 6px; } dd { margin-bottom: 8px; } }
</style>
