import api from '@/api'
import evaluation from '@/api/evaluation'
import { createLearningReadApi } from '@/shared/learning/api.js'

export function createTeacherInsightsApi(client, evaluationClient) {
  const shared = createLearningReadApi(client.analytics)
  return {
    students: () => client.analytics.teacherStudentReport(),
    effect: (studentId, days) => shared.effectForStudent(studentId, days),
    plan: studentId => client.analytics.teacherTeachingPlan(studentId),
    catalog: params => client.learningMap.teacherCatalog(params),
    evaluationStudents: params => evaluationClient.students(params),
    learning: params => evaluationClient.learning(params),
    attempt: id => evaluationClient.attempt(id),
    runtime: params => evaluationClient.runtime(params),
    todos: () => evaluationClient.todos(),
    createTodo: data => evaluationClient.createTodo(data),
    changeTodo: (id, data) => evaluationClient.changeTodo(id, data),
    syncTodos: () => evaluationClient.syncTodos(),
    consumeReceipts: () => evaluationClient.consumeReceipts(),
    retests: () => client.skillReview.teacherRetests(),
  }
}
export default createTeacherInsightsApi(api, evaluation)
