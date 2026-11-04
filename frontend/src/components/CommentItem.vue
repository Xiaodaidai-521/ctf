<template>
  <div class="comment-item">
    <div class="comment-content">
      <div class="comment-avatar">
        {{ comment.author?.username?.charAt(0) || 'U' }}
      </div>
      <div class="comment-body">
        <div class="comment-header">
          <span class="author-name">{{ comment.author?.username }}</span>
          <span class="comment-time">{{ formatTime(comment.created_at) }}</span>
        </div>

        <div v-if="comment.parent" class="reply-to">
          <span class="reply-label">回复</span>
          <span class="reply-author">@{{ comment.parent.author?.username }}</span>
        </div>

        <div class="comment-text">{{ comment.content }}</div>

        <div class="comment-actions">
          <button
            class="action-btn"
            :class="{ active: comment.is_liked }"
            :aria-label="comment.is_liked ? '取消点赞' : '点赞'"
            :aria-pressed="Boolean(comment.is_liked)"
            @click="handleLike"
          >
            <span><AppIcon :name="comment.is_liked ? 'bi-heart-fill' : 'bi-heart'" /></span>
            {{ comment.like_count }}
          </button>
          <button class="action-btn" @click="handleReply">
            <AppIcon name="bi-chat-dots" /> 回复
          </button>
          <button
            v-if="canDelete"
            class="action-btn delete-btn"
            @click="handleDelete"
          >
            <AppIcon name="bi-trash" /> 删除
          </button>
        </div>
      </div>
    </div>

    <!-- 回复列表 -->
    <div v-if="comment.replies && comment.replies.length > 0" class="replies-list">
      <CommentItem
        v-for="reply in comment.replies"
        :key="reply.id"
        :comment="reply"
        :current-user="currentUser"
        @reply="$emit('reply', $event, comment.id)"
        @like="$emit('like', $event)"
        @delete="$emit('delete', $event)"
      />
    </div>

    <!-- 回复输入框（展开时显示） -->
    <div v-if="showReplyInput" class="reply-input-box">
      <textarea
        v-model="replyText"
        class="reply-textarea"
        :placeholder="`回复 @${comment.author?.username}...`"
        rows="3"
      ></textarea>
      <div class="reply-actions">
        <button class="cancel-btn" @click="showReplyInput = false">取消</button>
        <button
          class="submit-btn"
          :disabled="!replyText.trim() || submitting"
          @click="handleSubmitReply"
        >
          {{ submitting ? '发送中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useUserStore } from '@/store/user'
import api from '@/api'

const props = defineProps({
  comment: {
    type: Object,
    required: true
  },
  currentUser: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['reply', 'like', 'delete'])

const userStore = useUserStore()
const showReplyInput = ref(false)
const replyText = ref('')
const submitting = ref(false)

const canDelete = computed(() => {
  return props.comment.author?.id === userStore.userInfo?.id || userStore.userInfo?.role === 'admin'
})

const handleLike = () => {
  emit('like', props.comment.id)
}

const handleReply = () => {
  if (!userStore.isAuthenticated) {
    alert('请先登录')
    return
  }
  showReplyInput.value = true
}

const handleSubmitReply = async () => {
  if (!replyText.value.trim()) return

  submitting.value = true
  try {
    await api.comment.create({
      article: props.comment.article,
      parent: props.comment.id,
      content: replyText.value
    })
    showReplyInput.value = false
    replyText.value = ''
    emit('reply', props.comment.id)
  } catch (error) {
    console.error('回复失败:', error)
    alert('回复失败')
  } finally {
    submitting.value = false
  }
}

const handleDelete = () => {
  if (confirm('确定要删除这条评论吗？')) {
    emit('delete', props.comment.id)
  }
}

const formatTime = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date

  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour

  if (diff < minute) {
    return '刚刚'
  } else if (diff < hour) {
    return Math.floor(diff / minute) + '分钟前'
  } else if (diff < day) {
    return Math.floor(diff / hour) + '小时前'
  } else if (diff < 7 * day) {
    return Math.floor(diff / day) + '天前'
  } else {
    return date.toLocaleDateString('zh-CN')
  }
}
</script>

<style scoped>
.comment-item {
  padding:var(--space-2) 0;
  border-bottom:var(--stroke) solid var(--line);
}

.comment-item:last-child {
  border-bottom:none;
}

.comment-content {
  display:flex;
  gap:var(--space-1);
}

.comment-avatar {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:50%;
  background: var(--surface-muted);
  color:var(--ink);
  font-size:var(--text-caption);
  font-weight:bold;
  display:flex;
  align-items:center;
  justify-content:center;
  flex-shrink:0;
}

.comment-body {
  flex:1;
  min-width:0;
}

.comment-header {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  margin-bottom:var(--space-1);
}

.author-name {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.comment-time {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.reply-to {
  margin-bottom:var(--space-1);
  padding:var(--space-1) var(--space-1);
  background:var(--surface);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.reply-label {
  color:var(--primary-color);
  font-weight: var(--weight-medium);
}

.reply-author {
  font-weight: var(--weight-medium);
}

.comment-text {
  font-size:var(--text-caption);
  line-height:1.6;
  color:var(--text-primary);
  margin-bottom:var(--space-1);
  white-space:pre-wrap;
}

.comment-actions {
  display:flex;
  gap:var(--space-2);
}

.action-btn {
  padding:calc(var(--space-1) / 2) var(--space-1);
  border:none;
  background:none;
  cursor:pointer;
  font-size:var(--text-caption);
  color:var(--text-secondary);
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  transition:all var(--motion-normal);
}

.action-btn:hover {
  color:var(--primary-color);
}

.action-btn.active {
  color:var(--ink-muted);
}

.action-btn.delete-btn:hover {
  color:var(--ink-muted);
}

.replies-list {
  margin-top:var(--space-2);
  padding-left:var(--space-6);
  border-left:calc(var(--stroke) * 2) solid var(--line);
}

.reply-input-box {
  margin-top:var(--space-2);
  padding:var(--space-2);
  background:var(--surface);
  border-radius:var(--radius-control);
}

.reply-textarea {
  width:100%;
  padding:var(--space-1);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  resize:vertical;
  min-height:var(--space-10);
  margin-bottom:var(--space-1);
}

.reply-textarea:focus {
  outline-offset:var(--focus-offset);
  border-color:var(--primary-color);
}

.reply-actions {
  display:flex;
  justify-content:flex-end;
  gap:var(--space-1);
}

.cancel-btn,
.submit-btn {
  padding:calc(var(--space-1) / 2) var(--space-2);
  border:none;
  border-radius:var(--radius-control);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
}

.cancel-btn {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
}

.cancel-btn:hover {
  background:var(--surface);
}

.submit-btn {
  background:var(--primary-color);
  color:var(--on-action);
}

.submit-btn:hover:not(:disabled) {
  opacity:0.9;
}

.submit-btn:disabled {
  opacity:0.6;
  cursor:not-allowed;
}
</style>
