<template>
  <div class="dashboard-page" :class="{ 'student-layout': isStudent }">
    <!-- ===== 管理员视图：用户学习报表 ===== -->
    <div v-if="userStore.userInfo?.role === 'admin'" class="container">
      <div class="report-heading">

        <h1 class="page-title">{{ names.globalInsights }}</h1>
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
          <a-progress :percent="record.mastery" :size="16" :show-text="false" :stroke-width="6" color="var(--ink)" style="width:var(--space-10)" />
          <span class="mastery-value">{{ record.mastery }}%</span>
        </template>
      </a-table>

      <!-- 用户详情弹窗 -->
      <a-modal v-model:visible="detailVisible" :title="(adminDetail?.username || '') + ' - 学习报表'" :footer="false" width="800px">
        <div v-if="adminDetail">
          <a-descriptions :column="3" bordered size="small" style="margin-bottom:var(--space-2)">
            <a-descriptions-item label="用户名">{{ adminDetail.username }}</a-descriptions-item>
            <a-descriptions-item label="引导">{{ adminDetail.onboarded ? '已完成' : '未完成' }}</a-descriptions-item>
            <a-descriptions-item label="总分数">{{ adminDetail.score }}</a-descriptions-item>
            <a-descriptions-item label="解题数">{{ adminDetail.solved_count }}</a-descriptions-item>
            <a-descriptions-item label="掌握度">{{ adminDetail.mastery }}%</a-descriptions-item>
            <a-descriptions-item label="学习目标" :span="3">{{ adminDetail.goals || '未设置' }}</a-descriptions-item>
          </a-descriptions>
          <h4 style="margin:var(--space-1) 0 var(--space-1)">CTF 六方向自评</h4>
          <div v-if="adminDetail.skills && Object.keys(adminDetail.skills).length">
            <div v-for="(v,k) in adminDetail.skills" :key="k" class="skill-row">
              <span class="skill-label">{{ dirLabel(k) }}</span>
              <a-rate :model-value="v" :count="5" disabled :size="14" style="flex:1" />
              <span class="skill-score">{{ v }}/5</span>
            </div>
          </div>
          <div v-else class="mini-empty">未设置</div>
          <h4 style="margin:var(--space-2) 0 var(--space-1)">知识概念掌握度</h4>
          <div v-if="adminDetail.concepts?.length">
            <div v-for="c in adminDetail.concepts" :key="c.name" class="admin-concept-row">
              <span class="concept-name">{{ c.name }}</span>
              <div class="concept-bar-bg"><div class="concept-bar" :class="'level-' + masteryLevel(c.mastery)" :style="{width:c.mastery*100+'%'}"></div></div>
              <span class="concept-val">{{ Math.round(c.mastery*100) }}%</span>
            </div>
          </div>
          <div v-else class="mini-empty">暂无数据</div>
        </div>
      </a-modal>
    </div>

    <!-- ===== 用户视图：个人学习看板 ===== -->
    <div v-else class="container">
      <!-- 顶部：用户信息 + 画像标签 -->
      <div class="dashboard-header">
        <div class="header-left">

          <h1 class="greeting">{{ names.growth }} · 学习进度</h1>
          <p>{{ greeting }}，{{ userStore.userName }}</p>
          <div class="persona-tags" v-if="personaTags.length">
            <a-tag v-for="t in personaTags" :key="t" :color="tagColor(t)">{{ t }}</a-tag>
          </div>
        </div>
      </div>

      <section v-if="isStudent" class="dashboard-console" aria-labelledby="dashboard-agent-heading">
        <div class="dashboard-console-heading"><icon-robot /><h2 id="dashboard-agent-heading">{{ names.guide }} · 你的学习工作台</h2></div>
        <form @submit.prevent="askTutor">
          <label for="dashboard-question">说说你的学习目标或卡住的地方</label>
          <textarea id="dashboard-question" v-model="question" placeholder="例如：我想理解访问控制，应该先练什么？" rows="3" maxlength="2000" @keydown.ctrl.enter.prevent="askTutor" />
          <div class="dashboard-console-actions"><span><icon-safe /> 先给思路与分级提示，不代做答案</span><a-button type="primary" html-type="submit" :disabled="!question.trim()">开始导学 <icon-arrow-right /></a-button></div>
        </form>
        <nav class="dashboard-console-links" aria-label="导学入口"><button class="text-action" @click="openTutor(router)">继续导学对话 <icon-message /></button><router-link to="/guide">开启{{ names.guide }} <icon-arrow-right /></router-link></nav>
      </section>

      <div class="dashboard-grid" :class="{ 'without-student-progress': isStudent && !hasStudentProgress }">
        <!-- 左列：推荐 + 复习 -->
        <div class="column-left">
          <div class="card recommend-card">
            <h3 class="card-title">AI 推荐学习</h3>
            <a-spin :loading="recommendLoading">
              <div v-if="recommendations.length" class="recommend-list">
                <div v-for="item in recommendations" :key="item.id" class="recommend-item" @click="item.action_link && router.push(item.action_link)" style="cursor:pointer">
                  <span class="rec-icon"><AppIcon :name="getRecommendationIcon(item.type)" /></span>
                  <div class="rec-content">
                    <div class="rec-title">{{ dashboardCopy(item.title) }}</div>
                    <div class="rec-reason">{{ dashboardCopy(item.reason) }}</div>
                    <div class="rec-meta" v-if="item.estimated_time || item.expected_gain">
                      <span v-if="item.estimated_time" class="rec-time">约 {{ item.estimated_time }}</span>
                      <span v-if="item.expected_gain" class="rec-gain">{{ item.expected_gain }}</span>
                    </div>
                    <details @click.stop>
                      <summary>查看推荐依据</summary>
                      <button class="btn btn-secondary" @click.stop="downloadRecord(item, '推荐依据.json')">下载推荐依据完整记录</button>
                    </details>
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
                      记忆率 {{ formatMemoryRate(item) }} · {{ item.challenge?.title || names.practice }}
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
                    <p class="insight-text">{{ dashboardCopy(item.title) }}</p>
                    <p class="insight-desc" v-if="item.description">{{ dashboardCopy(item.description) }}</p>
                    <details @click.stop>
                      <summary>查看洞察依据</summary>
                      <button class="btn btn-secondary" @click.stop="downloadRecord(item, '洞察依据.json')">下载洞察依据完整记录</button>
                    </details>
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
              <div class="total-progress" v-if="progressData && (!isStudent || hasStudentProgress)">
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
import { names, renameCopy } from '@/shared/navigation/names'

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import api from '@/api'
import { downloadRecord } from '@/shared/forms/referenceFile'
import { dashboardCopy } from './dashboardCopy'
import { openTutor } from '@/learning/agent/public.js'

const router = useRouter()
const userStore = useUserStore()
const isStudent = computed(() => userStore.userInfo?.role === 'student')
const question = ref('')
function askTutor() {
  if (question.value.trim()) openTutor(router, { prompt: question.value, userId: userStore.userInfo?.id })
}

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

// 学生只展示 API 真实返回的比例；空字符串/null/非法值不成为 0% 统计。
const hasStudentProgress = computed(() => {
  const value = progressData.value?.completion_rate
  return (typeof value === 'number' || (typeof value === 'string' && value.trim() !== '')) && Number.isFinite(Number(value)) && Number(value) >= 0
})
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
    weakness_fix: 'bi-book',
    strength: 'bi-hand-thumbs-up',
    onboarding: 'bi-bullseye',
    next_step: 'bi-bar-chart',
    goal_aligned: 'bi-bullseye',
    exploration: 'bi-trophy',
  }
  return map[type] || 'bi-pin-angle'
}

const normalizeArray = (v) => (Array.isArray(v) ? v : (v?.results || []))

const pickFirstItems = (items, count = 1) => normalizeArray(items).filter(Boolean).slice(0, count)

const trimText = (text, fallback = '') => {
  const value = String(text || fallback || '').replace(/\s+/g, ' ').trim()
  return value.length > 58 ? `${value.slice(0, 58)}...` : value
}

const formatMemoryRate = (item) => {
  // 与既有导学 reviewReason 相同：recall_probability 是 0–1 概率，不由自评或浏览次数推算。
  const value = item?.recall_probability
  if (!(typeof value === 'number' || (typeof value === 'string' && value.trim() !== '')) || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1) return '—'
  return `${Math.round(Number(value) * 100)}%`
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
      source: names.paths,
      sourceType: 'path',
      title: item.title,
      description: trimText(item.description, renameCopy('系统学习路径内容')),
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
      source: names.resources,
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
  min-height:calc(100vh - var(--space-8));
  background:var(--surface-page);
  padding:var(--space-2) 0 var(--space-2);
}

.container {
  max-width:var(--page-width);
  margin:0 auto;
  padding:0 var(--space-2);
}

.dashboard-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  min-height:var(--space-5);
  margin-bottom:var(--space-1);
}

.greeting { font-size:var(--text-card); font-weight: var(--weight-strong); color:var(--ink); margin:0 0 calc(var(--space-1) / 2); }

.persona-tags { display:flex; gap:calc(var(--space-1) / 2); flex-wrap:wrap; }

.dashboard-grid {
  display:grid;
  grid-template-columns:minmax(var(--panel-width), 1.08fr) minmax(var(--panel-width), 1fr) minmax(var(--panel-width), 1fr);
  grid-template-areas:
    "recommend insights articles"
    "review teaching progress";
  gap:var(--space-1);
  align-items:stretch;
}

.column-left,
.column-middle,
.column-right {
  display:contents;
  min-width:0;
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
  display:flex;
  flex-direction:column;
}

.card {
  width:100%;
  box-sizing:border-box;
  min-width:0;
  min-height:0;
  background:var(--surface);
  border-radius:var(--radius-control);
  padding:var(--space-1) var(--space-1);
  margin-bottom:0;
  box-shadow: var(--shadow-raised);
  border:var(--stroke) solid var(--line);
}

.card-title { font-size:var(--text-caption); font-weight: var(--weight-strong); color:var(--ink); margin:0 0 var(--space-1); }

.card :deep(.arco-spin),
.card :deep(.arco-spin-children) {
  display:block;
  width:100%;
  max-width:100%;
  min-width:0;
  min-height:0;
}

.recommend-item {
  display:flex; gap:var(--space-1); padding:var(--space-1);
  border-radius:var(--radius-control);
  background:var(--surface-muted);
  margin-bottom:calc(var(--space-1) / 2);
  transition:background var(--motion-normal);
}
.recommend-item:hover { background:var(--action-soft); }
.recommend-item:last-child { margin-bottom:0; }

.rec-icon { font-size:var(--text-card); flex-shrink:0; line-height:1.2; }

.rec-content { min-width:0; flex:1; overflow-wrap:anywhere; }
.rec-title { font-size:var(--text-caption); font-weight: var(--weight-strong); color:var(--ink); margin-bottom:var(--focus-width); }

.rec-reason {
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow:hidden;
  font-size:var(--text-caption);
  color:var(--ink-secondary);
  line-height:1.45;
}

.rec-meta { display:flex; flex-wrap:wrap; gap:var(--space-1); margin-top:calc(var(--space-1) / 2); }
.rec-time, .rec-gain { font-size:var(--text-caption); color:var(--ink-muted); }

.insight-feed {
  overflow:hidden;
}

.insight-item { display:flex; gap:var(--space-1); padding:calc(var(--space-1) / 2) 0; }
.insight-item > div { min-width:0; overflow-wrap:anywhere; }

.insight-dot {
  width:var(--space-1); height:var(--space-1); border-radius:50%;
  background:var(--action);
  flex-shrink:0; margin-top:calc(var(--space-1) / 2);
}

.insight-text { font-size:var(--text-caption); color:var(--ink-secondary); line-height:1.45; margin:0; font-weight: var(--weight-strong); }

.insight-desc {
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow:hidden;
  margin:calc(var(--stroke) * 2) 0 0;
  color:var(--ink-muted);
  font-size:var(--text-caption);
  line-height:1.45;
}

.teaching-plan {
  display:grid;
  grid-template-columns:1fr;
  gap:var(--space-1);
  align-items:start;
}

.plan-validity {
  display:inline-flex;
  width:fit-content;
  padding:var(--focus-width) var(--space-1);
  border-radius:var(--radius-control);
  background:var(--action-soft);
  color:var(--action);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.plan-summary {
  margin:0;
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  line-height:1.5;
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow:hidden;
}

.plan-steps {
  display:grid;
  grid-template-columns:repeat(3, minmax(0, 1fr));
  gap:calc(var(--space-1) / 2);
}

.plan-step {
  min-width:0;
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-control);
  background:var(--surface-muted);
  border:var(--stroke) solid var(--line);
}

.plan-step-head {
  display:grid;
  grid-template-columns:1fr auto;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  margin-bottom:calc(var(--space-1) / 2);
}

.plan-step-head strong {
  color:var(--ink);
  font-size:var(--text-caption);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.plan-step-head span {
  flex:0 0 auto;
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.plan-step ul {
  margin:0;
  padding-left:var(--space-2);
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  line-height:1.45;
  max-height:var(--space-4);
  overflow:hidden;
}

.total-progress {
  padding:0;
}

.progress-ring-wrap {
  display:grid;
  grid-template-columns:auto 1fr;
  align-items:center;
  gap:var(--space-1);
}

.progress-ring {
  width:var(--row-label-width);
  aspect-ratio:1;
  display:grid;
  place-items: center;
  border-radius:50%;
  background:conic-gradient(var(--action) var(--progress-deg), var(--surface-muted) 0deg);
  box-shadow: var(--shadow-raised);
}

.progress-ring-center {
  width:var(--space-8);
  aspect-ratio:1;
  display:grid;
  place-items: center;
  align-content: center;
  gap:calc(var(--space-1) / 2);
  border-radius:50%;
  background:var(--surface);
  box-shadow: none;
}

.progress-ring-center strong {
  color:var(--action);
  font-size:var(--text-card);
  font-weight: var(--weight-strong);
  line-height:1;
}

.progress-ring-center span {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.progress-ring-meta {
  width:100%;
  display:grid;
  grid-template-columns:1fr;
  gap:calc(var(--space-1) / 2);
}

.progress-ring-meta div {
  min-width:0;
  display:grid;
  grid-template-columns:auto 1fr;
  align-items:center;
  gap:calc(var(--space-1) / 2) calc(var(--space-1) / 2);
  padding:var(--space-1);
  border-radius:var(--radius-control);
  background:var(--surface-muted);
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.progress-ring-meta strong {
  grid-column:2;
  color:var(--ink);
  font-size:var(--text-caption);
}

.meta-dot {
  width:var(--space-1);
  height:var(--space-1);
  border-radius:50%;
}

.meta-dot.done {
  background:var(--action);
}

.meta-dot.remaining {
  background:var(--line-strong);
}

.review-card {
  padding:var(--space-1);
}

.review-card-head {
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin-bottom:calc(var(--space-1) / 2);
  color:var(--ink);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.review-card-head .card-title {
  margin-bottom:0;
}

.review-card-head span:last-child {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
}

.review-list {
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
}

.review-item {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:var(--space-1);
  padding:calc(var(--space-1) / 2) calc(var(--space-1) / 2);
  border-radius:var(--radius-control);
  background:var(--surface);
  border:var(--stroke) solid var(--line);
}

.review-info {
  min-width:0;
}

.review-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--ink);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.review-meta {
  margin-top:var(--focus-width);
  font-size:var(--text-caption);
  color:var(--ink-secondary);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.review-actions {
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  flex-shrink:0;
}

.review-actions :deep(.arco-btn-size-mini) {
  height:var(--space-3);
  padding:0 calc(var(--space-1) / 2);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
}

.review-empty {
  padding:var(--space-1) 0;
}

.article-recommend-list { display:flex; flex-direction:column; gap:calc(var(--space-1) / 2); }

.article-recommend-item {
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-control);
  background:var(--surface-muted);
  border:var(--stroke) solid var(--line);
  cursor:pointer;
  transition:background var(--motion-normal), border-color var(--motion-normal);
}

.article-recommend-item:hover {
  background:var(--surface-hover);
  border-color:var(--line);
}

.article-recommend-head {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:var(--space-1);
  margin-bottom:calc(var(--space-1) / 2);
}

.article-source {
  display:inline-flex;
  align-items:center;
  height:var(--space-2);
  padding:0 calc(var(--space-1) / 2);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.source-path { color:var(--action); background:var(--action-soft); }
.source-community { color:var(--positive); background:var(--positive-soft); }
.source-resource { color:var(--warning); background:var(--warning-soft); }

.article-meta {
  min-width:0;
  font-size:var(--text-caption);
  color:var(--ink-muted);
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.article-recommend-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--ink);
  line-height:1.4;
  margin-bottom:var(--focus-width);
}

.article-recommend-desc {
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow:hidden;
  font-size:var(--text-caption);
  color:var(--ink-secondary);
  line-height:1.45;
}

.empty-mini { text-align:center; color:var(--ink-muted); font-size:var(--text-caption); padding:var(--space-2) 0; }

/* 管理员视图 */
.page-title { font-size:var(--text-card); font-weight: var(--weight-strong); margin-bottom:var(--space-2); color:var(--ink); }
.summary-row { display:flex; gap:var(--space-2); margin-bottom:var(--space-2); }
.summary-card { flex:1; background:var(--surface); border-radius:var(--radius-control); padding:var(--space-2) var(--space-2); text-align:center; box-shadow: var(--shadow-raised); }
.s-num { display:block; font-size:var(--text-card); font-weight: var(--weight-strong); color:var(--ink) }
.s-label { display:block; font-size:var(--text-caption); color:var(--ink-muted); margin-top:calc(var(--stroke) * 2) }
.status-pill {
  display:inline-flex;
  align-items:center;
  min-height:var(--space-3);
  padding:calc(var(--stroke) * 2) var(--space-1);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  line-height:1;
}
.status-pill.is-guided {
  color:var(--text-primary);
  background:var(--bg-paper-2);
}
.status-pill.is-pending {
  color:var(--text-secondary);
  background:var(--surface-muted);
  border-style: dashed;
}
.admin-skill-dot {
  width:var(--space-1);
  height:var(--space-1);
  border-radius:var(--radius-control);
  display:inline-block;
  margin-right:calc(var(--space-1) / 2);
  border:var(--stroke) solid var(--line);
}
.admin-skill-dot.level-high,
.concept-bar.level-high {
  background:var(--text-primary);
}
.admin-skill-dot.level-mid,
.concept-bar.level-mid {
  background:var(--warning);
}
.admin-skill-dot.level-low,
.concept-bar.level-low {
  background:var(--line-strong);
}
.mini-empty { color:var(--ink-muted); text-align:center; padding:var(--space-1); }
.mastery-value {
  margin-left:var(--space-1);
  color:var(--text-primary);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}
.skill-row { display:flex; align-items:center; gap:var(--space-1); margin-bottom:calc(var(--space-1) / 2) }
.skill-label { width:var(--space-10); font-size:var(--text-caption); text-align:right }
.skill-score { font-size:var(--text-caption); font-weight: var(--weight-strong); width:var(--space-4) }
.admin-concept-row { display:flex; align-items:center; gap:var(--space-1); margin-bottom:calc(var(--space-1) / 2) }
.concept-name { width:var(--row-label-width); font-size:var(--text-caption); text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.concept-bar-bg { flex:1; height:var(--space-1); background:var(--surface-muted); border-radius:var(--radius-control); overflow:hidden }
.concept-bar { height:100%; border-radius:var(--radius-control); transition:width var(--motion-normal) }
.concept-val { width:var(--space-4); font-size:var(--text-caption); font-weight: var(--weight-strong); text-align:right }

@media (max-width: 1120px) {
  .dashboard-grid {
    grid-template-columns:minmax(0, 1fr) minmax(var(--panel-width), 0.9fr);
    grid-template-areas:
      "recommend insights"
      "review teaching"
      "articles progress";
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    padding-top:var(--space-1);
  }

  .dashboard-header {
    align-items:flex-start;
    margin-bottom:var(--space-1);
  }

  .greeting {
    font-size:var(--text-card);
  }

  .dashboard-grid {
    grid-template-columns:minmax(0, 1fr);
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
    grid-template-columns:1fr;
  }

  .progress-ring-wrap {
    justify-items: center;
  }
}

/* 一期修复：已建立的二期编辑风覆盖层与共享 tokens 冲突，整段移除。 */
/* 学生布局契约：必须由 role === 'student' 显式启用。 */
.student-layout.dashboard-page { padding-block: var(--space-8) var(--space-6); }
.student-layout .container { padding-inline: var(--page-gutter); }
.student-layout .dashboard-header { justify-content: center; margin: 0 auto var(--space-5); max-width: var(--reading-width); text-align: center; }
.student-layout .greeting { font-size: var(--student-hero-size, clamp(var(--text-page), 5vw, calc(var(--text-page) * 1.8))); line-height: var(--leading-tight); letter-spacing: -.025em; margin-bottom: var(--space-3); }
.student-layout .header-left > p { font-size: var(--text-body); color: var(--ink-secondary); }
.student-layout .persona-tags { justify-content: center; gap: var(--space-1); }
.student-layout .dashboard-console { width: min(100%, var(--reading-width)); box-sizing: border-box; margin: 0 auto var(--space-6); padding: var(--space-4); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--student-console-radius, var(--radius-panel)); box-shadow: var(--shadow-raised); }
.student-layout .dashboard-console:focus-within { border-color: var(--action); }
.student-layout .dashboard-console-heading { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
.student-layout .dashboard-console-heading > svg { color: var(--agent-accent); font-size: var(--text-section); }
.student-layout .dashboard-console h2 { margin: 0; font-size: var(--text-card); }
.student-layout .dashboard-console label { display: block; font-weight: var(--weight-medium); }
.student-layout .dashboard-console textarea { width: 100%; box-sizing: border-box; resize: vertical; border: 0; padding: var(--space-2) 0; background: transparent; color: var(--ink); font-size: var(--text-body); line-height: var(--leading-body); min-height: var(--tile-height); }
.student-layout .dashboard-console textarea::placeholder { color: var(--ink-muted); }
.student-layout .dashboard-console-actions { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-2); }
.student-layout .dashboard-console-actions > span { color: var(--ink-secondary); font-size: var(--text-caption); }
.student-layout .dashboard-console-links { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-3); padding-top: var(--space-3); border-top: var(--stroke) solid var(--line); }
.student-layout .dashboard-console-links .text-action { border: 0; background: transparent; color: var(--action); padding: 0; cursor: pointer; }
.student-layout .dashboard-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); grid-template-areas: 'recommend recommend review progress' 'teaching teaching insights insights' 'articles articles articles articles'; gap: var(--space-2); }
.student-layout .dashboard-grid.without-student-progress { grid-template-areas: 'recommend recommend review review' 'teaching teaching insights insights' 'articles articles articles articles' 'progress progress progress progress'; }
.student-layout .card { padding: var(--space-3); border-radius: var(--radius-panel); overflow-wrap: anywhere; }
.student-layout .card-title { font-size: var(--text-card); margin-bottom: var(--space-2); }
.student-layout .review-card-head .card-title { margin-bottom: 0; }
.student-layout .without-student-progress .progress-card { background: transparent; box-shadow: none; border-style: dashed; }
.student-layout .without-student-progress .progress-card .card-title { font-size: var(--text-caption); }
.student-layout .without-student-progress .progress-card .empty-mini { text-align: start; padding: 0; }
.student-layout .rec-title,
.student-layout .insight-text,
.student-layout .review-title,
.student-layout .article-recommend-title { font-size: var(--text-body); }
.student-layout .rec-reason,
.student-layout .insight-desc,
.student-layout .plan-summary,
.student-layout .article-recommend-desc { display: block; -webkit-line-clamp: unset; overflow: visible; }
.student-layout .plan-steps { grid-template-columns: minmax(0, 1fr); gap: var(--space-2); }
.student-layout .plan-step { padding: var(--space-2); border-radius: var(--radius-panel); }
.student-layout .plan-step-head strong { overflow: visible; white-space: normal; overflow-wrap: anywhere; }
.student-layout .plan-step ul { max-height: none; overflow: visible; }
.student-layout .review-title,
.student-layout .review-meta { white-space: normal; overflow: visible; overflow-wrap: anywhere; }
.student-layout .article-recommend-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); }
.student-layout .article-recommend-item { padding: var(--space-2); min-width: 0; }
@supports (background-clip: text) {
  .student-layout .greeting { background: var(--student-hero-gradient, linear-gradient(100deg, var(--agent-accent), var(--action))); background-clip: text; color: transparent; }
}
@media (max-width: 1120px) {
  .student-layout .dashboard-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-areas: 'recommend review' 'teaching insights' 'articles progress'; }
  .student-layout .dashboard-grid.without-student-progress { grid-template-areas: 'recommend review' 'teaching insights' 'articles articles' 'progress progress'; }
  .student-layout .article-recommend-list { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 768px) {
  .student-layout.dashboard-page { padding-top: var(--space-5); }
  .student-layout .dashboard-console { padding: var(--space-3); margin-bottom: var(--space-4); }
  .student-layout .dashboard-grid,
  .student-layout .dashboard-grid.without-student-progress { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'recommend' 'review' 'insights' 'teaching' 'articles' 'progress'; }
  .student-layout .review-item { flex-wrap: wrap; }
  .student-layout .plan-step-head { grid-template-columns: minmax(0, 1fr); }
}
</style>

