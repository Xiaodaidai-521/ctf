import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'

const routes = [
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

  // 智能学习平台路由
  {
    path: '/dashboard',
    name: 'StudentDashboard',
    component: () => import('@/views/StudentDashboard.vue'),
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
  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
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
