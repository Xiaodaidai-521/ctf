export function teachingDestination(path, query = {}, role) {
  if (role !== 'teacher') return null
  path = path.replace(/\/+$/, '')
  let target
  if (path === '/teaching-knowledge') target = '/teacher/materials'
  if (path === '/learning-paths/manage') target = '/teacher/learning-paths'
  if (path === '/learning-paths/new') target = '/teacher/learning-paths/new'
  const edit = /^\/learning-paths\/([^/]+)\/edit$/.exec(path)
  if (edit) target = `/teacher/learning-paths/${edit[1]}/edit`
  return target ? { path: target, query: { ...query } } : null
}
export const feedbackCandidateDestination = to => ({ path: '/teacher/feedback', query: { ...to.query }, hash: '#candidates' })
