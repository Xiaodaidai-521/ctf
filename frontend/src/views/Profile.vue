<template>
  <div class="profile-page">
    <div class="container">
      <div class="profile-container">
        <!-- 左侧边栏 -->
        <div class="profile-sidebar">
          <!-- 用户信息卡片 -->
          <div class="user-card">
            <div class="user-avatar">{{ userStore.userName.charAt(0).toUpperCase() }}</div>
            <div class="user-info">
              <h2 class="user-name">{{ userStore.userName }}</h2>
              <p class="user-id">UID: {{ userStore.userInfo?.id }}</p>
              <div class="user-role" :class="`role-${userStore.userInfo?.role}`">
                {{ userStore.userInfo?.role_display || '用户' }}
              </div>
            </div>
            <div class="user-bio" v-if="userStore.userInfo?.bio">
              {{ userStore.userInfo.bio }}
            </div>
            <div class="user-stats-mini">
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ userStore.userInfo?.score || 0 }}</span>
                <span class="stat-mini-label">积分</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.solved_challenges || 0 }}</span>
                <span class="stat-mini-label">解题</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.total_submissions || 0 }}</span>
                <span class="stat-mini-label">提交</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.success_rate || 0 }}%</span>
                <span class="stat-mini-label">正确率</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.collects || 0 }}</span>
                <span class="stat-mini-label">收藏</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.completion_rate || 0 }}%</span>
                <span class="stat-mini-label">进度</span>
              </div>
            </div>
          </div>

          <!-- 左侧导航菜单 -->
          <div class="sidebar-menu">
            <div
              v-for="menu in menus"
              :key="menu.value"
              class="menu-item"
              :class="{ active: activeTab === menu.value }"
              @click="activeTab = menu.value"
            >
              <span class="menu-icon">{{ menu.icon }}</span>
              <span class="menu-label">{{ menu.label }}</span>
              <span class="menu-count" v-if="menu.count !== undefined">{{ menu.count }}</span>
            </div>
          </div>
        </div>

        <!-- 右侧内容区 -->
        <div class="profile-main">
          <!-- 标题栏 -->
          <div class="content-header">
            <h2 class="content-title">{{ currentMenu?.label }}</h2>
          </div>

          <!-- 收藏列表 -->
          <div v-if="activeTab === 'favorites'" class="tab-content">
            <div v-if="favorites.length > 0" class="list-grid">
              <div
                v-for="item in favorites"
                :key="item.id"
                class="list-card"
              >
                <div class="card-badge" v-if="item.type">{{ item.type }}</div>
                <h3 class="card-title">{{ item.title }}</h3>
                <p class="card-summary">{{ item.summary || item.description }}</p>
                <div class="card-meta">
                  <span class="meta-time">{{ formatTime(item.created_at) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon">⭐</div>
              <p class="empty-text">还没有收藏任何内容</p>
            </div>
          </div>

          <!-- 完成题目 -->
          <div v-if="activeTab === 'solved'" class="tab-content">
            <div class="stats-overview">
              <div class="overview-card">
                <div class="overview-value">{{ stats.solved_challenges || 0 }}</div>
                <div class="overview-label">已解决题目</div>
              </div>
              <div class="overview-card">
                <div class="overview-value">{{ userStore.userInfo?.score || 0 }}</div>
                <div class="overview-label">总积分</div>
              </div>
              <div class="overview-card rank-card">
                <div class="overview-rank" :class="`rank-${userGrade.level}`">
                  {{ userGrade.level }}
                </div>
                <div class="overview-label">{{ userGrade.title }}</div>
              </div>
            </div>

            <div v-if="solvedChallenges.length > 0" class="challenges-grid">
              <div
                v-for="challenge in solvedChallenges"
                :key="challenge.id"
                class="challenge-card"
                @click="handleChallengeClick(challenge)"
              >
                <div class="challenge-card-header">
                  <div class="challenge-status-badge">
                    <span class="status-icon">✓</span>
                    <span class="status-text">已解决</span>
                  </div>
                  <span class="challenge-score">{{ challenge.score }} 分</span>
                </div>
                <h3 class="challenge-card-title">{{ challenge.title }}</h3>
                <p class="challenge-card-desc">{{ challenge.description || '暂无描述' }}</p>
                <div class="challenge-card-footer">
                  <span class="card-tag">{{ challenge.category_name }}</span>
                  <span class="card-difficulty" :class="`diff-${challenge.difficulty}`">
                    {{ challenge.difficulty_display }}
                  </span>
                  <span class="card-time">{{ formatTime(challenge.solved_at) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon">🎯</div>
              <p class="empty-text">还没有解决任何题目，开始挑战吧！</p>
            </div>

            <!-- 最近提交记录 -->
            <div v-if="stats.recent_submissions?.length" class="recent-subs-section" style="margin-top:24px">
              <h3 class="section-subtitle">最近提交</h3>
              <div class="recent-subs-list">
                <div v-for="(s,i) in stats.recent_submissions" :key="i" class="recent-sub-item">
                  <span :class="s.is_correct ? 'sub-badge-correct' : 'sub-badge-wrong'">{{ s.is_correct ? '✓' : '✗' }}</span>
                  <span class="sub-name">{{ s.challenge }}</span>
                  <span class="sub-time">{{ formatTime(s.submitted_at) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 学习进度 -->
          <div v-if="activeTab === 'progress'" class="tab-content">
            <div v-if="learningPaths.length > 0" class="paths-list">
              <div
                v-for="path in learningPaths"
                :key="path.id"
                class="path-item"
              >
                <div class="path-header">
                  <h3 class="path-title">{{ path.title }}</h3>
                  <div class="path-progress">
                    <div class="progress-bar">
                      <div
                        class="progress-fill"
                        :style="{ width: `${path.progress}%` }"
                      ></div>
                    </div>
                    <span class="progress-text">{{ path.progress }}%</span>
                  </div>
                </div>
                <div class="path-meta">
                  <span class="meta-modules">模块: {{ path.completed_modules }}/{{ path.total_modules }}</span>
                  <span class="meta-experiments">实验: {{ path.completed_experiments }}/{{ path.total_experiments }}</span>
                </div>
                <div v-if="path.progress < 100" class="path-actions">
                  <button class="btn btn-primary btn-sm" @click="handleTrackPath(path)">
                    继续学习
                  </button>
                </div>
                <div v-else class="path-actions">
                  <span class="completed-badge">✓ 已完成</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon">📚</div>
              <p class="empty-text">还没有加入学习路径</p>
              <button class="btn btn-link" @click="router.push('/learning-paths')">
                查看学习路径 →
              </button>
            </div>
          </div>

          <!-- 提交记录 -->
          <div v-if="activeTab === 'submissions'" class="tab-content">
            <div v-if="submissions.length > 0" class="submissions-list">
              <div
                v-for="submission in submissions"
                :key="submission.id"
                class="submission-item"
                :class="{ correct: submission.is_correct }"
              >
                <div class="submission-icon">
                  {{ submission.is_correct ? '✓' : '✗' }}
                </div>
                <div class="submission-content">
                  <div class="submission-title">{{ submission.challenge_title }}</div>
                  <div class="submission-meta">
                    <span class="meta-tag">{{ submission.category_name }}</span>
                    <span class="meta-time">{{ formatTime(submission.created_at) }}</span>
                  </div>
                  <div v-if="submission.is_correct" class="submission-flag">{{ submission.flag }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon">📭</div>
              <p class="empty-text">暂无提交记录</p>
            </div>
          </div>

          <!-- 学习画像 -->
          <div v-if="activeTab === 'persona'" class="tab-content">
            <a-spin :loading="personaLoading">
              <div v-if="personaData" class="persona-section">
                <section class="persona-hero-card">
                  <div class="persona-hero-main">
                    <div class="persona-kicker">AI 学习画像</div>
                    <h3 class="persona-title">{{ personaLabelText(personaData.persona_label) || '画像生成中' }}</h3>
                    <p class="persona-summary">{{ personaSummary }}</p>
                  </div>
                  <div class="persona-hero-side">
                    <div class="confidence-ring" :style="{ '--confidence': confidencePercent }">
                      <strong>{{ confidencePercent }}%</strong>
                      <span>画像置信度</span>
                    </div>
                    <span class="persona-status">{{ personaStatusText }}</span>
                  </div>
                </section>

                <div class="persona-grid">
                  <section class="persona-card">
                    <div class="persona-card-head">
                      <h3 class="persona-card-title">优势方向</h3>
                      <span>可迁移到实战解题</span>
                    </div>
                    <div class="direction-list">
                      <div v-for="item in strengthItems" :key="item.key || item.label" class="direction-row">
                        <div class="direction-row-main">
                          <strong>{{ item.label }}</strong>
                          <span>{{ item.reason || '当前掌握相对稳定' }}</span>
                        </div>
                        <div class="level-bar">
                          <i :style="{ width: `${skillPercent(item.level)}%` }"></i>
                        </div>
                        <em>{{ item.level || 0 }}/5</em>
                      </div>
                      <div v-if="!strengthItems.length" class="quiet-empty">暂无明显优势，先完成自评或更多练习。</div>
                    </div>
                  </section>

                  <section class="persona-card">
                    <div class="persona-card-head">
                      <h3 class="persona-card-title">优先补强</h3>
                      <span>下一轮学习重点</span>
                    </div>
                    <div class="direction-list">
                      <div v-for="item in weaknessItems" :key="item.key || item.label" class="direction-row weak">
                        <div class="direction-row-main">
                          <strong>{{ item.label }}</strong>
                          <span>{{ item.reason || '建议先补概念和基础题型' }}</span>
                        </div>
                        <div class="level-bar">
                          <i :style="{ width: `${skillPercent(item.level)}%` }"></i>
                        </div>
                        <em>{{ item.level || 0 }}/5</em>
                      </div>
                      <div v-if="!weaknessItems.length" class="quiet-empty">暂未发现明显短板。</div>
                    </div>
                  </section>
                </div>

                <section class="persona-card">
                  <div class="persona-card-head">
                    <h3 class="persona-card-title">AI 调整建议</h3>
                    <span>{{ scoreBasis }}</span>
                  </div>
                  <div class="advice-layout">
                    <div class="advice-block">
                      <h4>学习节奏</h4>
                      <p>{{ paceAdvice }}</p>
                    </div>
                    <div class="advice-block">
                      <h4>下一步动作</h4>
                      <ul>
                        <li v-for="item in nextActions" :key="item">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="advice-block">
                      <h4>注意事项</h4>
                      <ul>
                        <li v-for="item in riskAlerts" :key="item">{{ item }}</li>
                      </ul>
                    </div>
                  </div>
                </section>

                <section class="persona-card">
                  <div class="persona-card-head">
                    <h3 class="persona-card-title">推荐智能体</h3>
                    <span>按当前画像匹配</span>
                  </div>
                  <div class="agent-chip-row">
                    <span v-for="a in personaData.recommended_agent_roster" :key="a" class="agent-chip">{{ agentNameText(a) }}</span>
                  </div>
                </section>

                <section v-if="studentProfile" class="persona-card">
                  <div class="persona-card-head">
                    <h3 class="persona-card-title">数据依据</h3>
                    <span>无变化时不会重复调用模型</span>
                  </div>
                  <div class="evidence-grid">
                    <div class="evidence-item">
                      <span>能力自评</span>
                      <div class="rating-summary">
                        <span v-for="(v, k) in studentProfile.self_assessed_skills" :key="k" class="rating-chip">
                          {{ dirLabel(k) }} {{ v }}★
                        </span>
                      </div>
                    </div>
                    <div class="evidence-item" v-if="studentProfile.preference">
                      <span>学习偏好</span>
                      <strong>{{ paceText(studentProfile.preference.preferred_pace) }} / {{ studentProfile.preference.daily_study_hours }} 小时/天</strong>
                    </div>
                    <div class="evidence-item" v-if="studentProfile.learning_goals">
                      <span>学习目标</span>
                      <strong>{{ studentProfile.learning_goals }}</strong>
                    </div>
                  </div>
                </section>
              </div>
              <div v-else class="empty-state">
                <div class="empty-icon">🧠</div>
                <p class="empty-text">尚未设置学习画像</p>
                <a-button type="primary" @click="router.push('/profile/setup')">去设置</a-button>
              </div>
            </a-spin>
          </div>

          <!-- 个人资料 -->
          <div v-if="activeTab === 'profile'" class="tab-content">
            <div class="edit-form">
              <div class="form-group">
                <label class="form-label">用户名</label>
                <input
                  v-model="editForm.username"
                  type="text"
                  class="input"
                  disabled
                />
                <small class="form-hint">用户名不可修改</small>
              </div>

              <div class="form-group">
                <label class="form-label">昵称</label>
                <input
                  v-model="editForm.nickname"
                  type="text"
                  class="input"
                  placeholder="请输入昵称"
                />
              </div>

              <div class="form-group">
                <label class="form-label">邮箱</label>
                <input
                  v-model="editForm.email"
                  type="email"
                  class="input"
                  placeholder="请输入邮箱"
                />
              </div>

              <div class="form-group">
                <label class="form-label">战队</label>
                <input
                  v-model="editForm.team"
                  type="text"
                  class="input"
                  placeholder="请输入战队名称"
                />
              </div>

              <div class="form-group">
                <label class="form-label">班级</label>
                <input
                  v-model="editForm.class_name"
                  type="text"
                  class="input"
                  placeholder="请输入班级"
                />
              </div>

              <div class="form-group">
                <label class="form-label">学号</label>
                <input
                  v-model="editForm.student_id"
                  type="text"
                  class="input"
                  placeholder="请输入学号"
                />
              </div>

              <div class="form-group">
                <label class="form-label">个人简介</label>
                <textarea
                  v-model="editForm.bio"
                  class="input textarea"
                  rows="4"
                  placeholder="请输入个人简介"
                ></textarea>
              </div>

              <button
                class="btn btn-primary"
                @click="handleSave"
                :disabled="saving"
              >
                {{ saving ? '保存中...' : '保存修改' }}
              </button>
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

const router = useRouter()
const userStore = useUserStore()

const activeTab = ref('solved')
const submissions = ref([])
const favorites = ref([])
const solvedChallenges = ref([])
const learningPaths = ref([])
const stats = ref({})
const saving = ref(false)
const personaData = ref(null)
const studentProfile = ref(null)
const personaLoading = ref(false)

const personaLabelMap = {
  code_first: '实践派学员',
  theory_driven: '理论型学员',
  visual_learner: '视觉型学员',
  hands_on: '动手型学员',
  practice_builder: '实战拆解型学习者',
  foundation_rebuilder: '基础巩固型学习者',
  balanced_planner: '均衡规划型学习者',
  challenge_sprinter: '题目冲刺型学习者',
  research_mapper: '研究探索型学习者'
}
const agentNameMap = {
  tutor: '学习导师',
  curriculum: '课程设计师',
  content_gen: '内容创作者',
  code_mentor: '代码导师',
  assessor: '评估专家',
  analyst: '学习分析师'
}
const styleLabelMap = {
  hands_on: '动手实践型',
  theory_first: '理论先行型',
  visual: '视觉学习型',
  balanced: '均衡发展型'
}
const personaLabelText = (v) => personaLabelMap[v] || v
const agentNameText = (v) => agentNameMap[v] || v
const dirLabelMap = {
  web: 'Web安全',
  crypto: '密码学',
  pwn: '二进制安全',
  reverse: '逆向工程',
  forensics: '数字取证',
  misc: '综合杂项'
}
const paceLabelMap = {
  self_paced: '自主学习',
  scheduled: '计划学习',
  intensive: '强化学习'
}
const dirLabel = (key) => dirLabelMap[key] || key
const paceText = (value) => paceLabelMap[value] || value || '未设置'
const personaTraits = computed(() => personaData.value?.persona_traits || {})
const personaSummary = computed(() => (
  personaTraits.value.summary || '完成自评后，系统会结合评分表生成你的学习画像。'
))
const strengthItems = computed(() => personaTraits.value.strengths || [])
const weaknessItems = computed(() => personaTraits.value.weaknesses || [])
const paceAdvice = computed(() => personaTraits.value.pace_advice || '保持稳定练习节奏，每轮学习后复盘卡点。')
const nextActions = computed(() => personaTraits.value.next_actions || [])
const riskAlerts = computed(() => personaTraits.value.risk_alerts || [])
const scoreBasis = computed(() => personaTraits.value.score_basis || '基于当前自评表生成')
const confidencePercent = computed(() => Math.round((personaData.value?.confidence_score || 0) * 100))
const personaStatusText = computed(() => {
  const status = personaData.value?.generation_status
  if (personaData.value?.from_cache || status === 'cached') return '画像已同步'
  if (status === 'generated') return '首次生成完成'
  if (status === 'regenerated') return '评分变化后已更新'
  if (status === 'fallback') return '已用本地规则兜底'
  return '画像已生成'
})
const skillPercent = (level) => Math.max(0, Math.min(Number(level) || 0, 5)) * 20

const isAdminUser = computed(() => userStore.userInfo?.role === 'admin')

const baseMenus = [
  { label: '收藏', value: 'favorites', icon: '⭐', count: computed(() => favorites.length) },
  { label: '完成题目', value: 'solved', icon: '✓', count: computed(() => solvedChallenges.length) },
  { label: '学习进度', value: 'progress', icon: '📚', count: computed(() => learningPaths.length) },
  { label: '提交记录', value: 'submissions', icon: '📝', count: computed(() => submissions.length) },
  { label: '个人资料', value: 'profile', icon: '👤' },
  { label: '学习画像', value: 'persona', icon: '🧠' }
]

const menus = computed(() => (
  isAdminUser.value
    ? baseMenus.filter((menu) => menu.value !== 'persona')
    : baseMenus
))

const currentMenu = computed(() => menus.value.find(m => m.value === activeTab.value))

// 用户评级计算
const userGrade = computed(() => {
  const score = userStore.userInfo?.score || 0
  const solvedCount = stats.value.solved_challenges || 0

  // 评级系统
  if (score >= 5000 && solvedCount >= 20) {
    return { level: 'SSS', title: '顶尖玩家' }
  } else if (score >= 3000 && solvedCount >= 15) {
    return { level: 'SS', title: '高手' }
  } else if (score >= 2000 && solvedCount >= 10) {
    return { level: 'S', title: '专家' }
  } else if (score >= 1000 && solvedCount >= 5) {
    return { level: 'A', title: '高级' }
  } else if (score >= 500 && solvedCount >= 3) {
    return { level: 'B', title: '中级' }
  } else if (solvedCount > 0) {
    return { level: 'C', title: '初级' }
  } else {
    return { level: '-', title: '未评级' }
  }
})

const editForm = ref({
  username: '',
  nickname: '',
  email: '',
  team: '',
  class_name: '',
  student_id: '',
  bio: ''
})

const fetchSubmissions = async () => {
  try {
    submissions.value = await api.submission.mySubmissions()
  } catch (error) {
    console.error('获取提交记录失败:', error)
  }
}

const fetchFavorites = async () => {
  try {
    // 获取收藏的文章
    const response = await api.article.myFavorites()
    // 处理响应数据，确保是数组
    const articles = Array.isArray(response) ? response : (response.results || [])
    favorites.value = articles.map(item => ({
      id: item.id,
      type: '文章',
      title: item.title,
      summary: item.summary,
      created_at: item.created_at
    }))
  } catch (error) {
    console.error('获取收藏失败:', error)
    favorites.value = []
  }
}

const fetchSolvedChallenges = async () => {
  try {
    const response = await api.challenge.mySolved()
    // 处理响应数据，确保是数组
    const challenges = Array.isArray(response) ? response : (response.results || [])
    solvedChallenges.value = challenges
  } catch (error) {
    console.error('获取已解决题目失败:', error)
    solvedChallenges.value = []
  }
}

const fetchLearningPaths = async () => {
  try {
    // 修复 API 调用路径：learningPaths (复数) 而不是 learningPath (单数)
    const paths = await api.learningPaths.my()
    // 处理响应数据，确保是数组
    const pathsArray = Array.isArray(paths) ? paths : (paths.results || [])
    learningPaths.value = pathsArray.map(path => ({
      id: path.id,
      title: path.path_title,
      progress: path.progress_percentage || 0,
      completed_modules: path.completed_modules || 0,
      total_modules: path.total_modules || 0,
      completed_experiments: path.completed_labs || 0,
      total_experiments: path.total_labs || 0
    }))
  } catch (error) {
    console.error('获取学习进度失败:', error)
    learningPaths.value = []
  }
}

const fetchPersona = async () => {
  personaLoading.value = true
  try {
    const [profile, persona] = await Promise.all([
      api.studentProfile.get(),
      api.studentProfile.persona()
    ])
    studentProfile.value = profile
    personaData.value = persona
  } catch {
    personaData.value = null
  } finally {
    personaLoading.value = false
  }
}

const fetchStats = async () => {
  try {
    stats.value = await api.submission.stats()
  } catch (error) {
    console.error('获取统计信息失败:', error)
  }
}

const initEditForm = () => {
  editForm.value = {
    username: userStore.userInfo?.username || '',
    nickname: userStore.userInfo?.nickname || '',
    email: userStore.userInfo?.email || '',
    team: userStore.userInfo?.team || '',
    class_name: userStore.userInfo?.class_name || '',
    student_id: userStore.userInfo?.student_id || '',
    bio: userStore.userInfo?.bio || ''
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const result = await userStore.updateProfile(editForm.value)
    if (result.success) {
      await userStore.fetchProfile()
      alert('保存成功')
    }
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

const formatTime = (time) => {
  if (!time) return ''
  const date = new Date(time)
  const now = new Date()
  const diff = now - date

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString()
}

const handleTrackPath = (path) => {
  // 跳转到学习路径详情页
  router.push(`/learning-paths/${path.id}`)
}

const handleChallengeClick = (challenge) => {
  // 跳转到题目详情页
  router.push(`/challenges/${challenge.id}`)
}

onMounted(async () => {
  await Promise.all([
    userStore.fetchProfile(),
    fetchSubmissions(),
    fetchFavorites(),
    fetchSolvedChallenges(),
    fetchLearningPaths(),
    fetchStats(),
    fetchPersona()
  ])
  initEditForm()
})
</script>

<style scoped>
.profile-page {
  padding: 12px 0 24px;
  min-height: calc(100vh - 60px);
  background: #f6f7f8;
}

.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 16px;
}

.profile-container {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 16px;
  align-items: start;
}

/* 左侧边栏 */
.profile-sidebar {
  position: sticky;
  top: 80px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.user-card {
  background: white;
  border-radius: 6px;
  padding: 20px;
  text-align: center;
}

.user-avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 24px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}

.user-info {
  margin-bottom: 12px;
}

.user-name {
  font-size: 18px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 4px;
}

.user-id {
  font-size: 12px;
  color: #9499a0;
  margin-bottom: 6px;
}

.user-role {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.role-admin {
  background: #fff4e5;
  color: #ff9500;
}

.role-teacher {
  background: #e6f7ff;
  color: #1890ff;
}

.role-student {
  background: #f6ffed;
  color: #52c41a;
}

.user-bio {
  font-size: 12px;
  color: #61666d;
  line-height: 1.5;
  margin-bottom: 12px;
  padding: 0 4px;
}

.user-stats-mini {
  display: flex;
  justify-content: space-around;
  padding-top: 12px;
  border-top: 1px solid #f1f2f3;
}

.stat-mini-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-mini-value {
  font-size: 16px;
  font-weight: 600;
  color: #1f1f1f;
}

.stat-mini-label {
  font-size: 11px;
  color: #9499a0;
}

/* 左侧菜单 */
.sidebar-menu {
  background: white;
  border-radius: 6px;
  overflow: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: all 0.3s;
  border-left: 3px solid transparent;
}

.menu-item:hover {
  background: #f6f7f8;
}

.menu-item.active {
  background: #f6f7f8;
  border-left-color: #fb7299;
  color: #fb7299;
}

.menu-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.menu-label {
  flex: 1;
  font-size: 13px;
  color: #1f1f1f;
}

.menu-count {
  font-size: 11px;
  color: #9499a0;
  background: #f1f2f3;
  padding: 2px 6px;
  border-radius: 8px;
}

/* 右侧内容区 */
.profile-main {
  background: white;
  border-radius: 6px;
  min-height: 400px;
}

.content-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f1f2f3;
}

.content-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f1f1f;
}

.tab-content {
  padding: 20px;
}

/* 统计概览 */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.overview-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
  border-radius: 6px;
  text-align: center;
}

.overview-value {
  font-size: 28px;
  font-weight: 700;
  color: white;
  margin-bottom: 6px;
}

.overview-label {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
}

/* 评级卡片 */
.rank-card {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.overview-rank {
  font-size: 36px;
  font-weight: 800;
  color: white;
  margin-bottom: 6px;
  letter-spacing: 2px;
}

.overview-rank.rank-SSS {
  color: #ffd700;
  text-shadow: 0 0 20px rgba(255, 215, 0, 0.5);
}

.overview-rank.rank-SS {
  color: #c0c0c0;
  text-shadow: 0 0 15px rgba(192, 192, 192, 0.5);
}

.overview-rank.rank-S {
  color: #cd7f32;
  text-shadow: 0 0 15px rgba(205, 127, 50, 0.5);
}

.overview-rank.rank-A {
  color: #52c41a;
}

.overview-rank.rank-B {
  color: #1890ff;
}

.overview-rank.rank-C {
  color: #fa8c16;
}

/* 列表卡片 */
.list-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.list-card {
  padding: 14px;
  border: 1px solid #e3e5e7;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s;
}

.list-card:hover {
  border-color: #fb7299;
  box-shadow: 0 4px 12px rgba(251, 114, 153, 0.1);
}

.card-badge {
  display: inline-block;
  padding: 3px 6px;
  background: #f6f7f8;
  color: #61666d;
  border-radius: 4px;
  font-size: 11px;
  margin-bottom: 10px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 6px;
  line-height: 1.4;
}

.card-summary {
  font-size: 12px;
  color: #61666d;
  line-height: 1.5;
  margin-bottom: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-meta {
  font-size: 11px;
  color: #9499a0;
}

/* 题目卡片 */
.challenges-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.challenge-card {
  padding: 16px;
  border: 1px solid #e3e5e7;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: white;
}

.challenge-card:hover {
  border-color: #fb7299;
  box-shadow: 0 4px 16px rgba(251, 114, 153, 0.12);
  transform: translateY(-2px);
}

.challenge-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.challenge-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f6ffed;
  border-radius: 12px;
  font-size: 12px;
}

.status-icon {
  color: #52c41a;
  font-size: 14px;
}

.status-text {
  color: #52c41a;
  font-weight: 500;
}

.challenge-score {
  font-size: 16px;
  font-weight: 600;
  color: #fa8c16;
}

.challenge-card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 8px;
  line-height: 1.4;
}

.challenge-card-desc {
  font-size: 12px;
  color: #61666d;
  line-height: 1.5;
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: 36px;
}

.challenge-card-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding-top: 12px;
  border-top: 1px solid #f1f2f3;
}

.card-tag {
  padding: 3px 8px;
  background: #e6f7ff;
  color: #1890ff;
  border-radius: 4px;
  font-size: 11px;
}

.card-difficulty {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.card-time {
  margin-left: auto;
  color: #9499a0;
  font-size: 11px;
}

.diff-easy {
  background: #f6ffed;
  color: #52c41a;
}

.diff-medium {
  background: #fff7e6;
  color: #fa8c16;
}

.diff-hard {
  background: #fff1f0;
  color: #f5222d;
}

.diff-expert {
  background: #f9f0ff;
  color: #722ed1;
}

/* 学习路径 */
.paths-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.path-item {
  padding: 16px;
  border: 1px solid #e3e5e7;
  border-radius: 6px;
}

.path-header {
  margin-bottom: 10px;
}

.path-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 10px;
}

.path-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #f1f2f3;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
  transition: width 0.3s;
}

.progress-text {
  font-size: 13px;
  font-weight: 600;
  color: #667eea;
  min-width: 36px;
  text-align: right;
}

.path-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #61666d;
}

.path-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f1f2f3;
}

.completed-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  background: #f6ffed;
  color: #52c41a;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.btn-sm {
  padding: 6px 16px;
  font-size: 12px;
}

/* 提交记录 */
.submissions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.submission-item {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: #f6f7f8;
  border-radius: 6px;
  border-left: 4px solid #f5222d;
  transition: all 0.3s;
}

.submission-item.correct {
  background: #f6ffed;
  border-left-color: #52c41a;
}

.submission-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}

.submission-item.correct .submission-icon {
  background: #52c41a;
  color: white;
}

.submission-item:not(.correct) .submission-icon {
  background: #f5222d;
  color: white;
}

.submission-content {
  flex: 1;
}

.submission-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 6px;
}

.submission-meta {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}

.submission-flag {
  font-family: monospace;
  font-size: 12px;
  color: #61666d;
  background: white;
  padding: 6px 10px;
  border-radius: 4px;
  word-break: break-all;
}

/* 学习画像 */
.persona-section {
  display: grid;
  gap: 14px;
}

.persona-hero-card,
.persona-card {
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fbfcff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.persona-hero-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 18px;
  align-items: center;
  padding: 18px 20px;
}

.persona-kicker {
  color: #165dff;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 6px;
}

.persona-title {
  margin: 0 0 8px;
  color: #1f2937;
  font-size: 20px;
  font-weight: 700;
}

.persona-summary {
  max-width: 70ch;
  margin: 0;
  color: #4b5563;
  font-size: 13px;
  line-height: 1.65;
}

.persona-hero-side {
  display: grid;
  justify-items: center;
  gap: 8px;
}

.confidence-ring {
  width: 96px;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 4px;
  border-radius: 50%;
  background: radial-gradient(circle at center, #fbfcff 56%, transparent 57%),
    conic-gradient(#165dff calc(var(--confidence, 0) * 1%), #e8eef8 0);
  box-shadow: inset 0 0 0 1px #e8eef8;
}

.confidence-ring strong {
  color: #165dff;
  font-size: 22px;
  line-height: 1;
}

.confidence-ring span,
.persona-status {
  color: #6b7280;
  font-size: 12px;
}

.persona-status {
  padding: 4px 8px;
  border-radius: 4px;
  background: #edf5ff;
  color: #165dff;
  font-weight: 600;
}

.persona-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.persona-card {
  padding: 14px;
}

.persona-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.persona-card-title {
  margin: 0;
  color: #1f2937;
  font-size: 14px;
  font-weight: 700;
}

.persona-card-head span {
  color: #8a94a6;
  font-size: 12px;
}

.direction-list {
  display: grid;
  gap: 10px;
}

.direction-row {
  display: grid;
  grid-template-columns: 1fr 92px 38px;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border-radius: 6px;
  background: #f5f8fd;
}

.direction-row-main {
  min-width: 0;
}

.direction-row-main strong {
  display: block;
  color: #1f2937;
  font-size: 13px;
  margin-bottom: 4px;
}

.direction-row-main span {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.5;
}

.level-bar {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #e5edf8;
}

.level-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #165dff;
}

.direction-row.weak .level-bar i {
  background: #f59e0b;
}

.direction-row em {
  color: #475569;
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
  text-align: right;
}

.quiet-empty {
  padding: 12px;
  color: #8a94a6;
  font-size: 12px;
  text-align: center;
}

.advice-layout {
  display: grid;
  grid-template-columns: 1fr 1.1fr 1.1fr;
  gap: 12px;
}

.advice-block {
  min-width: 0;
  padding: 12px;
  border-radius: 6px;
  background: #f5f8fd;
}

.advice-block h4 {
  margin: 0 0 8px;
  color: #1f2937;
  font-size: 13px;
}

.advice-block p,
.advice-block li {
  color: #4b5563;
  font-size: 12px;
  line-height: 1.6;
}

.advice-block p {
  margin: 0;
}

.advice-block ul {
  margin: 0;
  padding-left: 16px;
}

.agent-chip-row,
.rating-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-chip,
.rating-chip {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.agent-chip {
  color: #166534;
  background: #dcfce7;
}

.rating-chip {
  color: #1d4ed8;
  background: #eaf2ff;
}

.evidence-grid {
  display: grid;
  gap: 10px;
}

.evidence-item {
  display: grid;
  grid-template-columns: 86px 1fr;
  gap: 10px;
  align-items: start;
}

.evidence-item > span {
  color: #8a94a6;
  font-size: 12px;
  font-weight: 600;
}

.evidence-item strong {
  color: #374151;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #9499a0;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-text {
  font-size: 13px;
  margin-bottom: 12px;
}

.btn-link {
  color: #fb7299;
  background: none;
  border: none;
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}

.btn-link:hover {
  text-decoration: underline;
}

/* 编辑表单 */
.edit-form {
  max-width: 500px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #1f1f1f;
}

.input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #e3e5e7;
  border-radius: 4px;
  font-size: 13px;
  transition: all 0.3s;
}

.input:focus {
  outline: none;
  border-color: #fb7299;
  box-shadow: 0 0 0 2px rgba(251, 114, 153, 0.1);
}

.input:disabled {
  background: #f6f7f8;
  cursor: not-allowed;
}

.textarea {
  resize: vertical;
  min-height: 80px;
}

.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #9499a0;
}

.btn {
  padding: 8px 20px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background: #fb7299;
  color: white;
}

.btn-primary:hover {
  background: #e85a8a;
}

.btn-primary:disabled {
  background: #f5f5f5;
  color: #c9ccd0;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .profile-container {
    grid-template-columns: 1fr;
  }

  .profile-sidebar {
    position: static;
  }

  .stats-overview {
    grid-template-columns: 1fr;
  }

  .persona-hero-card,
  .persona-grid,
  .advice-layout {
    grid-template-columns: 1fr;
  }

  .persona-hero-side {
    justify-items: start;
  }

  .direction-row {
    grid-template-columns: 1fr;
  }

  .direction-row em {
    text-align: left;
  }

  .evidence-item {
    grid-template-columns: 1fr;
  }

  .list-grid {
    grid-template-columns: 1fr;
  }
}
</style>
