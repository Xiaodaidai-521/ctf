import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'
import TeacherLayout from '@/teacher/TeacherLayout.vue'
import TeacherDashboard from '@/teacher/TeacherDashboard.vue'
import LearningEffectAnalysis from '@/teacher/LearningEffectAnalysis.vue'
import { guardDestination, pageTitle } from '@/shared/navigation/access.js'
import { teachingDestination, feedbackCandidateDestination } from '@/shared/navigation/phase3.js'
import { shadowDestination } from '@/learning/shadowRoutes.js'
const enterTeaching = to => {
  const user = useUserStore()
  const role = user.isAuthenticated ? user.userInfo?.role : 'guest'
  if (role === 'admin' && to.path.replace(/\/+$/, '') === '/teaching-knowledge') return { path: '/admin/legal/kb/materials', query: to.query, hash: to.hash }
  const destination = teachingDestination(to.path, to.query, role)
  return destination ? { ...destination, hash: to.hash } : true
}
const enterShadow = to => shadowDestination(to, useUserStore().userInfo?.role) || true

const routes = [
  {
    path: '/guide',
    name: 'Guide',
    component: () => import('@/learning/guide/GuideView.vue'),
    meta: { title: '智航', requiresAuth: true }
  },
  {
    path: '/access-denied',
    name: 'AccessDenied',
    component: () => import('@/shared/layout/AccessDenied.vue'),
    meta: { title: '暂无访问权限' }
  },
  {
    path: '/knowledge',
    name: 'KnowledgeLibrary',
    component: () => import('@/learningKnowledge/KnowledgeLibrary.vue'),
    meta: { title: '知识资料库', requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/teaching-knowledge',
    name: 'TeachingKnowledge',
    component: () => import('@/learningKnowledge/TeachingKnowledge.vue'),
    meta: { title: '材料工坊', requiresAuth: true, requiresTeacher: true },
    beforeEnter: enterTeaching
  },
  {
    path: '/learning-knowledge/:attemptId',
    name: 'LearningKnowledge',
    component: () => import('@/learningKnowledge/LearningKnowledge.vue'),
    meta: { title: '任务学习证据', requiresAuth: true }
  },
  // 前台路由
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首页' }
  },
  {
    path: '/challenges',
    name: 'Challenges',
    component: () => import('@/views/Challenges.vue'),
    meta: { title: '题目矩阵' }
  },
  {
    path: '/challenge/:id',
    name: 'ChallengeDetail',
    component: () => import('@/views/ChallengeDetail.vue'),
    meta: { title: '题目详情', requiresAuth: true }
  },
  {
    path: '/resources',
    name: 'Resources',
    component: () => import('@/views/Resources.vue'),
    meta: { title: '资源中心' }
  },
  {
    path: '/resources/upload',
    name: 'ResourceUpload',
    component: () => import('@/views/ResourceUpload.vue'),
    meta: { title: '上传资源', requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/community',
    name: 'Community',
    component: () => import('@/views/Community.vue'),
    meta: { title: '社区' }
  },
  {
    path: '/community/article/:id',
    name: 'ArticleDetail',
    component: () => import('@/views/ArticleDetail.vue'),
    meta: { title: '文章详情' }
  },
  {
    path: '/community/write',
    name: 'ArticleEditor',
    component: () => import('@/views/ArticleEditor.vue'),
    meta: { title: '写文章', requiresAuth: true }
  },
  {
    path: '/exam-center',
    name: 'ExamCenter',
    component: () => import('@/views/ExamCenter.vue'),
    meta: { title: '测试中心', requiresAuth: true }
  },
  {
    // 本区记录子视图：完整历史与筛选；记录区保留可分享、可刷新、可返回的 URL。
    path: '/exam-center/history',
    name: 'ExamHistory',
    component: () => import('@/learning/exams/components/ExamRecords.vue'),
    meta: { title: '测评记录', requiresAuth: true }
  },
  {
    // 旧深链保留兼容，查询条件（类型/状态）随跳转保留。
    path: '/exam-history',
    name: 'ExamHistoryLegacy',
    redirect: to => ({ path: '/exam-center/history', query: to.query, hash: to.hash }),
    meta: { title: '测评记录', requiresAuth: true }
  },
  {
    path: '/exam-taking/:id',
    name: 'ExamTaking',
    component: () => import('@/views/ExamTaking.vue'),
    meta: { title: '答题中', requiresAuth: true }
  },
  {
    // 结果属于记录区子视图，不再占用导航位置。
    path: '/exam-center/result/:id',
    name: 'ExamResult',
    component: () => import('@/learning/exams/components/ExamRecordDetail.vue'),
    meta: { title: '测评结果', requiresAuth: true }
  },
  {
    path: '/exam-result/:id',
    name: 'ExamResultLegacy',
    redirect: to => ({ path: `/exam-center/result/${to.params.id}`, query: to.query, hash: to.hash }),
    meta: { title: '测评结果', requiresAuth: true }
  },
  // 多智能体协作（需要登录）
  {
    path: '/multi-agent',
    name: 'MultiAgent',
    component: () => import('@/views/MultiAgent/MultiAgentView.vue'),
    meta: { title: '多智能体协作', requiresAuth: true }
  },
  {
    path: '/multi-agent/:challengeId',
    name: 'MultiAgentChallenge',
    component: () => import('@/views/MultiAgent/MultiAgentView.vue'),
    meta: { title: '智能体解题', requiresAuth: true }
  },
  {
    path: '/learning-paths',
    name: 'LearningPaths',
    component: () => import('@/views/LearningPaths/LearningPathsList.vue'),
    meta: { title: '学习路径', requiresAuth: true }
  },
  {
    path: '/resources/topics/data-security',
    name: 'DataLab',
    component: () => import('@/views/DataLab/DataLab.vue'),
    meta: { title: '智库 · 数据安全案例', requiresAuth: true, sensitive: true }
  },
  {
    path: '/data-lab',
    name: 'DataLabLegacy',
    redirect: enterShadow,
    meta: { title: '智库 · 数据安全案例', requiresAuth: true }
  },
  {
    path: '/data-lab/teacher',
    name: 'DataLabTeacherLegacy',
    component: () => import('@/views/DataLab/DataLabTeacher.vue'),
    beforeEnter: enterShadow,
    meta: { title: '数据安全案例管理', requiresAuth: true, requiresTeacher: true, sensitive: true }
  },
  {
    path: '/admin/data-cases',
    component: () => import('@/admin/components/AdminLayout.vue'),
    meta: { requiresAdmin: true, sensitive: true },
    children: [
      { path: '', name: 'AdminDataCases', component: () => import('@/views/DataLab/DataLabTeacher.vue'), meta: { title: '数据安全案例监督', requiresAdmin: true, sensitive: true } }
    ]
  },
  {
    // 学生旧入口归并到成长总览的“结果与复盘”区；教师/管理员保留原复盘页做教学核对。
    path: '/my-results',
    name: 'MyResults',
    component: () => import('@/views/SkillReview/MyResults.vue'),
    meta: { title: '结果与复盘', requiresAuth: true },
    beforeEnter: to => {
      const role = useUserStore().userInfo?.role
      if (role === 'teacher' || role === 'admin') return true
      return { path: '/dashboard', query: { ...to.query, section: 'results' }, hash: to.hash }
    }
  },
  {
    path: '/capability-map',
    name: 'CapabilityMap',
    component: () => import('@/views/LearningMap/CapabilityMap.vue'),
    meta: { title: '能力地图', requiresAuth: true }
  },
  {
    path: '/capability-map/changelog',
    name: 'CapabilityMapChangeLog',
    redirect: enterShadow,
    meta: { title: '能力图谱 · 学习历史', requiresAuth: true }
  },
  {
    path: '/feedback',
    name: 'FeedbackCenter',
    component: () => import('@/views/Feedback/FeedbackCenter.vue'),
    meta: { title: '反馈中心', requiresAuth: true }
  },
  {
    path: '/feedback/:id',
    name: 'FeedbackDetail',
    component: () => import('@/views/Feedback/FeedbackDetail.vue'),
    meta: { title: '反馈详情', requiresAuth: true }
  },
  {
    path: '/learning-paths/manage',
    name: 'LearningPathsManage',
    component: () => import('@/views/LearningPaths/LearningPathsManageList.vue'),
    meta: { title: '学习航线管理', requiresAuth: true, requiresTeacher: true },
    beforeEnter: enterTeaching
  },
  {
    path: '/learning-paths/new',
    name: 'LearningPathsCreate',
    component: () => import('@/views/LearningPaths/LearningPathsManage.vue'),
    meta: { title: '创建学习航线', requiresAuth: true, requiresTeacher: true },
    beforeEnter: enterTeaching
  },
  {
    path: '/learning-paths/:id',
    name: 'LearningPathDetail',
    component: () => import('@/views/LearningPaths/LearningPathDetail.vue'),
    meta: { title: '学习路径详情', requiresAuth: true }
  },
  {
    path: '/learning-paths/:id/edit',
    name: 'LearningPathsEdit',
    component: () => import('@/views/LearningPaths/LearningPathsManage.vue'),
    meta: { title: '编辑学习航线', requiresAuth: true, requiresTeacher: true },
    beforeEnter: enterTeaching
  },
  {
    path: '/learning-paths/:pathId/modules/:moduleId',
    name: 'ModuleLearning',
    component: () => import('@/views/LearningPaths/ModuleLearning.vue'),
    meta: { title: '模块学习', requiresAuth: true }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/Profile.vue'),
    meta: { title: '个人中心', requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册' }
  },

  {
    path: '/teacher',
    component: TeacherLayout,
    meta: { requiresTeacherOnly: true },
    children: [
      { path: '', name: 'TeacherHome', component: TeacherDashboard, meta: { title: '教师中心', requiresTeacherOnly: true } },
      { path: 'learning-paths', name: 'TeacherLearningPaths', component: () => import('@/teacher/paths/LearningPathsManageList.vue'), meta: { title: '学习航线管理', requiresTeacherOnly: true } },
      { path: 'learning-paths/new', name: 'TeacherLearningPathsCreate', component: () => import('@/teacher/paths/LearningPathsManage.vue'), meta: { title: '创建学习航线', requiresTeacherOnly: true } },
      { path: 'learning-paths/:id/edit', name: 'TeacherLearningPathsEdit', component: () => import('@/teacher/paths/LearningPathsManage.vue'), meta: { title: '编辑学习航线', requiresTeacherOnly: true } },
      { path: 'materials', name: 'TeacherMaterials', component: () => import('@/learningKnowledge/TeachingKnowledge.vue'), meta: { title: '材料工坊', requiresTeacherOnly: true } },
      { path: 'students/:studentId/growth', name: 'TeacherStudentGrowth', component: () => import('@/teacher/TeacherLearningEffect.vue'), meta: { title: '成长图谱 · 教师视角', requiresTeacherOnly: true } },
      { path: 'learning-evidence', name: 'TeacherLearningEvidence', redirect: to => ({ path: '/teacher/learning-effect', query: to.query, hash: '#task-evidence' }), meta: { title: '学情洞察 · 任务核对', requiresTeacherOnly: true } },
      { path: 'teaching-actions', name: 'TeacherTeachingActions', component: () => import('@/teacher/TeacherOperations.vue'), meta: { title: '教学安排', requiresTeacherOnly: true } },
      { path: 'capability-map', name: 'TeacherCapabilityMap', component: () => import('@/teacher/CapabilityMapAdmin.vue'), meta: { title: '能力地图审核', requiresTeacherOnly: true } },
      { path: 'data-cases', name: 'DataLabTeacher', component: () => import('@/views/DataLab/DataLabTeacher.vue'), meta: { title: '数据安全案例管理', requiresTeacherOnly: true, sensitive: true } },
      { path: 'skill-review', name: 'TeacherSkillReview', component: () => import('@/teacher/SkillReviewAdmin.vue'), meta: { title: '验收与抽查', requiresTeacherOnly: true } },
      { path: 'feedback/candidates', name: 'TeacherFeedbackCandidates', redirect: feedbackCandidateDestination, meta: { title: '问题组与候选', requiresTeacherOnly: true } },
      { path: 'feedback', name: 'TeacherFeedbackQueue', component: () => import('@/teacher/FeedbackWorkbench.vue'), meta: { title: '反馈处理', requiresTeacherOnly: true } },
      { path: 'feedback/reconciliation', name: 'TeacherFeedbackReconciliation', component: () => import('@/teacher/FeedbackReconciliation.vue'), meta: { title: '反馈事件核对', requiresTeacherOnly: true } },
      { path: 'feedback/:id', name: 'TeacherFeedbackDetail', component: () => import('@/teacher/FeedbackDetail.vue'), meta: { title: '反馈处理', requiresTeacherOnly: true } },
      { path: 'learning-scores', name: 'TeacherLearningScores', component: () => import('@/teacher/assessment/TeacherAssessment.vue'), meta: { title: '动态评测', requiresTeacherOnly: true } },
      { path: 'learning-effect', name: 'TeacherLearningEffect', component: LearningEffectAnalysis, meta: { title: '学情洞察', requiresTeacherOnly: true } },
      { path: 'challenges', name: 'TeacherChallenges', component: () => import('@/teacher/TeacherChallengePanel.vue'), meta: { title: '题目管理', requiresTeacherOnly: true } },
      { path: 'resources', name: 'TeacherResources', component: () => import('@/teacher/TeacherResourcePanel.vue'), meta: { title: '资源审核', requiresTeacherOnly: true } },
      { path: 'knowledge', name: 'TeacherKnowledgeLibrary', component: () => import('@/learningKnowledge/KnowledgeLibrary.vue'), meta: { title: '知识资料库', requiresTeacherOnly: true } },
    ]
  },

  // 管理员后台路由
  {
    path: '/admin',
    redirect: '/admin/dashboard',
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/dashboard',
    name: 'AdminDashboard',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminDashboardHome',
        component: () => import('@/admin/views/Dashboard.vue'),
        meta: { title: '治理驾驶舱', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/data-security',
    name: 'AdminDataSecurity',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminDataSecurityHome',
        component: () => import('@/admin/views/DataSecurity.vue'),
        meta: { title: '数据保护', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/users',
    name: 'AdminUsers',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminUsersHome',
        component: () => import('@/admin/views/Users.vue'),
        meta: { title: '用户管理', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/challenges',
    name: 'AdminChallenges',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminChallengesHome',
        component: () => import('@/admin/views/Challenges.vue'),
        meta: { title: '题目管理', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/submissions',
    name: 'AdminSubmissions',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminSubmissionsHome',
        component: () => import('@/admin/views/Submissions.vue'),
        meta: { title: '提交记录', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/categories',
    name: 'AdminCategories',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminCategoriesHome',
        component: () => import('@/admin/views/Categories.vue'),
        meta: { title: '分类管理', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/resources',
    name: 'AdminResources',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminResourcesHome',
        component: () => import('@/admin/views/Resources.vue'),
        meta: { title: '资源审核', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/articles',
    name: 'AdminArticles',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminArticlesHome',
        component: () => import('@/admin/views/Articles.vue'),
        meta: { title: '文章审核', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/announcements',
    name: 'AdminAnnouncements',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminAnnouncementsHome',
        component: () => import('@/admin/views/Announcements.vue'),
        meta: { title: '公告管理', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/student-learning',
    name: 'AdminStudentLearning',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminStudentLearningHome',
        component: () => import('@/admin/views/StudentLearning.vue'),
        meta: { title: '全局洞察', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/learning-scores',
    name: 'AdminLearningScores',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLearningScoresHome',
        component: () => import('@/admin/views/LearningScores.vue'),
        meta: { title: '评测监督', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/dashboard',
    name: 'AdminLegalDashboard',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalDashboardHome',
        component: () => import('@/admin/views/legal/ComplianceCenter.vue'),
        meta: { title: '合规中心', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/agent',
    name: 'AdminLegalAgent',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalAgentHome',
        component: () => import('@/admin/views/legal/ComplianceAgentCenter.vue'),
        meta: { title: '数智合规官', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/audit',
    name: 'AdminLegalAudit',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalAuditHome',
        component: () => import('@/admin/views/legal/AuditLogs.vue'),
        meta: { title: '合规审计', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/violations',
    name: 'AdminLegalViolations',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalViolationsHome',
        component: () => import('@/admin/views/legal/ViolationRecords.vue'),
        meta: { title: '违规记录', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/reports',
    name: 'AdminLegalReports',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalReportsHome',
        component: () => import('@/admin/views/legal/ComplianceReports.vue'),
        meta: { title: '合规报告', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/protocols',
    name: 'AdminLegalProtocols',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalProtocolsHome',
        component: () => import('@/admin/views/legal/ProtocolSigning.vue'),
        meta: { title: '协议签署', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/kb',
    name: 'AdminLegalKb',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalKbHome',
        component: () => import('@/admin/foundation/FoundationLibrary.vue'),
        meta: { title: '基座治理', requiresAdmin: true, sensitive: true }
      },
      {
        path: 'tools',
        name: 'AdminLegalKbTools',
        component: () => import('@/admin/foundation/IndexTools.vue'),
        meta: { title: '索引工具', requiresAdmin: true, sensitive: true }
      },
      {
        path: 'health',
        name: 'AdminLegalKbHealth',
        component: () => import('@/admin/foundation/IndexHealth.vue'),
        meta: { title: '索引健康', requiresAdmin: true, sensitive: true }
      },
      {
        path: 'authorization',
        name: 'AdminLegalKbAuthorization',
        component: () => import('@/admin/foundation/AuthorizationSupervision.vue'),
        meta: { title: '授权监督', requiresAdmin: true, sensitive: true }
      },
      {
        path: 'materials',
        name: 'AdminLegalKbMaterials',
        component: () => import('@/learningKnowledge/TeachingKnowledge.vue'),
        meta: { title: '受限材料维护', requiresAdmin: true, sensitive: true }
      }
    ],
    meta: { requiresAdmin: true }
  },
  {
    path: '/admin/legal/exercises',
    name: 'AdminLegalExercises',
    component: () => import('@/admin/components/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'AdminLegalExercisesHome',
        component: () => import('@/admin/views/legal/ComplianceExercises.vue'),
        meta: { title: '合规演练', requiresAdmin: true }
      }
    ],
    meta: { requiresAdmin: true }
  },

  // 智能学习平台路由
  {
    path: '/dashboard',
    name: 'StudentDashboard',
    component: () => import('@/shared/navigation/DashboardEntry.vue'),
    meta: { title: '学习仪表盘', requiresAuth: true }
  },
  {
    path: '/profile/setup',
    name: 'ProfileSetup',
    component: () => import('@/views/ProfileSetup.vue'),
    meta: { title: '画像设置', requiresAuth: true }
  },
  {
    // 学生旧入口归并到成长总览的“学习分析”区；教师/管理员仍可打开原分析页核对教学数据。
    path: '/analytics',
    name: 'LearningAnalytics',
    component: () => import('@/views/LearningAnalytics.vue'),
    meta: { title: '学习分析', requiresAuth: true },
    beforeEnter: to => {
      const role = useUserStore().userInfo?.role
      if (role === 'teacher' || role === 'admin') return true
      return { path: '/dashboard', query: { ...to.query, section: 'activity' }, hash: to.hash }
    }
  },
  {
    path: '/content/:id',
    name: 'GeneratedContent',
    component: () => import('@/views/GeneratedContent.vue'),
    meta: { title: '生成内容', requiresAuth: true }
  },

  // 404
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '404' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 入口与拒绝落点统一；后端仍独立校验每个请求的权限。
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  const title = pageTitle(to, userStore.userInfo?.role)
  document.title = title ? `${title} - 智航` : '智航'
  const destination = guardDestination(to, userStore)
  if (to.name === 'KnowledgeLibrary' && destination && !['/login', '/access-denied'].includes(destination)) {
    next({ path: destination, query: to.query, hash: to.hash })
  } else {
    next(destination)
  }
})

export default router







