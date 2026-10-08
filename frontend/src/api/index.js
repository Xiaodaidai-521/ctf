import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})

api.interceptors.response.use(
  (response) => response.config.responseType === 'blob' ? response : response.data,
  (error) => {
    if (error.response?.status === 401 || error.response?.data?.code === 'authentication_required') {
      localStorage.removeItem('userInfo')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)


const service = {
  // 认证相关
  auth: {
    csrf: () => api.get('/users/csrf/'),
    login: (data) => api.post('/users/login/', data),
    register: (data) => api.post('/users/register/', data),
    logout: () => api.post('/users/logout/'),
  },

  // 用户相关
  user: {
    profile: () => api.get('/users/profile/'),
    updateProfile: (data) => api.put('/users/profile/update/', data),
    leaderboard: (params) => api.get('/users/leaderboard/', { params }),
    adminUsers: (params) => api.get('/users/admin/users/', { params }),
    adminCreate: (data) => api.post('/users/admin/users/create/', data),
    adminUpdate: (id, data) => api.put(`/users/admin/users/${id}/update/`, data),
    adminDelete: (id) => api.delete(`/users/admin/users/${id}/delete/`),
    teacherApplications: () => api.get('/users/admin/teacher-applications/'),
    approveTeacherApplication: (id) => api.post(`/users/admin/teacher-applications/${id}/approve/`),
    rejectTeacherApplication: (id) => api.post(`/users/admin/teacher-applications/${id}/reject/`),
  },

  // 题目相关
  challenge: {
    getCategories: () => api.get('/challenges/categories/'),
    getChallenges: (params) => api.get('/challenges/challenges/', { params }),
    getChallengeDetail: (id) => api.get(`/challenges/challenge/${id}/`),
    submitFlag: (id, flag) => api.post(`/challenges/challenges/${id}/submit/`, {
      challenge_id: id,
      flag
    }),
    mySolved: () => api.get('/challenges/challenges/my_solved/'),
    // 棰樼洰绠＄悊锛堢鐞嗗憳锛?    create: (data) => api.post('/challenges/challenges/', data),
    update: (id, data) => api.put(`/challenges/challenges/${id}/`, data),
    delete: (id) => api.delete(`/challenges/challenges/${id}/`),
    // 容器相关
    startContainer: (id) => api.post(`/challenges/challenges/${id}/start/`),
    stopContainer: (id) => api.post(`/challenges/challenges/${id}/stop/`),
    getContainer: (id) => api.get(`/challenges/challenges/${id}/container/`),
  },

  // 提交相关
  submission: {
    mySubmissions: () => api.get('/submissions/my/'),
    allSubmissions: (params) => api.get('/submissions/all/', { params }),
    stats: () => api.get('/submissions/stats/'),
    adminStats: () => api.get('/submissions/admin/stats/'),
  },

  // 资源相关
  resource: {
    list: (params) => api.get('/resources/', { params }),
    adminList: (params) => api.get('/resources/admin/', { params }),
    detail: (id, params) => api.get(`/resources/${id}/`, { params }),
    upload: (data) => api.post('/resources/upload/', data, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),
    myResources: () => api.get('/resources/my/'),
    review: (data) => api.post('/resources/review/', data),
    download: (id, params) => api.get(`/resources/${id}/download/`, { params, responseType: 'blob' }),
  },

  // 文章相关
  article: {
    list: (params) => api.get('/articles/articles/', { params }),
    detail: (id) => api.get(`/articles/articles/${id}/`),
    create: (data) => api.post('/articles/articles/', data),
    update: (id, data) => api.put(`/articles/articles/${id}/`, data),
    delete: (id) => api.delete(`/articles/articles/${id}/`),
    my: () => api.get('/articles/articles/my/'),
    myFavorites: () => api.get('/articles/articles/my_favorites/'),
    hot: (params) => api.get('/articles/articles/hot/', { params }),
    recommend: (params) => api.get('/articles/articles/recommend/', { params }),
    like: (id) => api.post(`/articles/articles/${id}/like/`),
    collect: (id) => api.post(`/articles/articles/${id}/collect/`),
    review: (id, data) => api.post(`/articles/articles/${id}/review/`, data),
  },

  // 分类相关
  category: {
    list: () => api.get('/articles/categories/'),
  },

  // 评论相关
  comment: {
    list: (params) => api.get('/articles/comments/', { params }),
    create: (data) => api.post('/articles/comments/', data),
    delete: (id) => api.delete(`/articles/comments/${id}/`),
    like: (id) => api.post(`/articles/comments/${id}/like/`),
    replies: (id) => api.get(`/articles/comments/${id}/replies/`),
  },

  // 学习路径相关
  learningPaths: {
    // 学习路径列表
    list: (params) => api.get('/learning-paths/paths/', { params }),
    // 学习路径详情
    detail: (id) => api.get(`/learning-paths/paths/${id}/`),
    // 创建学习路径
    create: (data) => api.post('/learning-paths/paths/', data),
    // 更新学习路径
    update: (id, data) => api.put(`/learning-paths/paths/${id}/`, data),
    // 删除学习路径
    delete: (id) => api.delete(`/learning-paths/paths/${id}/`),
    // 寮€濮嬪涔犺矾寰?    start: (id) => api.post(`/learning-paths/paths/${id}/start/`),
    // 路径进度
    progress: (id) => api.get(`/learning-paths/paths/${id}/progress/`),
    // 我的路径
    my: () => api.get('/learning-paths/progress/'),
    // 推荐
    recommendations: () => api.get('/learning-paths/recommendations/'),
    reviewReminders: () => api.get('/learning-paths/recommendations/review-reminders/'),
    completeReview: (data) => api.post('/learning-paths/recommendations/complete-review/', data),
  },

  // 路径模块相关
  pathModules: {
    // 模块列表
    list: (params) => api.get('/learning-paths/modules/', { params }),
    // 模块详情
    detail: (id) => api.get(`/learning-paths/modules/${id}/`),
    // 创建模块
    create: (data) => api.post('/learning-paths/modules/', data),
    // 更新模块
    update: (id, data) => api.put(`/learning-paths/modules/${id}/`, data),
    // 删除模块
    delete: (id) => api.delete(`/learning-paths/modules/${id}/`),
    // 寮€濮嬫ā鍧?    start: (id) => api.post(`/learning-paths/modules/${id}/start/`),
    // 完成模块
    complete: (id) => api.post(`/learning-paths/modules/${id}/complete/`),
    // 妯″潡鐨勫疄楠?    labs: (id) => api.get(`/learning-paths/modules/${id}/labs/`),
  },

  // 学习进度相关
  learningProgress: {
    // 我的进度概览
    overview: () => api.get('/learning-paths/progress/'),
  },

  // 知识图谱相关
  knowledgeGraph: {
    // 知识概念列表
    concepts: (params) => api.get('/learning-paths/knowledge-concepts/', { params }),
    // 概念详情
    conceptDetail: (id) => api.get(`/learning-paths/knowledge-concepts/${id}/`),
    // 鎴戠殑鐭ヨ瘑鐘舵€?    myState: () => api.get('/learning-paths/knowledge/my-state/'),
  },

  // 考试相关
  exams: {
    levelRules: () => api.get('/exams/level-rules/'),
    // 理论题库
    theoryQuestions: (params) => api.get('/exams/theory-questions/', { params }),
    // 实战考试列表
    practiceExams: (params) => api.get('/exams/practice-exams/', { params }),
    // 理论考试列表
    theoryExams: (params) => api.get('/exams/theory-exams/', { params }),
    // 考试记录
    records: (params) => api.get('/exams/records/', { params }),
    // 我的考试历史
    myHistory: () => api.get('/exams/records/my_history/'),
    // 考试统计
    statistics: () => api.get('/exams/records/statistics/'),
    // 成绩趋势
    scoreTrend: () => api.get('/exams/records/score_trend/'),
    // 开始综合考试
    startComprehensiveExam: () => api.post('/exams/records/start_comprehensive_exam/'),
    // 获取考试题目
    getTheoryQuestions: (examId) => api.get(`/exams/theory-exams/${examId}/questions/`),
    getPracticeQuestions: (examId) => api.get(`/exams/practice-exams/${examId}/questions/`),
    // 提交答案
    submitAnswer: (recordId, data) => api.post(`/exams/records/${recordId}/answer/`, data),
    // 提交考试
    submitExam: (recordId) => api.post(`/exams/records/${recordId}/submit/`),
    // 考试结果
    getExamResult: (recordId) => api.get(`/exams/records/${recordId}/result/`),
  },

  // 公告相关
  announcement: {
    list: (params) => api.get('/announcements/announcements/', { params }),
    detail: (id) => api.get(`/announcements/announcements/${id}/`),
    create: (data) => api.post('/announcements/announcements/', data),
    update: (id, data) => api.put(`/announcements/announcements/${id}/`, data),
    delete: (id) => api.delete(`/announcements/announcements/${id}/`),
    latest: () => api.get('/announcements/announcements/latest/'),
    pinned: () => api.get('/announcements/announcements/pinned/'),
    publish: (id) => api.post(`/announcements/announcements/${id}/publish/`),
    unpublish: (id) => api.post(`/announcements/announcements/${id}/unpublish/`),
  },

  // 用户画像
  studentProfile: {
    get: () => api.get('/student-profiles/me/'),
    update: (data) => api.put('/student-profiles/me/', data),
    onboarding: (data) => api.post('/student-profiles/onboarding/', data),
    onboardingInterview: () => api.get('/student-profiles/onboarding/interview/'),
    answerOnboardingQuestion: (data) => api.post('/student-profiles/onboarding/interview/', data),
    reports: () => api.get('/student-profiles/me/reports/'),
    persona: () => api.get('/student-profiles/me/persona/'),
    personaGrowth: () => api.get('/student-profiles/me/persona-growth/'),
    growth: () => api.get('/student-profiles/me/growth/'),
    learningDirections: () => api.get('/student-profiles/learning-directions/'),
  },

  // 多智能体学习
  learningAgent: {
    agents: () => api.get('/ai/learning/agents/'),
    tutoring: (data) => api.post('/ai/learning/tutoring/', data),
    generate: (data) => api.post('/ai/learning/generate/', data),
    assess: (data) => api.post('/ai/learning/assess/', data),
    recommend: () => api.get('/ai/learning/recommend/'),
  },

  multiAgent: {
    agents: () => api.get('/ai/multi-agent/agents/'),
    presets: () => api.get('/ai/multi-agent/presets/'),
  },

  conversation: {
    detail: (id) => api.get(`/ai/conversations/${id}/`),
    list: () => api.get('/ai/list/'),
    remove: (id) => api.delete(`/ai/conversations/${id}/`),
  },

  // 内容生成
  content: {
    generateTutorial: (data) => api.post('/content/generate/tutorial/', data),
    generateQuiz: (data) => api.post('/content/generate/quiz/', data),
    generateDiagram: (data) => api.post('/content/generate/diagram/', data),
    generateExercise: (data) => api.post('/content/generate/exercise/', data),
    getDetail: (id) => api.get(`/content/${id}/`),
    regenerate: (id, data) => api.post(`/content/${id}/regenerate/`, data),
  },

  // 学习分析
  analytics: {
    insights: () => api.get('/analytics/insights/'),
    weeklySummary: () => api.get('/analytics/weekly-summary/'),
    progressReport: () => api.get('/analytics/progress-report/'),
    knowledgeMap: () => api.get('/analytics/knowledge-map/'),
    adminStudentReport: () => api.get('/analytics/admin/student-report/'),
    adminScores: (params) => api.get('/analytics/admin/scores/', { params }),
    createAdminScore: (data) => api.post('/analytics/admin/scores/', data),
    teachingPlan: () => api.get('/analytics/teaching-plan/'),
    adminTeachingPlan: (studentId) => api.get(`/analytics/admin/teaching-plan/${studentId}/`),
    teacherStudentReport: () => api.get('/analytics/teacher/student-report/'),
    teacherScores: (params) => api.get('/analytics/teacher/scores/', { params }),
    createTeacherScore: (data) => api.post('/analytics/teacher/scores/', data),
    teacherTeachingPlan: (studentId) => api.get(`/analytics/teacher/teaching-plan/${studentId}/`),
    learningEffect: (studentId) => api.get('/analytics/teacher/learning-effect/', { params: { student_id: studentId } }),
    learningEffectSummary: (studentId, days = 30) => api.get('/analytics/learning/effect/', { params: { student_id: studentId, days } }),
    createLearningAdjustment: (data) => api.post('/analytics/teacher/proposals/', data),
    decideLearningAdjustment: (id, status) => api.post(`/analytics/teacher/adjustments/${id}/`, { status }),
  },

  legal: {
    protocols: (params) => api.get('/legal/protocols/', { params }),
    protocolVersions: (params) => api.get('/legal/protocol-versions/', { params }),
    publishProtocolVersion: (id) => api.post(`/legal/protocol-versions/${id}/publish/`),
    consents: (params) => api.get('/legal/consents/', { params }),
    signConsent: (data) => api.post('/legal/consents/sign/', data),
    dataProcessing: (params) => api.get('/legal/data-processing/', { params }),
    analysisTasks: (params) => api.get('/legal/analysis-tasks/', { params }),
    createAnalysisTask: (data) => api.post('/legal/analysis-tasks/', data),
    runAnalysis: (id) => api.post(`/legal/analysis-tasks/${id}/run_analysis/`),
    findings: (params) => api.get('/legal/risk-findings/', { params }),
    evidence: (params) => api.get('/legal/evidence/', { params }),
    violations: (params) => api.get('/legal/violations/', { params }),
    createViolation: (data) => api.post('/legal/violations/', data),
    reports: (params) => api.get('/legal/reports/', { params }),
    exportReport: (id) => api.post(`/legal/reports/${id}/export/`),
    agentRuns: (params) => api.get('/legal/agent-runs/', { params }),
    containerAudits: (params) => api.get('/legal/container-audits/', { params }),
    previewExerciseFacts: (data) => api.post('/legal/exercise-facts/preview/', data),
    confirmExerciseFacts: (data) => api.post('/legal/exercise-facts/confirm/', data),
  },

  legalKb: {
    documents: (params) => api.get('/legal-kb/documents/', { params }),
    ingestDocument: (id) => api.post(`/legal-kb/documents/${id}/ingest/`),
    clauses: (params) => api.get('/legal-kb/clauses/', { params }),
    cases: (params) => api.get('/legal-kb/cases/', { params }),
    templates: (params) => api.get('/legal-kb/templates/', { params }),
    embeddings: (params) => api.get('/legal-kb/embeddings/', { params }),
    ingestionJobs: (params) => api.get('/legal-kb/ingestion-jobs/', { params }),
    retrievalLogs: (params) => api.get('/legal-kb/retrieval-logs/', { params }),
    retrieve: (data) => api.post('/legal-kb/retrieve/', data),
  },

  audit: {
    events: (params) => api.get('/audit/events/', { params }),
    aiLogs: (params) => api.get('/audit/ai-logs/', { params }),
    ledger: (params) => api.get('/audit/ledger/', { params }),
    verifyLedger: () => api.get('/audit/ledger/verify/'),
  },
}

export { api as http }
export default service
