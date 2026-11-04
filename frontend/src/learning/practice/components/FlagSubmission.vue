<template>
  <section class="flag-submission" aria-label="提交与反馈">
    <div v-if="challenge.is_solved" class="solved-banner">
      <AppIcon name="bi-check-circle" aria-hidden="true" />
      <div>
        <h2>已解决此题</h2>
        <p v-if="mode.scoring">获得 {{ challenge.score }} 分</p>
        <p v-else>自由练习不记分。</p>
      </div>
    </div>

    <div v-if="!mode.scoring" class="practice-notice">
      <h2 class="section-title">自由练习</h2>
      <p>本题用于自由练习，不要求提交 Flag、不计分，平台也不会同步练习成绩。</p>
      <p>停止或到期回收环境后，再次启动会重置练习数据。</p>
      <p class="notice-next">可以先按题面动手实践，遇到卡点再<button type="button" class="text-action" @click="$emit('ask-tutor')">向智航提问</button>。</p>
    </div>

    <template v-else>
      <h2 class="section-title">提交 Flag</h2>
      <form v-if="authenticated" class="submit-form" @submit.prevent="$emit('submit')">
        <label class="input-label" for="flag-input">Flag 答案</label>
        <input
          id="flag-input"
          :value="flag"
          type="text"
          class="input"
          autocomplete="off"
          spellcheck="false"
          placeholder="请输入 flag，例如 flag{...}"
          aria-label="Flag 答案"
          :disabled="submitting || challenge.is_solved"
          @input="$emit('update:flag', $event.target.value)"
        />
        <button
          type="submit"
          class="btn btn-primary"
          :disabled="submitting || challenge.is_solved || !flag.trim()"
          :aria-busy="submitting"
        >
          {{ submitting ? '正在提交…' : (challenge.is_solved ? '已解出' : '提交答案') }}
        </button>
      </form>
      <router-link v-else to="/login" class="btn btn-primary btn-block">登录后提交</router-link>
      <div v-if="message" class="submit-message" :class="messageType" :role="messageType === 'error' ? 'alert' : 'status'">
        {{ message }}
      </div>
      <p class="submit-hint">答案通常采用 flag{...} 格式，请以题目说明为准。</p>
    </template>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
import { modeBadge } from '@/learning/practice/workspaceView.js'
const props = defineProps({
  challenge: { type: Object, required: true },
  authenticated: Boolean,
  flag: { type: String, default: '' },
  submitting: Boolean,
  message: { type: String, default: '' },
  messageType: { type: String, default: '' },
})
defineEmits(['update:flag', 'submit', 'ask-tutor'])
const mode = computed(() => modeBadge(props.challenge))
</script>
<style scoped>
.flag-submission { display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
.section-title { margin: 0; font-size: var(--text-card); font-weight: var(--weight-strong); }
.solved-banner { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-control); background: var(--positive-soft); color: var(--positive); }
.solved-banner h2 { margin: 0 0 var(--space-1); font-size: var(--text-body); }
.solved-banner p { margin: 0; font-size: var(--text-caption); }
.practice-notice { display: grid; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.practice-notice p { margin: 0; }
.practice-notice .section-title { color: var(--ink); }
.notice-next { color: var(--ink); }
.text-action { border: 0; background: transparent; padding: 0; color: var(--action); font: inherit; cursor: pointer; text-decoration: underline; }
.submit-form { display: grid; gap: var(--space-1); }
.input-label { color: var(--ink-secondary); font-size: var(--text-caption); }
.input { width: 100%; min-width: 0; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; }
.input:disabled { background: var(--disabled); color: var(--disabled-ink); border-color: var(--line); cursor: not-allowed; }
.input:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-weight: var(--weight-medium); text-decoration: none; cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); }
.btn-primary:active:not(:disabled) { background: var(--action-pressed); }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); border-color: var(--line); cursor: not-allowed; }
.btn-block { width: 100%; }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.submit-message { padding: var(--space-2); border-radius: var(--radius-control); font-size: var(--text-caption); }
.submit-message.success { background: var(--positive-soft); color: var(--positive); }
.submit-message.error { background: var(--negative-soft); color: var(--negative); }
.submit-message.info { background: var(--action-soft); color: var(--action); }
.submit-hint { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
</style>
