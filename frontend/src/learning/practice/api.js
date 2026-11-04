import api from '@/api'
import { asList, pageInfo } from '../contracts.js'
import { submissionsForChallenge } from './submissions.js'

// 靶场/工作台域 API：只复用现有后端路径，组件不再自行拼 URL。
export const practiceApi = {
  categories: () => api.challenge.getCategories(),
  list: params => api.challenge.getChallenges(params),
  detail: id => api.challenge.getChallengeDetail(id),
  solved: () => api.challenge.mySolved(),
  mySubmissions: (params = {}) => api.submission.mySubmissions(params),
  stats: () => api.submission.stats(),
  submit: (id, flag) => api.challenge.submitFlag(id, flag),
  container: id => api.challenge.getContainer(id),
  startEnvironment: id => api.challenge.startContainer(id),
  stopEnvironment: id => api.challenge.stopContainer(id),
  myPaths: () => api.learningPaths.my(),
  pathRecommendations: () => api.learningPaths.recommendations(),
  pathDetail: id => api.learningPaths.detail(id),
  resourceDetail: (id, params) => api.resource.detail(id, params),
  resourceDownload: (id, params) => api.resource.download(id, params),
  articleDetail: id => api.article.detail(id),
}

export { asList, pageInfo, submissionsForChallenge }
export const normalizeCategories = value => asList(value).map(item => ({ id: item.id, name: item.name }))
