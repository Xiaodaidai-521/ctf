<template>
  <div class="article-editor-page">
    <div class="editor-container">
      <header class="editor-header">
        <button class="back-btn" @click="goBack">
          ← 返回
        </button>
        <h1 class="editor-title">{{ isEdit ? '编辑文章' : '写文章' }}</h1>
        <button
          class="publish-btn"
          :disabled="submitting || !canSubmit"
          @click="handlePublish"
        >
          {{ submitting ? '提交中...' : (isEdit ? '保存修改' : '发布文章') }}
        </button>
      </header>

      <div class="editor-body">
        <div class="form-section">
          <input
            v-model="articleForm.title"
            type="text"
            class="title-input"
            placeholder="请输入文章标题..."
            maxlength="100"
          />
          <div class="title-count">{{ articleForm.title.length }}/100</div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">分类</label>
            <select v-model="articleForm.category" class="form-select">
              <option value="">请选择分类</option>
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                {{ cat.name }}
              </option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">标签</label>
            <input
              v-model="articleForm.tags"
              type="text"
              class="form-input"
              placeholder="多个标签用逗号分隔，如：CTF,Web安全"
            />
          </div>
        </div>

        <div class="form-section">
          <label class="form-label">封面图（可选）</label>
          <div class="cover-upload">
            <input
              ref="coverInput"
              type="file"
              accept="image/*"
              @change="handleCoverChange"
              style="display: none"
            />
            <div v-if="!articleForm.cover" class="upload-placeholder" @click="selectCover">
              <div class="upload-icon">🖼️</div>
              <p>点击上传封面图</p>
              <p class="upload-hint">建议尺寸 16:9</p>
            </div>
            <div v-else class="cover-preview">
              <img :src="coverPreview" alt="封面预览" />
              <button class="remove-btn" @click="removeCover">✕</button>
            </div>
          </div>
        </div>

        <div class="form-section">
          <label class="form-label">摘要（可选）</label>
          <textarea
            v-model="articleForm.summary"
            class="summary-textarea"
            placeholder="请输入文章摘要，将显示在文章列表中..."
            rows="3"
            maxlength="200"
          ></textarea>
          <div class="char-count">{{ articleForm.summary.length }}/200</div>
        </div>

        <!-- Markdown 编辑器 -->
        <div class="editor-toolbar">
          <button class="toolbar-btn" @click="insertMarkdown('**', '**')" title="粗体">
            <strong>B</strong>
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('*', '*')" title="斜体">
            <em>I</em>
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('```\n', '\n```')" title="代码块">
            &lt;/&gt;
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('`', '`')" title="行内代码">
            &lt;code&gt;
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('# ', '')" title="标题">
            H
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('[', '](url)')" title="链接">
            🔗
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('> ', '')" title="引用">
            &quot;
          </button>
          <button class="toolbar-btn" @click="insertMarkdown('- ', '')" title="列表">
            ≡
          </button>

          <div class="preview-toggle">
            <button
              class="toggle-btn"
              :class="{ active: !showPreview }"
              @click="showPreview = false"
            >
              编辑
            </button>
            <button
              class="toggle-btn"
              :class="{ active: showPreview }"
              @click="showPreview = true"
            >
              预览
            </button>
          </div>
        </div>

        <div class="editor-content">
          <textarea
            v-show="!showPreview"
            ref="editor"
            v-model="articleForm.content"
            class="markdown-editor"
            placeholder="开始写作... 支持 Markdown 语法"
            @input="handleContentChange"
          ></textarea>
          <div
            v-show="showPreview"
            ref="preview"
            class="markdown-preview"
            v-html="renderedContent"
          ></div>
        </div>
      </div>
    </div>

    <!-- Toast 提示 -->
    <div v-if="showToast" :class="['toast', toastType]">
      <span class="toast-icon">{{ toastType === 'success' ? '✓' : '✕' }}</span>
      <span>{{ toastMessage }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'
import { useUserStore } from '@/store/user'
import api from '@/api'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

console.log('ArticleEditor 组件加载')
console.log('当前路由:', route.path)
console.log('用户信息:', userStore.userInfo)

const isEdit = computed(() => !!route.params.id)
const canSubmit = computed(() => {
  return articleForm.value.title.trim() && articleForm.value.content.trim()
})

const articleForm = ref({
  title: '',
  content: '',
  category: '',
  tags: '',
  cover: null,
  summary: ''
})

const categories = ref([])
const submitting = ref(false)
const showPreview = ref(false)
const coverPreview = ref('')
const coverInput = ref(null)
const editor = ref(null)
const preview = ref(null)

const showToast = ref(false)
const toastMessage = ref('')
const toastType = ref('success')

const renderedContent = computed(() => {
  if (!articleForm.value.content) return '<p class="empty-hint">预览内容将显示在这里...</p>'
  try {
    return sanitizeHtml(marked.parse(articleForm.value.content))
  } catch (error) {
    console.error('Markdown 解析失败:', error)
    return sanitizeHtml(articleForm.value.content)
  }
})

const fetchCategories = async () => {
  console.log('开始获取分类列表...')
  try {
    const response = await api.category.list()
    categories.value = response.results || []
    console.log('分类获取成功:', categories.value.length)
  } catch (error) {
    console.error('获取分类失败:', error)
  }
}

const fetchArticle = async () => {
  if (!isEdit.value) return
  console.log('开始获取文章详情...')
  try {
    const article = await api.article.detail(route.params.id)
    if (article.author?.id !== userStore.userInfo?.id && userStore.userInfo?.role !== 'admin') {
      alert('无权编辑此文章')
      router.back()
      return
    }
    articleForm.value = {
      title: article.title,
      content: article.content,
      category: article.category || '',
      tags: article.tags || '',
      cover: null,
      summary: article.summary || ''
    }
    coverPreview.value = article.cover || ''
    console.log('文章获取成功')
  } catch (error) {
    console.error('获取文章失败:', error)
    alert('文章不存在或已被删除')
    router.back()
  }
}

const selectCover = () => coverInput.value?.click()

const handleCoverChange = (e) => {
  const file = e.target.files[0]
  if (file) {
    if (file.size > 5 * 1024 * 1024) {
      showToastMessage('图片大小不能超过 5MB', 'error')
      return
    }
    articleForm.value.cover = file
    coverPreview.value = URL.createObjectURL(file)
  }
}

const removeCover = () => {
  articleForm.value.cover = null
  coverPreview.value = ''
  if (coverInput.value) coverInput.value.value = ''
}

const insertMarkdown = (before, after) => {
  const textarea = editor.value
  if (!textarea) return

  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const text = textarea.value

  const beforeText = text.substring(0, start)
  const selectedText = text.substring(start, end)
  const afterText = text.substring(end)

  articleForm.value.content = beforeText + before + selectedText + after + afterText

  setTimeout(() => {
    textarea.focus()
    textarea.setSelectionRange(
      start + before.length,
      start + before.length + selectedText.length
    )
  }, 0)
}

const handleContentChange = () => {
  // 可以在这里添加自动保存等逻辑
}

const handlePublish = async () => {
  if (!canSubmit.value) {
    showToastMessage('请填写标题和内容', 'error')
    return
  }

  submitting.value = true
  try {
    const formData = new FormData()
    formData.append('title', articleForm.value.title)
    formData.append('content', articleForm.value.content)
    if (articleForm.value.category) {
      formData.append('category', articleForm.value.category)
    }
    if (articleForm.value.tags) {
      formData.append('tags', articleForm.value.tags)
    }
    if (articleForm.value.summary) {
      formData.append('summary', articleForm.value.summary)
    }
    if (articleForm.value.cover) {
      formData.append('cover', articleForm.value.cover)
    }

    if (isEdit.value) {
      await api.article.update(route.params.id, formData)
      showToastMessage('文章已更新，等待审核', 'success')
    } else {
      await api.article.create(formData)
      showToastMessage('文章发布成功，等待审核', 'success')
    }

    setTimeout(() => {
      router.push('/community')
    }, 1500)

  } catch (error) {
    console.error('发布失败:', error)
    showToastMessage('发布失败: ' + (error.response?.data?.error || '未知错误'), 'error')
  } finally {
    submitting.value = false
  }
}

const goBack = () => {
  if (articleForm.value.title || articleForm.value.content) {
    if (confirm('确定要离开吗？未保存的内容将丢失')) {
      router.back()
    }
  } else {
    router.back()
  }
}

const showToastMessage = (message, type) => {
  toastMessage.value = message
  toastType.value = type
  showToast.value = true

  setTimeout(() => {
    showToast.value = false
  }, 3000)
}

onMounted(() => {
  console.log('ArticleEditor onMounted 开始')
  fetchCategories()
  fetchArticle()
  console.log('ArticleEditor onMounted 完成')
})
</script>

<style scoped>
.article-editor-page {
  max-width: 1200px;
  margin: 60px auto 20px;
  padding: 0 20px;
}

.editor-container {
  background: white;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  background: white;
}

.back-btn {
  padding: 6px 14px;
  border: 1px solid var(--border-color);
  background: white;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.back-btn:hover {
  background: var(--hover-bg);
}

.editor-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.publish-btn {
  padding: 8px 20px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s;
}

.publish-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.publish-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.editor-body {
  padding: 20px;
}

.form-section {
  margin-bottom: 20px;
}

.title-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 16px;
  font-weight: 500;
  transition: all 0.3s;
}

.title-input:focus {
  outline: none;
  border-color: var(--primary-color);
}

.title-count {
  text-align: right;
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 6px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.form-select,
.form-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 14px;
  transition: all 0.3s;
}

.form-select:focus,
.form-input:focus {
  outline: none;
  border-color: var(--primary-color);
}

.cover-upload {
  margin-top: 8px;
}

.upload-placeholder {
  border: 2px dashed var(--border-color);
  border-radius: var(--radius-md);
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
}

.upload-placeholder:hover {
  border-color: var(--primary-color);
  background: var(--hover-bg);
}

.upload-icon {
  font-size: 40px;
  margin-bottom: 8px;
}

.upload-placeholder p {
  margin: 4px 0;
  color: var(--text-primary);
}

.upload-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.cover-preview {
  position: relative;
  display: inline-block;
}

.cover-preview img {
  max-width: 300px;
  border-radius: var(--radius-sm);
}

.remove-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-btn:hover {
  background: rgba(0, 0, 0, 0.8);
}

.summary-textarea {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #e8e8e8;
  border-radius: var(--radius-sm);
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
  transition: all 0.3s;
}

.summary-textarea:focus {
  outline: none;
  border-color: var(--primary-color);
}

.char-count {
  text-align: right;
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 6px;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px;
  background: #f5f5f5;
  border: 1px solid #e8e8e8;
  border-bottom: none;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  flex-wrap: wrap;
}

.toolbar-btn {
  padding: 5px 10px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.toolbar-btn:hover {
  background: #e6f7ff;
  border-color: var(--primary-color);
}

.preview-toggle {
  margin-left: auto;
}

.toggle-btn {
  padding: 5px 14px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.toggle-btn.active {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.editor-content {
  border: 1px solid #e8e8e8;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  min-height: 500px;
  display: flex;
}

.markdown-editor {
  flex: 1;
  padding: 20px;
  border: none;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  line-height: 1.8;
  resize: none;
}

.markdown-editor:focus {
  outline: none;
}

.markdown-preview {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background: white;
}

.markdown-preview :deep(.empty-hint) {
  color: var(--text-secondary);
  font-style: italic;
  text-align: center;
  padding: 40px;
}

.markdown-preview :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-sm);
}

.markdown-preview :deep(pre) {
  background: #f6f8fa;
  border-radius: 6px;
  padding: 16px;
  overflow-x: auto;
}

.markdown-preview :deep(code) {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
}

.markdown-preview :deep(p) {
  margin-bottom: 16px;
}

.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
}

.toast {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 14px 20px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: 1000;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.toast.success {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.toast.error {
  background: #fff1f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.toast-icon {
  font-weight: bold;
  font-size: 18px;
}

@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .editor-header {
    flex-direction: column;
    gap: 12px;
  }

  .editor-toolbar {
    flex-wrap: wrap;
  }

  .preview-toggle {
    margin-left: 0;
    width: 100%;
  }

  .toggle-btn {
    width: 100%;
  }
}
</style>
