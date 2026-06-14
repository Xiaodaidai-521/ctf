<template>
  <div class="admin-challenges">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">题目管理</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchChallenges">
            🔄 刷新
          </button>
          <button class="action-btn btn-primary" @click="showCreateModal = true">
            ➕ 新增题目
          </button>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar" style="margin-bottom: 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
        <select v-model="filterCategory" class="form-select" style="width: 150px;">
          <option value="">全部分类</option>
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">
            {{ cat.name }}
          </option>
        </select>
        <select v-model="filterDifficulty" class="form-select" style="width: 120px;">
          <option value="">全部难度</option>
          <option value="easy">简单</option>
          <option value="medium">中等</option>
          <option value="hard">困难</option>
          <option value="expert">专家</option>
        </select>
        <select v-model="filterStatus" class="form-select" style="width: 120px;">
          <option value="">全部状态</option>
          <option value="true">已激活</option>
          <option value="false">未激活</option>
        </select>
        <button class="action-btn btn-primary" @click="fetchChallenges">
          🔍 筛选
        </button>
      </div>

      <!-- 题目列表 -->
      <div class="table-container" style="overflow-x: auto;">
        <table class="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>标题</th>
              <th>分类</th>
              <th>难度</th>
              <th>分数</th>
              <th>镜像信息</th>
              <th>解决人数</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="challenge in challenges" :key="challenge.id">
              <td>{{ challenge.id }}</td>
              <td>
                <strong>{{ challenge.title }}</strong>
              </td>
              <td>
                <span class="badge badge-info">{{ challenge.category_name }}</span>
              </td>
              <td>
                <span class="badge" :class="getDifficultyBadgeClass(challenge.difficulty)">
                  {{ getDifficultyText(challenge.difficulty) }}
                </span>
              </td>
              <td><strong>{{ challenge.score }}</strong></td>
              <td>
                <div v-if="challenge.docker_image" style="font-size: 12px;">
                  <div style="color: var(--text-primary);">🐳 {{ challenge.docker_image }}</div>
                  <div v-if="challenge.redirect_port" style="color: var(--text-secondary);">
                    端口: {{ challenge.redirect_port }}
                    <span v-if="challenge.redirect_type" style="margin-left: 4px;">
                      ({{ getRedirectTypeText(challenge.redirect_type) }})
                    </span>
                  </div>
                </div>
                <span v-else style="color: var(--text-secondary); font-size: 12px;">-</span>
              </td>
              <td>{{ challenge.solve_count }}</td>
              <td>
                <span class="badge" :class="challenge.is_active ? 'badge-success' : 'badge-warning'">
                  {{ challenge.is_active ? '已激活' : '未激活' }}
                </span>
              </td>
              <td>
                <button class="action-btn btn-default" @click="handleEdit(challenge)">
                  ✏️ 编辑
                </button>
                <button class="action-btn btn-danger" @click="handleDelete(challenge)">
                  🗑️ 删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="challenges.length === 0" class="empty-state">
          <div class="empty-icon">📭</div>
          <p>暂无题目数据</p>
        </div>
      </div>
    </div>

    <!-- 编辑题目弹窗 -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>编辑题目</h3>
          <button class="close-btn" @click="showEditModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">标题</label>
              <input v-model="editForm.title" type="text" class="form-input" placeholder="请输入题目标题" />
            </div>
            <div class="form-group">
              <label class="form-label required">分类</label>
              <select v-model="editForm.category" class="form-select">
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                  {{ cat.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label required">难度</label>
              <select v-model="editForm.difficulty" class="form-select">
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
                <option value="expert">专家</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label required">分数</label>
              <input v-model.number="editForm.score" type="number" class="form-input" placeholder="请输入分数" min="0" />
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label required">题目描述</label>
              <textarea v-model="editForm.description" class="form-textarea" rows="6" placeholder="请输入题目描述"></textarea>
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label required">Flag</label>
              <input v-model="editForm.flag" type="text" class="form-input" placeholder="请输入 Flag，例如: flag{...}" />
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label">提示</label>
              <textarea v-model="editForm.hint" class="form-textarea" rows="3" placeholder="请输入提示（可选）"></textarea>
            </div>
            <div class="form-group">
              <label class="form-label">状态</label>
              <select v-model="editForm.is_active" class="form-select">
                <option :value="true">已激活</option>
                <option :value="false">未激活</option>
              </select>
            </div>
          </div>

          <!-- 镜像信息 -->
          <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--admin-border-color);">
            <h4 style="margin: 0 0 16px 0; font-size: 14px; color: var(--text-primary);">🐳 Docker 容器配置</h4>
            <div class="admin-form">
              <div class="form-group">
                <label class="form-label">Docker 镜像名称</label>
                <input v-model="editForm.docker_image" type="text" class="form-input" placeholder="例如: ctf-web-challenge:latest" />
                <small style="color: var(--text-secondary); font-size: 12px;">留空表示非容器题目</small>
              </div>
              <div class="form-group">
                <label class="form-label">容器内部端口</label>
                <input v-model.number="editForm.redirect_port" type="number" class="form-input" placeholder="例如: 80" min="1" max="65535" />
                <small style="color: var(--text-secondary); font-size: 12px;">容器内服务监听的端口</small>
              </div>
              <div class="form-group">
                <label class="form-label">代理类型</label>
                <select v-model="editForm.redirect_type" class="form-select">
                  <option value="">无代理</option>
                  <option value="http">子域名</option>
                  <option value="path">路径路由</option>
                  <option value="direct">直连</option>
                </select>
                <small style="color: var(--text-secondary); font-size: 12px;">选择访问容器的方式</small>
              </div>
            </div>
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

    <!-- 新增题目弹窗 -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>新增题目</h3>
          <button class="close-btn" @click="showCreateModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">标题</label>
              <input v-model="createForm.title" type="text" class="form-input" placeholder="请输入题目标题" />
            </div>
            <div class="form-group">
              <label class="form-label required">分类</label>
              <select v-model="createForm.category" class="form-select">
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                  {{ cat.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label required">难度</label>
              <select v-model="createForm.difficulty" class="form-select">
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
                <option value="expert">专家</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label required">分数</label>
              <input v-model.number="createForm.score" type="number" class="form-input" placeholder="请输入分数" min="0" />
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label required">题目描述</label>
              <textarea v-model="createForm.description" class="form-textarea" rows="6" placeholder="请输入题目描述"></textarea>
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label required">Flag</label>
              <input v-model="createForm.flag" type="text" class="form-input" placeholder="请输入 Flag，例如: flag{...}" />
            </div>
            <div class="form-group" style="grid-column: 1 / -1;">
              <label class="form-label">提示</label>
              <textarea v-model="createForm.hint" class="form-textarea" rows="3" placeholder="请输入提示（可选）"></textarea>
            </div>
            <div class="form-group">
              <label class="form-label">状态</label>
              <select v-model="createForm.is_active" class="form-select">
                <option :value="true">已激活</option>
                <option :value="false">未激活</option>
              </select>
            </div>
          </div>

          <!-- 镜像信息 -->
          <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--admin-border-color);">
            <h4 style="margin: 0 0 16px 0; font-size: 14px; color: var(--text-primary);">🐳 Docker 容器配置</h4>
            <div class="admin-form">
              <div class="form-group">
                <label class="form-label">Docker 镜像名称</label>
                <input v-model="createForm.docker_image" type="text" class="form-input" placeholder="例如: ctf-web-challenge:latest" />
                <small style="color: var(--text-secondary); font-size: 12px;">留空表示非容器题目</small>
              </div>
              <div class="form-group">
                <label class="form-label">容器内部端口</label>
                <input v-model.number="createForm.redirect_port" type="number" class="form-input" placeholder="例如: 80" min="1" max="65535" />
                <small style="color: var(--text-secondary); font-size: 12px;">容器内服务监听的端口</small>
              </div>
              <div class="form-group">
                <label class="form-label">代理类型</label>
                <select v-model="createForm.redirect_type" class="form-select">
                  <option value="">无代理</option>
                  <option value="http">子域名</option>
                  <option value="path">路径路由</option>
                  <option value="direct">直连</option>
                </select>
                <small style="color: var(--text-secondary); font-size: 12px;">选择访问容器的方式</small>
              </div>
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
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useChallengeStore } from '@/store/challenge'
import api from '@/api'

const challengeStore = useChallengeStore()

const challenges = ref([])
const categories = ref([])

const filterCategory = ref('')
const filterDifficulty = ref('')
const filterStatus = ref('')

const showEditModal = ref(false)
const showCreateModal = ref(false)
const saving = ref(false)
const creating = ref(false)

const editForm = ref({
  id: null,
  title: '',
  category: null,
  difficulty: 'easy',
  score: 10,
  description: '',
  flag: '',
  hint: '',
  is_active: true,
  docker_image: '',
  redirect_port: null,
  redirect_type: ''
})

const createForm = ref({
  title: '',
  category: null,
  difficulty: 'easy',
  score: 10,
  description: '',
  flag: '',
  hint: '',
  is_active: true,
  docker_image: '',
  redirect_port: null,
  redirect_type: ''
})

const fetchCategories = async () => {
  try {
    const response = await api.challenge.getCategories()
    categories.value = response.results || []
  } catch (error) {
    console.error('获取分类失败:', error)
  }
}

const fetchChallenges = async () => {
  try {
    const params = {}
    if (filterCategory.value) params.category = filterCategory.value
    if (filterDifficulty.value) params.difficulty = filterDifficulty.value

    const response = await api.challenge.getChallenges(params)
    challenges.value = response.results || []
    total.value = response.count || 0
  } catch (error) {
    console.error('获取题目列表失败:', error)
  }
}

const handleEdit = async (challenge) => {
  try {
    // 获取完整的题目详情
    const detail = await api.challenge.getChallengeDetail(challenge.id)
    editForm.value = {
      id: detail.id,
      title: detail.title,
      category: detail.category,
      difficulty: detail.difficulty,
      score: detail.score,
      description: detail.description || '',
      flag: detail.flag || '',
      hint: detail.hint || '',
      is_active: detail.is_active,
      docker_image: detail.docker_image || '',
      redirect_port: detail.redirect_port || null,
      redirect_type: detail.redirect_type || ''
    }
    showEditModal.value = true
  } catch (error) {
    console.error('获取题目详情失败:', error)
    alert('获取题目详情失败')
  }
}

const handleSave = async () => {
  if (!editForm.value.title || !editForm.value.flag) {
    alert('请填写必填项')
    return
  }
  saving.value = true
  try {
    await api.challenge.update(editForm.value.id, editForm.value)
    alert('保存成功')
    showEditModal.value = false
    await fetchChallenges()
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

const handleDelete = async (challenge) => {
  if (confirm(`确定要删除题目 "${challenge.title}" 吗？此操作不可恢复。`)) {
    try {
      await api.challenge.delete(challenge.id)
      alert('删除成功')
      await fetchChallenges()
    } catch (error) {
      console.error('删除失败:', error)
      alert('删除失败: ' + (error.response?.data?.detail || error.message))
    }
  }
}

const handleCreate = async () => {
  if (!createForm.value.title || !createForm.value.flag) {
    alert('请填写必填项')
    return
  }
  creating.value = true
  try {
    await api.challenge.create(createForm.value)
    alert('创建成功')
    showCreateModal.value = false
    createForm.value = {
      title: '',
      category: null,
      difficulty: 'easy',
      score: 10,
      description: '',
      flag: '',
      hint: '',
      is_active: true,
      docker_image: '',
      redirect_port: null,
      redirect_type: ''
    }
    await fetchChallenges()
  } catch (error) {
    console.error('创建失败:', error)
    alert('创建失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    creating.value = false
  }
}

const getDifficultyText = (difficulty) => {
  const map = { 'easy': '简单', 'medium': '中等', 'hard': '困难', 'expert': '专家' }
  return map[difficulty] || '未知'
}

const getDifficultyBadgeClass = (difficulty) => {
  const map = {
    'easy': 'badge-success',
    'medium': 'badge-warning',
    'hard': 'badge-error',
    'expert': 'badge-info'
  }
  return map[difficulty] || 'badge-info'
}

const getRedirectTypeText = (type) => {
  const map = {
    'http': '子域名',
    'path': '路径路由',
    'direct': '直连'
  }
  return map[type] || type
}

onMounted(async () => {
  await Promise.all([fetchCategories(), fetchChallenges()])
})
</script>

<style scoped>
@import '../assets/admin.css';

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
  max-width: 600px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-large {
  max-width: 800px;
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
