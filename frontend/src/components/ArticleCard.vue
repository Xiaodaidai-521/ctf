<template>
  <div class="article-card" @click="handleClick">
    <div class="card-main">
      <div class="card-content">
        <h3 class="article-title">{{ article.title }}</h3>
        <p class="article-summary">{{ article.summary || article.title }}</p>

        <div class="article-tags" v-if="article.tags_list && article.tags_list.length">
          <span
            v-for="tag in article.tags_list.slice(0, 5)"
            :key="tag"
            class="tag"
          >
            #{{ tag }}
          </span>
        </div>
      </div>

      <div class="card-cover" v-if="article.cover">
        <img :src="article.cover" :alt="article.title" />
      </div>
    </div>

    <div class="card-footer">
      <div class="author-info">
        <span class="author-avatar">
          {{ article.author?.username?.charAt(0) || 'U' }}
        </span>
        <div class="author-details">
          <span class="author-name">{{ article.author?.username || '未知作者' }}</span>
          <span class="article-time">{{ formatTime(article.created_at) }}</span>
        </div>
      </div>

      <div class="article-stats">
        <span class="stat-item">
          <i class="bi bi-eye stat-icon"></i>
          {{ formatNumber(article.view_count) }}
        </span>
        <span class="stat-item">
          <i class="bi bi-heart-fill stat-icon"></i>
          {{ formatNumber(article.like_count) }}
        </span>
        <span class="stat-item">
          <i class="bi bi-chat-dots stat-icon"></i>
          {{ formatNumber(article.comment_count) }}
        </span>
      </div>

      <div class="article-badges">
        <span v-if="article.is_top" class="badge badge-top"><i class="bi bi-pin-angle"></i> 置顶</span>
        <span v-if="article.is_recommend" class="badge badge-recommend"><i class="bi bi-bookmark-star"></i> 推荐</span>
        <span v-if="article.category_name" class="badge badge-category">
          {{ article.category_name }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  article: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['click'])

const handleClick = () => {
  emit('click', props.article)
}

const formatNumber = (num) => {
  if (!num) return '0'
  if (num >= 10000) {
    return (num / 10000).toFixed(1) + 'w'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'k'
  }
  return num.toString()
}

const formatTime = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date

  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  const month = 30 * day

  if (diff < minute) {
    return '刚刚'
  } else if (diff < hour) {
    return Math.floor(diff / minute) + '分钟前'
  } else if (diff < day) {
    return Math.floor(diff / hour) + '小时前'
  } else if (diff < month) {
    return Math.floor(diff / day) + '天前'
  } else {
    return date.toLocaleDateString('zh-CN')
  }
}
</script>

<style scoped>
.article-card {
  background: transparent;
  border-radius: var(--radius-md);
  padding: 20px;
  box-shadow: none;
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid var(--border-color);
}

.article-card:hover {
  box-shadow: 8px 8px 0 rgba(24, 23, 19, 0.1);
  border-color: var(--primary-color);
  transform: translateY(-2px);
}

.card-main {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.card-content {
  flex: 1;
  min-width: 0;
}

.article-title {
  font-size: 18px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.article-summary {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.article-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  padding: 4px 10px;
  background: var(--bg-paper-2);
  color: var(--primary-color);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.3s;
}

.tag:hover {
  background: rgba(183, 53, 45, 0.08);
}

.card-cover {
  width: 160px;
  height: 100px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg-dark);
}

.card-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
  flex-wrap: wrap;
  gap: 12px;
}

.author-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.author-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--text-primary);
  color: #fbf7ef;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.author-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.author-name {
  font-size: 13px;
  font-weight: 850;
  color: var(--text-primary);
}

.article-time {
  font-size: 11px;
  color: var(--text-secondary);
}

.article-stats {
  display: flex;
  gap: 16px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-icon {
  font-size: 14px;
}

.article-badges {
  display: flex;
  gap: 8px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 850;
  white-space: nowrap;
  border: 1px solid var(--border-color);
}

.badge-top,
.badge-recommend {
  background: var(--bg-paper-2);
  color: var(--text-primary);
}

.badge-category {
  background: var(--bg-paper-2);
  color: var(--primary-color);
}

@media (max-width: 768px) {
  .card-main {
    flex-direction: column;
  }

  .card-cover {
    width: 100%;
    height: 150px;
  }

  .card-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .article-stats {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
