<template>
  <div class="challenge-card" :class="{ solved: challenge.is_solved }" @click="handleClick">
    <div class="card-header">
      <span class="challenge-id">#{{ challenge.id }}</span>
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
        <span class="meta-icon"><i class="bi bi-bar-chart"></i></span>
        <span class="meta-text">积分: {{ challenge.score }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-icon"><i class="bi bi-people"></i></span>
        <span class="meta-text">解出: {{ challenge.solve_count }}</span>
      </div>
      <div class="meta-item solved-indicator" v-if="challenge.is_solved">
        <span class="meta-icon"><i class="bi bi-check2-circle"></i></span>
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
.challenge-card {
  position: relative;
  background: rgba(255, 250, 242, 0.72);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: none;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  min-height: 178px;
}

.challenge-card:hover {
  box-shadow: 8px 8px 0 rgba(24, 23, 19, 0.1);
  transform: translateY(-2px);
  border-color: var(--primary-color);
}

.challenge-card.solved {
  border-color: var(--border-color);
  background: rgba(255, 250, 242, 0.72);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  background: var(--text-primary);
  color: #fbf7ef;
}

.challenge-card.solved .card-header {
  background: var(--text-primary);
}

.challenge-id {
  color: var(--secondary-color);
  font-size: 12px;
  font-weight: 950;
  opacity: 1;
}

.difficulty-badge {
  padding: 3px 8px;
  border-radius: 2px;
  font-size: 11px;
  font-weight: 850;
  color: var(--text-primary);
  background: var(--bg-paper-2);
  border: 1px solid rgba(24, 23, 19, 0.18);
}

.difficulty-easy {
  color: var(--text-primary);
  background: var(--bg-paper-2);
}

.difficulty-medium {
  color: #181713;
  background: rgba(239, 196, 107, 0.95);
}

.difficulty-hard {
  color: #f5eee4;
  background: rgba(183, 53, 45, 0.92);
}

.difficulty-expert {
  color: #f5eee4;
  background: #5c2f2a;
}

.card-body {
  padding: 16px 14px 18px;
  flex: 1;
}

.challenge-title {
  font-size: 18px;
  line-height: 1.25;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.challenge-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.category-tag {
  padding: 3px 8px;
  background: var(--bg-paper-2);
  color: var(--primary-color);
  border-radius: 2px;
  font-size: 12px;
  font-weight: 850;
}

.card-footer {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  padding: 0;
  background: transparent;
  border-top: 1px solid var(--border-color);
}

.meta-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 42px;
  padding: 8px 6px;
  border-right: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-secondary);
}

.meta-item:last-child {
  border-right: 0;
}

.meta-icon {
  color: var(--primary-color);
  font-size: 13px;
}

.meta-text {
  font-weight: 750;
}

.solved-indicator {
  color: var(--text-primary);
  font-weight: 850;
}
</style>
