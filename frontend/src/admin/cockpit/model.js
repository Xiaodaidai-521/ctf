import { countValue, listValue } from '../governance/data.js'
import { indexIssue } from '../foundation/presentation.js'
const definitions = [
  ['resources', '资源待审核', '/admin/resources?status=pending', '核对成品内容、出处与许可。', '资源审核'],
  ['articles', '文章待审核', '/admin/articles?status=pending', '核对待发布文章，再决定是否放行。', '文章审核'],
  ['jobs', '索引异常', '/admin/legal/kb/health?status=attention', '核对未完成的资料处理记录。', '最近已读取的索引任务'],
  ['applications', '教师权限待审核', '/admin/users#teacher-applications', '核对教师申请，授予或拒绝教师权限。', '教师申请'],
  ['materials', '材料待监督', '/admin/legal/kb/authorization?status=in_review#materials', '核对审阅责任、许可与发布范围；材料审阅由教师负责。', '当前有权管理的材料'],
  ['grants', '课程授权待处理', '/admin/legal/kb/authorization#grants', '按课程与人员核对授权，不代替教师审阅。', '课程授权'],
]
export function governanceTiles(sources) {
  return definitions.map(([key, title, href, description, scope]) => {
    const source = sources[key]
    let count = null
    if (source?.data != null && !source.error) {
      const rows = listValue(source.data)
      if (['resources', 'articles'].includes(key)) count = countValue(source.data.count ?? source.data.total)
      else if (key === 'jobs') count = rows.filter(row => indexIssue(row)).length
      else if (key === 'applications') count = rows.length
      else if (key === 'materials') count = rows.filter(row => row.review_status === 'in_review').length
    }
    return { key, title, href, description, scope, count, error: source?.error || '', loading: source?.loading || false,
      notice: key === 'grants' ? '这里还不能确认待处理数量，请打开授权记录逐项核对。' : '这里还不能确认待办数量，请打开记录逐项核对。' }
  })
}
