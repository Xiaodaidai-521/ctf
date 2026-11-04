import api from '@/api'
import { asList, ratioPercent } from '@/learning/contracts.js'

export const growthApi = {
  profile: () => api.studentProfile.get(),
  persona: () => api.studentProfile.persona(),
  reports: () => api.studentProfile.reports(),
  growth: () => api.studentProfile.growth(),
  directions: () => api.studentProfile.learningDirections(),
  progressReport: () => api.analytics.progressReport(),
  insights: () => api.analytics.insights(),
  weeklySummary: () => api.analytics.weeklySummary(),
  teachingPlan: () => api.analytics.teachingPlan(),
  learningEffect: (days = 7) => api.analytics.learningEffectSummary(undefined, days),
  recommendations: () => api.learningAgent.recommend(),
  reviewReminders: () => api.learningPaths.reviewReminders(),
  completeReview: data => api.learningPaths.completeReview(data),
  myPaths: () => api.learningPaths.my(),
  submissionStats: () => api.submission.stats(),
}

export const GROWTH_WINDOWS = Object.freeze([7, 30, 90])
export const growthWindow = days => GROWTH_WINDOWS.includes(Number(days)) ? Number(days) : 7

// 两个来源的完成率单位不同，必须按来源换算，不能合并后混算。
export function completionFrom(report, stats) {
  const reportRate = ratioPercent(report?.completion_rate, 'progress-report')
  const statsRate = ratioPercent(stats?.completion_rate, 'submission-stats')
  return { report: reportRate, submissions: statsRate }
}

export function weeklyReport(data, now = new Date()) {
  if (!data || typeof data !== 'object') return null
  const start = data.week_start ? new Date(data.week_start) : null
  const isCurrentWeek = start && !Number.isNaN(start.getTime()) && (now - start) < 7 * 24 * 3600 * 1000 && now >= start
  return {
    label: isCurrentWeek ? '本周周报' : '最近一期周报',
    minutes: Number.isFinite(Number(data.total_study_minutes)) ? Number(data.total_study_minutes) : null,
    modules: Number.isFinite(Number(data.modules_completed)) ? Number(data.modules_completed) : null,
    exercises: Number.isFinite(Number(data.exercises_completed)) ? Number(data.exercises_completed) : null,
    concepts: Number.isFinite(Number(data.concepts_mastered)) ? Number(data.concepts_mastered) : null,
    aiInteractions: Number.isFinite(Number(data.ai_interactions)) ? Number(data.ai_interactions) : null,
    sandboxExecutions: Number.isFinite(Number(data.sandbox_executions)) ? Number(data.sandbox_executions) : null,
    generatedAt: data.generated_at || null,
    start: data.week_start || null,
  }
}

export { asList }
