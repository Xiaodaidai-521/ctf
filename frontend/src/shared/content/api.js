import api from '@/api'

// 角色由工作面传入；这里的检查不是服务端授权的替代品。
export function requireContentRole(role) {
  if (!['teacher', 'admin'].includes(role)) throw new Error('此页面仅供教师和管理员使用。')
  return role
}

export function createContentApi(role, client = api) {
  requireContentRole(role)
  return {
    role,
    categories: () => client.challenge.getCategories(),
    challenges: params => client.challenge.getChallenges(params),
    challengeDetail: id => client.challenge.getChallengeDetail(id),
    createChallenge: data => client.challenge.create(data),
    updateChallenge: (id, data) => client.challenge.update(id, data),
    deleteChallenge: id => client.challenge.delete(id),
    // 教师仍走原审核接口，403 原样上抛，不退到公开列表或冒充管理员。
    resources: params => client.resource.adminList(params),
    reviewResource: (id, status, note) => client.resource.review({ resource_id: id, status, review_comment: note }),
    uploadResource: data => client.resource.upload(data),
    downloadResource: id => client.resource.download(id, { highlight_resource: id }),
  }
}
