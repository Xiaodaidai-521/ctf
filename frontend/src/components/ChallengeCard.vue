<template>
  <div class="challenge-card" :class="{ solved: challenge.is_solved }" @click="handleClick" role="button" tabindex="0" :aria-label="`打开题目：${challenge.title}`" @keydown.enter="handleClick" @keydown.space.prevent="handleClick">
    <div class="card-header">
      <span class="difficulty-badge" :class="difficultyClass">{{ difficultyText }}</span>
    </div>
    <div class="card-body">
      <h3 class="challenge-title">{{ challenge.title }}</h3>
      <div class="challenge-meta">
        <span class="category-tag">{{ challenge.category_name }}</span>
      </div>
    </div>
    <div class="card-footer">
      <div class="meta-item">
        <span class="meta-icon"><icon-bar-chart aria-hidden="true" /></span>
        <span class="meta-text">积分: {{ challenge.score }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-icon"><icon-user-group aria-hidden="true" /></span>
        <span class="meta-text">解出: {{ challenge.solve_count }}</span>
      </div>
      <div class="meta-item solved-indicator" v-if="challenge.is_solved">
        <span class="meta-icon"><icon-check-circle aria-hidden="true" /></span>
        <span class="meta-text">已解决</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  challenge: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['click'])

const difficultyText = computed(() => {
  const difficultyMap = {
    'easy': '简单',
    'medium': '中等',
    'hard': '困难',
    'expert': '专家'
  }
  return difficultyMap[props.challenge.difficulty] || '未知'
})

const difficultyClass = computed(() => {
  return `difficulty-${props.challenge.difficulty}`
})

const handleClick = () => {
  emit('click', props.challenge)
}
</script>

<style scoped>
.challenge-card { background: var(--surface); border-radius: var(--radius-panel); cursor: pointer; transition: background var(--motion-fast); display: flex; flex-direction: column; min-width: 0; }
.challenge-card:hover { background: var(--surface-hover); }
.challenge-card:active { background: var(--surface-muted); }
.card-header { display: flex; align-items: center; padding: var(--space-2) var(--space-2) 0; }
.difficulty-badge { padding: 0 var(--space-1); border-radius: var(--radius-control); font-size: var(--text-caption); color: var(--ink-secondary); background: var(--surface-muted); }
.card-body { padding: var(--space-2); flex: 1; }
.challenge-title { font-size: var(--text-card); line-height: var(--leading-tight); margin: 0 0 var(--space-2); overflow-wrap: anywhere; }
.challenge-meta { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.category-tag { color: var(--ink-secondary); font-size: var(--text-caption); }
.card-footer { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-2); padding: var(--space-2); border-top: var(--stroke) solid var(--line); }
.meta-item { display: flex; align-items: center; gap: var(--space-1); font-size: var(--text-caption); color: var(--ink-secondary); }
.meta-icon { font-size: var(--icon-size); }
.solved-indicator { color: var(--positive); }
</style>
