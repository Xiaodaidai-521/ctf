<template>
  <div class="admin-categories">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">分类管理</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchCategories">
            🔄 刷新
          </button>
          <button class="action-btn btn-primary" @click="showCreateModal = true">
            ➕ 新增分类
          </button>
        </div>
      </div>

      <!-- 分类列表 -->
      <div class="category-list">
        <div
          v-for="category in categories"
          :key="category.id"
          class="category-item-card"
        >
          <div class="category-header">
            <div class="category-info">
              <div class="category-name">{{ category.name }}</div>
              <div class="category-description">{{ category.description || '暂无描述' }}</div>
            </div>
            <div class="category-stats">
              <div class="category-stat">
                <span class="stat-value">{{ category.challenge_count || 0 }}</span>
                <span class="stat-label">题目</span>
              </div>
            </div>
          </div>
          <div class="category-actions">
            <button class="action-btn btn-default" @click="handleEdit(category)">
              ✏️ 编辑
            </button>
            <button class="action-btn btn-danger" @click="handleDelete(category)">
              🗑️ 删除
            </button>
          </div>
        </div>
      </div>

      <div v-if="categories.length === 0" class="empty-state">
        <div class="empty-icon">📭</div>
        <p>暂无分类数据</p>
      </div>
    </div>

    <!-- 编辑分类弹窗 -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>编辑分类</h3>
          <button class="close-btn" @click="showEditModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">分类名称</label>
              <input v-model="editForm.name" type="text" class="form-input" placeholder="请输入分类名称" />
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label">分类描述</label>
              <textarea v-model="editForm.description" class="form-textarea" rows="4" placeholder="请输入分类描述（可选）"></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showEditModal = false">取消</button>
          <button class="action-btn btn-primary" @click="handleSave" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新增分类弹窗 -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>新增分类</h3>
          <button class="close-btn" @click="showCreateModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">分类名称</label>
              <input v-model="createForm.name" type="text" class="form-input" placeholder="请输入分类名称，例如: Web" />
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label">分类描述</label>
              <textarea v-model="createForm.description" class="form-textarea" rows="4" placeholder="请输入分类描述（可选）"></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showCreateModal = false">取消</button>
          <button class="action-btn btn-primary" @click="handleCreate" :disabled="creating">
            {{ creating ? '创建中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'

const categories = ref([])

const showEditModal = ref(false)
const showCreateModal = ref(false)
const saving = ref(false)
const creating = ref(false)

const editForm = ref({
  id: null,
  name: '',
  description: ''
})

const createForm = ref({
  name: '',
  description: ''
})

const fetchCategories = async () => {
  try {
    const response = await api.challenge.getCategories()
    categories.value = response.results || []
  } catch (error) {
    console.error('获取分类列表失败:', error)
  }
}

const handleEdit = (category) => {
  editForm.value = {
    id: category.id,
    name: category.name,
    description: category.description
  }
  showEditModal.value = true
}

const handleSave = async () => {
  if (!editForm.value.name) {
    alert('请填写分类名称')
    return
  }
  saving.value = true
  try {
    // 这里应该调用更新分类的 API
    alert('保存成功（需要后端 API 支持）')
    showEditModal.value = false
    await fetchCategories()
  } catch (error) {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

const handleDelete = (category) => {
  if (confirm(`确定要删除分类 ${category.name} 吗？`)) {
    alert('删除功能需要后端 API 支持')
  }
}

const handleCreate = async () => {
  if (!createForm.value.name) {
    alert('请填写分类名称')
    return
  }
  creating.value = true
  try {
    // 这里应该调用创建分类的 API
    alert('创建功能需要后端 API 支持')
    showCreateModal.value = false
    createForm.value = {
      name: '',
      description: ''
    }
    await fetchCategories()
  } catch (error) {
    alert('创建失败')
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  fetchCategories()
})
</script>

<style scoped>
@import '../assets/admin.css';

.category-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.category-item-card {
  background: white;
  border: 1px solid var(--admin-border-color);
  border-radius: 6px;
  padding: 20px;
  transition: all 0.3s;
}

.category-item-card:hover {
  box-shadow: 0 2px 8px rgba(0, 21, 41, 0.12);
}

.category-header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  margin-bottom: 16px;
}

.category-info {
  flex: 1;
}

.category-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.category-description {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.category-stats {
  display: flex;
  gap: 24px;
  padding-left: 24px;
}

.category-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--admin-primary-color);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.category-actions {
  display: flex;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
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
  z-index: 2000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--admin-border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  border: none;
  background: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: color 0.3s;
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--admin-border-color);
}
</style>
