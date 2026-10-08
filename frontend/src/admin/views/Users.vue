<template>
  <div class="admin-users">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">用户管理</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchUsers">
            馃攧 刷新
          </button>
          <button class="action-btn btn-primary" @click="showCreateModal = true">
            鉃?新增用户
          </button>
        </div>
      </div>

      <section class="application-panel">
        <div class="application-header"><div><h4>Pending teacher applications</h4><p>Approve an application to grant teacher access.</p></div><button class="action-btn btn-default" @click="fetchTeacherApplications" :disabled="applicationsLoading">{{ applicationsLoading ? 'Loading...' : 'Refresh applications' }}</button></div>
        <p v-if="applicationsError" class="application-error">{{ applicationsError }}</p>
        <div v-else-if="teacherApplications.length" class="application-list"><div v-for="application in teacherApplications" :key="application.id" class="application-item"><div><strong>{{ application.nickname || application.username }}</strong><span>{{ application.username }} · {{ application.email }}</span></div><div><button class="action-btn btn-primary" :disabled="processingApplicationId === application.id" @click="reviewTeacherApplication(application, 'approve')">Approve</button><button class="action-btn btn-danger" :disabled="processingApplicationId === application.id" @click="reviewTeacherApplication(application, 'reject')">Reject</button></div></div></div>
        <p v-else class="application-empty">No teacher applications are awaiting review.</p>
      </section>
      <!-- 鎼滅储鍜岀瓫閫?-->
      <div class="filter-bar" style="margin-bottom: 20px; display: flex; gap: 12px;">
        <input
          v-model="searchKeyword"
          type="text"
          class="form-input"
          placeholder="搜索用户名或邮箱..."
          style="flex: 1; max-width: 300px;"
          @keyup.enter="fetchUsers"
        />
        <button class="action-btn btn-primary" @click="fetchUsers">
          馃攳 搜索
        </button>
      </div>

      <!-- 用户列表 -->
      <div class="table-container" style="overflow-x: auto;">
        <table class="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>鐢ㄦ埛鍚?</th>
              <th>昵称</th>
              <th>邮箱</th>
              <th>积分</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td>{{ user.id }}</td>
              <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <div class="user-avatar-small">{{ user.username.charAt(0) }}</div>
                  <span>{{ user.username }}</span>
                </div>
              </td>
              <td>{{ user.nickname || '-' }}</td>
              <td>{{ user.email }}</td>
              <td><strong>{{ user.score }}</strong></td>
              <td>{{ formatDate(user.created_at) }}</td>
              <td>
                <button class="action-btn btn-default" @click="handleEdit(user)">
                  鉁忥笍 编辑
                </button>
                <button class="action-btn btn-danger" @click="handleDelete(user)" :disabled="user.id === currentUserId">
                  馃棏锔?删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="users.length === 0" class="empty-state">
          <div class="empty-icon">馃摥</div>
          <p>暂无用户数据</p>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" style="display: flex; justify-content: space-between; align-items: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--admin-border-color);">
        <div class="pagination-info">
          鍏?{{ total }} 鏉¤褰?        </div>
        <div class="pagination-controls" style="display: flex; gap: 8px;">
          <button class="action-btn btn-default" @click="changePage(page - 1)" :disabled="page === 1">
            涓婁竴椤?          </button>
          <span style="padding: 8px 16px;">绗?{{ page }} 椤?</span>
          <button class="action-btn btn-default" @click="changePage(page + 1)" :disabled="page * pageSize >= total">
            涓嬩竴椤?          </button>
        </div>
      </div>
    </div>

    <!-- 编辑用户弹窗 -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>编辑用户</h3>
          <button class="close-btn" @click="showEditModal = false">鉁?</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label">鐢ㄦ埛鍚?</label>
              <input v-model="editForm.username" type="text" class="form-input" disabled />
            </div>
            <div class="form-group">
              <label class="form-label">昵称</label>
              <input v-model="editForm.nickname" type="text" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">邮箱</label>
              <input v-model="editForm.email" type="email" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">战队</label>
              <input v-model="editForm.team" type="text" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">角色</label>
              <select v-model="editForm.role" class="form-select">
                <option value="student">用户</option>
                <option value="teacher">教师</option>
                <option value="admin">绠＄悊鍛?</option>
              </select>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showEditModal = false">取消</button>
          <button class="action-btn btn-primary" @click="handleSave" :disabled="saving">
            {{ saving ? '淇濆瓨涓?..' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新增用户弹窗 -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>新增用户</h3>
          <button class="close-btn" @click="showCreateModal = false">鉁?</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label required">鐢ㄦ埛鍚?</label>
              <input v-model="createForm.username" type="text" class="form-input" placeholder="请输入用户名" />
            </div>
            <div class="form-group">
              <label class="form-label required">密码</label>
              <input v-model="createForm.password" type="password" class="form-input" placeholder="璇疯緭鍏ュ瘑鐮" />
            </div>
            <div class="form-group">
              <label class="form-label">昵称</label>
              <input v-model="createForm.nickname" type="text" class="form-input" placeholder="璇疯緭鍏ユ樀绉" />
            </div>
            <div class="form-group">
              <label class="form-label required">邮箱</label>
              <input v-model="createForm.email" type="email" class="form-input" placeholder="璇疯緭鍏ラ偖绠" />
            </div>
            <div class="form-group">
              <label class="form-label">战队</label>
              <input v-model="createForm.team" type="text" class="form-input" placeholder="璇疯緭鍏ユ垬闃熷悕绉" />
            </div>
            <div class="form-group">
              <label class="form-label">角色</label>
              <select v-model="createForm.role" class="form-select">
                <option value="student">用户</option>
                <option value="teacher">教师</option>
                <option value="admin">绠＄悊鍛?</option>
              </select>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showCreateModal = false">取消</button>
          <button class="action-btn btn-primary" @click="handleCreate" :disabled="creating">
            {{ creating ? '鍒涘缓涓?..' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useUserStore } from '@/store/user'
import api from '@/api'

const userStore = useUserStore()

const users = ref([])
const teacherApplications = ref([])
const applicationsLoading = ref(false)
const applicationsError = ref('')
const processingApplicationId = ref(null)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')

const showEditModal = ref(false)
const showCreateModal = ref(false)
const saving = ref(false)
const creating = ref(false)

const editForm = ref({
  id: null,
  username: '',
  nickname: '',
  email: '',
  team: '',
  role: 'student'
})

const createForm = ref({
  username: '',
  password: '',
  nickname: '',
  email: '',
  team: '',
  role: 'student'
})

const currentUserId = computed(() => userStore.userInfo?.id)

const fetchUsers = async () => {
  try {
    const response = await api.user.adminUsers({
      page: page.value,
      page_size: pageSize.value,
      search: searchKeyword.value
    })
    users.value = response.users
    total.value = response.total
  } catch (error) {
    console.error('获取用户列表失败:', error)
  }
}


const fetchTeacherApplications = async () => {
  applicationsLoading.value = true
  applicationsError.value = ''
  try {
    const response = await api.user.teacherApplications()
    teacherApplications.value = Array.isArray(response) ? response : response.applications || response.users || []
  } catch (error) {
    applicationsError.value = error.response?.data?.error || 'Unable to load teacher applications.'
  } finally {
    applicationsLoading.value = false
  }
}

const reviewTeacherApplication = async (application, action) => {
  if (!confirm('Confirm this action?')) return
  processingApplicationId.value = application.id
  try {
    if (action === 'approve') await api.user.approveTeacherApplication(application.id)
    else await api.user.rejectTeacherApplication(application.id)
    await Promise.all([fetchTeacherApplications(), fetchUsers()])
  } catch (error) {
    alert(error.response?.data?.error || `Unable to ${action} teacher application.`)
  } finally {
    processingApplicationId.value = null
  }
}
const handleEdit = (user) => {
  editForm.value = { ...user }
  showEditModal.value = true
}

const handleSave = async () => {
  saving.value = true
  try {
    await api.user.adminUpdate(editForm.value.id, {
      nickname: editForm.value.nickname,
      email: editForm.value.email,
      team: editForm.value.team,
      role: editForm.value.role
    })
    showEditModal.value = false
    await fetchUsers()
    alert('保存成功')
  } catch (error) {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

const handleDelete = async (user) => {
  if (!confirm('Confirm this action?')) return
  try {
    const res = await api.user.adminDelete(user.id)
    alert(res?.message || '删除成功')
    fetchUsers()
  } catch (e) {
    const msg = e.response?.data?.error || e.response?.statusText || e.message || '未知错误'
    alert('删除失败: ' + msg)
  }
}

const handleCreate = async () => {
  if (!createForm.value.username || !createForm.value.password || !createForm.value.email) {
    alert('请填写必填项')
    return
  }
  creating.value = true
  try {
    await api.user.adminCreate(createForm.value)
    alert('创建成功')
    showCreateModal.value = false
    createForm.value = {
      username: '',
      password: '',
      nickname: '',
      email: '',
      team: '',
      role: 'student'
    }
    await fetchUsers()
  } catch (error) {
    const msg = error.response?.data?.username?.[0] || error.response?.data?.error || '创建失败'
    alert(msg)
  } finally {
    creating.value = false
  }
}

const changePage = (newPage) => {
  page.value = newPage
  fetchUsers()
}

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchUsers()
  fetchTeacherApplications()
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

.application-panel { margin-bottom: 24px; padding: 18px; border: 1px solid var(--admin-border-color); border-radius: 8px; background: rgba(255, 255, 255, 0.5); }
.application-header, .application-item { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.application-header h4 { margin: 0; font-size: 16px; }.application-header p, .application-item span, .application-empty { margin: 4px 0 0; color: var(--text-secondary); font-size: 13px; }.application-item span { display: block; }.application-list { margin-top: 14px; border-top: 1px solid var(--admin-border-color); }.application-item { padding: 14px 0; border-bottom: 1px solid var(--admin-border-color); }.application-item button + button { margin-left: 8px; }.application-error { color: var(--error-color); font-size: 13px; }
</style>





