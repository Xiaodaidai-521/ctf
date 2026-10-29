<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { labApi } from './api'
import { splitCodepoints } from './codepoints'
import { readableError } from './errors'
import { currentReplays, latestRevealedReplays, replayVariants } from './replaySelection'

const route = useRoute(), router = useRouter()
const cases = ref([]), attempts = ref([]), selectedTask = ref(''), attemptId = ref('')
const state = ref(null), step = ref(0), saving = ref(false), saveStatus = ref('尚未保存'), error = ref('')
const indexLoading = ref(false), indexError = ref('')
const selected = ref(null), result = ref(null), help = ref(''), analysis = ref('')
const steps = ['任务简介', '依据与事实', '发现与复核', '四轮回放', '提交与结果']
const emptyBasis = () => ({ entity_category: '', personal_information: '', data_classification: '', uncertainties: '', fact_ids: [], basis_ids: [] })
const emptyReview = () => ({ action: 'confirm', reason: '', category_id: 'DEMO_PERSON_REF', row: 2, column: 1, start: 0, end: 1 })
const basis = reactive(emptyBasis()), review = reactive(emptyReview())
const predictions = reactive({}), explanation = ref('')
const pending = new Map(), pendingHelp = new Map()
let generation = 0
const material = computed(() => state.value?.material)
const scan = computed(() => state.value?.scan)
const rows = computed(() => [...new Set((scan.value?.cells || []).map(c => c.row))])
const replays = computed(() => currentReplays(state.value?.replays, scan.value))
const submissionReplays = computed(() => latestRevealedReplays(state.value?.replays, scan.value))
const missingVariants = computed(() => replayVariants.filter(v => !submissionReplays.value.some(r => r.scenario_variant === v)))
const refs = () => ({ fact_ids: [...basis.fact_ids], basis_ids: [...basis.basis_ids] })
const aid = (suffix = '', id = attemptId.value) => `attempts/${encodeURIComponent(id)}/${suffix}`

async function act(fn) {
  if (saving.value) return
  const token = generation
  saving.value = true; error.value = ''; saveStatus.value = '正在处理…'
  try {
    await fn()
    if (token === generation) saveStatus.value = '操作已完成'
  } catch (e) {
    if (token === generation) { error.value = readableError(e); saveStatus.value = '操作待重试' }
  } finally { if (token === generation) saving.value = false }
}

// Keep a failed request's key and body together; editing creates a new operation.
async function send(path, body) {
  const fingerprint = path + JSON.stringify(body)
  if (!pending.has(fingerprint)) pending.set(fingerprint, crypto.randomUUID())
  const key = pending.get(fingerprint)
  const response = await labApi.post(path, { ...body, idempotency_key: key })
  if (pending.get(fingerprint) === key) pending.delete(fingerprint)
  return response
}
async function load(id = attemptId.value, token = generation) {
  if (!id || token !== generation) return
  const next = await labApi.get(aid('', id))
  if (token !== generation) return
  if (next.scan?.scan_id !== scan.value?.scan_id || next.scan?.profile_id !== scan.value?.profile_id) selected.value = null
  state.value = next
  Object.assign(basis, emptyBasis(), next.basis)
  for (const r of next.replays) {
    predictions[r.replay_id] ||= { actions: r.scenario_variant === 'A4' ? ['', ''] : [''], reason: '' }
  }
}
function resetAttempt(id) {
  generation += 1
  attemptId.value = id; state.value = null; step.value = 0; saving.value = false
  selected.value = null; result.value = null; help.value = ''; analysis.value = ''; explanation.value = ''
  error.value = ''; saveStatus.value = '尚未保存'
  Object.assign(basis, emptyBasis()); Object.assign(review, emptyReview())
  for (const key of Object.keys(predictions)) delete predictions[key]
  pending.clear(); pendingHelp.clear()
}
async function resume() {
  const id = attemptId.value, token = generation
  await labApi.post(aid('', id))
  await load(id, token)
}
function open(id) { return router.push({ query: { ...route.query, attempt: id || undefined } }) }
async function claim() {
  const token = generation
  const value = await labApi.post(`cases/${encodeURIComponent(selectedTask.value)}/claim/`)
  if (token === generation) {
    if (!attempts.value.some(a => a.attempt_id === value.attempt_id)) attempts.value.push({ attempt_id: value.attempt_id, task_key: selectedTask.value })
    await open(value.attempt_id)
  }
}
async function saveBasis() {
  const id = attemptId.value, token = generation
  await labApi.post(aid('basis/', id), { ...basis, expected_revision: state.value.revision })
  await load(id, token)
}
async function identify() {
  const id = attemptId.value, token = generation
  await send(aid('scans/', id), { fixture_id: material.value.fixture_id })
  await load(id, token)
}
function cell(row, column) { return scan.value?.cells.find(c => c.row === row && c.column === column) }
function parts(c) {
  const loc = selected.value?.locations?.[0]
  return splitCodepoints(c?.source_text || '', loc && c && loc.row === c.row && loc.column === c.column ? loc.span : null)
}
async function saveReview() {
  const id = attemptId.value, token = generation
  const body = { expected_state_version: scan.value.state_version, action: review.action, reason: review.reason, ...refs() }
  if (review.action === 'add_manual') {
    const c = cell(Number(review.row), Number(review.column))
    if (!c) throw new Error('请选择原文中的逻辑单元格')
    const span = { start: Number(review.start), end: Number(review.end) }
    if (!splitCodepoints(c.source_text, span).selected) throw new Error('码点位置无效：须满足 0 ≤ start < end ≤ 原文码点数')
    body.category_id = review.category_id
    body.locations = [{ kind: 'span', sheet_id: c.sheet_id, row: c.row, column: c.column, channel: c.channel, span }]
  } else {
    if (!selected.value) throw new Error('请先选择一个待复核候选')
    body.finding_id = selected.value.finding_id
    if (review.action === 'correct') body.category_id = review.category_id
  }
  await send(`profiles/${scan.value.profile_id}/reviews/`, body)
  if (token === generation) selected.value = null
  await load(id, token)
}
async function replay(variant) {
  const id = attemptId.value, token = generation
  await send(aid('replays/', id), { scenario_variant: variant })
  await load(id, token)
}
async function judge(r) {
  const id = attemptId.value, token = generation
  await send(`replays/${r.replay_id}/`, { ...predictions[r.replay_id], ...refs() })
  await load(id, token)
}
async function submit() {
  const id = attemptId.value, token = generation
  if (missingVariants.value.length) throw new Error(`请先完成当前扫描与画像的 ${missingVariants.value.join('、')} 回放判断`)
  const saved = await send(aid('submissions/', id), { explanation: explanation.value, scan_id: scan.value.scan_id,
    profile_id: scan.value.profile_id, replay_ids: submissionReplays.value.map(r => r.replay_id) })
  if (token === generation) result.value = saved
  await load(id, token)
}
async function showSubmission(id, retry = false) {
  const token = generation
  const value = await labApi[retry ? 'post' : 'get'](`submissions/${id}/`)
  if (token === generation) result.value = value
}
async function showAnalysis() {
  const token = generation
  const value = await labApi.get(aid('analysis/'))
  if (token === generation) analysis.value = value.content
}
async function hint(level) {
  const id = attemptId.value, token = generation
  let requestId = pendingHelp.get(level)
  if (!requestId) {
    const requested = await send(aid('help/', id), { level, source: 'card' })
    if (token !== generation) return
    requestId = requested.request_id
    pendingHelp.set(level, requestId)
  }
  const displayed = await labApi.post(`help/${requestId}/display/`)
  if (token === generation) { help.value = displayed.content; pendingHelp.delete(level) }
}
async function loadIndex() {
  if (indexLoading.value) return
  indexLoading.value = true; indexError.value = ''
  try {
    const index = await labApi.get('cases/'); cases.value = index.cases; attempts.value = index.attempts
    if (!selectedTask.value) selectedTask.value = cases.value[0]?.task_key || ''
  } catch (e) { indexError.value = readableError(e, '无法读取课程，请重试') }
  finally { indexLoading.value = false }
}
watch(() => route.query.attempt, value => {
  resetAttempt(typeof value === 'string' ? value : '')
  if (attemptId.value) void act(resume)
}, { immediate: true })
onMounted(loadIndex)
</script>

<template>
  <main class="data-lab">
    <header class="lab-header">
      <h1>数据安全案例实验台</h1>
      <strong>教学演练：只看决策，不执行导出</strong>
      <p>执行：未开展 · 实际保护：未评估 · 教学阈值：draft（不作为业务审批标准）</p>
      <p>尝试 {{ attemptId || '未领取' }} · 材料 {{ material?.material_version || '—' }} · 规则 {{ material?.rule_version || '—' }}</p>
      <output aria-live="polite">{{ saveStatus }}</output>
    </header>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <section aria-label="任务与尝试切换">
      <p v-if="indexError" role="alert" class="error">{{ indexError }}</p>
      <button :disabled="indexLoading || saving" @click="loadIndex">{{ indexLoading ? '正在读取列表…' : '刷新任务列表' }}</button>
      <template v-if="!state">
        <label>案例 <select v-model="selectedTask" :disabled="saving || indexLoading"><option v-for="c in cases" :key="c.task_key" :value="c.task_key">{{ c.title }} · {{ c.status }}{{ c.paused ? ' · 已暂停' : '' }}{{ c.withdrawn ? ' · 已撤回' : '' }}</option></select></label>
        <button :disabled="saving || indexLoading || !selectedTask" @click="act(claim)">领取任务</button>
        <button v-if="attemptId" :disabled="saving" @click="act(resume)">重试读取当前尝试</button>
        <p>草案/未签收材料不能领取。复测须从结果与复盘页领取已分配新场景。</p>
      </template>
      <button v-if="attemptId" :disabled="saving" @click="open('')">返回任务选择</button>
      <button v-for="a in attempts" :key="a.attempt_id" :disabled="saving || a.attempt_id === attemptId" @click="open(a.attempt_id)">继续 {{ a.task_key }} / {{ a.attempt_id }}</button>
      <p>切换尝试会清空本页未保存的输入、结果与提示。</p>
    </section>
    <template v-if="state">
      <nav aria-label="实验步骤"><button v-for="(label, i) in steps" :key="label" :aria-current="step === i ? 'step' : undefined" @click="step = i">{{ i + 1 }}. {{ label }}</button></nav>
      <section v-if="step === 0">
        <h2>{{ material.title }}</h2><p>{{ material.synthetic_declaration }}</p>
        <p>资产版本：{{ material.asset_version_id }} · SHA-256：<code>{{ material.sha256 }}</code></p>
        <p>{{ material.position_contract }}</p>
        <p>先说明适用事实与三个不同结论，再识别、复核、提出回放建议并交证据。规则分数不是法律分类或校准概率。</p>
        <aside><h3>教师预制讲解样例</h3><p>{{ material.teacher_example.before }} → {{ material.teacher_example.after }}</p><p>{{ material.teacher_example.label }}</p></aside>
      </section>
      <section v-if="step === 1">
        <h2>依据与事实</h2>
        <label v-for="(fact, id) in material.facts" :key="id"><input v-model="basis.fact_ids" type="checkbox" :value="id"> {{ id }}：{{ fact }}</label>
        <article v-for="card in state.basis_cards" :key="card.card_id">
          <label><input v-model="basis.basis_ids" type="checkbox" :value="card.card_id"> {{ card.card_id }} · {{ card.source_title }} {{ card.source_clause }}</label>
          <p>{{ card.source_version }} · 核验日 {{ card.verified_date || '待核验' }} · {{ card.status }}</p>
          <a :href="card.source_url" target="_blank" rel="noopener noreferrer">官方来源</a><p>{{ card.uncertainties }}</p>
        </article>
        <label>实体识别类别<textarea v-model="basis.entity_category" maxlength="2048" /></label>
        <label>个人信息属性（基于哪些可识别性事实）<textarea v-model="basis.personal_information" maxlength="2048" /></label>
        <label>数据分类分级判断（不以字段名推断等级）<textarea v-model="basis.data_classification" maxlength="2048" /></label>
        <label>不确定项与待复核责任<textarea v-model="basis.uncertainties" maxlength="2048" /></label>
        <button :disabled="saving" @click="act(saveBasis)">保存依据与引用</button>
      </section>
      <section v-if="step === 2">
        <h2>发现与复核</h2><button :disabled="saving || !state.basis.entity_category" @click="act(identify)">识别登记合成样本 / 新建扫描</button>
        <p>新扫描不继承旧复核；未检出不等于不敏感。空格也计入处理覆盖。</p>
        <p v-if="scan?.status !== 'completed'">{{ scan?.message || '尚未识别' }}</p>
        <template v-else>
          <p>原扫描：{{ scan.counts.original_findings }} 个候选；学生补录：{{ scan.counts.manual_additions }}；复核后：{{ scan.counts.reviewed_findings }}。</p>
          <p>规则覆盖 {{ scan.coverage.rule.processed_count }} / {{ scan.coverage.rule.target_count }} 格；语义 {{ scan.coverage.semantic.status }}。人工补录不增加原检测覆盖。</p>
          <div class="review-grid">
            <table><caption>逻辑行（表头占第1行）；选候选后按码点高亮</caption><thead><tr><th>行</th><th v-for="n in 4" :key="n">列 {{ n }}</th></tr></thead>
              <tbody><tr v-for="row in rows" :key="row"><th>{{ row }}</th><td v-for="col in 4" :key="col"><span>{{ parts(cell(row,col)).before }}</span><mark v-if="parts(cell(row,col)).selected">{{ parts(cell(row,col)).selected }}</mark><span>{{ parts(cell(row,col)).after }}</span><em v-if="!cell(row,col)?.source_text">（空值）</em></td></tr></tbody>
            </table>
            <div><button v-for="f in scan.findings.items" :key="f.finding_id" @click="selected = f">{{ f.category_id }} · 行{{ f.locations[0].row }}列{{ f.locations[0].column }} · {{ f.source_type === 'manual' ? '学生复核' : '自动候选' }}</button>
              <p v-if="selected">{{ selected.judgment }} · {{ selected.detector_version || '人工' }} · 原始分数 {{ selected.raw_score ?? '不适用' }}（非概率）</p>
              <label>动作<select v-model="review.action"><option value="confirm">确认</option><option value="correct">纠正</option><option value="false_positive">误报</option><option value="add_manual">漏报补录</option></select></label>
              <label v-if="['correct','add_manual'].includes(review.action)">类别<select v-model="review.category_id"><option>DEMO_PERSON_REF</option><option>DEMO_CONTACT</option></select></label>
              <fieldset v-if="review.action === 'add_manual'"><legend>原文码点位置 [start,end)</legend><label v-for="k in ['row','column','start','end']" :key="k">{{ k }} <input v-model.number="review[k]" type="number" min="0"></label></fieldset>
              <label>复核理由（引用上一步选定事实/依据卡）<textarea v-model="review.reason" maxlength="1500" /></label>
              <button :disabled="saving || (!selected && review.action !== 'add_manual')" @click="act(saveReview)">保存复核与后继画像</button>
            </div>
          </div>
          <button :disabled="saving" @click="act(load)">刷新最新画像（冲突后先查看差异）</button>
          <details><summary>复核历史</summary><p v-for="r in scan.review_history" :key="r.review_id">{{ r.action }} · {{ r.reason }} · {{ r.successor_profile_id }}</p></details>
        </template>
      </section>
      <section v-if="step === 3">
        <h2>四轮决策回放</h2><p>先保存自己的建议，后显示程序建议。回放使用教师冻结参考画像，不把学生原扫描覆盖写成100%。</p>
        <p>仅展示当前扫描 {{ scan?.scan_id || '—' }} / 画像 {{ scan?.profile_id || '—' }} 的回放；重新扫描或复核后须重新完成四轮。</p>
        <button v-for="v in replayVariants" :key="v" :disabled="saving || scan?.status !== 'completed'" @click="act(() => replay(v))">开始 {{ v }}</button>
        <article v-for="r in replays" :key="r.replay_id">
          <h3>{{ r.scenario_variant }} · {{ r.policy_version }} / draft</h3><p>评估时刻 {{ r.evaluation_time }}</p>
          <template v-if="!r.revealed">
            <label v-for="(_, i) in predictions[r.replay_id]?.actions" :key="i">{{ r.scenario_variant === 'A4' ? `${50+i}次（每次10条）` : '我的建议' }}
              <select v-model="predictions[r.replay_id].actions[i]"><option value="">请选择</option><option v-for="a in ['allow','mask','deny','defer','require_approval']" :key="a">{{ a }}</option></select>
            </label><textarea v-model="predictions[r.replay_id].reason" aria-label="回放理由" maxlength="2048" />
            <button :disabled="saving" @click="act(() => judge(r))">保存判断并查看程序对照</button>
          </template>
          <template v-else><p>我的建议 {{ r.judgment.actions.join(' → ') }}；理由：{{ r.judgment.reason }}</p>
            <p v-for="(s, i) in r.frozen.steps" :key="i">程序建议 {{ s.result.recommended_action }}；请求次数 {{ s.inputs.features.values.req_count_long }}；已计入当前请求 {{ s.inputs.features.current_request_counted }}；义务 {{ s.result.obligations.map(o => o.type).join('、') || '无' }}</p>
            <p v-for="(reason, code) in r.reason_explanations" :key="code"><code>{{ code }}</code>：{{ reason }}</p>
            <details><summary>冻结输入与摘要</summary><pre>{{ JSON.stringify(r.frozen, null, 2) }}</pre></details>
          </template>
        </article>
      </section>
      <section v-if="step === 4">
        <h2>提交与结果</h2><label>依据、因果、证据与改进说明<textarea v-model="explanation" maxlength="4000" /></label>
        <p v-if="missingVariants.length">当前扫描/画像尚缺已揭示回放：{{ missingVariants.join('、') }}。</p>
        <p v-else>将提交每个变体最新的已揭示结果（不使用其他扫描或旧画像的回放）。</p>
        <ul><li v-for="r in submissionReplays" :key="r.replay_id">{{ r.scenario_variant }}：{{ r.replay_id }}</li></ul>
        <p>本阶段先保存证据；模块六交接以服务端返回状态为准，不将保存成功当作核验通过。</p>
        <button :disabled="saving || scan?.status !== 'completed' || missingVariants.length > 0" @click="act(submit)">保存证据 / 查询核验状态</button>
        <button v-for="id in state.submissions" :key="id" :disabled="saving" @click="act(() => showSubmission(id))">查看提交 {{ id }}</button>
        <article v-if="result"><p>保存 {{ result.save_status }} · 核验 {{ result.program_status }} · 人工 {{ result.manual_status }} · 帮助 {{ result.independence }}</p><p>{{ result.message }}</p>
          <p>执行：未开展；实际保护：未评估（不计执行成绩）</p><button :disabled="saving" @click="act(() => showSubmission(result.submission_id, true))">重试核验/交接</button></article>
        <router-link to="/my-results">模块六：结果、教师待评、复盘与新场景复测</router-link>
        <button :disabled="saving" @click="act(showAnalysis)">查看已解锁学生解析</button><p>{{ analysis }}</p>
      </section>
      <aside class="help"><h2>预置帮助（可选，无 AI 也能继续）</h2><p>请求与实际展示分别记录；任何层级展示均记受助。无提示复测仍可提交，不自动展开帮助。</p>
        <button v-for="level in 4" :key="level" :disabled="saving" @click="act(() => hint(level))">第 {{ level }} 层提示</button><p aria-live="polite">{{ help }}</p>
      </aside>
    </template>
  </main>
</template>

<style scoped>
.data-lab { max-width: 1240px; margin: 0 auto; padding: 24px; color: var(--color-text-1, #17212b); }
.lab-header { position: sticky; top: 0; z-index: 3; background: var(--color-bg-1, #fff); border-bottom: 2px solid #46596b; padding: 12px 0; }
.lab-header h1 { margin: 0 0 8px; font-size: 24px; } p { line-height: 1.65; } code { overflow-wrap: anywhere; }
nav { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0; } section, article, aside { margin: 20px 0; padding: 16px; border: 1px solid var(--color-border-2, #c7cdd3); border-radius: 6px; }
button, select, input, textarea { font: inherit; } button { margin: 4px; padding: 8px 12px; cursor: pointer; } button:disabled { cursor: not-allowed; opacity: .6; } [aria-current="step"] { font-weight: bold; outline: 2px solid #46596b; }
label { display: block; margin: 12px 0; } textarea { display: block; width: 100%; min-height: 80px; box-sizing: border-box; } input[type="number"] { width: 85px; }
.review-grid { display: grid; grid-template-columns: minmax(0, 3fr) minmax(260px, 2fr); gap: 16px; } table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #a6aeb6; padding: 8px; white-space: pre-wrap; overflow-wrap: anywhere; } td { max-width: 180px; } mark { background: #f6de8a; color: #17212b; } pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; } .error { border-left: 4px solid #a82b2b; padding: 12px; }
@media(max-width: 800px) { .review-grid { display: block; } .data-lab { padding: 12px; } .lab-header { position: static; } }
</style>
