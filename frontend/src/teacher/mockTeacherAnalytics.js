const clone = value => JSON.parse(JSON.stringify(value))

export const demoTeacherStudents = [
  {
    id: 'mock-student-123',
    username: '123',
    latest_admin_score: 78.5,
    latest_effect_score: 78.3,
    is_demo: true,
  },
  {
    id: 'mock-student-user-1',
    username: 'user_1',
    latest_admin_score: 64,
    latest_effect_score: 65.2,
    is_demo: true,
  },
]

const normalize = value => String(value ?? '').trim().toLowerCase()

export const withDemoTeacherStudents = (students = []) => {
  const baseStudents = Array.isArray(students) ? students : []
  const existingNames = new Set(baseStudents.map(student => normalize(student.username || student.name)))
  const missingDemoStudents = demoTeacherStudents.filter(student => !existingNames.has(normalize(student.username)))
  return [...baseStudents, ...missingDemoStudents.map(clone)]
}

export const getDemoStudentKey = (studentId, students = []) => {
  const id = String(studentId ?? '')
  const student = Array.isArray(students) ? students.find(item => String(item.id) === id) : null
  const username = normalize(student?.username || student?.name || id)

  if (id === 'mock-student-123' || username === '123') return 'student123'
  if (id === 'mock-student-user-1' || username === 'user_1') return 'user1'
  return null
}

const scorePayloads = {
  student123: {
    results: [
      {
        id: 'mock-123-score-2026-07-16',
        measured_at: '2026-07-16',
        total_score: 78.5,
        dimension_scores: { web: 82, crypto: 70, pwn: 66, reverse: 74, forensics: 80, misc: 76 },
        validity_status: 'effective',
        tags: ['Web稳定', '取证较好', 'Pwn待加强'],
        remark: 'Web 解题节奏稳定，Pwn 栈基础和 Crypto 常见编码题还需要继续补练。',
      },
      {
        id: 'mock-123-score-2026-07-02',
        measured_at: '2026-07-02',
        total_score: 72,
        dimension_scores: { web: 76, crypto: 64, pwn: 60, reverse: 70, forensics: 74, misc: 72 },
        validity_status: 'effective',
        tags: ['基础提升', '稳定完成'],
        remark: '整体完成度提升明显，建议保持每周两次复盘。',
      },
      {
        id: 'mock-123-score-2026-06-27',
        measured_at: '2026-06-27',
        total_score: 69,
        dimension_scores: { web: 72, crypto: 60, pwn: 58, reverse: 66, forensics: 70, misc: 68 },
        validity_status: 'filtered',
        tags: ['间隔过短'],
        remark: '与下一次测评间隔不足 7 天，仅作为趋势参考。',
      },
    ],
    effective_score_ids: ['mock-123-score-2026-07-16', 'mock-123-score-2026-07-02'],
    score_summary: {
      status: 'ready',
      self_assessment: { score: 74 },
      admin: { score: 78.5, measured_at: '2026-07-16' },
      final_score: 77.15,
      weights: { self_assessment: 0.3, admin: 0.7 },
    },
  },
  user1: {
    results: [
      {
        id: 'mock-user-1-score-2026-07-15',
        measured_at: '2026-07-15',
        total_score: 64,
        dimension_scores: { web: 68, crypto: 61, pwn: 52, reverse: 58, forensics: 66, misc: 70 },
        validity_status: 'effective',
        tags: ['入门巩固', 'Reverse薄弱'],
        remark: 'Misc 和 Web 能独立推进，Reverse 与 Pwn 题目需要拆成更小步骤训练。',
      },
      {
        id: 'mock-user-1-score-2026-07-01',
        measured_at: '2026-07-01',
        total_score: 59,
        dimension_scores: { web: 62, crypto: 56, pwn: 48, reverse: 52, forensics: 60, misc: 64 },
        validity_status: 'effective',
        tags: ['基础阶段', '需要陪跑'],
        remark: '能完成提示明确的题目，缺少独立定位漏洞和验证思路的经验。',
      },
      {
        id: 'mock-user-1-score-2026-06-18',
        measured_at: '2026-06-18',
        total_score: 55,
        dimension_scores: { web: 58, crypto: 52, pwn: 45, reverse: 49, forensics: 56, misc: 60 },
        validity_status: 'expired',
        tags: ['早期基线'],
        remark: '早期摸底成绩，仅用于观察成长趋势。',
      },
    ],
    effective_score_ids: ['mock-user-1-score-2026-07-15', 'mock-user-1-score-2026-07-01'],
    score_summary: {
      status: 'ready',
      self_assessment: { score: 61 },
      admin: { score: 64, measured_at: '2026-07-15' },
      final_score: 63.1,
      weights: { self_assessment: 0.3, admin: 0.7 },
    },
  },
}

const teachingPlans = {
  student123: {
    validity_label: '近 90 天已有 2 次有效评分，可生成阶段方案',
    title: '123 的阶段提升方案',
    summary: '继续保持 Web 与取证方向的稳定练习，把 Crypto 常见编码、Pwn 栈基础作为本阶段主线。建议每周安排 2 次专项题和 1 次复盘。',
  },
  user1: {
    validity_label: '近 90 天已有 2 次有效评分，可生成阶段方案',
    title: 'user_1 的基础巩固方案',
    summary: '先稳住 Web、Misc 的入门题完成率，再用短题拆解 Reverse 与 Pwn 的基本分析流程。建议使用示例题讲解加分步任务的方式推进。',
  },
}

const learningEffects = {
  student123: {
    snapshot: {
      total_effect_score: 78.3,
      effect_level: 'good',
      sample_description: { effective_learning_seconds: 12600 },
      dimensions: {
        time_score: 76,
        completion_score: 82,
        mastery_score: 79,
        retention_score: 75,
        consistency_score: 84,
        efficiency_score: 78,
        engagement_score: 81,
        focus_score: 72,
      },
    },
    previousSnapshot: {
      sample_description: { effective_learning_seconds: 9900 },
      dimensions: {
        time_score: 70,
        completion_score: 77,
        mastery_score: 73,
        retention_score: 70,
        consistency_score: 79,
        efficiency_score: 74,
        engagement_score: 76,
        focus_score: 68,
      },
    },
    recommendations: [
      { id: 'mock-123-focus', title: '优先提升 Pwn 与 Crypto', content: '本周安排栈基础、编码转换和基础密码题各 2 组，练后记录错因。' },
      { id: 'mock-123-review', title: '保持复盘节奏', content: 'Web 和取证方向继续用错题回看维持稳定，不需要大幅加量。' },
    ],
  },
  user1: {
    snapshot: {
      total_effect_score: 65.2,
      effect_level: 'developing',
      sample_description: { effective_learning_seconds: 8400 },
      dimensions: {
        time_score: 62,
        completion_score: 68,
        mastery_score: 60,
        retention_score: 63,
        consistency_score: 66,
        efficiency_score: 58,
        engagement_score: 71,
        focus_score: 64,
      },
    },
    previousSnapshot: {
      sample_description: { effective_learning_seconds: 6900 },
      dimensions: {
        time_score: 56,
        completion_score: 61,
        mastery_score: 55,
        retention_score: 57,
        consistency_score: 59,
        efficiency_score: 53,
        engagement_score: 66,
        focus_score: 60,
      },
    },
    recommendations: [
      { id: 'mock-user-1-foundation', title: '强化基础路径', content: '先完成 Web 入门和 Misc 基础题，建立稳定的解题检查清单。' },
      { id: 'mock-user-1-guided', title: '分步训练 Reverse/Pwn', content: '使用带提示的短题练习环境观察、关键函数定位和结果验证。' },
    ],
  },
}

export const getDemoScorePayload = studentKey => scorePayloads[studentKey] ? clone(scorePayloads[studentKey]) : null
export const getDemoTeachingPlan = studentKey => teachingPlans[studentKey] ? clone(teachingPlans[studentKey]) : null
export const getDemoLearningEffect = studentKey => learningEffects[studentKey] ? clone(learningEffects[studentKey]) : null
