<template>
  <div class="learning-paths-manage-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ names.paths }}管理</h1>
        <p class="page-subtitle">创建和编辑{{ names.paths }}，按章节组织内容</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goBack">
          <AppIcon name="bi-arrow-left" />
          返回
        </button>
        <button class="btn btn-primary" @click="savePath" :disabled="saving || loading || !!loadError || saveUncertain">
          <AppIcon name="bi-save" />
          {{ saving ? '保存中...' : `保存${names.paths}` }}
        </button>
      </div>
    </div>

    <p v-if="loading" class="state-message" role="status">正在读取航线与章节…</p>
    <div v-if="loadError" class="state-message error-message" role="alert">
      {{ loadError }} <button class="btn btn-secondary" @click="loadPathData">重新读取</button>
    </div>
    <p class="state-message">可新建航线、保存基本信息与章节，并选择草稿或发布。草稿仅教师与管理员可读；前置章节、实验关联和提示暂不能保存更改。</p>
    <div v-if="saveError" class="state-message error-message" role="alert">{{ saveError }} <button v-if="saveUncertain" class="btn btn-secondary" @click="loadPathData">重新读取航线核对</button></div>
    <p v-if="notice" class="state-message" role="status">{{ notice }}</p>
    <fieldset class="editor-fields" :disabled="loading || saving || !!loadError">
    <!-- 路径基本信息 -->
    <div class="path-info-section">
      <div class="section-header">
        <h2 class="section-title">
          <AppIcon name="bi-info-circle" />
          航线基本信息
        </h2>
        <button class="btn btn-sm btn-secondary" @click="pathInfoExpanded = !pathInfoExpanded">
          <AppIcon :name="pathInfoExpanded ? 'bi-chevron-up' : 'bi-chevron-down'" />
        </button>
      </div>
      <div v-show="pathInfoExpanded" class="section-body">
        <form class="admin-form" @submit.prevent>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label required">航线标题</label>
              <input
                v-model="pathForm.title"
                type="text"
                class="form-input"
                placeholder="例如：Web安全入门实战"
                required
              />
            </div>
            <div class="form-group">
              <label class="form-label">访问地址名称</label>
              <input
                v-model="pathForm.slug"
                type="text"
                class="form-input"
                :placeholder="isNewPath ? '留空自动生成，也可填写英文、数字与连字符' : '当前地址名称未提供'"
                :disabled="!isNewPath"
              />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label required">航线描述</label>
            <textarea
              v-model="pathForm.description"
              class="form-textarea"
              rows="3"
              :placeholder="renameCopy('描述这个学习路径的学习目标、适用对象等...')"
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
              <div class="color-field">
                <input
                  v-model="pathForm.color"
                  type="color"
                  class="color-input"
                />
                <span class="form-hint">所选航线主题色</span>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">发布状态</label>
            <div class="radio-group">
              <label class="radio-label">
                <input
                  v-model="pathForm.is_published"
                  type="radio"
                  :value="true"
                />
                <span>已发布（用户可见）</span>
              </label>
              <label class="radio-label">
                <input
                  v-model="pathForm.is_published"
                  type="radio"
                  :value="false"
                />
                <span>草稿（仅教师与管理员可见）</span>
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
          <AppIcon name="bi-list-ul" />
          学习章节（{{ chapters.length }}）
        </h2>
        <button class="btn btn-secondary" @click="addChapter">
          <AppIcon name="bi-plus-lg" />
          添加章节
        </button>
      </div>

      <div v-if="chapters.length === 0" class="empty-chapters">
        <AppIcon class="empty-icon" name="bi-journal-plus" />
        <p>还没有章节，点击右上角添加第一个章节</p>
        <button class="btn btn-secondary" @click="addChapter">
          <AppIcon name="bi-plus-lg" />
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
          <div class="chapter-header" role="button" tabindex="0" :aria-expanded="chapter.expanded" @keydown.enter.self="toggleChapter(index)" @keydown.space.self.prevent="toggleChapter(index)" @click="toggleChapter(index)">
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
                <AppIcon name="bi-arrow-up" />
              </button>
              <button class="btn-icon" @click="moveChapterDown(index)" :disabled="index === chapters.length - 1" title="下移">
                <AppIcon name="bi-arrow-down" />
              </button>
              <button class="btn-icon btn-danger" @click="deleteChapter(index)" title="删除章节">
                <AppIcon name="bi-trash" />
              </button>
              <button class="btn-icon" @click="chapter.expanded = !chapter.expanded" :title="chapter.expanded ? '收起' : '展开'">
                <AppIcon :name="chapter.expanded ? 'bi-chevron-up' : 'bi-chevron-down'" />
              </button>
            </div>
          </div>

          <!-- 章节详情编辑区 -->
          <div v-show="chapter.expanded" class="chapter-body">
            <form class="admin-form" @submit.prevent>
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
                    <option value="intro">介绍</option>
                    <option value="theory">理论</option>
                    <option value="practice">实践</option>
                    <option value="challenge">挑战</option>
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
                  <AppIcon name="bi-file-text" />
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
                  <AppIcon name="bi-flask" />
                  关联实验题目
                  <button class="btn btn-sm btn-secondary" @click="openChallengeSelector(index)">
                    <AppIcon name="bi-plus" />
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
                      <AppIcon name="bi-x-lg" />
                    </button>
                  </div>
                </div>
                <div v-else class="empty-challenges">
                  <AppIcon name="bi-flask" />
                  <span>暂无关联实验，点击"添加实验"选择题目</span>
                </div>
              </div>

              <!-- 前置章节依赖 -->
              <div v-if="index > 0" class="form-group">
                <label class="form-label">
                  <AppIcon name="bi-link-45deg" />
                  前置章节依赖
                  <span class="form-hint">需要先完成这些章节才能学习本章</span>
                </label>
                <div class="prerequisite-options">
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
                  <AppIcon name="bi-lightbulb" />
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
                <div class="radio-group">
                  <label class="radio-label">
                    <input v-model="chapter.is_required" type="radio" :value="true" />
                    <span>必修（必须完成）</span>
                  </label>
                  <label class="radio-label">
                    <input v-model="chapter.is_required" type="radio" :value="false" />
                    <span>选修（可选跳过）</span>
                  </label>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>

    </fieldset>

    <!-- 题目选择器弹窗 -->
    <div v-if="challengeSelectorVisible" class="modal-overlay" @click.self="challengeSelectorVisible = false">
      <div class="modal-content challenge-modal">
        <div class="modal-header">
          <h3>
            <AppIcon name="bi-flask" />
            选择实验题目
          </h3>
          <button class="close-btn" @click="challengeSelectorVisible = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
        </div>
        <div class="modal-body">
          <div class="filter-bar">
            <input
              v-model="challengeSearch"
              type="text"
              class="form-input"
              placeholder="搜索题目..."
            />
            <select v-model="challengeFilterCategory" class="form-select">
              <option value="">所有分类</option>
              <option v-for="category in categories" :key="category.id" :value="category.id">
                {{ category.name }}
              </option>
            </select>
          </div>
          <p v-if="challengesLoading" class="state-message" role="status">正在读取实验题目…</p>
          <p v-if="challengeError" class="state-message error-message" role="alert">{{ challengeError }} <button class="btn btn-secondary" @click="loadChallenges">重试读取题目</button></p>
          <p v-if="categoryError" class="state-message error-message" role="alert">{{ categoryError }} <button class="btn btn-secondary" @click="loadCategories">重试读取分类</button></p>
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
                  @click.stop
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
              <AppIcon class="selection-icon" name="bi-check-circle" />
            </div>
          </div>
          <div v-if="!challengesLoading && !challengeError && filteredChallenges.length === 0" class="empty-state">
            <AppIcon name="bi-search" />
            <p>没有找到匹配的题目</p>
          </div>
        </div>
        <div class="modal-footer">
          <div class="selection-summary">
            已选择 <strong>{{ selectedChallengesCount }}</strong> 个题目
          </div>
          <div class="modal-actions">
            <button class="action-btn btn-default" @click="challengeSelectorVisible = false">取消</button>
            <button class="action-btn btn-primary" :disabled="challengesLoading || !!challengeError" @click="confirmChallengeSelection">
              确认添加
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 确认删除弹窗 -->
    <div v-if="confirmModalVisible" class="modal-overlay" @click.self="confirmModalVisible = false">
      <div class="modal-content confirm-modal">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="close-btn" @click="confirmModalVisible = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
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
import { names, renameCopy } from '@/shared/navigation/names'
import { createAccountGuard, onAccountClear } from '@/shared/state/accountScope.js'
import { persistPath, pathSaveError } from './savePath.js'
import { uiSnapshot } from '@/shared/state/retention.js'

import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
const props = defineProps({ api: { type: Object, required: true }, managementBase: { type: String, default: '/teacher/learning-paths' }, listPath: String, takeDraft: Function })
const managementApi = props.api

const router = useRouter()
const route = useRoute()

// 路径信息
const pathInfoExpanded = ref(true)
const saving = ref(false)
const loading = ref(true)
const loadError = ref('')
const challengeError = ref('')
const categoryError = ref('')
const challengesLoading = ref(true)
const notice = ref('')
const account = createAccountGuard()
const originalModules = ref([])
const originalPublished = ref(false)
const saveError = ref('')
const saveUncertain = ref(false)
let alive = true
let pathRead = 0
let challengeRead = 0
let categoryRead = 0
const clearPrivateEditor = () => { alive = false; ++pathRead; ++challengeRead; ++categoryRead; account.dispose(); Object.assign(pathForm, { id: null, title: '', slug: '', description: '' }); chapters.value = []; originalModules.value = []; availableChallenges.value = []; notice.value = ''; saveError.value = ''; challengeSelectorVisible.value = false; confirmModalVisible.value = false }
const unsubscribe = onAccountClear(clearPrivateEditor)
onBeforeUnmount(() => { clearPrivateEditor(); unsubscribe() })
const isNewPath = ref(true)

const emptyPath = () => ({
  id: null,
  title: '',
  slug: '',
  description: '',
  difficulty: 'AP',
  estimated_hours: 10,
  color: '#B7352D',
  is_published: false,
})
const pathForm = reactive(emptyPath())

// 章节
const chapters = ref([])
const activeChapterId = ref(null)
const editingChapterIndex = ref(-1)
const editingChapterId = ref(null)

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
const selectedChallengesCount = computed(() => tempSelectedChallengeIds.value.size)

const filteredChallenges = computed(() => {
  return availableChallenges.value.filter(c => {
    const matchSearch = !challengeSearch.value || 
      String(c.title || '').toLowerCase().includes(challengeSearch.value.toLowerCase())
    const matchCategory = !challengeFilterCategory.value || String(c.category_id ?? c.category?.id ?? c.category) === String(challengeFilterCategory.value)
    return matchSearch && matchCategory
  })
})

// 方法
const loadPathData = async () => {
  const current = ++pathRead
  loading.value = true
  loadError.value = ''
  const routeId = route.params.id
  const pathId = (!routeId || routeId === 'new') && saveUncertain.value && pathForm.id ? pathForm.id : routeId
  isNewPath.value = !pathId || pathId === 'new'
  try {
    if (!isNewPath.value) {
      const [path, modules] = await Promise.all([managementApi.detail(pathId), managementApi.modules(pathId)])
      if (!alive || !account.current() || current !== pathRead || route.params.id !== routeId) return
      if (!path || typeof path !== 'object' || Array.isArray(path) || !Array.isArray(modules)) throw new Error('Incomplete path')
      // Normalize every chapter before replacing any editable data.
      const normalized = modules.map(m => ({
        ...m, expanded: false,
        prerequisites: m.prerequisites || m.requires || [],
        solution_hint: m.solution_hint || '',
        challenges: m.challenges || (m.module_labs || m.labs)?.map(ml => ({
          id: ml.lab_id ?? `associated-${ml.id}`, title: ml.lab_title, difficulty: ml.lab_difficulty,
          points: ml.lab_points ?? ml.lab_score, category_id: ml.lab_category, category_name: ml.lab_category_name,
        })) || [],
      }))
      Object.assign(pathForm, path, { id: path.id ?? pathId })
      chapters.value = normalized
      originalModules.value = JSON.parse(JSON.stringify(normalized))
      originalPublished.value = path.is_published
      saveUncertain.value = false; saveError.value = ''; notice.value = ''
      const feedback = uiSnapshot(`paths:saved:${props.managementBase}:${pathForm.id}`)
      if (feedback.read()) {
        notice.value = `航线基本信息与章节已保存，已重新读取核对。${path.is_published ? '已发布，学生可见。' : '已存为草稿，仅教师与管理员可见。'}`
        feedback.write(null)
      }
    }
    if (alive && current === pathRead) applyKnowledgeDraft()
  } catch {
    if (alive && current === pathRead) loadError.value = '航线或章节未能完整读取，请重试；暂不能编辑或保存。'
  } finally {
    if (alive && current === pathRead) loading.value = false
  }
}

const loadChallenges = async () => {
  const current = ++challengeRead
  challengesLoading.value = true
  challengeError.value = ''
  try {
    const rows = await managementApi.challenges()
    if (!alive || current !== challengeRead) return
    if (!Array.isArray(rows)) throw new Error('Incomplete challenges')
    availableChallenges.value = rows
  } catch {
    if (alive && current === challengeRead) challengeError.value = '实验题目未能完整读取，原关联仍保留，请重试。'
  } finally {
    if (alive && current === challengeRead) challengesLoading.value = false
  }
}

const loadCategories = async () => {
  const current = ++categoryRead
  categoryError.value = ''
  try {
    const rows = await managementApi.categories()
    if (!alive || current !== categoryRead) return
    if (!Array.isArray(rows)) throw new Error('Incomplete categories')
    categories.value = rows
  } catch {
    if (alive && current === categoryRead) categoryError.value = '题目分类读取失败，仍可按名称搜索，请重试。'
  }
}

let chapterSequence = 0
const addChapter = () => {
  const newChapter = {
    id: `new-${++chapterSequence}`,
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
    const currentIndex = chapters.value.findIndex(item => item.id === chapter.id)
    if (currentIndex < 0) return
    chapters.value.splice(currentIndex, 1)
    chapters.value.forEach((c, i) => {
      c.order = i
      c.prerequisites = (c.prerequisites || []).filter(id => id !== chapter.id)
    })
    if (editingChapterId.value === chapter.id) challengeSelectorVisible.value = false
  }
  confirmModalVisible.value = true
}

const openChallengeSelector = (index) => {
  editingChapterIndex.value = index
  const chapter = chapters.value[index]
  editingChapterId.value = chapter.id
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
  if (challengesLoading.value || challengeError.value) return
  const chapter = chapters.value.find(item => item.id === editingChapterId.value)
  if (!chapter) return
  // Keep existing associations even when they are no longer in the active bank.
  const byId = new Map([...(chapter.challenges || []), ...availableChallenges.value].map(c => [c.id, c]))
  const selectedChallenges = [...byId.values()].filter(c => tempSelectedChallengeIds.value.has(c.id))
  chapter.challenges = selectedChallenges.map(c => ({
    id: c.id,
    title: c.title,
    difficulty: c.difficulty,
    points: c.points,
    category_id: c.category_id ?? c.category?.id ?? c.category,
    category_name: c.category_name || c.category?.name,
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
  if (!alive || !account.current() || saving.value || loading.value || loadError.value || saveUncertain.value) return
  saveError.value = ''; notice.value = ''
  if (!pathForm.title.trim() || !pathForm.description.trim()) {
    saveError.value = '请填写航线基本信息。'
    pathInfoExpanded.value = true
    return
  }
  if (!chapters.value.length) { saveError.value = '请至少添加一个章节。'; return }
  for (let i = 0; i < chapters.value.length; i++) {
    if (!chapters.value[i].title?.trim() || !chapters.value[i].content?.trim()) {
      chapters.value[i].expanded = true
      saveError.value = `第 ${i + 1} 章的标题和内容不能为空。`
      return
    }
  }
  const pathId = route.params.id
  const generation = pathRead
  const creating = !pathForm.id
  const current = () => alive && account.current() && pathRead === generation && route.params.id === pathId
  let acknowledged = 0
  saving.value = true
  try {
    const result = await persistPath({ api: managementApi, form: pathForm, chapters: chapters.value,
      originalModules: originalModules.value, originalPublished: originalPublished.value, current,
      acknowledged: (kind, id, chapter) => {
        acknowledged++
        if (kind === 'path') { pathForm.id = id; isNewPath.value = false }
        else chapter.id = id
      },
    })
    if (!current() || !result) return
    Object.assign(pathForm, result.path)
    originalModules.value = JSON.parse(JSON.stringify(chapters.value))
    originalPublished.value = result.path.is_published
    notice.value = `航线基本信息与章节已保存，已重新读取核对。${result.path.is_published ? '已发布，学生可见。' : '已存为草稿，仅教师与管理员可见。'}`
    if (creating || !pathId || pathId === 'new') {
      uiSnapshot(`paths:saved:${props.managementBase}:${result.path.id}`).write(true)
      saving.value = false
      try { await router.replace(`${props.managementBase}/${result.path.id}/edit`) }
      catch { if (current()) notice.value += '页面地址未能更新，请从航线列表重新打开后再刷新。' }
    }
  } catch (error) {
    if (!current()) return
    saveError.value = error.userFacing ? error.message : pathSaveError(error)
    if (acknowledged) {
      notice.value = '部分内容已保存，但整条航线尚未确认保存完成。请先重新读取核对，填写内容仍保留在本页。'
      saveUncertain.value = true
    } else {
      saveUncertain.value = !error.userFacing && ![400, 401, 403, 404].includes(error.response?.status)
      notice.value = saveUncertain.value ? '保存结果尚未确认；填写内容仍保留在本页，请先核对，不要重复新建。' : '本次内容尚未保存；填写内容仍保留在本页，请勿关闭页面。'
    }
  } finally { if (current()) saving.value = false }
}

const confirmDelete = async () => {
  const callback = confirmCallback.value
  confirmCallback.value = null
  confirmModalVisible.value = false
  if (callback) await callback()
}

const goBack = () => {
  router.push(props.listPath || props.managementBase)
}

const getModuleTypeLabel = (type) => {
  const labels = { intro: '介绍', theory: '理论', practice: '实践', challenge: '挑战' }
  return Object.hasOwn(labels, type) ? labels[type] : '学习章节'
}

const getDifficultyBadgeClass = (difficulty) => {
  const classes = { Easy: 'badge-success', Medium: 'badge-warning', Hard: 'badge-danger' }
  return classes[difficulty] || 'badge-info'
}

let knowledgeDraftApplied = false
const applyKnowledgeDraft = () => {
  if (!alive || loadError.value || !isNewPath.value || knowledgeDraftApplied || !props.takeDraft) return
  const incoming = props.takeDraft()
  if (!incoming) return
  knowledgeDraftApplied = true
  pathForm.title = incoming.title
  pathForm.is_published = false
  addChapter()
  const source = incoming.source || {}
  Object.assign(chapters.value.at(-1), {
    title: incoming.title,
    content: [
      '## 教学目标', '请填写本章学完后能做到的事。',
      '## 评估', '请填写学习前的基础检查与需要关注的薄弱点。',
      '## 讲解', '请结合以下授权资料补充概念解释与教学提示。',
      '## 学习材料', incoming.text,
      '## 练习', '请关联实验题目，并补充练习要求。',
      '## 检验', '请填写掌握检查与验收标准。',
      '## 资料出处',
      ...[['来源', source.title], ['出版方', source.publisher], ['版本', source.source_version],
          ['来源链接', source.source_url], ['许可', source.license_id], ['署名', source.attribution_text]]
        .filter(([, value]) => value).map(([label, value]) => `${label}：${value}`),
    ].join('\n\n'),
    source: { ...source },
  })
  notice.value = '已准备章节草稿，请补充教学目标、练习与检验。尚未保存或发布。'
}

watch(() => route.params.id, id => {
  if (!alive || !account.current()) return
  if (pathForm.id && String(id) === String(pathForm.id) && !isNewPath.value) return
  Object.keys(pathForm).forEach(key => delete pathForm[key])
  Object.assign(pathForm, emptyPath())
  chapters.value = []; originalModules.value = []; originalPublished.value = false
  saveError.value = ''; saveUncertain.value = false; notice.value = ''; saving.value = false
  challengeSelectorVisible.value = false; confirmModalVisible.value = false
  knowledgeDraftApplied = false
  loadPathData()
}, { flush: 'sync' })

// A slow or failed optional challenge bank must not delay the unsaved draft.
onMounted(() => Promise.all([loadPathData(), loadChallenges(), loadCategories()]))
</script>

<style scoped src="./path-editor.css"></style>
