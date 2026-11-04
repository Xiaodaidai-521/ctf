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
          <AppIcon class="stat-icon" name="bi-eye" />
          {{ formatNumber(article.view_count) }}
        </span>
        <span class="stat-item">
          <AppIcon class="stat-icon" name="bi-heart-fill" />
          {{ formatNumber(article.like_count) }}
        </span>
        <span class="stat-item">
          <AppIcon class="stat-icon" name="bi-chat-dots" />
          {{ formatNumber(article.comment_count) }}
        </span>
      </div>

      <div class="article-badges">
        <span v-if="article.is_top" class="badge badge-top"><AppIcon name="bi-pin-angle" /> 置顶</span>
        <span v-if="article.is_recommend" class="badge badge-recommend"><AppIcon name="bi-bookmark-star" /> 推荐</span>
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
  background:transparent;
  border-radius:var(--radius-md);
  padding:var(--space-2);
  box-shadow: none;
  cursor:pointer;
  transition:all var(--motion-normal);
  border:var(--stroke) solid var(--border-color);
}

.article-card:hover {
  box-shadow: var(--shadow-raised);
  border-color:var(--primary-color);
  transform:translateY(calc(calc(var(--stroke) * 2) * -1));
}

.card-main {
  display:flex;
  gap:var(--space-2);
  margin-bottom:var(--space-2);
}

.card-content {
  flex:1;
  min-width:0;
}

.article-title {
  font-size:var(--text-card);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
  margin-bottom:var(--space-1);
  line-height:1.4;
  overflow:hidden;
  text-overflow:ellipsis;
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.article-summary {
  font-size:var(--text-caption);
  color:var(--text-secondary);
  line-height:1.6;
  margin-bottom:var(--space-1);
  overflow:hidden;
  text-overflow:ellipsis;
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.article-tags {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
}

.tag {
  padding:calc(var(--space-1) / 2) var(--space-1);
  background:var(--bg-paper-2);
  color:var(--primary-color);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.tag:hover {
  background:var(--surface-muted);
}

.card-cover {
  width:var(--row-label-width);
  height:var(--thumbnail-height);
  border-radius:var(--radius-sm);
  overflow:hidden;
  flex-shrink:0;
  background:var(--bg-dark);
}

.card-cover img {
  width:100%;
  height:100%;
  object-fit:cover;
}

.card-footer {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding-top:var(--space-2);
  border-top:var(--stroke) solid var(--border-color);
  flex-wrap:wrap;
  gap:var(--space-1);
}

.author-info {
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.author-avatar {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:50%;
  background:var(--surface-muted);
  color:var(--ink);
  font-size:var(--text-caption);
  font-weight:bold;
  display:flex;
  align-items:center;
  justify-content:center;
  flex-shrink:0;
}

.author-details {
  display:flex;
  flex-direction:column;
  gap:calc(var(--stroke) * 2);
}

.author-name {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.article-time {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.article-stats {
  display:flex;
  gap:var(--space-2);
}

.stat-item {
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.stat-icon {
  font-size:var(--text-caption);
}

.article-badges {
  display:flex;
  gap:var(--space-1);
}

.badge {
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  white-space:nowrap;
  border:var(--stroke) solid var(--border-color);
}

.badge-top,
.badge-recommend {
  background:var(--bg-paper-2);
  color:var(--text-primary);
}

.badge-category {
  background:var(--bg-paper-2);
  color:var(--primary-color);
}

@media (max-width: 768px) {
  .card-main {
    flex-direction:column;
  }

  .card-cover {
    width:100%;
    height:var(--thumbnail-height);
  }

  .card-footer {
    flex-direction:column;
    align-items:flex-start;
  }

  .article-stats {
    width:100%;
    justify-content:space-between;
  }
}
</style>
