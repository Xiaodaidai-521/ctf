// Shared read contract. Teacher calls must name a student; never fall back to /me.
export function createLearningReadApi(analytics) {
  return {
    effectForStudent(studentId, days) {
      if (!['number', 'string'].includes(typeof studentId) || !/^[1-9]\d*$/.test(String(studentId)) || !Number.isSafeInteger(Number(studentId))) throw new Error('Student required')
      if (![7, 30, 90].includes(Number(days))) throw new Error('Unsupported window')
      return analytics.learningEffectSummary(studentId, Number(days))
    },
  }
}
