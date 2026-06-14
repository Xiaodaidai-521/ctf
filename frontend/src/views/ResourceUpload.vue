<template>
  <div class="upload-page">
    <header class="page-header">
      <button class="btn btn-secondary" @click="goBack">
        ← 返回
      </button>
      <h1 class="page-title">上传学习资源</h1>
      <div></div>
    </header>

    <div class="upload-container">
      <form @submit.prevent="handleSubmit" class="upload-form">
        <div class="form-section">
          <h2 class="section-title">基本信息</h2>
          
          <div class="form-group">
            <label class="form-label">
              资源标题 <span class="required">*</span>
            </label>
            <input
              v-model="form.title"
              type="text"
              class="form-input"
              placeholder="请输入资源标题"
              required
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label class="form-label">
                资源类型 <span class="required">*</span>
              </label>
              <select v-model="form.resource_type" class="form-select" required>
                <option value="">请选择类型</option>
                <option value="document">文档</option>
                <option value="video">视频</option>
                <option value="report">报告</option>
                <option value="zip">压缩包</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">
                分类 <span class="required">*</span>
              </label>
              <select v-model="form.category" class="form-select" required>
                <option value="">请选择分类</option>
                <option value="网络安全">网络安全</option>
                <option value="Web安全">Web安全</option>
                <option value="逆向工程">逆向工程</option>
                <option value="密码学">密码学</option>
                <option value="渗透测试">渗透测试</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">
              资源描述 <span class="required">*</span>
            </label>
            <textarea
              v-model="form.description"
              class="form-textarea"
              rows="6"
              placeholder="请详细描述资源内容、适用对象等..."
              required
            ></textarea>
          </div>

          <div class="form-group">
            <label class="form-label">标签</label>
            <input
              v-model="tagsInput"
              type="text"
              class="form-input"
              placeholder="请输入标签，用逗号分隔（如：CTF, web, SQL注入）"
            />
            <p class="form-hint">多个标签请用逗号分隔</p>
          </div>
        </div>

        <div class="form-section">
          <h2 class="section-title">文件上传</h2>
          
          <div class="upload-dropzone" :class="{ 'dragover': isDragOver }" @drop.prevent="handleFileDrop" @dragover.prevent="isDragOver = true" @dragleave="isDragOver = false">
            <input
              ref="fileInput"
              type="file"
              @change="handleFileChange"
              accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.rar,.7z,.mp4,.avi,.mkv"
              style="display: none"
              required
            />
            
            <div v-if="!selectedFile" class="upload-prompt">
              <div class="upload-icon">📁</div>
              <p class="upload-text">点击或拖拽文件到此处上传</p>
              <p class="upload-hint">支持 PDF、Word、PPT、ZIP、视频等格式，最大 500MB</p>
              <button type="button" class="btn btn-primary" @click="selectFile">
                选择文件
              </button>
            </div>

            <div v-else class="file-preview">
              <div class="file-icon">📄</div>
              <div class="file-info">
                <p class="file-name">{{ selectedFile.name }}</p>
                <p class="file-size">{{ formatFileSize(selectedFile.size) }}</p>
              </div>
              <button type="button" class="remove-btn" @click="removeFile">
                ✕
              </button>
            </div>
          </div>
        </div>

        <div class="form-section">
          <h2 class="section-title">封面图片（可选）</h2>
          <div class="upload-dropzone" :class="{ 'dragover': isCoverDragOver }" @drop.prevent="handleCoverDrop" @dragover.prevent="isCoverDragOver = true" @dragleave="isCoverDragOver = false">
            <input
              ref="coverInput"
              type="file"
              @change="handleCoverChange"
              accept="image/*"
              style="display: none"
            />
            
            <div v-if="!selectedCover" class="upload-prompt">
              <div class="upload-icon">🖼️</div>
              <p class="upload-text">点击或拖拽封面图片到此处上传</p>
              <p class="upload-hint">支持 JPG、PNG、GIF 格式，建议尺寸 16:9</p>
              <button type="button" class="btn btn-secondary" @click="selectCover">
                选择图片
              </button>
            </div>

            <div v-else class="cover-preview">
              <img :src="coverPreview" alt="封面预览" class="cover-image" />
              <button type="button" class="remove-btn" @click="removeCover">
                ✕
              </button>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="goBack">
            取消
          </button>
          <button type="submit" class="btn btn-primary" :disabled="submitting">
            {{ submitting ? '上传中...' : '提交审核' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="showToast" class="toast" :class="toastType">
      <span class="toast-icon">{{ toastType === 'success' ? '✓' : '✗' }}</span>
      {{ toastMessage }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'

const router = useRouter()

const form = ref({
  title: '',
  resource_type: '',
  category: '',
  description: '',
})
const tagsInput = ref('')
const selectedFile = ref(null)
const selectedCover = ref(null)
const coverPreview = ref('')
const isDragOver = ref(false)
const isCoverDragOver = ref(false)
const submitting = ref(false)
const fileInput = ref(null)
const coverInput = ref(null)
const showToast = ref(false)
const toastMessage = ref('')
const toastType = ref('success')

const selectFile = () => fileInput.value?.click()

const selectCover = () => coverInput.value?.click()

const handleFileChange = (e) => {
  const file = e.target.files[0]
  if (file) {
    if (file.size > 500 * 1024 * 1024) {
      showToastMessage('文件大小不能超过 500MB', 'error')
      return
    }
    selectedFile.value = file
  }
}

const handleFileDrop = (e) => {
  isDragOver.value = false
  const file = e.dataTransfer.files[0]
  if (file) {
    if (file.size > 500 * 1024 * 1024) {
      showToastMessage('文件大小不能超过 500MB', 'error')
      return
    }
    selectedFile.value = file
  }
}

const handleCoverChange = (e) => {
  const file = e.target.files[0]
  if (file && file.type.startsWith('image/')) {
    selectedCover.value = file
    coverPreview.value = URL.createObjectURL(file)
  }
}

const handleCoverDrop = (e) => {
  isCoverDragOver.value = false
  const file = e.dataTransfer.files[0]
  if (file && file.type.startsWith('image/')) {
    selectedCover.value = file
    coverPreview.value = URL.createObjectURL(file)
  }
}

const removeFile = () => {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

const removeCover = () => {
  selectedCover.value = null
  coverPreview.value = ''
  if (coverInput.value) coverInput.value.value = ''
}

const handleSubmit = async () => {
  if (!selectedFile.value) {
    showToastMessage('请选择要上传的文件', 'error')
    return
  }

  submitting.value = true
  try {
    const formData = new FormData()
    formData.append('title', form.value.title)
    formData.append('resource_type', form.value.resource_type)
    formData.append('category', form.value.category)
    formData.append('description', form.value.description)
    formData.append('file', selectedFile.value)
    
    if (tagsInput.value) {
      formData.append('tags', tagsInput.value)
    }
    
    if (selectedCover.value) {
      formData.append('cover', selectedCover.value)
    }

    await api.resource.upload(formData)
    showToastMessage('资源上传成功，等待审核', 'success')
    
    setTimeout(() => {
      router.push('/resources')
    }, 1500)
  } catch (error) {
    console.error('上传失败:', error)
    showToastMessage('上传失败，请稍后重试', 'error')
  } finally {
    submitting.value = false
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

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i]
}

const goBack = () => router.back()
</script>

<style scoped>
.upload-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 24px;
}

.page-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 24px;
  margin-bottom: 32px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  text-align: center;
}

.upload-container {
  background: white;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.upload-form {
  padding: 40px;
}

.form-section {
  margin-bottom: 40px;
  padding-bottom: 40px;
  border-bottom: 2px solid #f0f0f0;
}

.form-section:last-of-type {
  border-bottom: none;
}

.section-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 24px;
  color: var(--text-primary);
}

.form-group {
  margin-bottom: 24px;
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.required {
  color: var(--error-color);
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid #e8e8e8;
  border-radius: var(--radius-sm);
  font-size: 14px;
  transition: all 0.3s;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--primary-color);
}

.form-textarea {
  resize: vertical;
  min-height: 120px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.upload-dropzone {
  border: 2px dashed #d9d9d9;
  border-radius: var(--radius-md);
  padding: 48px;
  text-align: center;
  transition: all 0.3s;
  cursor: pointer;
}

.upload-dropzone:hover,
.upload-dropzone.dragover {
  border-color: var(--primary-color);
  background: rgba(24, 144, 255, 0.05);
}

.upload-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.upload-icon {
  font-size: 48px;
}

.upload-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.upload-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: #fafafa;
  border-radius: var(--radius-sm);
}

.file-icon {
  font-size: 32px;
}

.file-info {
  flex: 1;
  text-align: left;
}

.file-name {
  font-weight: 600;
  margin-bottom: 4px;
}

.file-size {
  font-size: 12px;
  color: var(--text-secondary);
}

.remove-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: #ff4d4f;
  color: white;
  border-radius: 50%;
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-btn:hover {
  background: #ff7875;
}

.cover-preview {
  position: relative;
  display: inline-block;
  max-width: 100%;
}

.cover-image {
  max-width: 100%;
  max-height: 300px;
  border-radius: var(--radius-sm);
}

.form-actions {
  display: flex;
  gap: 16px;
  justify-content: flex-end;
}

.toast {
  position: fixed;
  top: 24px;
  right: 24px;
  padding: 16px 24px;
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
  .page-header {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .page-title {
    text-align: left;
  }

  .upload-form {
    padding: 24px;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column-reverse;
  }

  .form-actions .btn {
    width: 100%;
  }
}
</style>
