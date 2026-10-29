<template>
  <section class="operations">
    <h2>教师协作待办（正式、全平台范围）</h2>
    <p>协作记录不代替模块六评阅/抽查/争议处理。处理后须由实际新场景、无提示复测验证，不提供“标记已改善”。</p>
    <button :disabled="busy" @click="run(load)">刷新待办</button>
    <button :disabled="busy" @click="run(sync)">同步源队列</button>
    <button :disabled="busy" @click="run(receive)">接收更正并重算</button>
    <p v-if="message" role="status">{{ message }}</p>
    <form @submit.prevent="run(create)">
      <label>尝试 UUID<input v-model.trim="attemptId" required /></label>
      <label>原调整提案 ID（可选）<input v-model="proposalId" type="number" min="1" /></label>
      <button :disabled="busy">建立协作待办</button>
    </form>
    <section v-for="(items, kind) in groups" :key="kind">
      <h3>{{ kinds[kind] }}</h3><p v-if="!items.length">暂无待办。</p>
      <article v-for="item in items" :key="item.todo_id">
        <p>学生 {{ item.student_id }} · 负责人 {{ item.owner_id ?? '未认领' }} · {{ states[item.status] || item.status }} · revision {{ item.revision }}</p>
        <p>尝试：{{ item.attempt_id }} · 原结果：{{ item.original_result_id || '暂无' }}</p>
        <p>源队列当前状态：{{ sourceStates[item.source_current_status] || item.source_current_status || '手工待办，无源队列' }}</p>
        <p>{{ item.summary }}</p>
        <button v-if="!item.owner_id" :disabled="busy" @click="run(() => change(item, 'claim'))">认领</button>
        <template v-else>
          <label>处理摘要 / 转交原因<input v-model.trim="draft(item).summary" maxlength="1000" /></label>
          <button :disabled="busy" @click="run(() => change(item, 'handle'))">记录处理</button>
          <label>接手教师内部 ID<input v-model="draft(item).assignee" type="number" min="1" /></label>
          <button :disabled="busy" @click="run(() => change(item, 'transfer'))">转交</button>
          <label>模块六复测 UUID<input v-model.trim="draft(item).retest" /></label>
          <button :disabled="busy" @click="run(() => change(item, 'verify'))">核对实际复测</button>
        </template>
        <details><summary>源快照、复测证据和操作审计</summary><pre>{{ JSON.stringify(item, null, 2) }}</pre></details>
      </article>
    </section>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import evaluation from '@/api/evaluation'

const groups = ref({})
const drafts = reactive({})
const busy = ref(false)
const message = ref('')
const attemptId = ref('')
const proposalId = ref('')
const kinds = { help: '主动求助', manual_review: '开放题必评', sampling: '常规抽查', dispute: '争议复核', evidence: '证据异常' }
const states = { unclaimed: '未认领', in_progress: '处理中', pending_verification: '待验证', verified: '复测已验证' }
const sourceStates = { pending: '待认领', open: '开放', claimed: '处理中', completed: '已完成', needs_correction: '需更正', submitted: '已提交', under_review: '复核中', reviewed: '已评阅', resolved: '已解决', helped: '已协助' }
function draft(item) {
  return drafts[item.todo_id] || (drafts[item.todo_id] = { summary: '', assignee: '', retest: item.retest_id || '' })
}
async function load() { groups.value = (await evaluation.todos()).groups }
async function sync() { await evaluation.syncTodos(); await load() }
async function receive() {
  const response = await evaluation.consumeReceipts()
  await load()
  message.value = `已读取 ${response.receipts.length} 条幂等回执；未改写源成绩。`
}
async function create() {
  await evaluation.createTodo({ attempt_id: attemptId.value, ...(proposalId.value ? { proposal_id: Number(proposalId.value) } : {}) })
  await load()
}
async function change(item, action) {
  const edit = draft(item)
  await evaluation.changeTodo(item.todo_id, { revision: item.revision, action,
    ...(action === 'handle' || action === 'transfer' ? { summary: edit.summary } : {}),
    ...(action === 'transfer' ? { assignee_id: Number(edit.assignee) } : {}),
    ...(action === 'verify' && edit.retest ? { retest_id: edit.retest } : {}),
  })
  await load()
}
async function run(work) {
  busy.value = true
  message.value = ''
  try { await work() } catch (error) {
    message.value = error.response?.status === 409 ? '待办已变化，请刷新后按新 revision 操作。' : '操作失败；请核对权限、摘要与关联 ID 后重试。'
  } finally { busy.value = false }
}
</script>

<style scoped>
.operations{margin-top:32px}article{padding:14px;border:1px solid #888;margin:12px 0}label{display:inline-grid;gap:4px;margin:8px}button,input{font:inherit;padding:7px;background:transparent;color:inherit;border:1px solid #888;border-radius:4px}button{cursor:pointer;margin:4px}button:disabled{cursor:wait}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:500px;overflow:auto}
</style>
