<template>
  <section class="submission-history" aria-label="我的提交记录">
    <header class="history-heading">
      <h2>我的提交记录</h2>
      <span v-if="scopeNote" class="history-scope">{{ scopeNote }}</span>
    </header>
    <p v-if="!authenticated" class="history-state">登录后可查看本题的本人提交。</p>
    <p v-else-if="loading && !items.length" class="history-state" role="status">正在读取本题提交记录…</p>
    <p v-else-if="error" class="history-state error" role="alert">
      {{ error }}<button type="button" class="text-action" @click="$emit('retry')">重试</button>
    </p>
    <template v-else-if="items.length">
      <ol class="history-list">
        <li v-for="item in items" :key="item.id" class="history-item">
          <time>{{ formatTime(item.created_at) }}</time>
          <span class="history-result" :class="item.is_correct ? 'is-correct' : 'is-incorrect'">{{ item.is_correct ? '已通过' : '未通过' }}</span>
        </li>
      </ol>
      <button v-if="hasNext" type="button" class="btn" :disabled="loading" @click="$emit('more')">
        {{ loading ? '正在加载…' : '加载更早记录' }}
      </button>
    </template>
    <template v-else>
      <p class="history-state">{{ hasNext ? '已读取的最近记录里还没有本题提交，可继续加载更早记录。' : '本题还没有你的提交记录。' }}</p>
      <button v-if="hasNext" type="button" class="btn" :disabled="loading" @click="$emit('more')">
        {{ loading ? '正在加载…' : '加载更早记录' }}
      </button>
    </template>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { submissionScopeNote } from '@/learning/practice/workspaceView.js'
const props = defineProps({
  authenticated: Boolean,
  items: { type: Array, default: () => [] },
  loading: Boolean,
  error: { type: String, default: '' },
  hasNext: Boolean,
  info: { type: Object, default: null },
})
defineEmits(['more', 'retry'])
const scopeNote = computed(() => submissionScopeNote(props.info))
const formatTime = value => {
  const date = new Date(value)
  return value && Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN') : '时间暂不可用'
}
</script>
<style scoped>
.submission-history { padding-top: var(--space-3); border-top: var(--stroke) solid var(--line); }
.history-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-1); margin-bottom: var(--space-1); }
.history-heading h2 { margin: 0; font-size: var(--text-card); }
.history-scope, .history-state { color: var(--ink-secondary); font-size: var(--text-caption); }
.history-state { margin: 0; }
.history-state.error { color: var(--negative); }
.text-action { margin-left: var(--space-1); border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; text-decoration: underline; }
.history-list { display: grid; gap: var(--space-1); margin: 0 0 var(--space-2); padding: 0; list-style: none; }
.history-item { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-1) 0; border-bottom: var(--stroke) solid var(--line); font-size: var(--text-caption); }
.history-item time { color: var(--ink-secondary); }
.is-correct { color: var(--positive); }
.is-incorrect { color: var(--negative); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.btn:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
