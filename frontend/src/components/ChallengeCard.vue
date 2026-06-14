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
        <span class="meta-icon">📊</span>
        <span class="meta-text">积分: {{ challenge.score }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-icon">👥</span>
        <span class="meta-text">解出: {{ challenge.solve_count }}</span>
      </div>
      <div class="meta-item solved-indicator" v-if="challenge.is_solved">
        <span class="meta-icon">✅</span>
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
  background: white;
  border-radius: var(--radius-sm);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
}

.challenge-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--primary-color);
}

.challenge-card.solved {
  border-color: var(--success-color);
  background: #f6ffed;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.challenge-card.solved .card-header {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
}

.challenge-id {
  font-size: 11px;
  font-weight: 500;
  opacity: 0.9;
}

.difficulty-badge {
  padding: 2px 6px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 500;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(4px);
}

.difficulty-easy {
  background: rgba(82, 196, 26, 0.8);
}

.difficulty-medium {
  background: rgba(250, 173, 20, 0.8);
}

.difficulty-hard {
  background: rgba(255, 77, 79, 0.8);
}

.difficulty-expert {
  background: rgba(114, 46, 209, 0.8);
}

.card-body {
  padding: 12px;
  flex: 1;
}

.challenge-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
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
  padding: 2px 6px;
  background: #e6f7ff;
  color: var(--primary-color);
  border-radius: 2px;
  font-size: 11px;
  font-weight: 500;
}

.card-footer {
  display: flex;
  justify-content: space-around;
  padding: 10px 12px;
  background: #fafafa;
  border-top: 1px solid #f0f0f0;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

.meta-icon {
  font-size: 12px;
}

.meta-text {
  font-weight: 500;
}

.solved-indicator {
  color: var(--success-color);
  font-weight: 600;
}
</style>
