import { RETENTION_MS } from './retention.js'

export const VIEW_CACHE_ROUTES = Object.freeze([
  'Guide', 'Challenges', 'ChallengeDetail', 'StudentDashboard', 'Resources',
  'MultiAgent', 'MultiAgentChallenge', 'LearningPaths', 'LearningPathDetail',
  'ExamHistory',
])
export const UI_ONLY_ROUTES = Object.freeze([
  'TeacherChallenges', 'TeacherResources', 'TeacherLearningPaths',
  'AdminChallengesHome', 'AdminResourcesHome', 'AdminUsersHome',
  'AdminArticlesHome', 'AdminSubmissionsHome', 'AdminAnnouncementsHome', 'AdminCategoriesHome',
])
const PRIVATE_NAME = /Knowledge|Materials|DataLab|DataCases|ExamTaking|Profile|Feedback|LearningScores|Assessment|TeachingActions|StudentGrowth|ResourceUpload|Editor|Create|Edit|Legal/
const PRIVATE_PATH = /(?:learning-knowledge|teaching-knowledge|knowledge|materials|data-lab|data-security|exam-taking|profile|feedback|learning-scores|teaching-actions)(?:\/|$)/
export function cachePolicy(route, role) {
  if (PRIVATE_NAME.test(String(route?.name || '')) || PRIVATE_PATH.test(String(route?.path || ''))) return 'none'
  if (route?.meta?.cache === 'none' || route?.meta?.sensitive) return 'none'
  // A route meta cannot turn an unreviewed privileged page into a cached view.
  if (role === 'student' && VIEW_CACHE_ROUTES.includes(route?.name)) return 'view'
  if (UI_ONLY_ROUTES.includes(route?.name) && ['teacher', 'admin'].includes(role)) return 'ui'
  return 'none'
}
export function isStaffLayout(route, layer) {
  return layer === 'root' && /^\/(teacher|admin)(?:\/|$)/.test(route?.path || '')
}
export function retentionKey(route) { return String(route?.path || '/') }
export { RETENTION_MS }
