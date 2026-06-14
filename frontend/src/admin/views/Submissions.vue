<template>
  <div class="admin-submissions">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">提交记录</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchSubmissions">
            🔄 刷新
          </button>
          <button class="action-btn btn-success" @click="exportData">
            📥 导出
          </button>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar" style="margin-bottom: 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
        <select v-model="filterStatus" class="form-select" style="width: 120px;">
          <option value="">全部状态</option>
          <option value="true">正确</option>
          <option value="false">错误</option>
        </select>
        <input
          v-model="searchKeyword"
          type="text"
          class="form-input"
          placeholder="搜索用户名或题目..."
          style="flex: 1; max-width: 300px;"
          @keyup.enter="fetchSubmissions"
        />
        <button class="action-btn btn-primary" @click="fetchSubmissions">
          🔍 搜索
        </button>
      </div>

      <!-- 提交记录列表 -->
      <div class="table-container" style="overflow-x: auto;">
        <table class="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>用户</th>
              <th>学校/团队</th>
              <th>题目</th>
              <th>分类</th>
              <th>Flag</th>
              <th>状态</th>
              <th>IP地址</th>
              <th>提交时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="submission in submissions" :key="submission.id">
              <td>{{ submission.id }}</td>
              <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <div class="user-avatar-small">{{ submission.username.charAt(0) }}</div>
                  <div>
                    <div style="font-weight: 500;">{{ submission.username }}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">{{ submission.user_nickname || '未设置昵称' }}</div>
                  </div>
                </div>
              </td>
              <td>
                <div style="font-size: 13px;">{{ submission.user_team || '无团队' }}</div>
                <div style="font-size: 12px; color: var(--admin-primary-color); font-weight: 500;">{{ submission.user_score }}分</div>
              </td>
              <td>
                <strong>{{ submission.challenge_title }}</strong>
              </td>
              <td>
                <span class="badge badge-info">{{ submission.category_name }}</span>
              </td>
              <td>
                <code class="flag-code">{{ submission.flag }}</code>
              </td>
              <td>
                <span class="badge" :class="submission.is_correct ? 'badge-success' : 'badge-error'">
                  {{ submission.is_correct ? '正确' : '错误' }}
                </span>
              </td>
              <td>{{ submission.ip_address }}</td>
              <td>{{ formatDateTime(submission.created_at) }}</td>
            </tr>
          </tbody>
        </table>

        <div v-if="submissions.length === 0" class="empty-state">
          <div class="empty-icon">📭</div>
          <p>暂无提交记录</p>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" style="display: flex; justify-content: space-between; align-items: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--admin-border-color);">
        <div class="pagination-info">
          共 {{ total }} 条记录，每页 {{ pageSize }} 条，第 {{ page }} / {{ totalPages }} 页
        </div>
        <div class="pagination-controls" style="display: flex; gap: 8px; align-items: center;">
          <button class="action-btn btn-default" @click="changePage(page - 1)" :disabled="page === 1">
            上一页
          </button>
          <button class="action-btn btn-default" @click="changePage(1)" :disabled="page === 1">
            1
          </button>
          <span v-if="totalPages > 1" style="padding: 0 4px;">...</span>
          <button class="action-btn btn-default" @click="changePage(totalPages)" :disabled="page === totalPages">
            {{ totalPages }}
          </button>
          <button class="action-btn btn-default" @click="changePage(page + 1)" :disabled="page === totalPages">
            下一页
          </button>
        </div>
      </div>

      <!-- 统计摘要 -->
      <div class="stats-summary" style="margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--admin-border-color);">
        <div style="display: flex; gap: 32px;">
          <div>
            <div style="font-size: 24px; font-weight: bold; color: #52c41a;">{{ stats.correct }}</div>
            <div style="font-size: 13px; color: var(--text-secondary);">正确提交</div>
          </div>
          <div>
            <div style="font-size: 24px; font-weight: bold; color: #ff4d4f;">{{ stats.wrong }}</div>
            <div style="font-size: 13px; color: var(--text-secondary);">错误提交</div>
          </div>
          <div>
            <div style="font-size: 24px; font-weight: bold; color: var(--admin-primary-color);">{{ stats.rate }}%</div>
            <div style="font-size: 13px; color: var(--text-secondary);">正确率</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '@/api'

const submissions = ref([])
const total = ref(0)
const totalPages = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const filterStatus = ref('')

const stats = computed(() => {
  const correct = submissions.value.filter(s => s.is_correct).length
  const wrong = submissions.value.filter(s => !s.is_correct).length
  const rate = submissions.value.length > 0 ? Math.round((correct / submissions.value.length) * 100) : 0
  return { correct, wrong, rate }
})

const fetchSubmissions = async () => {
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      search: searchKeyword.value,
    }
    if (filterStatus.value) {
      params.is_correct = filterStatus.value
    }
    const response = await api.submission.allSubmissions(params)
    submissions.value = response.results
    total.value = response.total
    totalPages.value = response.total_pages
  } catch (error) {
    console.error('获取提交记录失败:', error)
  }
}

const exportData = () => {
  // 导出为 CSV
  const headers = ['ID', '用户名', '昵称', '学校/团队', '用户分数', '题目', '分类', 'Flag', '状态', 'IP地址', '提交时间']
  const rows = submissions.value.map(s => [
    s.id,
    s.username,
    s.user_nickname,
    s.user_team,
    s.user_score,
    s.challenge_title,
    s.category_name,
    s.flag,
    s.is_correct ? '正确' : '错误',
    s.ip_address,
    s.created_at
  ])

  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
  ].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `submissions_${new Date().toISOString().split('T')[0]}.csv`
  link.click()
}

const changePage = (newPage) => {
  page.value = newPage
  fetchSubmissions()
}

const formatDateTime = (dateStr) => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchSubmissions()
})
</script>

<style scoped>
@import '../assets/admin.css';

.user-avatar-small {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--admin-primary-color);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  font-weight: bold;
}

.flag-code {
  padding: 2px 6px;
  background: #f5f5f5;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}
</style>
