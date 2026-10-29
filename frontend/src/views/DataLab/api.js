import { http } from '@/api'

const root = '/data-lab/'
export const labApi = {
  get: (path) => http.get(root + path),
  post: (path, body = {}) => http.post(root + path, body),
}

export const teacherLabApi = {
  cases: () => labApi.get('teacher/cases/'),
  caseDetail: (taskKey) => labApi.get(`teacher/cases/${encodeURIComponent(taskKey)}/attempts/`),
  setStatus: (taskKey, body) => labApi.post(`teacher/cases/${encodeURIComponent(taskKey)}/attempts/`, body),
  help: (taskKey, attemptId, body) => labApi.post(
    `teacher/cases/${encodeURIComponent(taskKey)}/attempts/${encodeURIComponent(attemptId)}/help/`, body,
  ),
}
