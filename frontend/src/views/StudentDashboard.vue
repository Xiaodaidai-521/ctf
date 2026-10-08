<template>
  <div class="dashboard-page">
    <!-- ===== 管理员视图：用户学习报表 ===== -->
    <div v-if="userStore.userInfo?.role === 'admin'" class="container">
      <div class="report-heading">
        <p class="section-kicker">VIEW 03 / Capability Profile</p>
        <h1 class="page-title">用户学习进度与掌握报表</h1>
      </div>
      <div class="summary-row">
        <div class="summary-card"><span class="s-num">{{ adminStudents.length }}</span><span class="s-label">用户总数</span></div>
        <div class="summary-card"><span class="s-num">{{ adminOnboarded }}</span><span class="s-label">已完成引导</span></div>
        <div class="summary-card"><span class="s-num">{{ adminAvgMastery }}%</span><span class="s-label">平均掌握度</span></div>
        <div class="summary-card"><span class="s-num">{{ adminTotalSolved }}</span><span class="s-label">总解题数</span></div>
      </div>

      <div class="admin-toolbar">
        <a-input-search v-model="adminSearch" placeholder="搜索用户..." allow-clear />
      </div>

      <a-table :data="adminFiltered" :columns="adminColumns" :loading="adminLoading" row-key="id"
        :pagination="{ pageSize: 10 }" @row-click="showStudentDetail" style="cursor:pointer">
        <template #onboarded="{ record }">
          <span class="status-pill" :class="record.onboarded ? 'is-guided' : 'is-pending'">{{ record.onboarded ? '已引导' : '未引导' }}</span>
        </template>
        <template #skills="{ record }">
          <span v-for="(v,k) in record.skills" :key="k" class="admin-skill-dot" :class="'level-' + skillLevel(v)" :title="dirLabel(k)+':'+v"></span>
        </template>
        <template #mastery="{ record }">
          <a-progress :percent="record.mastery" :size="16" :show-text="false" :stroke-width="6" color="#181713" style="width:80px" />
          <span class="mastery-value">{{ record.mastery }}%</span>
        </template>
      </a-table>

      <!-- 用户详情弹窗 -->
      <a-modal v-model:visible="detailVisible" :title="(adminDetail?.username || '') + ' - 学习报表'" :footer="false" width="800px">
        <div v-if="adminDetail">
          <a-descriptions :column="3" bordered size="small" style="margin-bottom:16px">
            <a-descriptions-item label="用户名">{{ adminDetail.username }}</a-descriptions-item>
            <a-descriptions-item label="引导">{{ adminDetail.onboarded ? '已完成' : '未完成' }}</a-descriptions-item>
            <a-descriptions-item label="总分数">{{ adminDetail.score }}</a-descriptions-item>
            <a-descriptions-item label="解题数">{{ adminDetail.solved_count }}</a-descriptions-item>
            <a-descriptions-item label="掌握度">{{ adminDetail.mastery }}%</a-descriptions-item>
            <a-descriptions-item label="学习目标" :span="3">{{ adminDetail.goals || '未设置' }}</a-descriptions-item>
          </a-descriptions>
          <h4 style="margin:12px 0 8px">CTF 六方向自评</h4>
          <div v-if="adminDetail.skills && Object.keys(adminDetail.skills).length">
            <div v-for="(v,k) in adminDetail.skills" :key="k" class="skill-row">
              <span class="skill-label">{{ dirLabel(k) }}</span>
              <a-rate :model-value="v" :count="5" disabled :size="14" style="flex:1" />
              <span class="skill-score">{{ v }}/5</span>
            </div>
          </div>
          <div v-else style="color:#999;text-align:center;padding:12px">未设置</div>
          <h4 style="margin:16px 0 8px">知识概念掌握度</h4>
          <div v-if="adminDetail.concepts?.length">
            <div v-for="c in adminDetail.concepts" :key="c.name" class="admin-concept-row">
              <span class="concept-name">{{ c.name }}</span>
              <div class="concept-bar-bg"><div class="concept-bar" :class="'level-' + masteryLevel(c.mastery)" :style="{width:c.mastery*100+'%'}"></div></div>
              <span class="concept-val">{{ Math.round(c.mastery*100) }}%</span>
            </div>
          </div>
          <div v-else style="color:#999;text-align:center;padding:12px">暂无数据</div>
        </div>
      </a-modal>
    </div>

    <!-- ===== 用户视图：个人学习看板 ===== -->
    <div v-else class="container">
      <!-- 顶部：用户信息 + 画像标签 -->
      <div class="dashboard-header">
        <div class="header-left">
          <p class="section-kicker">STUDENT DESK / Personal Brief</p>
          <h1 class="greeting">{{ greeting }}，{{ userStore.userName }}</h1>
          <div class="persona-tags" v-if="personaTags.length">
            <a-tag v-for="t in personaTags" :key="t" :color="tagColor(t)">{{ t }}</a-tag>
          </div>
        </div>
      </div>

      <div class="dashboard-grid">
        <!-- 左列：推荐 + 复习 -->
        <div class="column-left">
          <div class="card recommend-card">
            <h3 class="card-title">AI 推荐学习</h3>
            <a-spin :loading="recommendLoading">
              <div v-if="recommendations.length" class="recommend-list">
                <div v-for="item in recommendations" :key="item.id" class="recommend-item" @click="item.action_link && router.push(item.action_link)" style="cursor:pointer">
                  <span class="rec-icon">{{ getRecommendationIcon(item.type) }}</span>
                  <div class="rec-content">
                    <div class="rec-title">{{ item.title }}</div>
                    <div class="rec-reason">{{ item.reason }}</div>
                    <div class="rec-meta" v-if="item.estimated_time || item.expected_gain">
                      <span v-if="item.estimated_time" class="rec-time">约 {{ item.estimated_time }}</span>
                      <span v-if="item.expected_gain" class="rec-gain">{{ item.expected_gain }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="empty-mini">暂无推荐</div>
            </a-spin>
          </div>

          <div class="card review-card">
            <div class="review-card-head">
              <h3 class="card-title">复习提醒</h3>
              <span>{{ reviewReminders.length }} 项</span>
            </div>
            <a-spin :loading="reviewLoading">
              <div v-if="reviewReminders.length" class="review-list">
                <div v-for="(item, index) in reviewReminders" :key="item.id" class="review-item">
                  <div class="review-info">
                    <div class="review-title">{{ item.concept_name }}</div>
                    <div class="review-meta">
                      记忆率 {{ formatMemoryRate(item, index) }} · {{ item.challenge?.title || '题库练习' }}
                    </div>
                  </div>
                  <div class="review-actions">
                    <a-button size="mini" type="primary" @click="goReviewPractice(item)">练习</a-button>
                    <a-button
                      size="mini"
                      type="text"
                      :loading="reviewCompletingId === item.id"
                      @click="completeReview(item)"
                    >
                      完成
                    </a-button>
                  </div>
                </div>
              </div>
              <div v-else class="empty-mini review-empty">暂无待复习项</div>
            </a-spin>
          </div>

        </div>

        <div class="column-middle">
          <div class="card insights-card">

            <h3 class="card-title">学习洞察</h3>
            <a-spin :loading="insightsLoading">
              <div v-if="insights.length" class="insight-feed">
                <div v-for="item in insights" :key="item.id" class="insight-item">
                  <span class="insight-dot" :class="'severity-' + (item.severity || 'info')"></span>
                  <div>
                    <p class="insight-text">{{ item.title }}</p>
                    <p class="insight-desc" v-if="item.description">{{ item.description }}</p>
                  </div>
                </div>
              </div>
              <div v-else class="empty-mini">暂无洞察</div>
            </a-spin>
          </div>

          <div class="card teaching-card">
            <h3 class="card-title">个性化教学方案</h3>
            <a-spin :loading="teachingPlanLoading">
              <div v-if="teachingPlan" class="teaching-plan">
                <div class="plan-validity">{{ teachingPlan.validity_label || '基于用户自评生成' }}</div>
                <p class="plan-summary">{{ teachingPlan.summary }}</p>
                <div class="plan-steps">
                  <div v-for="item in teachingPlan.plan_items" :key="item.phase" class="plan-step">
                    <div class="plan-step-head">
                      <strong>{{ item.phase }} · {{ item.title }}</strong>
                      <span>{{ item.duration }}</span>
                    </div>
                    <ul>
                      <li v-for="action in item.actions" :key="action">{{ action }}</li>
                    </ul>
                  </div>
                </div>
              </div>
              <div v-else class="empty-mini">暂无教学方案</div>
            </a-spin>
          </div>
        </div>

        <!-- 右列：文章 + 进度 -->
        <div class="column-right">
          <div class="card articles-card">
            <h3 class="card-title">推荐文章</h3>
            <a-spin :loading="articleLoading">
              <div v-if="recommendedArticles.length" class="article-recommend-list">
                <div
                  v-for="item in recommendedArticles"
                  :key="item.key"
                  class="article-recommend-item"
                  @click="router.push(item.link)"
                >
                  <div class="article-recommend-head">
                    <span class="article-source" :class="'source-' + item.sourceType">{{ item.source }}</span>
                    <span class="article-meta">{{ item.meta }}</span>
                  </div>
                  <div class="article-recommend-title">{{ item.title }}</div>
                  <div class="article-recommend-desc">{{ item.description }}</div>
                </div>
              </div>
              <div v-else class="empty-mini">暂无推荐文章</div>
            </a-spin>
          </div>

          <div class="card progress-card">
            <h3 class="card-title">学习进度</h3>
            <a-spin :loading="progressLoading">
              <div class="total-progress" v-if="progressData">
                <div class="progress-ring-wrap">
                  <div
                    class="progress-ring"
                    :style="{ '--progress-deg': `${completionPercent * 3.6}deg` }"
                  >
                    <div class="progress-ring-center">
                      <strong>{{ completionPercent }}%</strong>
                      <span>总进度</span>
                    </div>
                  </div>
                  <div class="progress-ring-meta">
                    <div>
                      <span class="meta-dot done"></span>
                      <span>已完成</span>
                      <strong>{{ completionPercent }}%</strong>
                    </div>
                    <div>
                      <span class="meta-dot remaining"></span>
                      <span>待完成</span>
                      <strong>{{ 100 - completionPercent }}%</strong>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="empty-mini">加载进度数据中...</div>
            </a-spin>
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

const router = useRouter()
const userStore = useUserStore()

// ===== 管理员数据 =====
const adminStudents = ref([])
const adminLoading = ref(false)
const adminSearch = ref('')
const adminDetail = ref(null)
const detailVisible = ref(false)
const adminColumns = [
  { title: '用户名', dataIndex: 'username', width: 110 },
  { title: '引导', slotName: 'onboarded', width: 75 },
  { title: 'CTF方向', slotName: 'skills', width: 130 },
  { title: '掌握度', slotName: 'mastery', width: 140 },
]
const skillLevel = (value) => {
  const score = Number(value) || 0
  if (score >= 4) return 'high'
  if (score >= 2) return 'mid'
  return 'low'
}
const masteryLevel = (value) => {
  const score = Number(value) || 0
  if (score > 0.7) return 'high'
  if (score > 0.4) return 'mid'
  return 'low'
}
const adminFiltered = computed(() => {
  const q = adminSearch.value.toLowerCase()
  return q ? adminStudents.value.filter(s => s.username.toLowerCase().includes(q)) : adminStudents.value
})
const adminOnboarded = computed(() => adminStudents.value.filter(s => s.onboarded).length)
const adminAvgMastery = computed(() => {
  const v = adminStudents.value.filter(s => s.mastery > 0).map(s => s.mastery)
  return v.length ? Math.round(v.reduce((a,b)=>a+b,0)/v.length) : 0
})
const adminTotalSolved = computed(() => adminStudents.value.reduce((a,b)=>a+(b.solved_count||0),0))
const dirLabel = (k) => ({
  web: 'Web安全',
  crypto: '密码学',
  pwn: '二进制安全',
  reverse: '逆向工程',
  forensics: '数字取证',
  misc: '综合杂项',
}[k] || k)

const fetchAdminData = async () => {
  adminLoading.value = true
  try { adminStudents.value = await api.analytics.adminStudentReport() || [] } catch(e){ console.error(e) }
  finally { adminLoading.value = false }
}
const showStudentDetail = (record) => { adminDetail.value = record; detailVisible.value = true }

// 检查是否是管理员
const isAdmin = computed(() => userStore.userInfo?.role === 'admin')

const personaTags = ref([])
const recommendations = ref([])
const insights = ref([])
const progressData = ref(null)
const recommendedArticles = ref([])
const reviewReminders = ref([])
const teachingPlan = ref(null)
const recommendLoading = ref(false)
const insightsLoading = ref(false)
const progressLoading = ref(false)
const articleLoading = ref(false)
const reviewLoading = ref(false)
const teachingPlanLoading = ref(false)
const reviewCompletingId = ref(null)

const completionPercent = computed(() => {
  const v = progressData.value?.completion_rate
  if (v === undefined || v === null) return 0
  const n = Number(v)
  const pct = n <= 1 ? Math.round(n * 100) : Math.round(n)
  return isNaN(pct) ? 0 : Math.max(0, Math.min(100, pct))
})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const tagColor = (t) => {
  const map = { '新手': 'green', '进阶': 'blue', '专家': 'purple', '活跃': 'orange' }
  return map[t] || 'arcoblue'
}

const getRecommendationIcon = (type) => {
  const map = {
    weakness_fix: '📚',
    strength: '💪',
    onboarding: '🎯',
    next_step: '📈',
    goal_aligned: '🎯',
    exploration: '🏆',
  }
  return map[type] || '📌'
}

const normalizeArray = (v) => (Array.isArray(v) ? v : (v?.results || []))

const pickFirstItems = (items, count = 1) => normalizeArray(items).filter(Boolean).slice(0, count)

const trimText = (text, fallback = '') => {
  const value = String(text || fallback || '').replace(/\s+/g, ' ').trim()
  return value.length > 58 ? `${value.slice(0, 58)}...` : value
}

const formatMemoryRate = (item, index = 0) => {
  const seed = String(item?.id ?? item?.concept_name ?? index)
  const hash = Array.from(seed).reduce((sum, char) => sum + char.charCodeAt(0), index * 7)
  const base = 68 + (hash % 17)
  const mastery = Number(item?.mastery_level)
  const timesViewed = Number(item?.times_viewed)
  const masteryBoost = Number.isFinite(mastery) ? Math.round(Math.max(0, Math.min(1, mastery)) * 8) : 0
  const reviewBoost = Number.isFinite(timesViewed) ? Math.min(5, Math.max(0, timesViewed)) : 0
  const pct = Math.max(68, Math.min(92, base + masteryBoost + reviewBoost))
  return `${pct}%`
}

const fetchPersona = async () => {
  try {
    const data = await api.studentProfile.persona()
    personaTags.value = data?.tags || data?.persona_tags || []
  } catch { /* non-critical */ }
}

const fetchRecommendations = async () => {
  recommendLoading.value = true
  try {
    const data = await api.learningAgent.recommend()
    // rule_engine 杩斿洖 {recommendations: [...]}
    if (data?.recommendations) {
      recommendations.value = data.recommendations.map((r, i) => ({ id: i + 1, ...r }))
    } else if (data?.recommendation) {
      recommendations.value = [{ id: 1, type: 'recommendation', title: '学习推荐', reason: data.recommendation }]
    } else {
      recommendations.value = normalizeArray(data)
    }
  } catch { recommendations.value = [] }
  finally { recommendLoading.value = false }
}

const fetchInsights = async () => {
  insightsLoading.value = true
  try {
    const data = await api.analytics.insights()
    insights.value = normalizeArray(data).slice(0, 5)
  } catch { insights.value = [] }
  finally { insightsLoading.value = false }
}

const fetchProgress = async () => {
  progressLoading.value = true
  try {
    const [report, stats] = await Promise.all([
      api.analytics.progressReport(),
      api.submission.stats()
    ])
    progressData.value = { ...report, ...stats }
  } catch { progressData.value = null }
  finally { progressLoading.value = false }
}

const fetchRecommendedArticles = async () => {
  articleLoading.value = true
  try {
    const [pathData, communityData, resourceData] = await Promise.all([
      api.learningPaths.list({ page_size: 3 }),
      api.article.recommend({ limit: 3 }),
      api.resource.list({ page_size: 3, ordering: '-view_count' })
    ])

    const pathItems = pickFirstItems(pathData, 3).map(item => ({
      key: `path-${item.id}`,
      source: '学习路径',
      sourceType: 'path',
      title: item.title,
      description: trimText(item.description, '系统学习路径内容'),
      meta: item.difficulty_display || item.difficulty || '路径',
      link: `/learning-paths/${item.id}`
    }))

    const communityItems = pickFirstItems(communityData, 3).map(item => ({
      key: `community-${item.id}`,
      source: '社区',
      sourceType: 'community',
      title: item.title,
      description: trimText(item.summary || item.content, item.title),
      meta: item.category_name || '文章',
      link: `/community/article/${item.id}`
    }))

    const resourceItems = pickFirstItems(resourceData, 3).map(item => ({
      key: `resource-${item.id}`,
      source: '资源中心',
      sourceType: 'resource',
      title: item.title,
      description: trimText(item.description, '推荐学习资源'),
      meta: item.resource_type_display || item.category || '资源',
      link: `/resources?resource=${item.id}`
    }))

    const grouped = [pathItems[0], communityItems[0], resourceItems[0]].filter(Boolean)
    const fallback = [...pathItems, ...communityItems, ...resourceItems]
      .filter(item => item && !grouped.some(selected => selected.key === item.key))

    recommendedArticles.value = [...grouped, ...fallback].slice(0, 3)
  } catch {
    recommendedArticles.value = []
  } finally {
    articleLoading.value = false
  }
}

const fetchReviewReminders = async () => {
  reviewLoading.value = true
  try {
    const data = await api.learningPaths.reviewReminders()
    reviewReminders.value = normalizeArray(data).slice(0, 3)
  } catch {
    reviewReminders.value = []
  } finally {
    reviewLoading.value = false
  }
}

const fetchTeachingPlan = async () => {
  teachingPlanLoading.value = true
  try {
    teachingPlan.value = await api.analytics.teachingPlan()
  } catch {
    teachingPlan.value = null
  } finally {
    teachingPlanLoading.value = false
  }
}

const goReviewPractice = (item) => {
  if (item?.challenge?.id) {
    router.push({ name: 'ChallengeDetail', params: { id: item.challenge.id } })
    return
  }

  if (item?.action_link) {
    router.push(item.action_link)
    return
  }

  router.push('/challenges')
}

const completeReview = async (item) => {
  reviewCompletingId.value = item.id
  try {
    await api.learningPaths.completeReview({ state_id: item.id, success: true })
    await Promise.all([fetchReviewReminders(), fetchProgress()])
  } finally {
    reviewCompletingId.value = null
  }
}

onMounted(async () => {
  if (userStore.userInfo?.role === 'admin') {
    fetchAdminData()
    return
  }
  // 检查是否完成引导，未完成则跳转
  try {
    const profile = await api.studentProfile.get()
    if (!profile.onboarding_completed) {
      router.replace('/profile/setup')
      return
    }
  } catch {}

  fetchPersona()
  fetchRecommendations()
  fetchInsights()
  fetchProgress()
  fetchRecommendedArticles()
  fetchReviewReminders()
  fetchTeachingPlan()
})
</script>

<style scoped>
.dashboard-page {
  min-height: calc(100vh - 64px);
  background: #f5f7fb;
  padding: 14px 0 18px;
}

.container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 14px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 44px;
  margin-bottom: 12px;
}

.greeting { font-size: 20px; font-weight: 650; color: #1a3a5c; margin: 0 0 4px; }

.persona-tags { display: flex; gap: 6px; flex-wrap: wrap; }

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(340px, 1.08fr) minmax(320px, 1fr) minmax(320px, 1fr);
  grid-template-areas:
    "recommend insights articles"
    "review teaching progress";
  gap: 8px;
  align-items: stretch;
}

.column-left,
.column-middle,
.column-right {
  display: contents;
  min-width: 0;
}

.recommend-card {
  grid-area: recommend;
}

.review-card {
  grid-area: review;
}

.insights-card {
  grid-area: insights;
}

.teaching-card {
  grid-area: teaching;
}

.articles-card {
  grid-area: articles;
}

.progress-card {
  grid-area: progress;
}

.articles-card,
.progress-card {
  display: flex;
  flex-direction: column;
}

.card {
  width: 100%;
  box-sizing: border-box;
  min-height: 0;
  background: #fbfcff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 0;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04);
  border: 1px solid #e4eaf3;
}

.card-title { font-size: 14px; font-weight: 650; color: #1a3a5c; margin: 0 0 10px; }

.progress-card :deep(.arco-spin),
.progress-card :deep(.arco-spin-children) {
  width: 100%;
  min-height: 0;
}

.recommend-item {
  display: flex; gap: 8px; padding: 9px;
  border-radius: 6px;
  background: #f7f9fd;
  margin-bottom: 6px;
  transition: background .2s;
}
.recommend-item:hover { background: #eef3ff; }
.recommend-item:last-child { margin-bottom: 0; }

.rec-icon { font-size: 18px; flex-shrink: 0; line-height: 1.2; }

.rec-title { font-size: 13px; font-weight: 650; color: #1a3a5c; margin-bottom: 3px; }

.rec-reason {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  color: #6b7c93;
  line-height: 1.45;
}

.rec-meta { display: flex; gap: 10px; margin-top: 5px; }
.rec-time, .rec-gain { font-size: 11px; color: #7b8ba3; }

.insight-feed {
  overflow: hidden;
}

.insight-item { display: flex; gap: 8px; padding: 6px 0; }

.insight-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: linear-gradient(135deg, #165dff, #4080ff);
  flex-shrink: 0; margin-top: 6px;
}

.insight-text { font-size: 12px; color: #4a5a72; line-height: 1.45; margin: 0; font-weight: 600; }

.insight-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 2px 0 0;
  color: #7b8ba3;
  font-size: 11px;
  line-height: 1.45;
}

.teaching-plan {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  align-items: start;
}

.plan-validity {
  display: inline-flex;
  width: fit-content;
  padding: 3px 8px;
  border-radius: 4px;
  background: #edf5ff;
  color: #165dff;
  font-size: 12px;
  font-weight: 600;
}

.plan-summary {
  margin: 0;
  color: #4a5a72;
  font-size: 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.plan-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.plan-step {
  min-width: 0;
  padding: 7px 8px;
  border-radius: 6px;
  background: #f7f9fc;
  border: 1px solid #edf1f7;
}

.plan-step-head {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.plan-step-head strong {
  color: #1a3a5c;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-step-head span {
  flex: 0 0 auto;
  color: #6b7c93;
  font-size: 11px;
}

.plan-step ul {
  margin: 0;
  padding-left: 16px;
  color: #5f6f86;
  font-size: 11px;
  line-height: 1.45;
  max-height: 34px;
  overflow: hidden;
}

.total-progress {
  padding: 0;
}

.progress-ring-wrap {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 10px;
}

.progress-ring {
  width: 112px;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    conic-gradient(#165dff var(--progress-deg), #e8eef8 0deg);
  box-shadow: 0 8px 18px rgba(22, 93, 255, 0.10);
}

.progress-ring-center {
  width: 72px;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 4px;
  border-radius: 50%;
  background: #fff;
  box-shadow: inset 0 0 0 1px #edf1f7;
}

.progress-ring-center strong {
  color: #165dff;
  font-size: 22px;
  font-weight: 760;
  line-height: 1;
}

.progress-ring-center span {
  color: #6b7c93;
  font-size: 11px;
  font-weight: 600;
}

.progress-ring-meta {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}

.progress-ring-meta div {
  min-width: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 4px 6px;
  padding: 8px;
  border-radius: 6px;
  background: #f7f9fc;
  color: #6b7c93;
  font-size: 12px;
}

.progress-ring-meta strong {
  grid-column: 2;
  color: #1a3a5c;
  font-size: 14px;
}

.meta-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.meta-dot.done {
  background: #165dff;
}

.meta-dot.remaining {
  background: #cbd5e1;
}

.review-card {
  padding: 12px;
}

.review-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  color: #1a3a5c;
  font-size: 13px;
  font-weight: 600;
}

.review-card-head .card-title {
  margin-bottom: 0;
}

.review-card-head span:last-child {
  color: #6b7c93;
  font-size: 11px;
  font-weight: 500;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.review-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 7px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #edf1f7;
}

.review-info {
  min-width: 0;
}

.review-title {
  font-size: 12px;
  font-weight: 600;
  color: #1a3a5c;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-meta {
  margin-top: 3px;
  font-size: 11px;
  color: #6b7c93;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.review-actions :deep(.arco-btn-size-mini) {
  height: 24px;
  padding: 0 7px;
  border-radius: 4px;
  font-size: 11px;
}

.review-empty {
  padding: 12px 0;
}

.article-recommend-list { display: flex; flex-direction: column; gap: 6px; }

.article-recommend-item {
  padding: 7px 9px;
  border-radius: 6px;
  background: #f7f9fc;
  border: 1px solid #edf1f7;
  cursor: pointer;
  transition: background .2s, border-color .2s;
}

.article-recommend-item:hover {
  background: #f1f6ff;
  border-color: #d8e6fb;
}

.article-recommend-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.article-source {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.source-path { color: #165dff; background: #edf5ff; }
.source-community { color: #00875f; background: #ebf8f2; }
.source-resource { color: #b65b00; background: #fff4e8; }

.article-meta {
  min-width: 0;
  font-size: 11px;
  color: #9499a0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.article-recommend-title {
  font-size: 12px;
  font-weight: 600;
  color: #1a3a5c;
  line-height: 1.4;
  margin-bottom: 3px;
}

.article-recommend-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 11px;
  color: #6b7c93;
  line-height: 1.45;
}

.empty-mini { text-align: center; color: #9499a0; font-size: 13px; padding: 20px 0; }

/* 管理员视图 */
.page-title { font-size: 22px; font-weight: 700; margin-bottom: 20px; color: #1f1f1f; }
.summary-row { display: flex; gap: 16px; margin-bottom: 20px; }
.summary-card { flex:1; background:#fff; border-radius:8px; padding:16px 20px; text-align:center; box-shadow:0 1px 4px rgba(0,0,0,.06); }
.s-num { display:block; font-size:22px; font-weight:700; color:#1f1f1f }
.s-label { display:block; font-size:12px; color:#9499a0; margin-top:2px }
.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 10px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 850;
  line-height: 1;
}
.status-pill.is-guided {
  color: var(--text-primary);
  background: var(--bg-paper-2);
}
.status-pill.is-pending {
  color: var(--text-secondary);
  background: rgba(24, 23, 19, 0.06);
  border-style: dashed;
}
.admin-skill-dot {
  width: 12px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;
  margin-right: 4px;
  border: 1px solid rgba(24, 23, 19, 0.12);
}
.admin-skill-dot.level-high,
.concept-bar.level-high {
  background: var(--text-primary);
}
.admin-skill-dot.level-mid,
.concept-bar.level-mid {
  background: #8b7356;
}
.admin-skill-dot.level-low,
.concept-bar.level-low {
  background: #d6c6b2;
}
.mastery-value {
  margin-left: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}
.skill-row { display:flex; align-items:center; gap:10px; margin-bottom:6px }
.skill-label { width:80px; font-size:13px; text-align:right }
.skill-score { font-size:13px; font-weight:600; width:30px }
.admin-concept-row { display:flex; align-items:center; gap:10px; margin-bottom:6px }
.concept-name { width:100px; font-size:12px; text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.concept-bar-bg { flex:1; height:12px; background:#f0f0f0; border-radius:6px; overflow:hidden }
.concept-bar { height:100%; border-radius:6px; transition:width .3s }
.concept-val { width:36px; font-size:12px; font-weight:600; text-align:right }

@media (max-width: 1180px) {
  .dashboard-grid {
    grid-template-columns: minmax(0, 1fr) minmax(320px, 0.9fr);
    grid-template-areas:
      "recommend insights"
      "review teaching"
      "articles progress";
  }
}

@media (max-width: 760px) {
  .dashboard-page {
    padding-top: 10px;
  }

  .dashboard-header {
    align-items: flex-start;
    margin-bottom: 10px;
  }

  .greeting {
    font-size: 18px;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
    grid-template-areas:
      "recommend"
      "review"
      "insights"
      "teaching"
      "articles"
      "progress";
  }

  .teaching-plan,
  .plan-steps,
  .progress-ring-wrap {
    grid-template-columns: 1fr;
  }

  .progress-ring-wrap {
    justify-items: center;
  }
}

/* Phase 2 Editorial UI override */
.dashboard-page {
  background:
    linear-gradient(90deg, rgba(24, 23, 19, 0.045) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(180deg, #faf7f0 0%, var(--bg-paper) 100%);
  padding: 42px 0 72px;
}

.container {
  width: min(1180px, calc(100% - 40px));
  max-width: none;
  padding: 0;
}

.report-heading,
.dashboard-header {
  margin-bottom: 24px;
}

.dashboard-header {
  align-items: flex-end;
}

.page-title,
.greeting {
  margin: 6px 0 8px;
  color: var(--text-primary);
  font-size: 44px;
  line-height: 1;
  font-weight: 950;
}

.dashboard-grid {
  grid-template-columns: minmax(320px, 0.95fr) minmax(320px, 1fr) minmax(300px, 0.9fr);
  gap: 16px;
}

.card,
.summary-card {
  background: rgba(255, 250, 242, 0.74);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: none;
}

.card {
  padding: 18px;
}

.card-title {
  margin: 0 0 14px;
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1.1;
  font-weight: 950;
}

.recommend-item,
.insight-item,
.review-item,
.article-recommend-item {
  background: transparent;
  border-radius: 0;
}

.recommend-item {
  padding: 13px 0;
  border-bottom: 1px solid var(--border-color);
}

.recommend-item:hover,
.article-recommend-item:hover {
  color: var(--primary-color);
  background: var(--bg-paper-2);
  border-color: var(--primary-color);
}

.review-item,
.article-recommend-item,
.plan-step,
.progress-ring-meta div {
  background: rgba(255, 250, 242, 0.66);
  border: 1px solid var(--border-color);
}

.rec-title,
.insight-text,
.review-title,
.article-recommend-title,
.plan-step-head strong,
.progress-ring-meta strong {
  color: var(--text-primary);
  font-weight: 850;
}

.rec-reason,
.insight-desc,
.review-meta,
.article-recommend-desc,
.plan-summary,
.plan-step-head span,
.plan-step ul,
.progress-ring-meta div {
  color: var(--text-secondary);
}

.insight-dot,
.meta-dot.done {
  background: var(--primary-color);
}

.plan-validity,
.source-resource {
  color: #785313;
  background: rgba(239, 196, 107, 0.32);
}

.source-path {
  color: var(--primary-color);
  background: rgba(183, 53, 45, 0.1);
}

.source-community {
  color: var(--success-color);
  background: rgba(79, 124, 82, 0.12);
}

.progress-ring {
  background: conic-gradient(var(--primary-color) var(--progress-deg), var(--bg-paper-2) 0deg);
  box-shadow: none;
}

.progress-ring-center {
  background: #fffaf2;
  box-shadow: inset 0 0 0 1px var(--border-color);
}

.progress-ring-center strong {
  color: var(--primary-color);
}

.progress-ring-center span,
.rec-time,
.rec-gain,
.article-meta,
.empty-mini {
  color: var(--text-muted);
}

.meta-dot.remaining {
  background: var(--bg-paper-2);
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.summary-card {
  min-height: 118px;
  display: grid;
  place-items: center;
  align-content: center;
  padding: 18px 20px;
}

.s-num {
  color: var(--text-primary);
  font-size: 34px;
  line-height: 1;
  font-weight: 950;
}

.s-label {
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

/* 学生学习概览：采用两列留白布局，避免空数据时出现拥挤的小卡片。 */
.dashboard-page {
  padding: 56px 0 88px;
}

.container {
  width: min(1220px, calc(100% - 64px));
}

.dashboard-header {
  margin-bottom: 34px;
}

.dashboard-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-areas:
    "recommend insights"
    "review teaching"
    "articles progress";
  gap: 24px;
}

.card {
  min-height: 218px;
  padding: 26px;
}

.empty-mini {
  display: grid;
  min-height: 112px;
  place-items: center;
  padding: 0;
  text-align: center;
}

@media (max-width: 760px) {
  .dashboard-page { padding: 28px 0 48px; }
  .container { width: min(100% - 32px, 620px); }
  .dashboard-header { margin-bottom: 24px; }
  .dashboard-grid {
    grid-template-columns: 1fr;
    grid-template-areas: "recommend" "review" "insights" "teaching" "articles" "progress";
    gap: 16px;
  }
  .card { min-height: 190px; padding: 20px; }
}

.admin-toolbar {
  width: min(360px, 100%);
  margin-bottom: 18px;
}

.concept-bar-bg {
  background: var(--bg-paper-2);
  border-radius: 999px;
}

:deep(.arco-table-container) {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255, 250, 242, 0.78);
}

:deep(.arco-table-th) {
  background: var(--bg-paper-2);
  color: var(--text-primary);
  font-weight: 850;
}

:deep(.arco-table-td) {
  background: rgba(255, 250, 242, 0.5);
  border-color: var(--border-color);
}

:deep(.arco-input-wrapper) {
  background: rgba(255, 250, 242, 0.78);
  border-radius: 4px;
}

@media (max-width: 760px) {
  .page-title,
  .greeting {
    font-size: 34px;
  }

  .summary-row {
    grid-template-columns: 1fr;
  }
}
</style>

