<template>
  <section class="retest-list" aria-labelledby="retest-heading">
    <header class="block-head">
      <div>
        <h3 id="retest-heading">待复测</h3>
        <p class="block-note">复测会使用安排好的新场景；领取后进入对应任务继续练习。到期未参加不记为知识错误。</p>
      </div>
      <button type="button" class="text-action" :disabled="loading" @click="load">刷新</button>
    </header>

    <p v-if="loading" class="state-note" role="status">正在读取复测安排…</p>
    <p v-else-if="error" class="state-note is-error" role="alert">{{ error }}<button type="button" class="text-action" @click="load">重试</button></p>
    <p v-else-if="!rows.length" class="state-note">暂无复测安排。完成复盘并提交完整学习记录后，会按规则安排新场景。</p>

    <ul v-else class="retest-items">
      <li v-for="item in rows" :key="item.id" class="retest-item">
        <div class="retest-main">
          <strong>{{ item.taskTitle || '等待补充新场景' }}</strong>
          <div class="retest-meta">
            <span class="status-chip" :class="`is-${item.status}`">{{ item.statusLabel }}</span>
            <span>建议 {{ item.dueLabel }}</span>
            <span v-if="item.versionLabel">版本 {{ item.versionLabel }}</span>
            <span v-if="item.originalTaskTitle">原任务：{{ item.originalTaskTitle }}</span>
          </div>
          <p v-if="item.outcomeLabel" class="retest-outcome">结果：{{ item.outcomeLabel }}<template v-if="item.completedLabel"> · {{ item.completedLabel }}</template></p>
          <p v-if="item.note" class="retest-note">说明：{{ item.note }}</p>
          <p v-if="feedback[item.id]" class="retest-feedback" :class="{ 'is-error': feedback[item.id].error }" role="status">{{ feedback[item.id].text }}</p>
          <p v-if="targets[item.id]" class="retest-target">
            <span v-if="targets[item.id].unresolved" class="retest-target-missing">{{ targets[item.id].reason }}</span>
            <span v-else-if="!targets[item.id].available" class="retest-target-missing">{{ targets[item.id].reason }}</span>
            <span v-if="targets[item.id].attemptId" class="retest-target-ids">任务：{{ targets[item.id].taskTitle }}<template v-if="targets[item.id].versionLabel"> · {{ targets[item.id].versionLabel }}</template> · 尝试编号 {{ targets[item.id].attemptId }}</span>
            <span v-if="targets[item.id].note" class="retest-target-note">{{ targets[item.id].note }}</span>
          </p>
        </div>
        <div class="retest-actions">
          <button
            v-if="item.claimable"
            type="button"
            class="btn btn-primary"
            :disabled="claiming === item.id"
            @click="claim(item)"
          >{{ claiming === item.id ? '领取中…' : item.claimLabel }}</button>
          <span v-else-if="item.pendingItem" class="status-chip is-pending_item">待补题</span>
        </div>
      </li>
    </ul>
  </section>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '@/api'
import { claimTarget, errorText, retestViews } from '../reviewActions.js'

const rows = ref([])
const loading = ref(true)
const error = ref('')
const claiming = ref(null)
const feedback = reactive({})
const targets = reactive({})

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = retestViews(await api.skillReview.myRetests())
  } catch (err) {
    rows.value = []
    error.value = errorText(err)
  } finally {
    loading.value = false
  }
}

// 领取成功不吞掉返回的目标：把 attempt_id/task/created/note 原样转成工作面入口。
async function claim(item) {
  if (claiming.value) return
  claiming.value = item.id
  delete feedback[item.id]
  try {
    const payload = await api.skillReview.claimRetest(item.id)
    targets[item.id] = claimTarget(payload)
    feedback[item.id] = { text: targets[item.id].available ? targets[item.id].message : targets[item.id].reason, error: !targets[item.id].available }
    await load()
  } catch (err) {
    feedback[item.id] = { text: `领取未完成：${errorText(err)}`, error: true }
  } finally {
    claiming.value = null
  }
}

onMounted(load)
defineExpose({ load, rows, loading, error, claim, claiming, targets, feedback })
</script>
<style scoped>
.retest-list { display: grid; gap: var(--space-2); }
.block-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.block-head h3 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.block-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.retest-items { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.retest-item { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.retest-main { display: grid; gap: var(--space-1); min-width: 0; }
.retest-main strong { overflow-wrap: anywhere; }
.retest-meta { display: flex; flex-wrap: wrap; gap: var(--space-2); color: var(--ink-secondary); font-size: var(--text-caption); }
.status-chip { display: inline-flex; align-items: center; padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.status-chip.is-due { background: var(--warning-soft); color: var(--warning); }
.status-chip.is-in_progress { background: var(--action-soft); color: var(--action); }
.status-chip.is-completed { background: var(--positive-soft); color: var(--positive); }
.status-chip.is-missed { background: var(--negative-soft); color: var(--negative); }
.retest-outcome, .retest-note, .retest-target, .retest-feedback { margin: 0; font-size: var(--text-caption); }
.retest-outcome { color: var(--ink-secondary); }
.retest-note, .retest-target-note { color: var(--ink-muted); }
.retest-target-ids { color: var(--ink-secondary); overflow-wrap: anywhere; }
.retest-feedback { color: var(--positive); }
.retest-feedback.is-error, .retest-target-missing { color: var(--negative); }
.retest-target { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-2); align-items: center; }
.retest-actions { display: flex; align-items: center; gap: var(--space-1); }
.btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:disabled { border-color: var(--line); background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.text-link { display: inline-flex; align-items: center; min-height: var(--control-height); color: var(--action); font-size: var(--text-caption); text-decoration: none; }
.btn:focus-visible, .text-link:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.is-compact .retest-item { flex-direction: column; }
</style>
