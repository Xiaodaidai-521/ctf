import api from '@/api'
export const guideApi = {
  paths: () => api.learningPaths.my(),
  reviews: () => api.learningPaths.reviewReminders(),
  conversations: () => api.conversation.list(),
}
