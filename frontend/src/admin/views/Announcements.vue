<template>
  <div class="admin-announcements">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">公告管理</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchAnnouncements">
            🔄 刷新
          </button>
          <button class="action-btn btn-primary" @click="handleCreate">
            ➕ 新增公告
          </button>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <select v-model="filters.status" @change="fetchAnnouncements" class="filter-select">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="published">已发布</option>
          <option value="archived">已归档</option>
        </select>
        <select v-model="filters.priority" @change="fetchAnnouncements" class="filter-select">
          <option value="">全部优先级</option>
          <option value="low">普通</option>
          <option value="medium">重要</option>
          <option value="high">紧急</option>
        </select>
      </div>

      <!-- 公告列表 -->
      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="announcements.length === 0" class="empty-state">
        <div class="empty-icon">📢</div>
        <p>暂无公告</p>
      </div>

      <div v-else class="announcement-list">
        <div
          v-for="announcement in announcements"
          :key="announcement.id"
          class="announcement-item"
          :class="{
            'pinned': announcement.is_pinned,
            'priority-high': announcement.priority === 'high',
            'priority-medium': announcement.priority === 'medium',
          }"
        >
          <div class="announcement-header">
            <div class="announcement-info">
              <h4 class="announcement-title">
                <span v-if="announcement.is_pinned" class="pinned-badge">📌</span>
                {{ announcement.title }}
              </h4>
              <div class="announcement-badges">
                <span class="badge" :class="`status-${announcement.status}`">
                  {{ announcement.status_display }}
                </span>
                <span class="badge" :class="`priority-${announcement.priority}`">
                  {{ announcement.priority_display }}
                </span>
              </div>
            </div>
            <div class="announcement-actions">
              <button
                v-if="announcement.status === 'draft'"
                class="action-btn btn-success"
                @click="handlePublish(announcement)"
              >
                发布
              </button>
              <button
                v-if="announcement.status === 'published'"
                class="action-btn btn-warning"
                @click="handleUnpublish(announcement)"
              >
                撤回
              </button>
              <button class="action-btn btn-default" @click="handleEdit(announcement)">
                编辑
              </button>
              <button class="action-btn btn-danger" @click="handleDelete(announcement)">
                删除
              </button>
            </div>
          </div>
          <div class="announcement-summary">
            {{ announcement.summary }}
          </div>
          <div class="announcement-meta">
            <span class="meta-item">作者: {{ announcement.author_name }}</span>
            <span class="meta-item">浏览: {{ announcement.view_count }}</span>
            <span class="meta-item">创建: {{ formatDate(announcement.created_at) }}</span>
            <span class="meta-item" v-if="announcement.published_at">
              发布: {{ formatDate(announcement.published_at) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑/创建弹窗 -->
    <div v-if="showEditorModal" class="modal-overlay" @click.self="showEditorModal = false">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>{{ isEdit ? '编辑公告' : '新增公告' }}</h3>
          <button class="close-btn" @click="showEditorModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">公告标题</label>
              <input
                v-model="formData.title"
                type="text"
                class="form-input"
                placeholder="请输入公告标题"
                maxlength="200"
              />
            </div>
            <div class="form-group">
              <label class="form-label">优先级</label>
              <select v-model="formData.priority" class="form-select">
                <option value="low">普通</option>
                <option value="medium">重要</option>
                <option value="high">紧急</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">状态</label>
              <select v-model="formData.status" class="form-select">
                <option value="draft">草稿</option>
                <option value="published">已发布</option>
                <option value="archived">已归档</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">置顶</label>
              <label class="checkbox-label">
                <input
                  v-model="formData.is_pinned"
                  type="checkbox"
                  class="form-checkbox"
                />
                <span>置顶公告（会始终显示在列表顶部）</span>
              </label>
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label required">公告内容</label>
              <textarea
                v-model="formData.content"
                class="form-textarea"
                rows="10"
                placeholder="请输入公告内容，支持 Markdown 格式"
              ></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showEditorModal = false">取消</button>
          <button class="action-btn btn-primary" @click="handleSave" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'

const announcements = ref([])
const loading = ref(false)
const saving = ref(false)

const filters = ref({
  status: '',
  priority: '',
})

const showEditorModal = ref(false)
const isEdit = ref(false)

const formData = ref({
  id: null,
  title: '',
  content: '',
  priority: 'low',
  status: 'draft',
  is_pinned: false,
})

const fetchAnnouncements = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.priority) params.priority = filters.value.priority

    const response = await api.announcement.list(params)
    announcements.value = response.results || []
  } catch (error) {
    console.error('获取公告列表失败:', error)
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  isEdit.value = false
  formData.value = {
    id: null,
    title: '',
    content: '',
    priority: 'low',
    status: 'draft',
    is_pinned: false,
  }
  showEditorModal.value = true
}

const handleEdit = (announcement) => {
  isEdit.value = true
  formData.value = {
    id: announcement.id,
    title: announcement.title,
    content: announcement.content,
    priority: announcement.priority,
    status: announcement.status,
    is_pinned: announcement.is_pinned,
  }
  showEditorModal.value = true
}

const handleSave = async () => {
  if (!formData.value.title || !formData.value.content) {
    alert('请填写公告标题和内容')
    return
  }

  saving.value = true
  try {
    if (isEdit.value) {
      await api.announcement.update(formData.value.id, formData.value)
    } else {
      await api.announcement.create(formData.value)
    }
    showEditorModal.value = false
    await fetchAnnouncements()
  } catch (error) {
    alert(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

const handlePublish = async (announcement) => {
  if (!confirm(`确定要发布公告"${announcement.title}"吗？`)) return

  try {
    await api.announcement.publish(announcement.id)
    await fetchAnnouncements()
  } catch (error) {
    alert('发布失败')
  }
}

const handleUnpublish = async (announcement) => {
  if (!confirm(`确定要撤回公告"${announcement.title}"吗？`)) return

  try {
    await api.announcement.unpublish(announcement.id)
    await fetchAnnouncements()
  } catch (error) {
    alert('撤回失败')
  }
}

const handleDelete = (announcement) => {
  if (!confirm(`确定要删除公告"${announcement.title}"吗？此操作不可恢复！`)) return

  try {
    api.announcement.delete(announcement.id).then(() => {
      fetchAnnouncements()
    })
  } catch (error) {
    alert('删除失败')
  }
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchAnnouncements()
})
</script>

<style scoped>
.admin-announcements {
  padding: 20px;
}

.page-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  color: #333;
}

.page-actions {
  display: flex;
  gap: 12px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  min-width: 120px;
}

.announcement-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.announcement-item {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.announcement-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.announcement-item.pinned {
  border-left: 4px solid #ff6b6b;
}

.announcement-item.priority-high {
  border-left: 4px solid #ff4757;
}

.announcement-item.priority-medium {
  border-left: 4px solid #ffa502;
}

.announcement-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.announcement-title {
  margin: 0;
  font-size: 18px;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
}

.pinned-badge {
  font-size: 16px;
}

.announcement-badges {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-draft {
  background: #f0f0f0;
  color: #666;
}

.status-published {
  background: #e8f5e9;
  color: #4caf50;
}

.status-archived {
  background: #e0e0e0;
  color: #999;
}

.priority-low {
  background: #e3f2fd;
  color: #2196f3;
}

.priority-medium {
  background: #fff3e0;
  color: #ff9800;
}

.priority-high {
  background: #ffebee;
  color: #f44336;
}

.announcement-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.announcement-summary {
  color: #666;
  margin-bottom: 12px;
  line-height: 1.6;
}

.announcement-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #999;
}

.action-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-default {
  background: #f0f0f0;
  color: #333;
}

.btn-primary {
  background: #2196f3;
  color: white;
}

.btn-success {
  background: #4caf50;
  color: white;
}

.btn-warning {
  background: #ff9800;
  color: white;
}

.btn-danger {
  background: #f44336;
  color: white;
}

.action-btn:hover {
  opacity: 0.8;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #999;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #2196f3;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  max-width: 800px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-large {
  max-width: 1000px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 24px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e0e0e0;
}

.admin-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.form-label {
  font-size: 14px;
  color: #333;
  margin-bottom: 8px;
  font-weight: 500;
}

.form-label.required::after {
  content: ' *';
  color: #f44336;
}

.form-input,
.form-select,
.form-textarea {
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  font-family: inherit;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #2196f3;
}

.form-textarea {
  resize: vertical;
  font-family: inherit;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.form-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
}
</style>
