<template>
  <section class="challenge-body" aria-label="题面">
    <header class="challenge-header">
      <h1 class="challenge-title">{{ challenge.title }}</h1>
      <div class="challenge-badges">
        <span class="badge">{{ difficultyText(challenge.difficulty) }}</span>
        <span v-if="challenge.category_name" class="badge">{{ challenge.category_name }}</span>
        <span class="badge" :class="{ 'badge-practice': !mode.scoring }">{{ mode.label }}</span>
        <span v-if="challenge.is_solved" class="badge badge-solved">已解出</span>
      </div>
    </header>

    <h2 class="section-title">题目说明</h2>
    <div class="challenge-description">{{ challenge.description || '题面暂未提供。' }}</div>

    <div v-if="challenge.hint" class="challenge-hint">
      <h2 class="section-title">提示</h2>
      <div class="hint-content">{{ challenge.hint }}</div>
    </div>

    <div class="challenge-tutor-entry">
      <span>想继续深入时，先说说你的尝试，再让智航按策略分级提示。</span>
      <button type="button" class="btn" @click="$emit('ask-tutor')">请给一点提示</button>
    </div>

    <div v-if="challenge.attachment" class="challenge-attachment">
      <h2 class="section-title">附件</h2>
      <a :href="challenge.attachment" class="attachment-link" target="_blank" rel="noopener noreferrer">
        <AppIcon name="bi-arrow-down" aria-hidden="true" />下载附件
      </a>
    </div>
  </section>
</template>
<script setup>
import AppIcon from '@/shared/design/AppIcon.vue'
import { difficultyText, modeBadge } from '@/learning/practice/workspaceView.js'
import { computed } from 'vue'
const props = defineProps({ challenge: { type: Object, required: true } })
defineEmits(['ask-tutor'])
const mode = computed(() => modeBadge(props.challenge))
</script>
<style scoped>
.challenge-body { min-width: 0; }
.challenge-header { padding-bottom: var(--space-2); margin-bottom: var(--space-3); border-bottom: var(--stroke) solid var(--line); }
.challenge-title { margin: 0 0 var(--space-2); font-size: var(--text-section); font-weight: var(--weight-strong); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.challenge-badges { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.badge { padding: 0 var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.badge-practice { background: var(--agent-soft); color: var(--agent-accent); }
.badge-solved { background: var(--positive-soft); color: var(--positive); }
.section-title { margin: 0 0 var(--space-2); font-size: var(--text-card); font-weight: var(--weight-strong); }
.challenge-description, .hint-content { white-space: pre-wrap; overflow-wrap: anywhere; }
.challenge-description { margin: 0 0 var(--space-3); color: var(--ink); line-height: var(--leading-body); }
.challenge-hint, .challenge-attachment { margin-bottom: var(--space-3); }
.challenge-tutor-entry { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); margin-bottom: var(--space-3); padding: var(--space-2); border-radius: var(--radius-control); background: var(--agent-soft); color: var(--ink-secondary); font-size: var(--text-caption); }
.challenge-tutor-entry .btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.challenge-tutor-entry .btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.hint-content { padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.attachment-link { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); color: var(--action); text-decoration: none; }
.attachment-link:hover { background: var(--surface-hover); }
.attachment-link:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
