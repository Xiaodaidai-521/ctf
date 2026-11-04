import client from '@/api'

// Adapt the existing clients only. Actions, versions and permissions remain
// server-owned; this domain module does not define new endpoints.
export function createTeacherFeedbackApi(service = client) {
  const adapt = (domain, keys) => Object.fromEntries(keys.map(key => [key, (...args) => service[domain][key](...args)]))
  return {
    feedback: adapt('feedback', [
      'options', 'teacherQueue', 'teacherDetail', 'teacherAction',
      'samplingBatches', 'createSamplingBatch', 'samplingBatch',
      'downloadAttachment', 'reconciliation', 'retryEvents', 'phase3Contracts',
    ]),
    feedbackPhase3: adapt('feedbackPhase3', [
      'issueGroups', 'issueGroup', 'createIssueGroup', 'addIssueGroupMember',
      'confirmIssueGroup', 'rejectIssueGroup', 'splitIssueGroup', 'mergeIssueGroups',
      'candidates', 'candidate', 'createCandidate', 'submitCandidate',
      'attachCandidateReport', 'completeCandidateEvaluation', 'approveCandidate',
      'activateCandidate', 'observeCandidate', 'markCandidateStable', 'rollbackCandidate',
      'disputeLink', 'openDisputeLink',
    ]),
    learningMap: adapt('learningMap', ['catalog']),
    skillReview: adapt('skillReview', ['teacherRetests']),
  }
}

export default createTeacherFeedbackApi()
