<template>
  <div class="community-page">
    <div class="community-container">
      <!-- 左侧主内容区 -->
      <div class="main-content">
        <!-- 顶部Tab切换 -->
        <div class="content-tabs">
          <div
            v-for="tab in tabs"
            :key="tab.value"
            class="tab-item"
            :class="{ active: activeTab === tab.value }"
            @click="handleTabChange(tab.value)"
          >
            {{ tab.label }}
          </div>
          <button class="write-btn" @click="handleWrite">
            ✍️ 写文章
          </button>
        </div>

        <!-- 分类筛选 -->
        <div class="category-filter">
          <div
            v-for="cat in categories"
            :key="cat.id"
            class="category-item"
            :class="{ active: selectedCategory === cat.id }"
            @click="handleCategoryChange(cat.id)"
          >
            <span v-if="cat.icon">{{ cat.icon }}</span>
            {{ cat.name }}
          </div>
        </div>

        <!-- 文章列表 -->
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="articles.length === 0" class="empty-state">
          <div class="empty-icon">📝</div>
          <h3>暂无文章</h3>
          <p>快来发布第一篇文章吧</p>
        </div>

        <div v-else class="article-list">
          <ArticleCard
            v-for="article in articles"
            :key="article.id"
            :article="article"
            @click="handleArticleClick"
          />
        </div>

        <!-- 加载更多 -->
        <div v-if="hasMore" class="load-more">
          <button class="load-more-btn" @click="loadMore" :disabled="loadingMore">
            {{ loadingMore ? '加载中...' : '加载更多' }}
          </button>
        </div>
      </div>

      <!-- 右侧侧边栏 -->
      <div class="sidebar">
        <!-- 热门文章排行 -->
        <div class="sidebar-card hot-rank">
          <div class="card-header">
            <h3>🔥 热门文章</h3>
            <span class="more-link" @click="handleViewMore('hot')">更多</span>
          </div>
          <div class="rank-list">
            <div
              v-for="(item, index) in hotArticles"
              :key="item.id"
              class="rank-item"
              @click="handleArticleClick(item)"
            >
              <div class="rank-number" :class="`rank-${index + 1}`">{{ index + 1 }}</div>
              <div class="rank-info">
                <h4 class="rank-title">{{ item.title }}</h4>
                <div class="rank-stats">
                  <span>👁️ {{ item.view_count }}</span>
                  <span>❤️ {{ item.like_count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 推荐文章 -->
        <div class="sidebar-card recommend">
          <div class="card-header">
            <h3>⭐ 精选推荐</h3>
            <span class="more-link" @click="handleViewMore('recommend')">更多</span>
          </div>
          <div class="recommend-list">
            <div
              v-for="item in recommendArticles"
              :key="item.id"
              class="recommend-item"
              @click="handleArticleClick(item)"
            >
              <img v-if="item.cover" :src="item.cover" class="recommend-cover" />
              <div class="recommend-info">
                <h4 class="recommend-title">{{ item.title }}</h4>
                <p class="recommend-summary">{{ item.summary || item.title }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- 分类导航 -->
        <div class="sidebar-card category-nav">
          <div class="card-header">
            <h3>📂 分类导航</h3>
          </div>
          <div class="category-nav-list">
            <div
              v-for="cat in categories"
              :key="cat.id"
              class="nav-item"
              @click="handleCategoryChange(cat.id)"
            >
              <span v-if="cat.icon" class="nav-icon">{{ cat.icon }}</span>
              <span class="nav-name">{{ cat.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import api from '@/api'
import ArticleCard from '@/components/ArticleCard.vue'

const router = useRouter()
const userStore = useUserStore()

const tabs = [
  { label: '最新', value: 'latest' },
  { label: '热门', value: 'hot' },
  { label: '推荐', value: 'recommend' },
  { label: '我的', value: 'my' },
]

const activeTab = ref('latest')
const selectedCategory = ref('')
const articles = ref([])
const categories = ref([])
const hotArticles = ref([])
const recommendArticles = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const currentPage = ref(1)
const hasMore = ref(true)

const fetchCategories = async () => {
  try {
    const data = await api.category.list()
    // 处理分页格式的响应
    categories.value = Array.isArray(data) ? data : (data.results || [])
  } catch (error) {
    console.error('获取分类失败:', error)
  }
}

const fetchArticles = async (append = false) => {
  if (append && loadingMore.value) return

  if (!append) {
    loading.value = true
    currentPage.value = 1
  } else {
    loadingMore.value = true
  }

  try {
    const params = {
      page: currentPage.value,
      page_size: 10,
    }

    if (activeTab.value === 'my') {
      const data = await api.article.my()
      articles.value = Array.isArray(data) ? data : (data.results || [])
      hasMore.value = false
    } else {
      if (activeTab.value === 'hot') {
        params.ordering = 'hot'
      } else if (activeTab.value === 'recommend') {
        params.ordering = 'recommend'
      }

      if (selectedCategory.value) {
        params.category = selectedCategory.value
      }

      const response = await api.article.list(params)
      const results = response.results || []
      if (append) {
        articles.value = [...articles.value, ...results]
      } else {
        articles.value = results
      }

      // 根据总条数判断是否还有更多数据
      const totalCount = response.count || 0
      hasMore.value = (currentPage.value * params.page_size) < totalCount
    }
  } catch (error) {
    console.error('获取文章列表失败:', error)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const fetchHotArticles = async () => {
  try {
    const data = await api.article.hot({ limit: 10 })
    hotArticles.value = data.results || []
  } catch (error) {
    console.error('获取热门文章失败:', error)
  }
}

const fetchRecommendArticles = async () => {
  try {
    const data = await api.article.recommend({ limit: 6 })
    recommendArticles.value = data.results || []
  } catch (error) {
    console.error('获取推荐文章失败:', error)
  }
}

const handleTabChange = (tab) => {
  if (tab === 'my' && !userStore.isAuthenticated) {
    router.push('/login')
    return
  }
  activeTab.value = tab
  selectedCategory.value = ''
  fetchArticles()
}

const handleCategoryChange = (categoryId) => {
  selectedCategory.value = categoryId
  if (activeTab.value === 'my') {
    activeTab.value = 'latest'
  }
  fetchArticles()
}

const handleArticleClick = (article) => {
  router.push(`/community/article/${article.id}`)
}

const handleWrite = () => {
  if (!userStore.isAuthenticated) {
    router.push('/login')
    return
  }
  router.push('/community/write')
}

const handleViewMore = (type) => {
  activeTab.value = type
  selectedCategory.value = ''
  fetchArticles()
}

const loadMore = () => {
  currentPage.value++
  fetchArticles(true)
}

onMounted(() => {
  fetchCategories()
  fetchArticles()
  fetchHotArticles()
  fetchRecommendArticles()
})
</script>

<style scoped>
.community-page {
  max-width: 1400px;
  margin: 80px auto 32px;
  padding: 0 24px;
}

.community-container {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 24px;
}

.main-content {
  min-height: calc(100vh - 150px);
}

.content-tabs {
  display: flex;
  align-items: center;
  background: white;
  border-radius: var(--radius-md);
  padding: 0 16px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-sm);
}

.tab-item {
  padding: 16px 20px;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.3s;
}

.tab-item:hover {
  color: var(--primary-color);
}

.tab-item.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
  font-weight: 600;
}

.write-btn {
  margin-left: auto;
  padding: 8px 20px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.write-btn:hover {
  opacity: 0.9;
  transform: translateY(-2px);
}

.category-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  background: white;
  padding: 16px;
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  box-shadow: var(--shadow-sm);
}

.category-item {
  padding: 6px 16px;
  background: #f5f5f5;
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 4px;
}

.category-item:hover {
  background: #e6f7ff;
  color: var(--primary-color);
}

.category-item.active {
  background: var(--primary-color);
  color: white;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
  background: white;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #f0f0f0;
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 24px;
}

.article-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.load-more {
  padding: 24px 0;
  text-align: center;
}

.load-more-btn {
  padding: 12px 48px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary);
  transition: all 0.3s;
}

.load-more-btn:hover:not(:disabled) {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sidebar {
  position: sticky;
  top: 80px;
  height: fit-content;
}

.sidebar-card {
  background: white;
  border-radius: var(--radius-md);
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #f0f0f0;
}

.card-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.more-link {
  font-size: 13px;
  color: var(--primary-color);
  cursor: pointer;
}

.more-link:hover {
  text-decoration: underline;
}

.hot-rank .rank-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rank-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.rank-item:hover {
  background: #f0f0f0;
  transform: translateX(4px);
}

.rank-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  font-size: 14px;
  font-weight: bold;
  color: white;
  flex-shrink: 0;
}

.rank-1 { background: #ff4d4f; }
.rank-2 { background: #ff7a45; }
.rank-3 { background: #ffc53d; }

.rank-number:not(.rank-1):not(.rank-2):not(.rank-3) {
  background: #d9d9d9;
  color: var(--text-secondary);
}

.rank-info {
  flex: 1;
  min-width: 0;
}

.rank-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.recommend-item {
  display: flex;
  gap: 12px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.recommend-item:hover {
  background: #f5f5f5;
}

.recommend-cover {
  width: 80px;
  height: 60px;
  border-radius: 6px;
  object-fit: cover;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  flex-shrink: 0;
}

.recommend-info {
  flex: 1;
  min-width: 0;
}

.recommend-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recommend-summary {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-nav-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s;
  font-size: 13px;
}

.nav-item:hover {
  background: #e6f7ff;
  color: var(--primary-color);
}

.nav-icon {
  font-size: 16px;
}

.nav-name {
  flex: 1;
}

@media (max-width: 1024px) {
  .community-container {
    grid-template-columns: 1fr;
  }

  .sidebar {
    display: none;
  }
}
</style>
