<template>
  <div class="article-detail-page">
    <div class="detail-container">
      <!-- 返回按钮 -->
      <div class="back-nav">
        <button class="back-btn" @click="goBack">
          <span>← 返回</span>
        </button>
      </div>

      <!-- 左侧文章内容区 -->
      <div class="article-main">
        <!-- 文章头部 -->
        <div class="article-header">
          <h1 class="article-title">{{ article?.title }}</h1>

          <div class="article-meta">
            <div class="author-section">
              <div class="author-avatar">
                {{ article?.author?.username?.charAt(0) || 'U' }}
              </div>
              <div class="author-info">
                <span class="author-name">{{ article?.author?.username }}</span>
                <span class="publish-time">{{ formatTime(article?.published_at || article?.created_at) }}</span>
              </div>
            </div>

            <div class="article-actions">
              <button
                class="action-btn"
                :class="{ active: article?.is_liked }"
                :aria-label="article?.is_liked ? '取消点赞' : '点赞'"
                :aria-pressed="Boolean(article?.is_liked)"
                @click="handleLike"
              >
                <span><AppIcon :name="article?.is_liked ? 'bi-heart-fill' : 'bi-heart'" /></span>
                {{ article?.like_count || 0 }}
              </button>
              <button
                class="action-btn"
                :class="{ active: article?.is_collected }"
                :aria-label="article?.is_collected ? '取消收藏' : '收藏'"
                :aria-pressed="Boolean(article?.is_collected)"
                @click="handleCollect"
              >
                <span><AppIcon :name="article?.is_collected ? 'bi-star-fill' : 'bi-star'" /></span>
                {{ article?.collect_count || 0 }}
              </button>
              <button class="action-btn" @click="handleShare">
                <span><AppIcon name="bi-link-45deg" /></span>
                分享
              </button>
            </div>
          </div>

          <div class="article-badges">
            <span v-if="article?.is_top" class="badge badge-top"><AppIcon name="bi-pin-angle" /> 置顶</span>
            <span v-if="article?.is_recommend" class="badge badge-recommend"><AppIcon name="bi-star-fill" /> 推荐</span>
            <span v-if="article?.category_name" class="badge badge-category">
              {{ article?.category_name }}
            </span>
            <span class="badge badge-views"><AppIcon name="bi-eye" /> {{ article?.view_count }} 阅读</span>
          </div>
        </div>

        <!-- 文章内容 -->
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else class="article-content markdown-body">
          <div v-html="renderedContent"></div>
        </div>

        <!-- 文章标签 -->
        <div v-if="article?.tags_list?.length" class="article-tags-section">
          <span
            v-for="tag in article.tags_list"
            :key="tag"
            class="tag"
          >
            #{{ tag }}
          </span>
        </div>

        <!-- 分隔线 -->
        <div class="divider"></div>

        <!-- 评论区 -->
        <div class="comments-section">
          <div class="comments-header">
            <h3>评论 ({{ article?.comment_count || 0 }})</h3>
          </div>

          <!-- 评论输入框 -->
          <div class="comment-input-box">
            <textarea
              v-model="newComment"
              class="comment-textarea"
              placeholder="写下你的评论..."
              rows="4"
            ></textarea>
            <div class="comment-actions">
              <button
                class="submit-btn"
                :disabled="!newComment.trim() || submitting"
                @click="handleSubmitComment"
              >
                {{ submitting ? '发布中...' : '发表评论' }}
              </button>
            </div>
          </div>

          <!-- 评论列表 -->
          <div v-if="loadingComments" class="loading-state">
            <div class="loading-spinner small"></div>
            <p>加载评论中...</p>
          </div>

          <div v-else-if="comments.length === 0" class="empty-comments">
            <div class="empty-icon"><AppIcon name="bi-chat-dots" /></div>
            <p>还没有评论，快来发表第一条吧</p>
          </div>

          <div v-else class="comments-list">
            <CommentItem
              v-for="comment in comments"
              :key="comment.id"
              :comment="comment"
              @reply="handleReply"
              @like="handleCommentLike"
              @delete="handleDeleteComment"
            />
          </div>
        </div>
      </div>

      <!-- 右侧侧边栏 -->
      <div class="sidebar">
        <!-- 作者信息 -->
        <div class="sidebar-card author-card">
          <div class="card-header">
            <h3>作者信息</h3>
          </div>
          <div class="author-card-content">
            <div class="author-large-avatar">
              {{ article?.author?.username?.charAt(0) || 'U' }}
            </div>
            <h4 class="author-name">{{ article?.author?.username }}</h4>
            <p class="author-nickname">{{ article?.author?.nickname || '暂无昵称' }}</p>
            <div class="author-stats">
              <span>文章 {{ articleCount }}</span>
              <span>粉丝 0</span>
            </div>
            <button class="follow-btn" disabled title="作者关注功能尚未开放">关注暂未开放</button>
          </div>
        </div>

        <!-- 相关推荐 -->
        <div class="sidebar-card">
          <div class="card-header">
            <h3>相关推荐</h3>
          </div>
          <div v-if="relatedArticles.length > 0" class="related-articles">
            <div
              v-for="item in relatedArticles"
              :key="item.id"
              class="related-item"
              @click="goToArticle(item.id)"
            >
              <img v-if="item.cover" :src="item.cover" class="related-cover" />
              <div v-else class="related-cover related-cover-placeholder">
                {{ item.title.charAt(0) }}
              </div>
              <div class="related-info">
                <h5 class="related-title">{{ item.title }}</h5>
                <div class="related-meta">
                  <span class="related-tag">{{ item.category_name || '未分类' }}</span>
                  <span class="related-stats"><AppIcon name="bi-eye" /> {{ item.view_count }}</span>
                </div>
                <span class="related-time">{{ formatTime(item.published_at || item.created_at) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-related">
            <div class="empty-icon"><AppIcon name="bi-book" /></div>
            <p>暂无相关推荐</p>
          </div>
        </div>

        <!-- 文章统计 -->
        <div class="sidebar-card">
          <div class="card-header">
            <h3>文章统计</h3>
          </div>
          <div class="stats-list">
            <div class="stat-row">
              <span>阅读量</span>
              <strong>{{ article?.view_count || 0 }}</strong>
            </div>
            <div class="stat-row">
              <span>点赞数</span>
              <strong>{{ article?.like_count || 0 }}</strong>
            </div>
            <div class="stat-row">
              <span>评论数</span>
              <strong>{{ article?.comment_count || 0 }}</strong>
            </div>
            <div class="stat-row">
              <span>收藏数</span>
              <strong>{{ article?.collect_count || 0 }}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import api from '@/api'
import CommentItem from '@/components/CommentItem.vue'
import { sanitizeHtml } from '@/utils/sanitize'

const route = useRoute()
const router = useRouter()

const article = ref(null)
const comments = ref([])
const relatedArticles = ref([])
const loading = ref(false)
const loadingComments = ref(false)
const submitting = ref(false)
const newComment = ref('')
const articleCount = ref(0)

// 配置 marked
marked.setOptions({
  highlight: function(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    return hljs.highlight(code, { language }).value
  },
  langPrefix: 'hljs language-'
})

const renderedContent = computed(() => {
  if (!article.value?.content) return ''
  try {
    return sanitizeHtml(marked.parse(article.value.content))
  } catch (error) {
    console.error('Markdown 解析失败:', error)
    return article.value.content
  }
})

const fetchArticle = async () => {
  loading.value = true
  try {
    article.value = await api.article.detail(route.params.id)
    document.title = `${article.value.title} - 社区`
  } catch (error) {
    console.error('获取文章详情失败:', error)
    alert('文章不存在或已被删除')
    router.push('/community')
  } finally {
    loading.value = false
  }
}

const fetchComments = async () => {
  loadingComments.value = true
  try {
    const data = await api.comment.list({ article: route.params.id })
    comments.value = data.results || []
  } catch (error) {
    console.error('获取评论失败:', error)
  } finally {
    loadingComments.value = false
  }
}

const fetchRelatedArticles = async () => {
  try {
    // 先获取推荐文章（基于标记为推荐的文章）
    const recommendData = await api.article.recommend({ limit: 6 })
    
    // 再获取同分类的文章
    const categoryId = article.value?.category
    const categoryData = await api.article.list({
      category: categoryId,
      status: 'approved',
      page: 1,
      page_size: 6
    })

    // 合并推荐文章和同分类文章，去重
    const allArticles = [
      ...(recommendData.results || []),
      ...(categoryData.results || [])
    ]

    // 去重并排除当前文章
    const uniqueArticles = []
    const seenIds = new Set()
    for (const item of allArticles) {
      if (item.id !== article.value.id && !seenIds.has(item.id)) {
        seenIds.add(item.id)
        uniqueArticles.push(item)
      }
    }

    // 取前5篇
    relatedArticles.value = uniqueArticles.slice(0, 5)
    
    // 更新作者文章数
    articleCount.value = categoryData.count || 0
  } catch (error) {
    console.error('获取相关文章失败:', error)
    relatedArticles.value = []
  }
}

const handleLike = async () => {
  if (!article.value) return
  try {
    const result = await api.article.like(article.value.id)
    article.value.is_liked = result.liked
    article.value.like_count = result.like_count
  } catch (error) {
    console.error('点赞失败:', error)
  }
}

const handleCollect = async () => {
  if (!article.value) return
  try {
    const result = await api.article.collect(article.value.id)
    article.value.is_collected = result.collected
    article.value.collect_count = result.collect_count
  } catch (error) {
    console.error('收藏失败:', error)
  }
}

const handleShare = () => {
  const url = window.location.href
  navigator.clipboard.writeText(url).then(() => {
    alert('链接已复制到剪贴板')
  })
}

const handleSubmitComment = async () => {
  if (!newComment.value.trim()) return

  submitting.value = true
  try {
    await api.comment.create({
      article: route.params.id,
      content: newComment.value
    })
    newComment.value = ''
    article.value.comment_count++
    fetchComments()
  } catch (error) {
    console.error('发表评论失败:', error)
    alert('发表评论失败')
  } finally {
    submitting.value = false
  }
}

const handleReply = (parentId) => {
  // 回复已成功提交，刷新评论列表
  article.value.comment_count++
  fetchComments()
}

const handleCommentLike = async (commentId) => {
  try {
    await api.comment.like(commentId)
    fetchComments()
  } catch (error) {
    console.error('点赞评论失败:', error)
  }
}

const handleDeleteComment = async (commentId) => {
  if (!confirm('确定要删除这条评论吗？')) return

  try {
    await api.comment.delete(commentId)
    article.value.comment_count--
    fetchComments()
  } catch (error) {
    console.error('删除评论失败:', error)
    alert('删除失败')
  }
}

const handleFollow = () => {
  alert('作者关注功能尚未开放。')
}

const goBack = () => {
  router.back()
}

const goToArticle = (id) => {
  router.push(`/community/article/${id}`)
}

const formatTime = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

watch(() => route.params.id, (newId) => {
  if (newId) {
    fetchArticle()
    fetchComments()
    fetchRelatedArticles()
  }
}, { immediate: true })

onMounted(() => {
  fetchArticle()
  fetchComments()
  fetchRelatedArticles()
})
</script>

<style scoped>
.article-detail-page {
  max-width:var(--page-width);
  margin:var(--space-3) auto var(--space-4);
  padding:0 var(--space-3);
}

.detail-container {
  display:grid;
  grid-template-columns:1fr var(--panel-width);
  gap:var(--space-3);
}

.article-main {
  background:var(--surface);
  border-radius:var(--radius-md);
  padding:var(--space-3);
  box-shadow: var(--shadow-raised);
}

.article-header {
  margin-bottom:var(--space-4);
  padding-bottom:var(--space-3);
  border-bottom:calc(var(--stroke) * 2) solid var(--line);
}

.article-title {
  font-size:var(--text-page);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
  line-height:1.4;
  margin-bottom:var(--space-2);
}

.article-meta {
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:var(--space-2);
  flex-wrap:wrap;
  gap:var(--space-2);
}

.author-section {
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.author-avatar {
  width:var(--space-5);
  height:var(--space-5);
  border-radius:50%;
  background: var(--surface-muted);
  color:var(--ink);
  font-size:var(--text-body);
  font-weight:bold;
  display:flex;
  align-items:center;
  justify-content:center;
}

.author-info {
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
}

.author-name {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.publish-time {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.article-actions {
  display:flex;
  gap:var(--space-1);
}

.action-btn {
  padding:var(--space-1) var(--space-2);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-sm);
  background:var(--surface);
  cursor:pointer;
  font-size:var(--text-caption);
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  transition:all var(--motion-normal);
}

.action-btn:hover {
  background:var(--surface);
  border-color:var(--line);
}

.action-btn.active {
  background:var(--surface);
  border-color:var(--line);
}

.article-badges {
  display:flex;
  gap:var(--space-1);
  flex-wrap:wrap;
}

.badge {
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-panel);
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
}

.badge-top {
  background:var(--surface);
  color:var(--ink-secondary);
}

.badge-recommend {
  background:var(--surface);
  color:var(--ink-secondary);
}

.badge-category {
  background:var(--surface);
  color:var(--primary-color);
}

.badge-views {
  background:var(--surface);
  color:var(--text-secondary);
}

.loading-state {
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:var(--space-10) var(--space-2);
  gap:var(--space-2);
  color:var(--text-secondary);
}

.loading-spinner {
  width:var(--space-6);
  height:var(--space-6);
  border:calc(var(--space-1) / 2) solid var(--line);
  border-top-color:var(--primary-color);
  border-radius:50%;
  animation:spin var(--motion-loop) linear infinite;
}

.loading-spinner.small {
  width:var(--space-4);
  height:var(--space-4);
  border-width:var(--focus-width);
}

@keyframes spin {
  to { transform:rotate(360deg); }
}

.article-content {
  font-size:var(--text-body);
  line-height:1.8;
  color:var(--text-primary);
  margin-bottom:var(--space-4);
}

.markdown-body :deep(img) {
  max-width:100%;
  border-radius:var(--radius-sm);
}

.markdown-body :deep(pre) {
  background:var(--surface);
  border-radius:var(--radius-control);
  padding:var(--space-2);
  overflow-x:auto;
}

.markdown-body :deep(code) {
  font-family:'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size:var(--text-caption);
}

.markdown-body :deep(p) {
  margin-bottom:var(--space-2);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top:var(--space-3);
  margin-bottom:var(--space-2);
  font-weight: var(--weight-strong);
}

.markdown-body :deep(h1) {
  font-size:var(--text-section);
}

.markdown-body :deep(h2) {
  font-size:var(--text-section);
}

.markdown-body :deep(h3) {
  font-size:var(--text-card);
}

.markdown-body :deep(blockquote) {
  border-left:calc(var(--space-1) / 2) solid var(--primary-color);
  padding-left:var(--space-2);
  margin:var(--space-2) 0;
  color:var(--text-secondary);
}

.article-tags-section {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  margin-bottom:var(--space-4);
}

.tag {
  padding:calc(var(--space-1) / 2) var(--space-2);
  background:var(--surface);
  color:var(--primary-color);
  border-radius:var(--radius-panel);
  font-size:var(--text-caption);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.tag:hover {
  background:var(--surface);
}

.divider {
  height:calc(var(--stroke) * 2);
  background:var(--surface);
  margin:var(--space-4) 0;
}

.comments-section {
  margin-top:var(--space-4);
}

.comments-header {
  margin-bottom:var(--space-2);
}

.comments-header h3 {
  font-size:var(--text-card);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.comment-input-box {
  margin-bottom:var(--space-4);
  padding:var(--space-2);
  background:var(--surface);
  border-radius:var(--radius-sm);
}

.comment-textarea {
  width:100%;
  padding:var(--space-1);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-sm);
  font-size:var(--text-caption);
  resize:vertical;
  min-height:var(--tile-short-height);
  margin-bottom:var(--space-1);
}

.comment-textarea:focus {
  outline-offset:var(--focus-offset);
  border-color:var(--primary-color);
}

.comment-actions {
  display:flex;
  justify-content:flex-end;
}

.submit-btn {
  padding:var(--space-1) var(--space-3);
  background:var(--primary-color);
  color:var(--on-action);
  border:none;
  border-radius:var(--radius-sm);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
}

.submit-btn:hover:not(:disabled) {
  opacity:0.9;
}

.submit-btn:disabled {
  opacity:0.6;
  cursor:not-allowed;
}

.empty-comments {
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:var(--space-7) var(--space-2);
  color:var(--text-secondary);
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-2);
}

.sidebar {
  position:sticky;
  top:var(--space-10);
  height:fit-content;
}

.sidebar-card {
  background:var(--surface);
  border-radius:var(--radius-md);
  padding:var(--space-2);
  margin-bottom:var(--space-2);
  box-shadow: var(--shadow-raised);
}

.card-header {
  margin-bottom:var(--space-2);
  padding-bottom:var(--space-1);
  border-bottom:var(--stroke) solid var(--line);
}

.card-header h3 {
  font-size:var(--text-body);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.author-card-content {
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:var(--space-1);
}

.author-large-avatar {
  width:var(--space-8);
  height:var(--space-8);
  border-radius:50%;
  background: var(--surface-muted);
  color:var(--ink);
  font-size:var(--text-section);
  font-weight:bold;
  display:flex;
  align-items:center;
  justify-content:center;
}

.author-name {
  font-size:var(--text-body);
  font-weight: var(--weight-strong);
}

.author-nickname {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.author-stats {
  display:flex;
  gap:var(--space-3);
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.follow-btn {
  padding:var(--space-1) var(--space-3);
  background:var(--primary-color);
  color:var(--on-action);
  border:none;
  border-radius:var(--radius-sm);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
}

.follow-btn:hover {
  opacity:0.9;
}

.related-articles {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.related-item {
  display:flex;
  gap:var(--space-1);
  padding:var(--space-1);
  border-radius:var(--radius-control);
  cursor:pointer;
  transition:all var(--motion-normal);
  border:var(--stroke) solid transparent;
}

.related-item:hover {
  background:var(--surface);
  border-color:var(--line);
  transform:translateX(calc(var(--stroke) * 2));
}

.related-cover {
  width:var(--space-10);
  height:var(--space-7);
  border-radius:var(--radius-control);
  object-fit:cover;
  flex-shrink:0;
}

.related-cover-placeholder {
  background: var(--surface-muted);
  color:var(--ink);
  font-size:var(--text-section);
  font-weight:bold;
  display:flex;
  align-items:center;
  justify-content:center;
}

.related-info {
  flex:1;
  min-width:0;
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
}

.related-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
  margin:0;
  line-height:1.4;
  overflow:hidden;
  text-overflow:ellipsis;
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.related-meta {
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.related-tag {
  padding:calc(var(--stroke) * 2) var(--space-1);
  background:var(--surface);
  color:var(--ink-secondary);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
}

.related-stats {
  font-size:var(--text-caption);
  color:var(--ink-muted);
}

.related-time {
  font-size:var(--text-caption);
  color:var(--ink-muted);
}

.empty-related {
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:var(--space-5) var(--space-2);
  color:var(--ink-muted);
}

.empty-related .empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-1);
}

.stats-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.stat-row {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:var(--space-1) 0;
  border-bottom:var(--stroke) solid var(--line);
}

.stat-row:last-child {
  border-bottom:none;
}

.stat-row span {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.stat-row strong {
  font-size:var(--text-body);
  color:var(--text-primary);
}

.back-nav {
  margin-bottom:var(--space-1);
  grid-column:1 / -1;
}

.back-btn {
  padding:calc(var(--space-1) / 2) var(--space-1);
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  cursor:pointer;
  font-size:var(--text-caption);
  color:var(--text-secondary);
  transition:all var(--motion-normal);
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  width:fit-content;
}

.back-btn:hover {
  background:var(--surface);
  color:var(--primary-color);
  border-color:var(--primary-color);
}

@media (max-width: 1120px) {
  .detail-container {
    grid-template-columns:1fr;
  }

  .sidebar {
    display:none;
  }

  .article-title {
    font-size:var(--text-section);
  }
}
</style>
