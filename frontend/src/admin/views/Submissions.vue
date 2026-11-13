<template>
  <div class="admin-submissions">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">提交记录</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchSubmissions">
            <AppIcon name="bi-arrow-clockwise" /> 刷新
          </button>
          <button class="action-btn btn-success" @click="exportData">
            <AppIcon name="bi-download" /> 导出
          </button>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar" style="margin-bottom:var(--space-2); display:flex; gap:var(--space-1); align-items:center; flex-wrap:wrap;">
        <select v-model="filterStatus" class="form-select" style="width:var(--row-label-width);">
          <option value="">全部状态</option>
          <option value="true">正确</option>
          <option value="false">错误</option>
        </select>
        <input
          v-model="searchKeyword"
          type="text"
          class="form-input"
          placeholder="搜索用户名或题目..."
          style="flex:1; max-width:var(--menu-width);"
          @keyup.enter="fetchSubmissions"
        />
        <button class="action-btn btn-primary" @click="fetchSubmissions">
          <AppIcon name="bi-search" /> 搜索
        </button>
      </div>

      <p v-if="listError" role="alert">{{ listError }}</p>
      <!-- 提交记录列表 -->
      <div class="table-container" style="overflow-x:auto;">
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
                <div style="display:flex; align-items:center; gap:var(--space-1);">
                  <div class="user-avatar-small">{{ submission.username.charAt(0) }}</div>
                  <div>
                    <div style="font-weight: var(--weight-medium);">{{ submission.username }}</div>
                    <div style="font-size:var(--text-caption); color:var(--text-secondary);">{{ submission.user_nickname || '未设置昵称' }}</div>
                  </div>
                </div>
              </td>
              <td>
                <div style="font-size:var(--text-caption);">{{ submission.user_team || '无团队' }}</div>
                <div style="font-size:var(--text-caption); color:var(--admin-primary-color); font-weight: var(--weight-medium);">{{ submission.user_score }}分</div>
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

        <div v-if="!listError && submissions.length === 0" class="empty-state">
          <div class="empty-icon"><AppIcon name="bi-inbox" /></div>
          <p>暂无提交记录</p>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" style="display:flex; justify-content:space-between; align-items:center; margin-top:var(--space-2); padding-top:var(--space-2); border-top:var(--stroke) solid var(--admin-border-color);">
        <div class="pagination-info">
          共 {{ total }} 条记录，每页 {{ pageSize }} 条，第 {{ page }} / {{ totalPages }} 页
        </div>
        <div class="pagination-controls" style="display:flex; gap:var(--space-1); align-items:center;">
          <button class="action-btn btn-default" @click="changePage(page - 1)" :disabled="page === 1">
            上一页
          </button>
          <button class="action-btn btn-default" @click="changePage(1)" :disabled="page === 1">
            1
          </button>
          <span v-if="totalPages > 1" style="padding:0 calc(var(--space-1) / 2);">...</span>
          <button class="action-btn btn-default" @click="changePage(totalPages)" :disabled="page === totalPages">
            {{ totalPages }}
          </button>
          <button class="action-btn btn-default" @click="changePage(page + 1)" :disabled="page === totalPages">
            下一页
          </button>
        </div>
      </div>

      <!-- 统计摘要 -->
      <div class="stats-summary" style="margin-top:var(--space-3); padding-top:var(--space-3); border-top:var(--stroke) solid var(--admin-border-color);">
        <div style="display:flex; gap:var(--space-4);">
          <div>
            <div style="font-size:var(--text-section); font-weight:bold; color:var(--ink-secondary);">{{ stats.correct }}</div>
            <div style="font-size:var(--text-caption); color:var(--text-secondary);">正确提交</div>
          </div>
          <div>
            <div style="font-size:var(--text-section); font-weight:bold; color:var(--ink-muted);">{{ stats.wrong }}</div>
            <div style="font-size:var(--text-caption); color:var(--text-secondary);">错误提交</div>
          </div>
          <div>
            <div style="font-size:var(--text-section); font-weight:bold; color:var(--admin-primary-color);">{{ stats.rate }}%</div>
            <div style="font-size:var(--text-caption); color:var(--text-secondary);">正确率</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import api from '@/api'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import { createAccountGuard } from '@/shared/state/accountScope.js'

const guard = createAccountGuard()
onBeforeUnmount(guard.dispose)
let listGeneration = 0
const listError = ref('')

const submissions = ref([])
const total = ref(0)
const totalPages = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const filterStatus = ref('')
usePageFilters('admin-submissions', { searchKeyword, filterStatus, page, pageSize })

const stats = computed(() => {
  const correct = submissions.value.filter(s => s.is_correct).length
  const wrong = submissions.value.filter(s => !s.is_correct).length
  const rate = submissions.value.length > 0 ? Math.round((correct / submissions.value.length) * 100) : 0
  return { correct, wrong, rate }
})

const fetchSubmissions = async () => {
  const reading = ++listGeneration
  listError.value = ''
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
    if (!guard.current() || reading !== listGeneration) return
    submissions.value = response.results
    total.value = response.total
    totalPages.value = response.total_pages
  } catch (error) {
    if (guard.current() && reading === listGeneration) { submissions.value = []; listError.value = '提交记录读取失败，请重试。' }
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

<style scoped src="../assets/admin.css"></style>

<style scoped>

.user-avatar-small {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:50%;
  background:var(--admin-primary-color);
  display:flex;
  align-items:center;
  justify-content:center;
  color:var(--on-action);
  font-size:var(--text-caption);
  font-weight:bold;
}

.flag-code {
  padding:calc(var(--stroke) * 2) calc(var(--space-1) / 2);
  background:var(--surface);
  border-radius:var(--radius-control);
  font-family:'Courier New', monospace;
  font-size:var(--text-caption);
  color:var(--text-primary);
  max-width:var(--row-value-width);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  display:inline-block;
}

.empty-state {
  text-align:center;
  padding:var(--space-7) var(--space-2);
  color:var(--text-secondary);
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-2);
}
</style>
