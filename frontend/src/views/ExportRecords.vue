<template>
  <main class="exports-page">
    <h1>导出记录</h1><p>这里展示当前账号仍有权使用的导出任务。生成与下载均须通过现有授权检查。</p>
    <p v-if="resourceId">当前筛选：所选资源</p><router-link to="/privacy">隐私与数据保护</router-link>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button type="button" :disabled="loading || busy" @click="load(0)">刷新</button>
    <p v-if="loading" role="status">正在核对导出任务…</p><p v-else-if="!items.length && !error">暂无可使用的导出任务。导出范围与相关授权准备完成后，任务会显示在这里。</p>
    <article v-for="item in items" :key="item.id" class="export-item">
      <h2>{{ item.title }}</h2><p>{{ exportStateLabel(item.state) }} · 有效至 {{ new Date(item.expires_at).toLocaleString() }}</p>
      <template v-if="exportConfirmed(item)"><p><AppIcon name="bi-check-circle" /> 导出内容已完成脱敏处理</p><p><AppIcon name="bi-check-circle" /> 服务器保存的导出文件已加密</p></template>
      <p v-else>导出保护状态待确认。</p>
      <button v-if="item.can_execute" type="button" :disabled="busy || loading" @click="selected = item">生成导出文件</button>
      <button v-if="exportConfirmed(item)" type="button" :disabled="busy || loading" @click="download(item)">下载文件</button>
    </article>
    <button v-if="offset > 0" type="button" :disabled="loading || busy" @click="load(Math.max(0, offset - 20))">上一页</button>
    <button v-if="next !== null" type="button" :disabled="loading || busy" @click="load(next)">下一页</button>
    <a-modal :visible="Boolean(selected)" title="生成导出文件" :ok-loading="busy" :closable="!busy" :mask-closable="!busy" :cancel-button-props="{ disabled: busy }" @cancel="selected = null" @ok="generate">
      <p>{{ selected?.title }}</p><p>文件将按已获授权的范围和脱敏策略生成。服务器保存的文件采用加密保护。</p><p>下载到本机后的文件需要自行妥善保存。</p>
    </a-modal>
  </main>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { captureAccount } from '@/shared/state/accountScope.js'
import { useUserStore } from '@/store/user'
import api from '@/api'
import { exportConfirmed, exportStateLabel } from '@/shared/privacy/presentation.js'
const route = useRoute(), user = useUserStore()
const resourceId = computed(() => /^\d+$/.test(String(route.query.resource || '')) ? String(route.query.resource) : null)
const items = ref([]), selected = ref(null), offset = ref(0), next = ref(null), loading = ref(false), busy = ref(false), error = ref(''), notice = ref('')
let generation = 0, scopeGeneration = 0, alive = true
const refs = item => ({ source_ref: item.source_ref, permission_ref: item.permission_ref })
async function load(page = 0) {
  const version = ++generation, account = captureAccount()
  loading.value = true; error.value = ''; items.value = []; next.value = null
  try { const data = await api.privacy.exports({ offset: page, ...(resourceId.value ? { resource_id: resourceId.value } : {}) }); if (!alive || version !== generation || !account.current()) return; items.value = data.items || []; offset.value = page; next.value = data.next_offset }
  catch (err) { if (alive && version === generation && account.current()) error.value = err.response?.status === 503 ? '受控导出当前尚未开放。' : '导出任务暂时无法读取，请重试。' }
  finally { if (alive && version === generation && account.current()) loading.value = false }
}
async function generate() {
  if (!selected.value || busy.value) return
  const account = captureAccount(), version = generation, scope = scopeGeneration, item = selected.value
  busy.value = true; error.value = ''; notice.value = ''
  try { await api.privacy.generateExport(refs(item)); if (!alive || !account.current() || version !== generation) return; selected.value = null; await load(offset.value); if (!alive || !account.current() || scope !== scopeGeneration) return; const current = items.value.find(row => row.id === item.id); notice.value = exportConfirmed(current) ? '导出文件已生成，内容已脱敏，服务器保存的文件已加密。' : '生成请求已处理，文件保护状态尚待核对。' }
  catch { if (alive && account.current() && version === generation) error.value = '文件生成失败或授权已失效，请刷新后重试。' }
  finally { if (alive && account.current() && scope === scopeGeneration) busy.value = false }
}
async function download(item) {
  if (busy.value) return
  const account = captureAccount(), version = generation, scope = scopeGeneration
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const response = await api.privacy.downloadExport(refs(item))
    if (!alive || !account.current() || version !== generation) return
    const url = URL.createObjectURL(response.data), link = document.createElement('a')
    link.href = url; link.download = response.headers['content-disposition']?.includes('.xlsx') ? 'export.xlsx' : 'export.csv'; link.click(); URL.revokeObjectURL(url)
    notice.value = '已开始下载，请在本机妥善保存文件。'
  } catch { if (alive && account.current() && version === generation) error.value = '文件下载失败或授权已失效，请刷新后重试。' }
  finally { if (alive && account.current() && scope === scopeGeneration) busy.value = false }
}
watch(() => `${user.userInfo?.id}:${user.userInfo?.role}:${resourceId.value}`, () => { generation++; scopeGeneration++; selected.value = null; notice.value = ''; busy.value = false; load(0) })
onMounted(() => load(0)); onBeforeUnmount(() => { alive = false; generation++; scopeGeneration++ })
</script>
<style scoped>
.exports-page { max-width: 900px; margin: 30px auto; padding: 24px; line-height: 1.8; } .export-item { margin-block: 18px; padding: 20px; border: 1px solid var(--line, #ddd); border-radius: 10px; } .export-item h2 { font-size: 18px; }
</style>
