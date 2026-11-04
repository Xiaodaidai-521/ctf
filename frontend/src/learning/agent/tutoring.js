// 题内辅导的提示口径：只呈现后台真实给出的层级，不按题号或难度推导，也不提供“完整答案”开关。
// 普通题目对话（multi-agent chat / tutoring）与 TeachingRun 的 1–4 级提示不是同一套契约；
// 只有后台响应带回合法 attempt/run 关联与 hintLevel 时才显示当前层级。
export const HINT_TIERS = Object.freeze([
  { key: 'attempt', label: '先说说你的尝试', description: '默认先由学生说明已经试过什么。' },
  { key: 'direction', label: '给思路', description: '确认尝试后再给方向，不直接给答案。' },
  { key: 'keypoint', label: '关键点', description: '按后台策略给出关键检查点或步骤。' },
  { key: 'example', label: '局部示例', description: '仅在策略允许时给出局部示例，不展开完整解法。' },
])

function pick(value, camel, snake) {
  return value?.[camel] ?? value?.[snake] ?? null
}

// 只认后台返回的任务关联；challenge_id/难度都不算 attempt。
export function taskBindingFrom(metadata) {
  const source = metadata?.taskBinding ?? metadata?.task_binding ?? null
  if (!source || typeof source !== 'object') {
    return { available: false, hintLevel: null, attemptId: null, runId: null }
  }
  const attemptId = pick(source, 'attemptId', 'attempt_id')
  const runId = pick(source, 'runId', 'run_id')
  const rawLevel = Number(pick(source, 'hintLevel', 'hint_level'))
  const hintLevel = Number.isInteger(rawLevel) && rawLevel >= 1 && rawLevel <= 4 ? rawLevel : null
  return {
    available: Boolean(attemptId || runId),
    hintLevel,
    attemptId: attemptId || null,
    runId: runId || null,
  }
}

export function tutoringPolicy({ context = null, metadata = null, authorHint = false } = {}) {
  const binding = taskBindingFrom(metadata)
  const isChallenge = context?.kind === 'challenge'
  const target = isChallenge ? `当前题目：${context.title || context.ref}` : ''
  const level = binding.hintLevel
  return {
    isChallenge,
    target,
    authorHint: {
      available: Boolean(authorHint),
      label: '题目作者公开提示',
      note: '由题目作者提供，显示在题面区；它不是智能体已解锁的下一层提示。',
    },
    level,
    levelLabel: level ? `后台记录：当前提示层级为第 ${level} 级。` : '后台未返回当前提示层级；以对话中的实际回复为准。',
    // 层级只作说明：普通题对话没有按层级请求的接口，前端不能指定或自动推进。
    canRequestLevel: false,
    autoAdvance: false,
    fullAnswer: false,
    tiers: HINT_TIERS.map((tier, index) => ({
      ...tier,
      index: index + 1,
      state: level ? (index + 1 <= level ? 'available' : 'later') : 'policy',
    })),
    note: '本页不提供“完整答案”开关，也不会自动连续请求下一层；每次只回应你本轮的问题。',
  }
}

// 换题时给出清楚的边界提示，避免把上一题的对话继续拼进新题的请求。
export function challengeSwitchNote(previous, next) {
  if (!previous || !next || previous.kind !== 'challenge' || next.kind !== 'challenge') return ''
  if (String(previous.ref) === String(next.ref)) return ''
  return `已切换到《${next.title || next.ref}》，辅导从这道题重新开始。`
}
