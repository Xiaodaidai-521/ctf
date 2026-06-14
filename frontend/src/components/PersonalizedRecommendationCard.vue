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
  path: { label: '学习路径', color: 'orange' },
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
  background: var(--color-bg-1);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.recommendation-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  align-items: center;
}

.card-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-1);
  line-height: 1.4;
}

.card-reason {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-2);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
}

.footer-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-3);
}

.info-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.info-item.gain {
  color: rgb(var(--green-6));
}
</style>
