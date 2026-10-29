import axios from 'axios'

const client = axios.create({
  baseURL: '/api/evaluation',
  timeout: 30000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})
client.interceptors.response.use(response => response.data)

export default {
  students: params => client.get('/students/', { params }),
  learning: params => client.get('/learning/', { params }),
  attempt: id => client.get(`/attempts/${encodeURIComponent(id)}/`),
  runtime: params => client.get('/runtime/', { params }),
  todos: () => client.get('/todos/'),
  createTodo: data => client.post('/todos/', data),
  changeTodo: (id, data) => client.post(`/todos/${encodeURIComponent(id)}/`, data),
  syncTodos: () => client.post('/todos/sync/', {}),
  consumeReceipts: () => client.post('/receipts/', {}),
}
