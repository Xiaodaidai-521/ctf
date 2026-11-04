import { pageInfo } from '../contracts.js'

// “我的提交”按时间倒序分页，服务端没有按题目过滤的参数；本题记录可能落在很后面的页里。
// 因此不能只看第一页就下“没有提交”的结论。
export const SUBMISSION_SCAN_PAGES = 50

export function challengeRefOf(item) {
  return item?.challenge_id ?? item?.challenge?.id ?? item?.challenge
}

export function isChallengeSubmission(item, challengeId) {
  return String(challengeRefOf(item)) === String(challengeId)
}

export function submissionsForChallenge(value, challengeId, pageSize = 20) {
  const info = pageInfo(value, pageSize)
  const matched = info.items.filter(item => isChallengeSubmission(item, challengeId))
  return { ...info, items: matched, scoped: info.hasNext }
}

// 从第一页起逐页读取，直到找到本题记录或读完；找到后再由“加载更早记录”继续往后翻。
export async function collectChallengeSubmissions({
  fetchPage, challengeId, startPage = 1, pageSize = 20, maxPages = SUBMISSION_SCAN_PAGES, shouldStop = null,
}) {
  const items = []
  const seen = new Set()
  let count = null
  let page = Math.max(1, Number(startPage) || 1)
  let hasNext = false
  let pagesRead = 0
  while (pagesRead < maxPages) {
    if (shouldStop && shouldStop()) break
    const value = await fetchPage(page)
    const info = pageInfo(value, pageSize)
    pagesRead = page
    if (Number.isFinite(info.count)) count = info.count
    for (const item of info.items) {
      if (!isChallengeSubmission(item, challengeId)) continue
      const key = String(item?.id)
      if (seen.has(key)) continue
      seen.add(key)
      items.push(item)
    }
    // 分页响应以 next 为准；裸数组或非分页响应才退回 count 推算。
    hasNext = value && typeof value === 'object' && 'next' in value ? Boolean(value.next) : info.hasNext
    if (items.length || !hasNext) break
    page += 1
  }
  return {
    items, count, hasNext, pagesRead, loaded: items.length,
    exhausted: !hasNext,
  }
}
