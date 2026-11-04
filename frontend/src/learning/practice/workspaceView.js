// 工作台展示所需的纯映射：不猜测缺失字段，不把自由练习当计分题。
export const DIFFICULTY_LABELS = Object.freeze({ easy: '简单', medium: '中等', hard: '困难', expert: '专家' })

export const RELATION_LABELS = Object.freeze({
  recommended_reading: '推荐阅读',
  background: '背景补充',
  practice_extension: '延伸练习',
  official_reference: '参考资料',
})

export function difficultyText(value) {
  return DIFFICULTY_LABELS[value] || '难度未注明'
}

export function relationTypeLabel(type) {
  return RELATION_LABELS[type] || '关联材料'
}

// practice 模式不计分、不要求 Flag；普通题显示真实分值。
export function modeBadge(challenge) {
  if (challenge?.submission_mode === 'practice') return { label: '自由练习', scoring: false }
  const score = Number(challenge?.score)
  return { label: Number.isFinite(score) ? `${score} 分` : '分值未提供', scoring: Number.isFinite(score) }
}

export function relatedGroups(challenge, sameCategory = []) {
  return {
    articles: (Array.isArray(challenge?.recommended_articles) ? challenge.recommended_articles : []).map(item => ({
      key: `article-${item.article_id ?? item.id ?? item.url}`,
      title: item.title || '未命名阅读',
      reason: item.reason || '',
      summary: item.summary || '',
      url: item.url || '',
    })).filter(item => item.url),
    resources: (Array.isArray(challenge?.recommended_resources) ? challenge.recommended_resources : []).map(item => ({
      key: `resource-${item.resource_id ?? item.id ?? item.url}`,
      title: item.title || '未命名资源',
      reason: item.reason || '',
      category: item.category || '',
      relation: item.relation_type ? relationTypeLabel(item.relation_type) : '',
      url: item.url || '',
    })).filter(item => item.url),
    // 相关题目只来自真实同分类列表，理由写明“同分类练习”。
    sameCategory: sameCategory.map(item => ({
      key: `challenge-${item.id}`,
      id: item.id,
      title: item.title || '未命名题目',
      difficulty: difficultyText(item.difficulty),
      reason: '同分类练习',
      solved: Boolean(item.is_solved),
    })),
  }
}

// 提交记录只对已读取范围给结论；还有下一页时明确说明，没找到时也不冒充“没有提交”。
export function submissionScopeNote(info) {
  if (!info) return ''
  const loaded = Number(info.loaded) || 0
  if (loaded > 0) {
    return info.hasNext
      ? `已读取本题 ${loaded} 条，仍有更早记录未展开。`
      : `已读取本题 ${loaded} 条提交记录。`
  }
  if (!info.hasNext) return ''
  const pages = Number(info.pagesRead) > 0 ? `最近 ${info.pagesRead} 页` : '最近记录'
  return `已读取${pages}，暂未找到本题提交；仍有更早记录未加载。`
}

export function submitFeedback(result, fallback = '') {
  if (!result) return { type: '', message: fallback }
  if (result.busy) return { type: 'info', message: result.message || '正在提交，请稍候。' }
  if (result.ok) return { type: 'success', message: result.message || '提交成功' }
  return { type: 'error', message: result.message || fallback || '提交未通过，请检查后再试。' }
}
