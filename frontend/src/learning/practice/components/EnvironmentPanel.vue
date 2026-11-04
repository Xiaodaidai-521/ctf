<template>
  <section class="environment-panel" aria-label="练习环境">
    <header class="env-heading">
      <h2>练习环境</h2>
      <span class="env-status" :class="statusClass">{{ state.phase === 'timeout' ? '读取超时' : status.label }}</span>
    </header>

    <p v-if="state.error" class="env-error" role="alert">
      {{ state.error }}<button v-if="authenticated" type="button" class="text-action" :disabled="state.starting" @click="$emit('refresh')">重新读取</button>
    </p>
    <p v-if="message" class="env-feedback" :class="messageType" :role="messageType === 'error' ? 'alert' : 'status'">{{ message }}</p>

    <p v-if="state.phase === 'waiting'" class="env-note" role="status">环境正在启动或尚未提供访问地址，读取到可用地址后这里会显示。</p>
    <p v-if="state.phase === 'expired'" class="env-note">环境已到期，重新启动会重置练习数据。</p>

    <template v-if="state.info && (state.phase === 'ready' || state.phase === 'waiting')">
      <div v-if="accessUrl" class="env-access">
        <span class="access-label">访问地址</span>
        <a :href="accessUrl" target="_blank" rel="noopener noreferrer" class="access-link">{{ accessUrl }}</a>
        <button type="button" class="btn btn-small" @click="$emit('copy')">复制地址</button>
      </div>
      <p class="env-note">剩余时间：{{ countdownText }}</p>
    </template>

    <div class="env-actions">
      <button
        v-if="!running"
        type="button"
        class="btn btn-primary"
        :disabled="state.starting || !authenticated"
        :aria-busy="state.starting"
        @click="$emit('start')"
      >{{ state.starting ? '正在启动…' : '启动环境' }}</button>
      <button
        v-else
        type="button"
        class="btn"
        :disabled="state.stopping"
        :aria-busy="state.stopping"
        @click="$emit('stop')"
      >{{ state.stopping ? '正在停止…' : '停止环境' }}</button>
      <router-link v-if="!authenticated" to="/login" class="btn">登录后启动</router-link>
    </div>
    <p class="env-note">环境状态只读取服务端真实状态；启动进度以服务端是否就绪为准，不显示预计百分比。</p>
  </section>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({
  state: { type: Object, required: true },
  status: { type: Object, required: true },
  countdownText: { type: String, default: '未提供' },
  authenticated: Boolean,
  message: { type: String, default: '' },
  messageType: { type: String, default: '' },
})
defineEmits(['start', 'stop', 'copy', 'refresh'])
const running = computed(() => props.status.running)
const accessUrl = computed(() => props.status.accessUrl)
const statusClass = computed(() => ({
  'is-ready': props.state.phase === 'ready',
  'is-busy': ['waiting', 'timeout'].includes(props.state.phase),
  'is-error': props.state.phase === 'error',
  'is-expired': props.state.phase === 'expired',
}))
</script>
<style scoped>
.environment-panel { display: grid; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); min-width: 0; }
.env-heading { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2); }
.env-heading h2 { margin: 0; font-size: var(--text-card); }
.env-status { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface); color: var(--ink-secondary); font-size: var(--text-caption); }
.env-status.is-ready { background: var(--positive-soft); color: var(--positive); }
.env-status.is-busy { background: var(--warning-soft); color: var(--ink); }
.env-status.is-error { background: var(--negative-soft); color: var(--negative); }
.env-status.is-expired { background: var(--surface); color: var(--ink-muted); }
.env-error { margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--negative-soft); color: var(--negative); font-size: var(--text-caption); }
.env-feedback { margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--positive-soft); color: var(--positive); font-size: var(--text-caption); }
.env-feedback.error { background: var(--negative-soft); color: var(--negative); }
.env-feedback.info { background: var(--action-soft); color: var(--action); }
.env-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.text-action { margin-left: var(--space-1); border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; text-decoration: underline; }
.env-access { display: grid; gap: var(--space-1); }
.access-label { color: var(--ink-secondary); font-size: var(--text-caption); }
.access-link { color: var(--action); font-size: var(--text-caption); overflow-wrap: anywhere; }
.env-actions { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; text-decoration: none; cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn-small { min-height: calc(var(--control-height) - var(--space-1)); }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); border-color: var(--line); cursor: not-allowed; }
.btn:focus-visible, .access-link:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
