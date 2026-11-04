<template>
  <FoundationFrame current="authorization"><main class="governance-page">
    <header class="governance-hero"><h1>{{ names.foundation }} · {{ names.authorizationSupervision }}</h1><p class="governance-muted">核对材料责任、来源许可与课程权限。一般教学材料的生产和独立审阅仍在教师材料工坊完成。</p><p class="governance-muted">受限材料维护仅供已有相应权限的人员使用，每次操作仍由后台独立校验，不因打开页面而获得权限。</p><router-link to="/admin/legal/kb/materials">{{ names.materialMaintenance }}</router-link></header>
    <div class="governance-heading"><p class="governance-muted">管理可见不等于学生可读，不代替真实课程授权。</p><button :disabled="loading || busy" @click="reload">刷新资料</button></div>
    <p v-if="paused" class="governance-notice" role="status">资料与未提交内容已收起，请重新读取。<button @click="reload">重新读取</button></p>
    <p v-if="uncertain" class="governance-notice" role="alert">上次授权结果尚未确认，已暂停重复提交。请核对授权记录后再处理。</p>
    <p v-if="error" class="governance-error" role="alert">{{ error }}</p><p v-if="message" class="governance-notice" role="status">{{ message }}</p>
    <section id="materials" class="governance-panel"><div class="governance-heading"><h2>材料监督</h2><label>审阅状态 <select v-model="status"><option value="all">全部材料</option><option value="in_review">待审阅</option><option value="published">已发布</option><option value="withdrawn">已撤回</option></select></label></div>
      <p v-if="sources.materials.loading" role="status">正在读取材料…</p><p v-else-if="sources.materials.error" class="governance-error" role="alert">{{ sources.materials.error }}</p><template v-else-if="sources.materials.data"><p class="governance-muted">当前有权管理的材料；筛选不改变权限。</p><p v-if="!materials.length">当前可读取范围内没有符合筛选的材料。</p><div v-else class="governance-table-wrap"><table class="governance-mobile-records"><thead><tr><th>材料</th><th>用途</th><th>版本</th><th>状态</th><th>监督</th></tr></thead><tbody><tr v-for="row in materials" :key="row.material_id"><td data-label="材料">{{ row.title || '未命名材料' }}</td><td data-label="用途">{{ materialClass(row.material_class) }}</td><td data-label="版本">第 {{ row.revision }} 版</td><td data-label="状态">{{ materialStatus(row.review_status) }}</td><td data-label="监督"><button :disabled="busy || paused" @click="inspect(row)">核对责任与许可</button></td></tr></tbody></table></div></template>
    </section>
    <section v-if="detail" class="governance-panel"><h2>{{ detail.title || '材料监督详情' }}</h2><dl><template v-for="fact in facts" :key="fact[0]"><dt>{{ fact[0] }}</dt><dd>{{ fact[1] }}</dd></template><dt>状态</dt><dd>{{ materialStatus(detail.review_status) }}</dd><dt>来源版本</dt><dd>{{ detail.source_version || '未提供' }}</dd><dt>发布机构</dt><dd>{{ detail.publisher || '未提供' }}</dd><dt>许可</dt><dd>{{ detail.license_id || '未提供' }}</dd><dt>署名要求</dt><dd>{{ detail.attribution_text || '未提供' }}</dd><dt>使用范围</dt><dd>{{ detail.reuse_scope || '未提供' }}</dd><dt>适用说明</dt><dd>{{ detail.applicability || '未提供' }}</dd><dt>审阅时间</dt><dd>{{ dateLabel(detail.reviewed_at) }}</dd><dt>发布时间</dt><dd>{{ dateLabel(detail.published_at) }}</dd><dt>影响任务</dt><dd>{{ taskCount }}</dd></dl><details><summary>查看原文与出处</summary><p>{{ detail.source_snapshot || '原文未提供' }}</p><p><a v-if="safeSource" :href="safeSource" target="_blank" rel="noopener noreferrer">查看来源原文</a><span v-else>未提供可访问来源。</span></p></details><p class="governance-muted">此处没有审阅、发布或评分操作；授权决定不能替代独立审阅。</p></section>
    <section id="grants" class="governance-panel"><h2>课程授权</h2><p class="governance-notice">当前授权清单和待处理申请数量尚未提供。下方只能按课程与人员提交授权，不能推断既有权限；提交将替换该人员在所选课程的授权设置，请事先核对。</p>
      <p v-if="sources.catalog.loading || sources.people.loading" role="status">正在读取课程与人员…</p><p v-if="sources.catalog.error" class="governance-error" role="alert">课程：{{ sources.catalog.error }}</p><p v-if="sources.people.error" class="governance-error" role="alert">人员：{{ sources.people.error }}</p>
      <form class="governance-form" @submit.prevent="confirmGrant">
        <label>课程<select v-model="selectedCatalog" :disabled="busy || paused || !catalog"><option value="">请选择课程</option><option v-if="catalog" :value="catalog.version">{{ catalog.label }}</option></select></label>
        <label>查找人员<input v-model="personSearch" :disabled="busy || paused" placeholder="输入姓名或用户名" /></label>
        <label>人员<select v-model="form.user" :disabled="busy || paused || !people.length"><option value="">请选择人员</option><option v-for="person in filteredPeople" :key="person.id" :value="person.id">{{ person.username }} · {{ roleLabel(person.role) }}</option></select></label><p class="governance-muted">人员范围：本次已读取的前 {{ people.length }} 人；查不到时请到用户与权限核对。</p>
        <label>课程访问<select v-model="form.active" :disabled="busy || paused"><option :value="true">启用</option><option :value="false">停用</option></select></label>
        <label>独立审阅职责<select v-model="form.can_review" :disabled="busy || paused"><option :value="false">不授予</option><option :value="true">授予（教师或管理员）</option></select></label>
        <label>受限材料维护<select v-model="form.maintain_secrets" :disabled="busy || paused"><option :value="false">不授予</option><option :value="true">授予（仅管理员）</option></select></label>
        <label><span><input v-model="acknowledged" type="checkbox" :disabled="busy || paused" /> 已核对原有授权，确认用上述设置替换</span></label>
        <button v-if="!confirmation" class="governance-primary" :disabled="busy || paused || uncertain || !acknowledged || !selectedCatalog || !form.user">核对授权变更</button>
      </form>
      <div v-if="confirmation" class="governance-notice"><h3>确认授权变更</h3><p>{{ confirmation.person }} · {{ confirmation.course }}：{{ confirmation.payload.active ? '启用' : '停用' }}课程访问，{{ confirmation.payload.can_review ? '授予' : '不授予' }}审阅职责，{{ confirmation.payload.maintain_secrets ? '授予' : '不授予' }}受限材料维护。</p><div class="governance-actions"><button class="governance-primary" :disabled="busy || uncertain" @click="submitGrant">{{ busy ? '正在提交…' : '确认提交' }}</button><button :disabled="busy" @click="confirmation = null">取消</button></div></div>
    </section>
  </main></FoundationFrame>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { names } from '@/shared/navigation/names.js'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import { usePrivatePage } from '@/learningKnowledge/usePrivatePage.js'
import FoundationFrame from './FoundationFrame.vue'
import { foundationApi } from './api.js'
import { grantPayload, materialClass, materialStatus, supervisionFacts } from './presentation.js'
import { countValue, dateLabel, governanceError, listValue } from '../governance/data.js'
import { useGovernanceSources } from '../governance/useSources.js'
const route = useRoute(), status = ref('all'), detail = ref(null), error = ref(''), message = ref(''), busy = ref(false), uncertain = ref(false)
const personSearch = ref(''), selectedCatalog = ref(''), acknowledged = ref(false), confirmation = ref(null), mutationPending = ref(false)
const form = reactive({ user: '', active: true, can_review: false, maintain_secrets: false })
usePageFilters('admin-authorization-supervision', { status })
if (!['all', 'in_review', 'published', 'withdrawn'].includes(status.value)) status.value = 'all'
watch(() => route.query.status, value => { if (value !== undefined) status.value = ['in_review', 'published', 'withdrawn'].includes(value) ? value : 'all' }, { immediate: true })
const { sources, loading, load, clear } = useGovernanceSources({ materials: foundationApi.materials, people: foundationApi.people, catalog: foundationApi.catalog })
const people = computed(() => sources.people.data || []), catalog = computed(() => sources.catalog.data)
const filteredPeople = computed(() => people.value.filter(person => person.is_active !== false && String(person.username || '').toLowerCase().includes(personSearch.value.toLowerCase())))
const materials = computed(() => sources.materials.data ? listValue(sources.materials.data).filter(row => status.value === 'all' || row.review_status === status.value) : [])
const facts = computed(() => detail.value ? supervisionFacts(detail.value, people.value) : [])
const taskCount = computed(() => countValue(detail.value?.affected_task_count) === null ? '未提供' : `${detail.value.affected_task_count} 项`)
const safeSource = computed(() => { try { const url = new URL(detail.value?.source_url); return ['https:', 'http:'].includes(url.protocol) ? url.href : '' } catch { return '' } })
const roleLabel = role => ({ admin: '管理员', teacher: '教师', student: '学生' }[role] || '身份未提供')
const privacy = usePrivatePage(() => { if (mutationPending.value) uncertain.value = true; mutationPending.value = false; clear(); detail.value = null; error.value = ''; message.value = ''; busy.value = false; confirmation.value = null; acknowledged.value = false; personSearch.value = ''; selectedCatalog.value = ''; Object.assign(form, { user: '', active: true, can_review: false, maintain_secrets: false }) })
const { paused } = privacy
async function reload() { if (privacy.resume()) await load() }
async function inspect(row) {
  const request = privacy.begin(); if (!request) return
  busy.value = true; detail.value = null; error.value = ''
  try { const data = await foundationApi.inspect(row.material_id, row.revision, request.signal); if (request.isCurrent()) detail.value = data }
  catch (cause) { if (request.isCurrent()) error.value = governanceError(cause) }
  finally { if (request.isCurrent()) busy.value = false; request.finish() }
}
function confirmGrant() {
  if (busy.value || paused.value || uncertain.value || !acknowledged.value || selectedCatalog.value !== catalog.value?.version) return
  try { const payload = grantPayload(form, people.value, catalog.value); confirmation.value = { payload, person: people.value.find(person => person.id === payload.user_id).username, course: catalog.value.label }; error.value = '' }
  catch (cause) { error.value = cause.message }
}
async function submitGrant() {
  if (!confirmation.value || busy.value || uncertain.value) return
  const request = privacy.begin(); if (!request) return
  const payload = { ...confirmation.value.payload }; busy.value = true; mutationPending.value = true; error.value = ''; message.value = ''
  try { const result = await foundationApi.grant(payload, request.signal); if (request.isCurrent()) {
    if (typeof result?.active !== 'boolean' || result.active !== payload.active) { uncertain.value = true; error.value = '未能确认授权结果，请核对后再操作。' }
    else { message.value = `授权请求已受理，课程访问${result.active ? '已启用' : '已停用'}；完整授权详情仍需核对。`; confirmation.value = null; acknowledged.value = false }
  } } catch (cause) { if (request.isCurrent()) { error.value = governanceError(cause, true); uncertain.value = ![400, 401, 403, 404, 409].includes(cause.response?.status) } }
  finally { if (request.isCurrent()) { busy.value = false; mutationPending.value = false }; request.finish() }
}
onMounted(reload)
</script>
<style scoped src="../governance/governance.css"></style>
