import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'
import TeacherLayout from '@/teacher/TeacherLayout.vue'
import TeacherDashboard from '@/teacher/TeacherDashboard.vue'
import LearningEffectAnalysis from '@/teacher/LearningEffectAnalysis.vue'

const routes = [
  {
    path: '/teaching-knowledge',
    name: 'TeachingKnowledge',
    component: () => import('@/learningKnowledge/TeachingKnowledge.vue'),
    meta: { title: '教学材料审阅', requiresAuth: true, requiresTeacher: true }
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
    path: '/exam-history',
    name: 'ExamHistory',
    component: () => import('@/views/ExamHistory.vue'),
    meta: { title: '考试历史', requiresAuth: true }
  },
  {
    path: '/exam-taking/:id',
    name: 'ExamTaking',
    component: () => import('@/views/ExamTaking.vue'),
    meta: { title: '答题中', requiresAuth: true }
  },
  {
    path: '/exam-result/:id',
    name: 'ExamResult',
    component: () => import('@/views/ExamResult.vue'),
    meta: { title: '考试结果', requiresAuth: true }
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
    path: '/my-results',
    name: 'MyResults',
    component: () => import('@/views/SkillReview/MyResults.vue'),
    meta: { title: '结果与复盘', requiresAuth: true }
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
    component: () => import('@/views/LearningMap/ChangeLog.vue'),
    meta: { title: '路径变更记录', requiresAuth: true }
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
    meta: { title: '管理学习路径', requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/learning-paths/new',
    name: 'LearningPathsCreate',
    component: () => import('@/views/LearningPaths/LearningPathsManage.vue'),
    meta: { title: '创建学习路径', requiresAuth: true, requiresTeacher: true }
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
    meta: { title: '编辑学习路径', requiresAuth: true, requiresTeacher: true }
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
      { path: 'learning-paths', name: 'TeacherLearningPaths', component: () => import('@/views/LearningPaths/LearningPathsManageList.vue'), meta: { title: '学习路径', requiresTeacherOnly: true } },
      { path: 'capability-map', name: 'TeacherCapabilityMap', component: () => import('@/teacher/CapabilityMapAdmin.vue'), meta: { title: '能力地图审核', requiresTeacherOnly: true } },
      { path: 'skill-review', name: 'TeacherSkillReview', component: () => import('@/teacher/SkillReviewAdmin.vue'), meta: { title: '验收与抽查', requiresTeacherOnly: true } },
      { path: 'feedback/candidates', name: 'TeacherFeedbackCandidates', component: () => import('@/teacher/FeedbackCandidates.vue'), meta: { title: '问题组与候选', requiresTeacherOnly: true } },
      { path: 'feedback', name: 'TeacherFeedbackQueue', component: () => import('@/teacher/FeedbackQueue.vue'), meta: { title: '反馈待办', requiresTeacherOnly: true } },
      { path: 'feedback/reconciliation', name: 'TeacherFeedbackReconciliation', component: () => import('@/teacher/FeedbackReconciliation.vue'), meta: { title: '反馈事件核对', requiresTeacherOnly: true } },
      { path: 'feedback/:id', name: 'TeacherFeedbackDetail', component: () => import('@/teacher/FeedbackDetail.vue'), meta: { title: '反馈处理', requiresTeacherOnly: true } },
      { path: 'learning-scores', name: 'TeacherLearningScores', component: () => import('@/admin/views/LearningScores.vue'), meta: { title: '学习评分', requiresTeacherOnly: true } },
      { path: 'learning-effect', name: 'TeacherLearningEffect', component: LearningEffectAnalysis, meta: { title: '学习成效', requiresTeacherOnly: true } },
      { path: 'challenges', name: 'TeacherChallenges', component: () => import('@/admin/views/Challenges.vue'), meta: { title: '题目管理', requiresTeacherOnly: true } },
      { path: 'resources', name: 'TeacherResources', component: () => import('@/admin/views/Resources.vue'), meta: { title: '资源审核', requiresTeacherOnly: true } },
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
        meta: { title: '仪表盘', requiresAdmin: true }
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
        meta: { title: '用户学习报表', requiresAdmin: true }
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
        meta: { title: '动态评分管理', requiresAdmin: true }
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
        component: () => import('@/admin/views/legal/KnowledgeBase.vue'),
        meta: { title: '法律知识库', requiresAdmin: true }
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
    component: () => import('@/teacher/DashboardEntry.vue'),
    meta: { title: '学习仪表盘', requiresAuth: true }
  },
  {
    path: '/profile/setup',
    name: 'ProfileSetup',
    component: () => import('@/views/ProfileSetup.vue'),
    meta: { title: '画像设置', requiresAuth: true }
  },
  {
    path: '/analytics',
    name: 'LearningAnalytics',
    component: () => import('@/views/LearningAnalytics.vue'),
    meta: { title: '学习分析', requiresAuth: true }
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

// 路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()

  // 设置页面标题
  document.title = to.meta.title ? `${to.meta.title} - 在线学习平台` : '在线学习平台'

  // 检查是否需要登录
  if (to.meta.requiresTeacherOnly && !userStore.isAuthenticated) {
    next('/login')
  }
  else if (to.meta.requiresTeacherOnly && userStore.userInfo?.role !== 'teacher') {
    next(userStore.userInfo?.role === 'admin' ? '/admin/dashboard' : '/')
  }
  else if (to.path === '/dashboard' && userStore.userInfo?.role === 'admin') {
    next('/admin/dashboard')
  }
  else if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    next('/login')
  }
  // 检查是否需要管理员权限
  else if (to.meta.requiresAdmin && (!userStore.isAuthenticated || userStore.userInfo?.role !== 'admin')) {
    if (!userStore.isAuthenticated) {
      next('/login')
    } else {
      next('/')
    }
  }
  // 检查是否需要教师权限（管理员也可以访问）
  else if (to.meta.requiresTeacher && (!userStore.isAuthenticated ||
    (userStore.userInfo?.role !== 'teacher' && userStore.userInfo?.role !== 'admin'))) {
    if (!userStore.isAuthenticated) {
      next('/login')
    } else {
      next('/')
    }
  }
  else {
    next()
  }
})

export default router







