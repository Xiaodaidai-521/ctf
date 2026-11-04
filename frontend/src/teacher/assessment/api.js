import api from '@/api'
export function createTeacherAssessmentApi(client) {
  return {
    students: () => client.analytics.teacherStudentReport(),
    scores: studentId => client.analytics.teacherScores({ student_id: studentId }),
    save: data => client.analytics.createTeacherScore(data),
    plan: studentId => client.analytics.teacherTeachingPlan(studentId),
  }
}
export default createTeacherAssessmentApi(api)
