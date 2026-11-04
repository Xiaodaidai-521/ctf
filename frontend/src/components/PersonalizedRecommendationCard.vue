<template>
  <div class="recommendation-card" @click="handleAction">
    <div class="card-header">
      <a-tag :color="typeConfig.color">{{ typeConfig.label }}</a-tag>
    </div>

    <h4 class="card-title">{{ recommendation.title || '未命名推荐' }}</h4>

    <p class="card-reason">{{ recommendation.reason || '暂无说明' }}</p>

    <div class="card-footer">
      <div class="footer-info">
        <span v-if="recommendation.estimated_time" class="info-item">
          <icon-clock-circle />
          {{ recommendation.estimated_time }}
        </span>
        <span v-if="recommendation.expected_gain" class="info-item gain">
          <icon-arrow-up />
          {{ recommendation.expected_gain }}
        </span>
      </div>
      <a-button type="primary" size="small" @click.stop="handleAction">
        开始
      </a-button>
    </div>
  </div>
</template>

<script setup>
import { names } from '@/shared/navigation/names'

import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  recommendation: {
    type: Object,
    required: true,
    default: () => ({})
  }
})

const router = useRouter()

const TYPE_CONFIG = {
  challenge: { label: '题目', color: 'arcoblue' },
  article: { label: '文章', color: 'purple' },
  video: { label: '视频', color: 'red' },
  resource: { label: '资源', color: 'green' },
  path: { label: names.paths, color: 'orange' },
  exercise: { label: '练习', color: 'cyan' }
}

const typeConfig = computed(() => {
  return TYPE_CONFIG[props.recommendation.type] || { label: props.recommendation.type || '推荐', color: 'gray' }
})

const handleAction = () => {
  const link = props.recommendation.action_link
  if (!link) return
  if (/^https?:\/\//.test(link)) {
    window.open(link, '_blank')
  } else {
    router.push(link)
  }
}
</script>

<style scoped>
.recommendation-card {
  background:var(--color-bg-1);
  border:var(--stroke) solid var(--color-border);
  border-radius:var(--radius-control);
  padding:var(--space-2);
  cursor:pointer;
  transition:box-shadow var(--motion-normal), transform var(--motion-normal);
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.recommendation-card:hover {
  box-shadow: var(--shadow-raised);
  transform:translateY(calc(calc(var(--stroke) * 2) * -1));
}

.card-header {
  display:flex;
  align-items:center;
}

.card-title {
  margin:0;
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--color-text-1);
  line-height:1.4;
}

.card-reason {
  margin:0;
  font-size:var(--text-caption);
  color:var(--color-text-2);
  line-height:1.6;
  display:-webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow:hidden;
}

.card-footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin-top:auto;
}

.footer-info {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  font-size:var(--text-caption);
  color:var(--color-text-3);
}

.info-item {
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
}

.info-item.gain {
  color:var(--positive);
}
</style>
