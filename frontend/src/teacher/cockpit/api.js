import api from '@/api'
import { staffKnowledgeApi } from '@/shared/knowledge/staffApi.js'
import { createContentApi } from '@/shared/content/api.js'
const content = createContentApi('teacher')
export const cockpitApi = {
  feedback: () => api.feedback.teacherQueue({ page_size: 5, sort: 'priority' }),
  reviews: () => api.skillReview.teacherQueue(),
  resources: () => content.resources({ status: 'pending', page_size: 1 }),
  materials: () => staffKnowledgeApi.materials(),
  paths: () => api.learningPaths.list(),
}
