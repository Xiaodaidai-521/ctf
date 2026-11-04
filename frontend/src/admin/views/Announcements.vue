<template>
  <div class="admin-announcements">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">公告管理</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchAnnouncements">
            <AppIcon name="bi-arrow-clockwise" /> 刷新
          </button>
          <button class="action-btn btn-primary" @click="handleCreate">
            <AppIcon name="bi-plus" /> 新增公告
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
        <div class="empty-icon"><AppIcon name="bi-megaphone" /></div>
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
                <span v-if="announcement.is_pinned" class="pinned-badge"><AppIcon name="bi-pin-angle" /></span>
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
          <button class="close-btn" @click="showEditorModal = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
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
            <div class="form-group" style="grid-column:1 / -1;">
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
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import api from '@/api'

const announcements = ref([])
const loading = ref(false)
const saving = ref(false)

const filters = ref({
  status: '',
  priority: '',
})

usePageFilters('admin-announcements', { filters })
const guard = createAccountGuard()
onBeforeUnmount(guard.dispose)
let request = 0
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
  const current = ++request
  loading.value = true
  try {
    const params = {}
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.priority) params.priority = filters.value.priority

    const response = await api.announcement.list(params)
    if (!guard.current() || current !== request) return
    announcements.value = response.results || []
  } catch (error) {
    console.error('获取公告列表失败:', error)
  } finally {
    if (guard.current() && current === request) loading.value = false
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
  padding:var(--space-2);
}

.page-card {
  background:var(--surface);
  border-radius:var(--radius-control);
  box-shadow: var(--shadow-raised);
  padding:var(--space-3);
}

.page-header {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-2);
  justify-content:space-between;
  align-items:center;
  margin-bottom:var(--space-3);
}

.page-title {
  margin:0;
  font-size:var(--text-section);
  color:var(--ink);
}

.page-actions {
  display:flex;
  gap:var(--space-1);
}

.filter-bar {
  display:flex;
  gap:var(--space-1);
  margin-bottom:var(--space-3);
}

.filter-select {
  padding:var(--space-1) var(--space-1);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  min-width:var(--row-label-width);
}

.announcement-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.announcement-item {
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-2);
  transition:all var(--motion-normal);
}

.announcement-item:hover {
  box-shadow: var(--shadow-raised);
}

.announcement-item.pinned {
  border-left:calc(var(--space-1) / 2) solid var(--line);
}

.announcement-item.priority-high {
  border-left:calc(var(--space-1) / 2) solid var(--negative);
}

.announcement-item.priority-medium {
  border-left:calc(var(--space-1) / 2) solid var(--warning);
}

.announcement-header {
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  margin-bottom:var(--space-1);
}

.announcement-title {
  margin:0;
  font-size:var(--text-card);
  color:var(--ink);
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.pinned-badge {
  font-size:var(--text-body);
}

.announcement-badges {
  display:flex;
  gap:var(--space-1);
  margin-top:var(--space-1);
}

.badge {
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
}

.status-draft {
  background:var(--surface);
  color:var(--ink-secondary);
}

.status-published {
  background:var(--positive-soft);
  color:var(--positive);
}

.status-archived {
  background:var(--surface);
  color:var(--ink-muted);
}

.priority-low {
  background:var(--surface);
  color:var(--action);
}

.priority-medium {
  background:var(--warning-soft);
  color:var(--warning);
}

.priority-high {
  background:var(--negative-soft);
  color:var(--negative);
}

.announcement-actions {
  display:flex;
  gap:var(--space-1);
  flex-shrink:0;
}

.announcement-summary {
  color:var(--ink-secondary);
  margin-bottom:var(--space-1);
  line-height:1.6;
}

.announcement-meta {
  display:flex;
  gap:var(--space-2);
  font-size:var(--text-caption);
  color:var(--ink-muted);
}

.action-btn {
  padding:var(--space-1) var(--space-2);
  border:none;
  border-radius:var(--radius-control);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
}

.btn-default {
  background:var(--surface);
  color:var(--ink);
}

.btn-primary {
  background:var(--action);
  color:var(--on-action);
}

.btn-success {
  background:var(--positive);
  color:var(--on-action);
}

.btn-warning {
  background:var(--warning);
  color:var(--on-action);
}

.btn-danger {
  background:var(--negative);
  color:var(--on-action);
}

.action-btn:hover {
  opacity:0.8;
}

.action-btn:disabled {
  opacity:0.5;
  cursor:not-allowed;
}

.loading-state,
.empty-state {
  text-align:center;
  padding:var(--space-7) var(--space-2);
  color:var(--ink-muted);
}

.loading-spinner {
  width:var(--space-5);
  height:var(--space-5);
  border:calc(var(--space-1) / 2) solid var(--line);
  border-top:calc(var(--space-1) / 2) solid var(--line);
  border-radius:50%;
  animation:spin var(--motion-loop) linear infinite;
  margin:0 auto var(--space-2);
}

@keyframes spin {
  0% { transform:rotate(0deg); }
  100% { transform:rotate(360deg); }
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-2);
}

.modal-overlay {
  position:fixed;
  top:0;
  left:0;
  right:0;
  bottom:0;
  background:var(--overlay);
  display:flex;
  align-items:center;
  justify-content:center;
  z-index:var(--z-overlay);
}

.modal-content {
  background:var(--surface);
  border-radius:var(--radius-control);
  max-width:var(--reading-width);
  width:90%;
  max-height:90vh;
  overflow-y:auto;
}

.modal-large {
  max-width:var(--reading-width);
}

.modal-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:var(--space-2) var(--space-3);
  border-bottom:var(--stroke) solid var(--line);
}

.modal-header h3 {
  margin:0;
  font-size:var(--text-card);
}

.close-btn {
  background:none;
  border:none;
  font-size:var(--text-section);
  cursor:pointer;
  color:var(--ink-muted);
}

.close-btn:hover {
  color:var(--ink);
}

.modal-body {
  padding:var(--space-3);
}

.modal-footer {
  display:flex;
  justify-content:flex-end;
  gap:var(--space-1);
  padding:var(--space-2) var(--space-3);
  border-top:var(--stroke) solid var(--line);
}

.admin-form {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:var(--space-2);
}

.form-group {
  display:flex;
  flex-direction:column;
}

.form-label {
  font-size:var(--text-caption);
  color:var(--ink);
  margin-bottom:var(--space-1);
  font-weight: var(--weight-medium);
}

.form-label.required::after {
  content:' *';
  color:var(--ink-muted);
}

.form-input,
.form-select,
.form-textarea {
  padding:var(--space-1) var(--space-1);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-family: var(--font-family);
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline-offset:var(--focus-offset);
  border-color:var(--line);
}

.form-textarea {
  resize:vertical;
  font-family: var(--font-family);
}

.checkbox-label {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  cursor:pointer;
}

.form-checkbox {
  width:var(--space-2);
  height:var(--space-2);
  cursor:pointer;
}
</style>
