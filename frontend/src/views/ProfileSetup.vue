<template>
  <div class="profile-setup-page">
    <div class="setup-container">
      <a-steps :current="step + 1" class="setup-steps">
        <a-step title="能力评估" />
        <a-step title="学习偏好" />
      </a-steps>

      <div class="step-content" v-if="step === 0">
        <h2 class="step-title">CTF 各方向能力自评</h2>
        <p class="step-desc">1星为入门，5星为精通</p>
        <div class="rating-list">
          <div v-for="d in directions" :key="d.key" class="rating-row">
            <span class="rating-label">{{ d.label }}</span>
            <a-rate v-model="form.ratings[d.key]" :count="5" />
          </div>
        </div>
        <div class="step-actions">
          <span></span>
          <a-button type="primary" size="large" @click="step = 1">下一步</a-button>
        </div>
      </div>

      <div class="step-content" v-if="step === 1">
        <h2 class="step-title">学习偏好设置</h2>

        <div class="pref-section">
          <label class="pref-label">学习节奏</label>
          <a-radio-group v-model="form.preferences.pace">
            <a-radio value="scheduled">稳扎稳打</a-radio>
            <a-radio value="intensive">快速突击</a-radio>
            <a-radio value="self_paced">灵活调整</a-radio>
          </a-radio-group>
        </div>

        <div class="pref-section">
          <label class="pref-label">学习形式（多选）</label>
          <a-checkbox-group v-model="form.preferences.formats">
            <a-checkbox value="video">视频教程</a-checkbox>
            <a-checkbox value="reading">文本阅读</a-checkbox>
            <a-checkbox value="hands_on">动手实验</a-checkbox>
            <a-checkbox value="discussion">互动讨论</a-checkbox>
          </a-checkbox-group>
        </div>

        <div class="pref-section">
          <label class="pref-label">每日学习时长：{{ form.preferences.duration }} 分钟</label>
          <a-slider v-model="form.preferences.duration" :min="15" :max="240" :step="15" />
        </div>

        <div class="pref-section">
          <label class="pref-label">难度偏好：{{ difficultyLabel }}</label>
          <a-slider v-model="form.preferences.difficulty_bias" :min="-2" :max="2" :step="1" :marks="difficultyMarks" />
        </div>

        <div class="step-actions">
          <a-button size="large" @click="step = 0">上一步</a-button>
          <a-button type="primary" size="large" :loading="submitting" @click="handleSubmit">完成设置</a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import api from '@/api'

const router = useRouter()
const step = ref(0)
const submitting = ref(false)

const defaultDirections = [
  { key: 'web', label: 'Web 安全' },
  { key: 'crypto', label: '密码学' },
  { key: 'pwn', label: '二进制安全' },
  { key: 'reverse', label: '逆向工程' },
  { key: 'forensics', label: '电子取证' },
  { key: 'misc', label: '安全杂项' }
]
const directions = ref(defaultDirections)

const form = ref({
  ratings: {},
  preferences: {
    pace: 'scheduled',
    formats: ['hands_on'],
    duration: 60,
    difficulty_bias: 0
  }
})

const syncRatingKeys = () => {
  directions.value.forEach((direction) => {
    if (form.value.ratings[direction.key] === undefined) {
      form.value.ratings[direction.key] = 0
    }
  })
}

const loadDirections = async () => {
  try {
    const data = await api.studentProfile.learningDirections()
    if (Array.isArray(data) && data.length > 0) {
      directions.value = data
    }
  } catch (error) {
    console.error('Failed to load learning directions:', error)
  } finally {
    syncRatingKeys()
  }
}

const difficultyMarks = { [-2]: '偏易', [0]: '适中', [2]: '偏难' }

const difficultyLabel = computed(() => {
  const v = form.value.preferences.difficulty_bias
  if (v === 0) return '适中'
  return v > 0 ? `偏难 +${v}` : `偏易 ${v}`
})

const handleSubmit = async () => {
  submitting.value = true
  try {
    await api.studentProfile.onboarding({
      skills: form.value.ratings,
      pace: form.value.preferences.pace,
      modality: form.value.preferences.formats,
      daily_hours: form.value.preferences.duration / 60,
      difficulty_bias: form.value.preferences.difficulty_bias,
    })
    Message.success('画像设置完成')
    router.replace('/dashboard')
  } catch {
    Message.error('提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

onMounted(loadDirections)
</script>

<style scoped>
.profile-setup-page {
  min-height: calc(100vh - 64px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f6f7f8;
  padding: 24px;
}

.setup-container {
  width: 100%;
  max-width: 640px;
  background: white;
  border-radius: 12px;
  padding: 40px;
  box-shadow: 0 2px 16px rgba(0,0,0,0.06);
}

.setup-steps { margin-bottom: 40px; }

.step-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 8px;
}

.step-desc {
  font-size: 13px;
  color: #9499a0;
  margin-bottom: 24px;
}

.rating-list { margin-bottom: 24px; }

.rating-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid #f1f2f3;
}

.rating-label {
  font-size: 14px;
  color: #1f1f1f;
  min-width: 100px;
}

.pref-section { margin-bottom: 24px; }

.pref-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #1f1f1f;
  margin-bottom: 12px;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
}
</style>
