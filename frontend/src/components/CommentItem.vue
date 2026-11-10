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
            @click="handleLike"
          >
            <span>{{ comment.is_liked ? '❤️' : '🤍' }}</span>
            {{ comment.like_count }}
          </button>
          <button class="action-btn" @click="handleReply">
            💬 回复
          </button>
          <button
            v-if="canDelete"
            class="action-btn delete-btn"
            @click="handleDelete"
          >
            🗑️ 删除
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
  padding: 20px 0;
  border-bottom: 1px solid #f0f0f0;
}

.comment-item:last-child {
  border-bottom: none;
}

.comment-content {
  display: flex;
  gap: 12px;
}

.comment-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.comment-body {
  flex: 1;
  min-width: 0;
}

.comment-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.author-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.comment-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.reply-to {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.reply-label {
  color: var(--primary-color);
  font-weight: 500;
}

.reply-author {
  font-weight: 500;
}

.comment-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  margin-bottom: 12px;
  white-space: pre-wrap;
}

.comment-actions {
  display: flex;
  gap: 16px;
}

.action-btn {
  padding: 4px 12px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.3s;
}

.action-btn:hover {
  color: var(--primary-color);
}

.action-btn.active {
  color: #ff4d4f;
}

.action-btn.delete-btn:hover {
  color: #ff4d4f;
}

.replies-list {
  margin-top: 16px;
  padding-left: 48px;
  border-left: 2px solid #f0f0f0;
}

.reply-input-box {
  margin-top: 16px;
  padding: 16px;
  background: #f9f9f9;
  border-radius: 6px;
}

.reply-textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  font-size: 13px;
  resize: vertical;
  min-height: 80px;
  margin-bottom: 10px;
}

.reply-textarea:focus {
  outline: none;
  border-color: var(--primary-color);
}

.reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.cancel-btn,
.submit-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.cancel-btn {
  background: white;
  border: 1px solid #d9d9d9;
}

.cancel-btn:hover {
  background: #f5f5f5;
}

.submit-btn {
  background: var(--primary-color);
  color: white;
}

.submit-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
