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
            <AppIcon name="bi-pencil-square" />
            写文章
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
            <span class="category-icon"><AppIcon :name="['bi', getCategoryIcon(cat)]" /></span>
            {{ cat.name }}
          </div>
        </div>

        <!-- 文章列表 -->
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="articles.length === 0" class="empty-state">
          <div class="empty-icon"><AppIcon name="bi-journal-text" /></div>
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
            <h3><AppIcon name="bi-fire" /> 热门文章</h3>
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
                  <span><AppIcon name="bi-eye" /> {{ item.view_count }}</span>
                  <span><AppIcon name="bi-heart-fill" /> {{ item.like_count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 推荐文章 -->
        <div class="sidebar-card recommend">
          <div class="card-header">
            <h3><AppIcon name="bi-bookmark-star" /> 精选推荐</h3>
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
            <h3><AppIcon name="bi-folder2-open" /> 分类导航</h3>
          </div>
          <div class="category-nav-list">
            <div
              v-for="cat in categories"
              :key="cat.id"
              class="nav-item"
              @click="handleCategoryChange(cat.id)"
            >
              <span class="nav-icon"><AppIcon :name="['bi', getCategoryIcon(cat)]" /></span>
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

const categoryIconMap = [
  { keywords: ['web'], icon: 'bi-globe2' },
  { keywords: ['网络'], icon: 'bi-lock' },
  { keywords: ['系统'], icon: 'bi-pc-display' },
  { keywords: ['devsecops'], icon: 'bi-shield-check' },
  { keywords: ['移动'], icon: 'bi-phone' },
  { keywords: ['二进制'], icon: 'bi-diagram-3' },
  { keywords: ['扫描'], icon: 'bi-search' },
]

const getCategoryIcon = (category) => {
  const name = String(category?.name || '').toLowerCase()
  const match = categoryIconMap.find(item =>
    item.keywords.some(keyword => name.includes(keyword))
  )
  return match?.icon || 'bi-folder2'
}

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
  max-width:var(--page-width);
  margin:var(--space-10) auto var(--space-4);
  padding:0 var(--space-3);
}

.community-container {
  display:grid;
  grid-template-columns:1fr var(--panel-width);
  gap:var(--space-3);
}

.main-content {
  min-height:calc(100vh - var(--content-short-height));
}

.content-tabs {
  display:flex;
  align-items:center;
  background:transparent;
  border-bottom:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-md);
  padding:0 var(--space-2);
  margin-bottom:var(--space-2);
  box-shadow: none;
}

.tab-item {
  padding:var(--space-2) var(--space-2);
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
  color:var(--text-secondary);
  cursor:pointer;
  border-bottom:var(--focus-width) solid transparent;
  transition:all var(--motion-normal);
}

.tab-item:hover {
  color:var(--primary-color);
}

.tab-item.active {
  color:var(--primary-color);
  border-bottom-color:var(--primary-color);
  font-weight: var(--weight-strong);
}

.write-btn {
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  margin-left:auto;
  padding:var(--space-1) var(--space-2);
  background:var(--primary-color);
  color:var(--on-action);
  border:var(--stroke) solid var(--primary-color);
  border-radius:var(--radius-sm);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
}

.write-btn:hover {
  opacity:0.9;
  transform:translateY(calc(calc(var(--stroke) * 2) * -1));
}

.category-filter {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  background:transparent;
  padding:var(--space-2);
  border-bottom:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-md);
  margin-bottom:var(--space-2);
  box-shadow: none;
}

.category-item {
  padding:calc(var(--space-1) / 2) var(--space-2) calc(var(--space-1) / 2) var(--space-1);
  background:var(--bg-paper-2);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
  cursor:pointer;
  transition:all var(--motion-normal);
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.category-item:hover {
  background:var(--surface-muted);
  border-color:var(--line);
  color:var(--primary-color);
}

.category-item.active {
  background:var(--primary-color);
  border-color:var(--primary-color);
  color:var(--on-action);
}

.category-icon,
.nav-icon {
  width:var(--space-3);
  height:var(--space-3);
  display:inline-grid;
  place-items: center;
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface);
  color:var(--primary-color);
  font-size:var(--text-caption);
  flex-shrink:0;
}

.category-item.active .category-icon {
  color:var(--ink);
  background:var(--surface-muted);
  border-color:var(--line);
}

.loading-state,
.empty-state {
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:var(--space-10) var(--space-2);
  text-align:center;
  background:transparent;
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-md);
  box-shadow: none;
}

.loading-spinner {
  width:var(--space-6);
  height:var(--space-6);
  border:calc(var(--space-1) / 2) solid var(--line);
  border-top-color:var(--primary-color);
  border-radius:50%;
  animation:spin var(--motion-loop) linear infinite;
  margin-bottom:var(--space-2);
}

@keyframes spin {
  to { transform:rotate(360deg); }
}

.empty-icon {
  width:var(--space-8);
  height:var(--space-8);
  display:grid;
  place-items: center;
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface);
  color:var(--primary-color);
  font-size:var(--text-page);
  margin-bottom:var(--space-3);
}

.article-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.load-more {
  padding:var(--space-3) 0;
  text-align:center;
}

.load-more-btn {
  padding:var(--space-1) var(--space-6);
  background:transparent;
  border:var(--stroke) solid var(--text-primary);
  border-radius:var(--radius-sm);
  cursor:pointer;
  font-size:var(--text-caption);
  color:var(--text-primary);
  transition:all var(--motion-normal);
}

.load-more-btn:hover:not(:disabled) {
  background:var(--primary-color);
  color:var(--on-action);
  border-color:var(--primary-color);
}

.load-more-btn:disabled {
  opacity:0.6;
  cursor:not-allowed;
}

.sidebar {
  position:sticky;
  top:var(--space-10);
  height:fit-content;
}

.sidebar-card {
  background:transparent;
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-md);
  padding:var(--space-2);
  margin-bottom:var(--space-2);
  box-shadow: none;
}

.card-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:var(--space-2);
  padding-bottom:var(--space-1);
  border-bottom:var(--stroke) solid var(--border-color);
}

.card-header h3 {
  display:inline-flex;
  align-items:center;
  gap:var(--space-1);
  font-size:var(--text-body);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.card-header h3 .app-icon {
  color:var(--primary-color);
  font-size:var(--text-caption);
}

.more-link {
  font-size:var(--text-caption);
  color:var(--primary-color);
  cursor:pointer;
}

.more-link:hover {
  text-decoration:underline;
}

.hot-rank .rank-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.rank-item {
  display:flex;
  gap:var(--space-1);
  padding:var(--space-1);
  background:var(--bg-paper-2);
  border:var(--stroke) solid transparent;
  border-radius:var(--radius-control);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.rank-item:hover {
  background:var(--surface-muted);
  border-color:var(--line);
  transform:translateX(calc(var(--space-1) / 2));
}

.rank-number {
  width:var(--space-3);
  height:var(--space-3);
  display:flex;
  align-items:center;
  justify-content:center;
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight:bold;
  color:var(--ink);
  flex-shrink:0;
}

.rank-1 { background:var(--action); }
.rank-2 { background:var(--action); }
.rank-3 { background:var(--action); }

.rank-number:not(.rank-1):not(.rank-2):not(.rank-3) {
  background:var(--surface);
  color:var(--text-secondary);
}

.rank-info {
  flex:1;
  min-width:0;
}

.rank-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
  margin-bottom:calc(var(--space-1) / 2);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.rank-stats {
  display:flex;
  gap:var(--space-1);
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.rank-stats span {
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
}

.recommend-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.recommend-item {
  display:flex;
  gap:var(--space-1);
  padding:var(--space-1);
  border-radius:var(--radius-control);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.recommend-item:hover {
  background:var(--bg-paper-2);
}

.recommend-cover {
  width:var(--space-10);
  height:var(--space-7);
  border-radius:var(--radius-control);
  object-fit:cover;
  background:var(--bg-dark);
  flex-shrink:0;
}

.recommend-info {
  flex:1;
  min-width:0;
}

.recommend-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
  margin-bottom:calc(var(--space-1) / 2);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.recommend-summary {
  font-size:var(--text-caption);
  color:var(--text-secondary);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.category-nav-list {
  display:grid;
  grid-template-columns:repeat(2, 1fr);
  gap:var(--space-1);
}

.nav-item {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  padding:var(--space-1);
  background:var(--bg-paper-2);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  cursor:pointer;
  transition:all var(--motion-normal);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.nav-item:hover {
  background:var(--surface-muted);
  border-color:var(--line);
  color:var(--primary-color);
}

.nav-name {
  flex:1;
}

@media (max-width: 1120px) {
  .community-container {
    grid-template-columns:1fr;
  }

  .sidebar {
    display:none;
  }
}
</style>
