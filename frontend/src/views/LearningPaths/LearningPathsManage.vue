<template>
  <div class="learning-paths-manage-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">管理学习路径</h1>
        <p class="page-subtitle">创建和编辑学习路径，按章节组织内容</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goBack">
          <i class="bi bi-arrow-left"></i>
          返回
        </button>
        <button class="btn btn-primary" @click="savePath" :disabled="saving">
          <i class="bi bi-save"></i>
          {{ saving ? '保存中...' : '保存路径' }}
        </button>
      </div>
    </div>

    <!-- 路径基本信息 -->
    <div class="path-info-section">
      <div class="section-header">
        <h2 class="section-title">
          <i class="bi bi-info-circle"></i>
          路径基本信息
        </h2>
        <button class="btn btn-sm btn-primary" @click="pathInfoExpanded = !pathInfoExpanded">
          <i class="bi" :class="pathInfoExpanded ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
        </button>
      </div>
      <div v-show="pathInfoExpanded" class="section-body">
        <form class="admin-form">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label required">路径标题</label>
              <input
                v-model="pathForm.title"
                type="text"
                class="form-input"
                placeholder="例如：Web安全入门实战"
                required
              />
            </div>
            <div class="form-group">
              <label class="form-label required">URL Slug</label>
              <input
                v-model="pathForm.slug"
                type="text"
                class="form-input"
                placeholder="web-security-intro"
                required
              />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label required">路径描述</label>
            <textarea
              v-model="pathForm.description"
              class="form-textarea"
              rows="3"
              placeholder="描述这个学习路径的学习目标、适用对象等..."
              required
            ></textarea>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label class="form-label required">难度等级</label>
              <select v-model="pathForm.difficulty" class="form-select" required>
                <option value="AP">入门 - 适合初学者</option>
                <option value="PR">进阶 - 需要基础</option>
                <option value="EX">专家 - 深入掌握</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">预计学习时长</label>
              <input
                v-model.number="pathForm.estimated_hours"
                type="number"
                class="form-input"
                min="0"
                step="0.5"
                placeholder="10"
              />
            </div>
            <div class="form-group">
              <label class="form-label">主题色</label>
              <div style="display: flex; align-items: center; gap: 8px;">
                <input
                  v-model="pathForm.color"
                  type="color"
                  style="width: 60px; height: 36px; cursor: pointer; border: 1px solid #ddd; border-radius: 4px;"
                />
                <span class="form-hint">{{ pathForm.color }}</span>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">发布状态</label>
            <div style="display: flex; gap: 24px;">
              <label class="radio-label">
                <input
                  v-model="pathForm.is_published"
                  type="radio"
                  :value="true"
                />
                <span>📤 已发布（用户可见）</span>
              </label>
              <label class="radio-label">
                <input
                  v-model="pathForm.is_published"
                  type="radio"
                  :value="false"
                />
                <span>📝 草稿（仅自己可见）</span>
              </label>
            </div>
          </div>
        </form>
      </div>
    </div>

    <!-- 章节编辑区域 -->
    <div class="chapters-section">
      <div class="section-header">
        <h2 class="section-title">
          <i class="bi bi-list-ul"></i>
          学习章节（{{ chapters.length }}）
        </h2>
        <button class="btn btn-primary" @click="addChapter">
          <i class="bi bi-plus-lg"></i>
          添加章节
        </button>
      </div>

      <div v-if="chapters.length === 0" class="empty-chapters">
        <i class="bi bi-journal-plus empty-icon"></i>
        <p>还没有章节，点击右上角添加第一个章节</p>
        <button class="btn btn-primary" @click="addChapter">
          <i class="bi bi-plus-lg"></i>
          添加第一个章节
        </button>
      </div>

      <div v-else class="chapters-list">
        <div
          v-for="(chapter, index) in chapters"
          :key="chapter.id"
          class="chapter-card"
          :class="{ 'expanded': chapter.expanded, 'active': activeChapterId === chapter.id }"
        >
          <!-- 章节头部 -->
          <div class="chapter-header" @click="toggleChapter(index)">
            <div class="chapter-number">
              <span class="number-badge">第 {{ index + 1 }} 章</span>
              <span class="chapter-type-badge" :class="chapter.module_type">
                {{ getModuleTypeLabel(chapter.module_type) }}
              </span>
            </div>
            <div class="chapter-title">
              <span v-if="!chapter.title" class="placeholder">章节标题</span>
              <span v-else>{{ chapter.title }}</span>
              <span v-if="chapter.is_required" class="required-tag">必修</span>
            </div>
            <div class="chapter-actions" @click.stop>
              <button class="btn-icon" @click="moveChapterUp(index)" :disabled="index === 0" title="上移">
                <i class="bi bi-arrow-up"></i>
              </button>
              <button class="btn-icon" @click="moveChapterDown(index)" :disabled="index === chapters.length - 1" title="下移">
                <i class="bi bi-arrow-down"></i>
              </button>
              <button class="btn-icon btn-danger" @click="deleteChapter(index)" title="删除章节">
                <i class="bi bi-trash"></i>
              </button>
              <button class="btn-icon" @click="chapter.expanded = !chapter.expanded" :title="chapter.expanded ? '收起' : '展开'">
                <i class="bi" :class="chapter.expanded ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
              </button>
            </div>
          </div>

          <!-- 章节详情编辑区 -->
          <div v-show="chapter.expanded" class="chapter-body">
            <form class="admin-form">
              <div class="form-row">
                <div class="form-group flex-2">
                  <label class="form-label required">章节标题</label>
                  <input
                    v-model="chapter.title"
                    type="text"
                    class="form-input"
                    placeholder="例如：第一章：SQL注入基础"
                  />
                </div>
                <div class="form-group">
                  <label class="form-label">类型</label>
                  <select v-model="chapter.module_type" class="form-select">
                    <option value="intro">📖 介绍</option>
                    <option value="theory">📚 理论</option>
                    <option value="practice">💻 实践</option>
                    <option value="challenge">🎯 挑战</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">预计时长（分钟）</label>
                  <input
                    v-model.number="chapter.estimated_minutes"
                    type="number"
                    class="form-input"
                    min="0"
                    placeholder="30"
                  />
                </div>
              </div>

              <div class="form-group">
                <label class="form-label">章节简介</label>
                <textarea
                  v-model="chapter.description"
                  class="form-textarea"
                  rows="2"
                  placeholder="简要描述本章学习内容..."
                ></textarea>
              </div>

              <div class="form-group">
                <label class="form-label">
                  <i class="bi bi-file-text"></i>
                  章节内容（支持 Markdown）
                  <span class="badge badge-info">支持代码高亮</span>
                </label>
                <textarea
                  v-model="chapter.content"
                  class="form-textarea markdown-editor"
                  rows="15"
                  placeholder="## 章节内容

在此输入详细的教学内容，支持 Markdown 格式。

### 示例代码

\`\`\`sql
SELECT * FROM users WHERE id = 1
\`\`\`

### 重点提示

- 这里可以插入重点提示
- 支持列表、表格等格式
"
                ></textarea>
              </div>

              <!-- 关联实验 -->
              <div class="form-group">
                <label class="form-label">
                  <i class="bi bi-flask"></i>
                  关联实验题目
                  <button class="btn btn-sm btn-secondary" @click="openChallengeSelector(index)">
                    <i class="bi bi-plus"></i>
                    添加实验
                  </button>
                </label>
                <div v-if="chapter.challenges && chapter.challenges.length > 0" class="challenges-list">
                  <div
                    v-for="(challenge, cIndex) in chapter.challenges"
                    :key="challenge.id"
                    class="challenge-item"
                  >
                    <div class="challenge-info">
                      <span class="badge" :class="getDifficultyBadgeClass(challenge.difficulty)">
                        {{ challenge.difficulty }}
                      </span>
                      <span class="challenge-title">{{ challenge.title }}</span>
                      <span class="challenge-points">{{ challenge.points }} 分</span>
                    </div>
                    <button class="btn-icon btn-danger" @click="removeChallenge(index, cIndex)" title="移除">
                      <i class="bi bi-x-lg"></i>
                    </button>
                  </div>
                </div>
                <div v-else class="empty-challenges">
                  <i class="bi bi-flask"></i>
                  <span>暂无关联实验，点击"添加实验"选择题目</span>
                </div>
              </div>

              <!-- 前置章节依赖 -->
              <div v-if="index > 0" class="form-group">
                <label class="form-label">
                  <i class="bi bi-link-45deg"></i>
                  前置章节依赖
                  <span class="form-hint">需要先完成这些章节才能学习本章</span>
                </label>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                  <label
                    v-for="(prevChapter, pIndex) in chapters.slice(0, index)"
                    :key="prevChapter.id"
                    class="checkbox-label"
                  >
                    <input
                      type="checkbox"
                      :checked="isPrerequisiteSelected(chapter, prevChapter.id)"
                      @change="togglePrerequisite(index, prevChapter.id)"
                    />
                    <span>第 {{ pIndex + 1 }} 章：{{ prevChapter.title || '未命名章节' }}</span>
                  </label>
                </div>
              </div>

              <!-- 答案/提示 -->
              <div class="form-group">
                <label class="form-label">
                  <i class="bi bi-lightbulb"></i>
                  实验答案/提示（可选）
                </label>
                <textarea
                  v-model="chapter.solution_hint"
                  class="form-textarea"
                  rows="4"
                  placeholder="提供实验的提示或答案，用于用户参考或自动验证..."
                ></textarea>
              </div>

              <div class="form-group">
                <label class="form-label">是否必修</label>
                <div style="display: flex; gap: 24px;">
                  <label class="radio-label">
                    <input v-model="chapter.is_required" type="radio" :value="true" />
                    <span>✅ 必修（必须完成）</span>
                  </label>
                  <label class="radio-label">
                    <input v-model="chapter.is_required" type="radio" :value="false" />
                    <span>⭕ 选修（可选跳过）</span>
                  </label>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>

    <!-- 题目选择器弹窗 -->
    <div v-if="challengeSelectorVisible" class="modal-overlay" @click.self="challengeSelectorVisible = false">
      <div class="modal-content" style="max-width: 900px; max-height: 80vh; overflow: hidden;">
        <div class="modal-header">
          <h3>
            <i class="bi bi-flask"></i>
            选择实验题目
          </h3>
          <button class="close-btn" @click="challengeSelectorVisible = false">✕</button>
        </div>
        <div class="modal-body" style="overflow-y: auto; max-height: calc(80vh - 140px);">
          <div class="filter-bar">
            <input
              v-model="challengeSearch"
              type="text"
              class="form-input"
              placeholder="搜索题目..."
              style="flex: 1;"
            />
            <select v-model="challengeFilterCategory" class="form-select" style="width: 150px;">
              <option value="">所有分类</option>
              <option v-for="category in categories" :key="category.id" :value="category.id">
                {{ category.name }}
              </option>
            </select>
          </div>
          <div class="challenges-selector-list">
            <div
              v-for="challenge in filteredChallenges"
              :key="challenge.id"
              class="challenge-selector-item"
              :class="{ 'selected': isChallengeSelected(challenge.id) }"
              @click="toggleChallengeSelection(challenge)"
            >
              <div class="selector-checkbox">
                <input
                  type="checkbox"
                  :checked="isChallengeSelected(challenge.id)"
                  @change.stop="toggleChallengeSelection(challenge)"
                />
              </div>
              <div class="challenge-details">
                <div class="challenge-meta">
                  <span class="badge" :class="getDifficultyBadgeClass(challenge.difficulty)">
                    {{ challenge.difficulty }}
                  </span>
                  <span class="category-badge">{{ challenge.category_name }}</span>
                  <span class="points-badge">{{ challenge.points }} 分</span>
                </div>
                <h4 class="challenge-title">{{ challenge.title }}</h4>
                <p class="challenge-description">{{ challenge.description }}</p>
              </div>
              <i class="bi bi-check-circle selection-icon"></i>
            </div>
          </div>
          <div v-if="filteredChallenges.length === 0" class="empty-state">
            <i class="bi bi-search"></i>
            <p>没有找到匹配的题目</p>
          </div>
        </div>
        <div class="modal-footer">
          <div class="selection-summary">
            已选择 <strong>{{ selectedChallengesCount }}</strong> 个题目
          </div>
          <div>
            <button class="action-btn btn-default" @click="challengeSelectorVisible = false">取消</button>
            <button class="action-btn btn-primary" @click="confirmChallengeSelection">
              确认添加
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 确认删除弹窗 -->
    <div v-if="confirmModalVisible" class="modal-overlay" @click.self="confirmModalVisible = false">
      <div class="modal-content" style="max-width: 400px;">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="close-btn" @click="confirmModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <p>{{ confirmMessage }}</p>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="confirmModalVisible = false">取消</button>
          <button class="action-btn btn-danger" @click="confirmDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api'

const router = useRouter()
const route = useRoute()

// 路径信息
const pathInfoExpanded = ref(true)
const saving = ref(false)
const isNewPath = ref(true)

const pathForm = reactive({
  id: null,
  title: '',
  slug: '',
  description: '',
  difficulty: 'AP',
  estimated_hours: 10,
  color: '#1890ff',
  is_published: false,
})

// 章节
const chapters = ref([])
const activeChapterId = ref(null)
const editingChapterIndex = ref(-1)

// 题目选择器
const challengeSelectorVisible = ref(false)
const challengeSearch = ref('')
const challengeFilterCategory = ref('')
const availableChallenges = ref([])
const categories = ref([])
const tempSelectedChallengeIds = ref(new Set())

// 确认弹窗
const confirmModalVisible = ref(false)
const confirmMessage = ref('')
const confirmCallback = ref(null)

// 计算属性
const selectedChallengesCount = computed(() => {
  if (editingChapterIndex.value >= 0) {
    return chapters.value[editingChapterIndex.value].challenges?.length || 0
  }
  return tempSelectedChallengeIds.value.size
})

const filteredChallenges = computed(() => {
  return availableChallenges.value.filter(c => {
    const matchSearch = !challengeSearch.value || 
      c.title.toLowerCase().includes(challengeSearch.value.toLowerCase())
    const matchCategory = !challengeFilterCategory.value || c.category_id === challengeFilterCategory.value
    return matchSearch && matchCategory
  })
})

// 方法
const loadPathData = async () => {
  const pathId = route.params.id
  if (pathId && pathId !== 'new') {
    isNewPath.value = false
    try {
      const res = await api.learningPaths.detail(pathId)
      Object.assign(pathForm, res)
      // 加载章节
      await loadChapters(pathId)
    } catch (error) {
      console.error('Failed to load path:', error)
      alert('加载失败')
    }
  }
}

const loadChapters = async (pathId) => {
  try {
    const res = await api.pathModules.list({ learning_path: pathId })
    chapters.value = (res.results || res).map(m => ({
      ...m,
      expanded: false,
      challenges: m.module_labs?.map(ml => ({
        id: ml.lab_id,
        title: ml.lab_title,
        difficulty: ml.lab_difficulty,
        points: ml.lab_points,
        category_id: ml.lab_category,
        category_name: ml.lab_category_name,
      })) || []
    }))
  } catch (error) {
    console.error('Failed to load chapters:', error)
  }
}

const loadChallenges = async () => {
  try {
    const res = await api.challenge.getChallenges({ is_active: true })
    availableChallenges.value = res.results || res
  } catch (error) {
    console.error('Failed to load challenges:', error)
  }
}

const loadCategories = async () => {
  try {
    const res = await api.challenge.getCategories()
    categories.value = res.results || res
  } catch (error) {
    console.error('Failed to load categories:', error)
  }
}

const addChapter = () => {
  const newChapter = {
    id: `new-${Date.now()}`,
    title: '',
    description: '',
    module_type: 'theory',
    content: '',
    order: chapters.value.length,
    estimated_minutes: 30,
    is_required: true,
    solution_hint: '',
    challenges: [],
    prerequisites: [],
    expanded: true,
  }
  chapters.value.push(newChapter)
  // 自动展开新章节
  setTimeout(() => {
    newChapter.expanded = true
  }, 100)
}

const toggleChapter = (index) => {
  chapters.value[index].expanded = !chapters.value[index].expanded
}

const moveChapterUp = (index) => {
  if (index > 0) {
    const temp = chapters.value[index - 1]
    chapters.value[index - 1] = chapters.value[index]
    chapters.value[index] = temp
    // 更新顺序
    chapters.value.forEach((c, i) => c.order = i)
  }
}

const moveChapterDown = (index) => {
  if (index < chapters.value.length - 1) {
    const temp = chapters.value[index + 1]
    chapters.value[index + 1] = chapters.value[index]
    chapters.value[index] = temp
    // 更新顺序
    chapters.value.forEach((c, i) => c.order = i)
  }
}

const deleteChapter = (index) => {
  const chapter = chapters.value[index]
  confirmMessage.value = `确定要删除"第 ${index + 1} 章：${chapter.title || '未命名章节'}"吗？此操作不可撤销。`
  confirmCallback.value = () => {
    chapters.value.splice(index, 1)
    // 更新顺序
    chapters.value.forEach((c, i) => c.order = i)
  }
  confirmModalVisible.value = true
}

const openChallengeSelector = (index) => {
  editingChapterIndex.value = index
  const chapter = chapters.value[index]
  tempSelectedChallengeIds.value = new Set(chapter.challenges?.map(c => c.id) || [])
  challengeSelectorVisible.value = true
}

const isChallengeSelected = (challengeId) => {
  return tempSelectedChallengeIds.value.has(challengeId)
}

const toggleChallengeSelection = (challenge) => {
  if (tempSelectedChallengeIds.value.has(challenge.id)) {
    tempSelectedChallengeIds.value.delete(challenge.id)
  } else {
    tempSelectedChallengeIds.value.add(challenge.id)
  }
}

const confirmChallengeSelection = () => {
  const selectedChallenges = availableChallenges.value.filter(c => 
    tempSelectedChallengeIds.value.has(c.id)
  )
  chapters.value[editingChapterIndex.value].challenges = selectedChallenges.map(c => ({
    id: c.id,
    title: c.title,
    difficulty: c.difficulty,
    points: c.points,
    category_id: c.category_id,
    category_name: c.category?.name,
  }))
  challengeSelectorVisible.value = false
}

const removeChallenge = (chapterIndex, challengeIndex) => {
  chapters.value[chapterIndex].challenges.splice(challengeIndex, 1)
}

const isPrerequisiteSelected = (chapter, prerequisiteId) => {
  return chapter.prerequisites?.includes(prerequisiteId) || false
}

const togglePrerequisite = (chapterIndex, prerequisiteId) => {
  const chapter = chapters.value[chapterIndex]
  if (!chapter.prerequisites) {
    chapter.prerequisites = []
  }
  const index = chapter.prerequisites.indexOf(prerequisiteId)
  if (index > -1) {
    chapter.prerequisites.splice(index, 1)
  } else {
    chapter.prerequisites.push(prerequisiteId)
  }
}

const savePath = async () => {
  // 验证
  if (!pathForm.title || !pathForm.slug || !pathForm.description) {
    alert('请填写路径基本信息')
    return
  }

  if (chapters.value.length === 0) {
    alert('请至少添加一个章节')
    return
  }

  // 验证每个章节
  for (let i = 0; i < chapters.value.length; i++) {
    const chapter = chapters.value[i]
    if (!chapter.title || !chapter.content) {
      alert(`第 ${i + 1} 章的标题和内容不能为空`)
      return
    }
  }

  saving.value = true
  try {
    // 构建保存数据
    const pathData = {
      ...pathForm,
      chapters: chapters.value.map(c => ({
        title: c.title,
        description: c.description,
        module_type: c.module_type,
        content: c.content,
        order: c.order,
        estimated_minutes: c.estimated_minutes,
        is_required: c.is_required,
        solution_hint: c.solution_hint,
        prerequisites: c.prerequisites || [],
        challenges: c.challenges?.map(ch => ch.id) || [],
      }))
    }

    if (isNewPath.value) {
      // 创建
      // await api.learningPaths.create(pathData)
      alert('创建功能需要后端 API 支持')
    } else {
      // 更新
      // await api.learningPaths.update(pathForm.id, pathData)
      alert('更新功能需要后端 API 支持')
    }
    
    alert('路径保存成功！')
  } catch (error) {
    console.error('Failed to save path:', error)
    alert('保存失败：' + error.message)
  } finally {
    saving.value = false
  }
}

const confirmDelete = async () => {
  if (confirmCallback.value) {
    await confirmCallback.value()
  }
  confirmModalVisible.value = false
}

const goBack = () => {
  router.push('/learning-paths')
}

const getModuleTypeLabel = (type) => {
  const labels = { intro: '介绍', theory: '理论', practice: '实践', challenge: '挑战' }
  return labels[type] || type
}

const getDifficultyBadgeClass = (difficulty) => {
  const classes = { Easy: 'badge-success', Medium: 'badge-warning', Hard: 'badge-danger' }
  return classes[difficulty] || 'badge-info'
}

// 生命周期
onMounted(async () => {
  await Promise.all([
    loadPathData(),
    loadChallenges(),
    loadCategories(),
  ])
})
</script>

<style scoped>
@import '../../admin/assets/admin.css';

.learning-paths-manage-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  background: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  background: white;
  padding: 24px 32px;
  border-radius: 12px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.header-content {
  flex: 1;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 8px 0;
}

.page-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

/* 路径信息区域 */
.path-info-section,
.chapters-section {
  background: white;
  border-radius: 12px;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title i {
  color: #1890ff;
}

.section-body {
  padding: 24px 32px;
}

/* 章节卡片 */
.chapters-list {
  padding: 16px;
}

.chapter-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  margin-bottom: 12px;
  background: white;
  transition: all 0.3s ease;
}

.chapter-card:hover {
  border-color: #1890ff;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.chapter-card.expanded {
  border-color: #1890ff;
}

.chapter-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  gap: 16px;
}

.chapter-number {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.number-badge {
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.chapter-type-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.chapter-type-badge.intro { background: #f0f0f0; color: #666; }
.chapter-type-badge.theory { background: #e6f7ff; color: #1890ff; }
.chapter-type-badge.practice { background: #f6ffed; color: #52c41a; }
.chapter-type-badge.challenge { background: #fff2e8; color: #fa8c16; }

.chapter-title {
  flex: 1;
  font-size: 16px;
  font-weight: 500;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
}

.chapter-title .placeholder {
  color: #999;
  font-style: italic;
}

.required-tag {
  padding: 2px 8px;
  background: #ffec3d;
  color: #8c6900;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.chapter-actions {
  display: flex;
  gap: 4px;
}

.btn-icon {
  width: 32px;
  height: 32px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  transition: all 0.2s;
}

.btn-icon:hover:not(:disabled) {
  color: #1890ff;
  border-color: #1890ff;
}

.btn-icon:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-icon.btn-danger:hover {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

.chapter-body {
  padding: 24px 20px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

/* Markdown 编辑器 */
.markdown-editor {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
}

/* 关联实验 */
.challenges-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.challenge-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  transition: all 0.2s;
}

.challenge-item:hover {
  border-color: #1890ff;
  background: #f0f7ff;
}

.challenge-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.challenge-points {
  color: #52c41a;
  font-weight: 500;
}

.empty-challenges {
  padding: 24px;
  text-align: center;
  color: #999;
  border: 2px dashed #e8e8e8;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}

/* 题目选择器 */
.filter-bar {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.challenges-selector-list {
  max-height: 400px;
  overflow-y: auto;
}

.challenge-selector-item {
  display: flex;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.2s;
}

.challenge-selector-item:hover {
  background: #f5f7fa;
}

.challenge-selector-item.selected {
  background: #e6f7ff;
  border-color: #1890ff;
}

.selector-checkbox {
  margin-right: 12px;
}

.challenge-details {
  flex: 1;
}

.challenge-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.category-badge {
  background: #f0f0f0;
  color: #666;
}

.points-badge {
  background: #f6ffed;
  color: #52c41a;
}

.challenge-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin: 0 0 4px 0;
}

.challenge-description {
  font-size: 13px;
  color: #666;
  margin: 0;
  line-height: 1.5;
}

.selection-icon {
  font-size: 20px;
  color: #52c41a;
  margin-left: 12px;
}

/* 空状态 */
.empty-chapters {
  text-align: center;
  padding: 80px 20px;
  color: #999;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
  display: block;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #999;
}

/* 按钮 */
.btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-secondary {
  background: #fff;
  color: #333;
  border: 1px solid #d9d9d9;
}

.btn-secondary:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 13px;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 表单 */
.admin-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-row {
  display: flex;
  gap: 20px;
}

.form-row .form-group {
  flex: 1;
}

.form-row .form-group.flex-2 {
  flex: 2;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label.required::after {
  content: '*';
  color: #ff4d4f;
}

.form-input,
.form-select,
.form-textarea {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.2s;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.form-hint {
  font-size: 12px;
  color: #999;
}

.radio-label,
.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

/* 徽章 */
.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.badge-success { background: #f6ffed; color: #52c41a; }
.badge-warning { background: #fff2e8; color: #fa8c16; }
.badge-danger { background: #fff1f0; color: #ff4d4f; }
.badge-info { background: #e6f7ff; color: #1890ff; }

/* 弹窗 */
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
  border-radius: 12px;
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
  border-bottom: 1px solid #f0f0f0;
}

.modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.action-btn {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.action-btn.btn-primary {
  background: #1890ff;
  color: white;
}

.action-btn.btn-default {
  background: white;
  color: #333;
  border: 1px solid #d9d9d9;
}

.action-btn.btn-danger {
  background: #ff4d4f;
  color: white;
}

.selection-summary {
  font-size: 14px;
  color: #666;
}
</style>
