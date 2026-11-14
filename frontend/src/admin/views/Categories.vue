<template>
  <div class="admin-categories">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">分类管理</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchCategories">
            <AppIcon name="bi-arrow-clockwise" /> 刷新
          </button>
          <button class="action-btn btn-primary" disabled title="分类写入功能尚未开放">
            <AppIcon name="bi-plus" /> 新增分类
          </button>
        </div>
      </div>

      <p role="status">当前仅支持查看分类。新增、编辑和删除尚未开放。</p>
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
            <button class="action-btn btn-default" disabled title="分类写入功能尚未开放">
              <AppIcon name="bi-pencil" /> 编辑
            </button>
            <button class="action-btn btn-danger" disabled title="分类写入功能尚未开放">
              <AppIcon name="bi-trash" /> 删除
            </button>
          </div>
        </div>
      </div>

      <div v-if="categories.length === 0" class="empty-state">
        <div class="empty-icon"><AppIcon name="bi-inbox" /></div>
        <p>暂无分类数据</p>
      </div>
    </div>

    <!-- 编辑分类弹窗 -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>编辑分类</h3>
          <button class="close-btn" @click="showEditModal = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">分类名称</label>
              <input v-model="editForm.name" type="text" class="form-input" placeholder="请输入分类名称" />
            </div>
            <div class="form-group" style="grid-column:1 / -1;">
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
          <button class="close-btn" @click="showCreateModal = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">分类名称</label>
              <input v-model="createForm.name" type="text" class="form-input" placeholder="请输入分类名称，例如: Web" />
            </div>
            <div class="form-group" style="grid-column:1 / -1;">
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
    alert('分类修改尚未开放，本次内容未保存。')
  } catch (error) {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

const handleDelete = (category) => {
  if (confirm(`确定要删除分类 ${category.name} 吗？`)) {
    alert('分类删除尚未开放，未删除任何分类。')
  }
}

const handleCreate = async () => {
  if (!createForm.value.name) {
    alert('请填写分类名称')
    return
  }
  creating.value = true
  try {
    alert('分类新增尚未开放，本次内容未保存。')
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

<style scoped src="../assets/admin.css"></style>

<style scoped>

.category-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.category-item-card {
  background:var(--surface);
  border:var(--stroke) solid var(--admin-border-color);
  border-radius:var(--radius-control);
  padding:var(--space-2);
  transition:all var(--motion-normal);
}

.category-item-card:hover {
  box-shadow: var(--shadow-raised);
}

.category-header {
  display:flex;
  justify-content:space-between;
  align-items:start;
  margin-bottom:var(--space-2);
}

.category-info {
  flex:1;
}

.category-name {
  font-size:var(--text-card);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
  margin-bottom:var(--space-1);
}

.category-description {
  font-size:var(--text-caption);
  color:var(--text-secondary);
  line-height:1.5;
}

.category-stats {
  display:flex;
  gap:var(--space-3);
  padding-left:var(--space-3);
}

.category-stat {
  display:flex;
  flex-direction:column;
  align-items:center;
}

.stat-value {
  font-size:var(--text-section);
  font-weight:bold;
  color:var(--admin-primary-color);
}

.stat-label {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.category-actions {
  display:flex;
  gap:var(--space-1);
  padding-top:var(--space-2);
  border-top:var(--stroke) solid var(--line);
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
  z-index:2000;
}

.modal-content {
  background:var(--surface);
  border-radius:var(--radius-control);
  width:100%;
  max-width:var(--message-width);
  max-height:90vh;
  overflow:hidden;
  display:flex;
  flex-direction:column;
}

.modal-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:var(--space-2) var(--space-3);
  border-bottom:var(--stroke) solid var(--admin-border-color);
}

.modal-header h3 {
  margin:0;
  font-size:var(--text-body);
  font-weight: var(--weight-strong);
}

.close-btn {
  border:none;
  background:none;
  font-size:var(--text-card);
  cursor:pointer;
  color:var(--text-secondary);
  transition:color var(--motion-normal);
}

.close-btn:hover {
  color:var(--text-primary);
}

.modal-body {
  padding:var(--space-3);
  overflow-y:auto;
  flex:1;
}

.modal-footer {
  display:flex;
  justify-content:flex-end;
  gap:var(--space-1);
  padding:var(--space-2) var(--space-3);
  border-top:var(--stroke) solid var(--admin-border-color);
}
</style>
