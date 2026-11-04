import { knowledgeApi } from '@/learningKnowledge/api.js'
import { governanceKnowledgeApi } from './governanceApi.js'
// Staff capabilities only. The task-scoped student evidence API stays untouched.
export const staffKnowledgeApi = {
  ...governanceKnowledgeApi,
  library: (...args) => knowledgeApi.library(...args),
  libraryDetail: (...args) => knowledgeApi.libraryDetail(...args),
  upload: (...args) => knowledgeApi.upload(...args),
  materialSearch: (...args) => knowledgeApi.materialSearch(...args),
  materials: (...args) => knowledgeApi.materials(...args),
  inspect: (...args) => knowledgeApi.inspect(...args),
  register: (...args) => knowledgeApi.register(...args),
  revise: (...args) => knowledgeApi.revise(...args),
  transition: (...args) => knowledgeApi.transition(...args),
}
