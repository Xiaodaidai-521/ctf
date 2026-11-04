import api from '@/api'
import { staffKnowledgeApi } from '@/shared/knowledge/staffApi.js'
import { listValue } from '../governance/data.js'
const checked = async promise => { const data = await promise; listValue(data); return data }
export const governanceCockpitApi = {
  resources: () => checked(api.resource.adminList({ status: 'pending', page_size: 1 })),
  articles: () => checked(api.article.list({ status: 'pending', page_size: 1 })),
  jobs: signal => checked(staffKnowledgeApi.jobs({ page_size: 50 }, signal)),
  applications: async () => {
    const data = await api.user.teacherApplications()
    const rows = Array.isArray(data) ? data : data?.applications ?? data?.users
    return listValue(rows)
  },
  materials: signal => checked(staffKnowledgeApi.materials(signal)),
}
