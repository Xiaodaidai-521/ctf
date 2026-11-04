import api from '@/api'
import { listValue } from '../governance/data.js'
const checked = async promise => { const data = await promise; listValue(data); return data }
export const platformInsightsApi = {
  students: () => checked(api.analytics.adminStudentReport()),
  users: async () => { const data = await api.user.adminUsers({ page_size: 1 }); listValue(data?.users ?? data?.results); return data },
  leaderboard: () => api.user.leaderboard({ page_size: 100 }),
  challenges: () => checked(api.challenge.getChallenges()),
  submissions: () => api.submission.adminStats(),
  activities: () => checked(api.submission.allSubmissions({ is_correct: 'true', page_size: 8 })),
}
// Deliberately GET-only: no createAdminScore, proposals, student self APIs or teacher pages.
export const assessmentSupervisionApi = {
  students: platformInsightsApi.students,
  scores: studentId => checked(api.analytics.adminScores({ student_id: studentId })),
  plan: studentId => api.analytics.adminTeachingPlan(studentId),
}
