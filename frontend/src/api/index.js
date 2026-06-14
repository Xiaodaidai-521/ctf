import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Token ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)


const service = {
  // 璁よ瘉鐩稿叧
  auth: {
    login: (data) => api.post('/users/login/', data),
    register: (data) => api.post('/users/register/', data),
  },

  // 鐢ㄦ埛鐩稿叧
  user: {
    profile: () => api.get('/users/profile/'),
    updateProfile: (data) => api.put('/users/profile/update/', data),
    leaderboard: (params) => api.get('/users/leaderboard/', { params }),
    adminUsers: (params) => api.get('/users/admin/users/', { params }),
    adminCreate: (data) => api.post('/users/admin/users/create/', data),
    adminUpdate: (id, data) => api.put(`/users/admin/users/${id}/update/`, data),
    adminDelete: (id) => api.delete(`/users/admin/users/${id}/delete/`),
  },

  // 棰樼洰鐩稿叧
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
    // 瀹瑰櫒鐩稿叧
    startContainer: (id) => api.post(`/challenges/challenges/${id}/start/`),
    stopContainer: (id) => api.post(`/challenges/challenges/${id}/stop/`),
    getContainer: (id) => api.get(`/challenges/challenges/${id}/container/`),
  },

  // 鎻愪氦鐩稿叧
  submission: {
    mySubmissions: () => api.get('/submissions/my/'),
    allSubmissions: (params) => api.get('/submissions/all/', { params }),
    stats: () => api.get('/submissions/stats/'),
    adminStats: () => api.get('/submissions/admin/stats/'),
  },

  // 璧勬簮鐩稿叧
  resource: {
    list: (params) => api.get('/resources/', { params }),
    adminList: (params) => api.get('/resources/admin/', { params }),
    detail: (id) => api.get(`/resources/${id}/`),
    upload: (data) => api.post('/resources/upload/', data, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),
    myResources: () => api.get('/resources/my/'),
    review: (data) => api.post('/resources/review/', data),
    download: (id) => api.post(`/resources/${id}/download/`),
  },

  // 鏂囩珷鐩稿叧
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

  // 鍒嗙被鐩稿叧
  category: {
    list: () => api.get('/articles/categories/'),
  },

  // 璇勮鐩稿叧
  comment: {
    list: (params) => api.get('/articles/comments/', { params }),
    create: (data) => api.post('/articles/comments/', data),
    delete: (id) => api.delete(`/articles/comments/${id}/`),
    like: (id) => api.post(`/articles/comments/${id}/like/`),
    replies: (id) => api.get(`/articles/comments/${id}/replies/`),
  },

  // 瀛︿範璺緞鐩稿叧
  learningPaths: {
    // 瀛︿範璺緞鍒楄〃
    list: (params) => api.get('/learning-paths/paths/', { params }),
    // 瀛︿範璺緞璇︽儏
    detail: (id) => api.get(`/learning-paths/paths/${id}/`),
    // 鍒涘缓瀛︿範璺緞
    create: (data) => api.post('/learning-paths/paths/', data),
    // 鏇存柊瀛︿範璺緞
    update: (id, data) => api.put(`/learning-paths/paths/${id}/`, data),
    // 鍒犻櫎瀛︿範璺緞
    delete: (id) => api.delete(`/learning-paths/paths/${id}/`),
    // 寮€濮嬪涔犺矾寰?    start: (id) => api.post(`/learning-paths/paths/${id}/start/`),
    // 璺緞杩涘害
    progress: (id) => api.get(`/learning-paths/paths/${id}/progress/`),
    // 鎴戠殑璺緞
    my: () => api.get('/learning-paths/progress/'),
    // 鎺ㄨ崘
    recommendations: () => api.get('/learning-paths/recommendations/'),
    reviewReminders: () => api.get('/learning-paths/recommendations/review-reminders/'),
    completeReview: (data) => api.post('/learning-paths/recommendations/complete-review/', data),
  },

  // 璺緞妯″潡鐩稿叧
  pathModules: {
    // 妯″潡鍒楄〃
    list: (params) => api.get('/learning-paths/modules/', { params }),
    // 妯″潡璇︽儏
    detail: (id) => api.get(`/learning-paths/modules/${id}/`),
    // 鍒涘缓妯″潡
    create: (data) => api.post('/learning-paths/modules/', data),
    // 鏇存柊妯″潡
    update: (id, data) => api.put(`/learning-paths/modules/${id}/`, data),
    // 鍒犻櫎妯″潡
    delete: (id) => api.delete(`/learning-paths/modules/${id}/`),
    // 寮€濮嬫ā鍧?    start: (id) => api.post(`/learning-paths/modules/${id}/start/`),
    // 瀹屾垚妯″潡
    complete: (id) => api.post(`/learning-paths/modules/${id}/complete/`),
    // 妯″潡鐨勫疄楠?    labs: (id) => api.get(`/learning-paths/modules/${id}/labs/`),
  },

  // 瀛︿範杩涘害鐩稿叧
  learningProgress: {
    // 鎴戠殑杩涘害姒傝
    overview: () => api.get('/learning-paths/progress/'),
  },

  // 鐭ヨ瘑鍥捐氨鐩稿叧
  knowledgeGraph: {
    // 鐭ヨ瘑姒傚康鍒楄〃
    concepts: (params) => api.get('/learning-paths/knowledge-concepts/', { params }),
    // 姒傚康璇︽儏
    conceptDetail: (id) => api.get(`/learning-paths/knowledge-concepts/${id}/`),
    // 鎴戠殑鐭ヨ瘑鐘舵€?    myState: () => api.get('/learning-paths/knowledge/my-state/'),
  },

  // 鑰冭瘯鐩稿叧
  exams: {
    levelRules: () => api.get('/exams/level-rules/'),
    // 鐞嗚棰樺簱
    theoryQuestions: (params) => api.get('/exams/theory-questions/', { params }),
    // 瀹炴垬鑰冭瘯鍒楄〃
    practiceExams: (params) => api.get('/exams/practice-exams/', { params }),
    // 鐞嗚鑰冭瘯鍒楄〃
    theoryExams: (params) => api.get('/exams/theory-exams/', { params }),
    // 鑰冭瘯璁板綍
    records: (params) => api.get('/exams/records/', { params }),
    // 鎴戠殑鑰冭瘯鍘嗗彶
    myHistory: () => api.get('/exams/records/my_history/'),
    // 鑰冭瘯缁熻
    statistics: () => api.get('/exams/records/statistics/'),
    // 鎴愮哗瓒嬪娍
    scoreTrend: () => api.get('/exams/records/score_trend/'),
    // 寮€濮嬬患鍚堣€冭瘯
    startComprehensiveExam: () => api.post('/exams/records/start_comprehensive_exam/'),
    // 鑾峰彇鑰冭瘯棰樼洰
    getTheoryQuestions: (examId) => api.get(`/exams/theory-exams/${examId}/questions/`),
    getPracticeQuestions: (examId) => api.get(`/exams/practice-exams/${examId}/questions/`),
    // 鎻愪氦绛旀
    submitAnswer: (recordId, data) => api.post(`/exams/records/${recordId}/answer/`, data),
    // 鎻愪氦鑰冭瘯
    submitExam: (recordId) => api.post(`/exams/records/${recordId}/submit/`),
    // 鑰冭瘯缁撴灉
    getExamResult: (recordId) => api.get(`/exams/records/${recordId}/result/`),
  },

  // 鍏憡鐩稿叧
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

  // 鐢ㄦ埛鐢诲儚
  studentProfile: {
    get: () => api.get('/student-profiles/me/'),
    update: (data) => api.put('/student-profiles/me/', data),
    onboarding: (data) => api.post('/student-profiles/onboarding/', data),
    persona: () => api.get('/student-profiles/me/persona/'),
    learningDirections: () => api.get('/student-profiles/learning-directions/'),
  },

  // 澶氭櫤鑳戒綋瀛︿範
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

  // 鍐呭鐢熸垚
  content: {
    generateTutorial: (data) => api.post('/content/generate/tutorial/', data),
    generateQuiz: (data) => api.post('/content/generate/quiz/', data),
    generateDiagram: (data) => api.post('/content/generate/diagram/', data),
    generateExercise: (data) => api.post('/content/generate/exercise/', data),
    getDetail: (id) => api.get(`/content/${id}/`),
    regenerate: (id, data) => api.post(`/content/${id}/regenerate/`, data),
  },

  // 瀛︿範鍒嗘瀽
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
  },
}

export { api as http }
export default service
