<template>
  <div class="challenge-modal" @click.self="handleClose">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal-container">
        <button class="close-btn" @click="handleClose" aria-label="Close">
          x
        </button>

        <div v-if="loading" class="challenge-state">
          <p>Loading challenge...</p>
        </div>

        <div v-else-if="!challenge" class="challenge-state">
          <p>Challenge unavailable.</p>
          <button class="btn btn-primary" @click="handleClose">
            Back to challenges
          </button>
        </div>

        <div v-else class="modal-content">
          <div class="challenge-section">
            <div class="challenge-header">
              <h1 class="challenge-title">{{ challenge.title }}</h1>
              <div class="challenge-badges">
                <span class="badge" :class="`badge-${challenge.difficulty}`">
                  {{ difficultyText }}
                </span>
                <span class="badge badge-primary">{{ challenge.category_name }}</span>
                <span class="badge badge-success">{{ challenge.score }} pts</span>
              </div>
            </div>

            <div class="challenge-body">
              <h2 class="section-title">Description</h2>
              <div class="challenge-description">{{ challenge.description }}</div>

              <div v-if="challenge.hint" class="challenge-hint">
                <h2 class="section-title">Hint</h2>
                <div class="hint-content">{{ challenge.hint }}</div>
              </div>

              <div v-if="challenge.attachment" class="challenge-attachment">
                <h2 class="section-title">Attachment</h2>
                <a :href="challenge.attachment" class="attachment-link" target="_blank">
                  <span class="attachment-icon">></span>
                  Download attachment
                </a>
              </div>
            </div>
          </div>

          <div class="submit-section">
            <div v-if="challenge.is_solved" class="success-banner">
              <div class="success-icon">OK</div>
              <div class="success-text">
                <h3>Already solved</h3>
                <p>Score {{ challenge.score }} pts</p>
              </div>
            </div>

            <h2 class="section-title">Submit Flag</h2>
            <div class="submit-form">
              <input
                v-model="flagInput"
                type="text"
                class="input"
                placeholder="Enter flag, for example flag{...}"
                @keyup.enter="handleSubmit"
              />
              <button
                class="btn btn-primary"
                @click="handleSubmit"
                :disabled="submitting || challenge.is_solved"
              >
                {{ submitting ? 'Submitting...' : 'Submit' }}
              </button>
            </div>

            <div v-if="message" class="submit-message" :class="messageType">
              <span class="message-icon">{{ messageType === 'success' ? 'OK' : '!' }}</span>
              {{ message }}
            </div>

            <div class="submit-hint">
              <p>Flag format is usually flag{...}</p>
            </div>

            <AIAssistant
              :challenge-id="route.params.id"
              :challenge-info="challenge"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChallengeStore } from '@/store/challenge'
import { useUserStore } from '@/store/user'
import AIAssistant from '@/components/AIAssistant.vue'

const route = useRoute()
const router = useRouter()
const challengeStore = useChallengeStore()
const userStore = useUserStore()

const challenge = ref(null)
const loading = ref(false)
const flagInput = ref('')
const submitting = ref(false)
const message = ref('')
const messageType = ref('')

const difficultyText = computed(() => {
  const map = {
    easy: 'Easy',
    medium: 'Medium',
    hard: 'Hard',
    expert: 'Expert',
  }
  return map[challenge.value?.difficulty] || 'Unknown'
})

const handleClose = () => {
  router.push('/challenges')
}

const fetchChallenge = async () => {
  loading.value = true
  challenge.value = null
  message.value = ''
  try {
    challenge.value = await challengeStore.fetchChallengeDetail(route.params.id)
  } catch (error) {
    console.error('Failed to fetch challenge detail:', error)
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  if (!challenge.value) {
    return
  }

  if (!flagInput.value.trim()) {
    message.value = 'Please enter a flag'
    messageType.value = 'error'
    return
  }

  submitting.value = true
  message.value = ''

  try {
    const result = await challengeStore.submitFlag(route.params.id, flagInput.value)
    if (result.success) {
      message.value = result.message
      messageType.value = 'success'
      flagInput.value = ''
      await fetchChallenge()
      if (userStore.isAuthenticated) {
        await userStore.fetchProfile()
      }
    } else {
      message.value = result.message
      messageType.value = 'error'
    }
  } catch (error) {
    message.value = 'Submit failed, please try again later'
    messageType.value = 'error'
  } finally {
    submitting.value = false
  }
}

watch(
  () => route.params.id,
  () => {
    fetchChallenge()
  },
  { immediate: true }
)
</script>

<style scoped>
.challenge-modal {
  position: fixed;
  inset: 0;
  z-index: 2000;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.modal-container {
  width: 100%;
  max-width: 1000px;
  max-height: 90vh;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  animation: slideUp 0.3s ease;
  position: relative;
}

@keyframes slideUp {
  from {
    transform: translateY(30px);
    opacity: 0;
  }

  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 50%;
  font-size: 20px;
  cursor: pointer;
  transition: all 0.3s;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.close-btn:hover {
  background: rgba(0, 0, 0, 0.1);
  color: var(--error-color);
  transform: rotate(90deg);
}

.challenge-state {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 32px;
  text-align: center;
}

.modal-content {
  display: grid;
  grid-template-columns: 1fr 380px;
  height: 90vh;
  overflow: hidden;
}

.challenge-section {
  padding: 32px;
  overflow-y: auto;
  border-right: 1px solid #f0f0f0;
  min-height: 0;
}

.challenge-header {
  border-bottom: 2px solid #f0f0f0;
  padding-bottom: 20px;
  margin-bottom: 24px;
}

.challenge-title {
  font-size: 28px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 16px;
  line-height: 1.3;
}

.challenge-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.badge {
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.badge-easy {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
}

.badge-medium {
  background: linear-gradient(135deg, #faad14 0%, #ffc53d 100%);
}

.badge-hard {
  background: linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%);
}

.badge-expert {
  background: linear-gradient(135deg, #7235d2 0%, #9254de 100%);
}

.badge-primary {
  background: linear-gradient(135deg, #1890ff 0%, #40a9ff 100%);
}

.badge-success {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.challenge-description {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-primary);
  white-space: pre-wrap;
  margin-bottom: 24px;
  padding: 20px;
  background: #fafafa;
  border-radius: var(--radius-md);
  border-left: 4px solid var(--primary-color);
}

.challenge-hint {
  margin-bottom: 24px;
}

.hint-content {
  background: linear-gradient(135deg, #fffbe6 0%, #fff7cc 100%);
  padding: 16px 20px;
  border-radius: var(--radius-md);
  border-left: 4px solid var(--warning-color);
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
}

.challenge-attachment {
  margin-bottom: 24px;
}

.attachment-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  color: var(--primary-color);
  border-radius: var(--radius-sm);
  text-decoration: none;
  transition: all 0.3s;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.15);
}

.attachment-link:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.25);
}

.attachment-icon {
  font-size: 18px;
}

.submit-section {
  padding: 32px;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
  min-height: 0;
}

.success-banner {
  padding: 20px;
  background: linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%);
  border-radius: var(--radius-md);
  border: 2px solid #b7eb8f;
  display: flex;
  align-items: center;
  gap: 16px;
}

.success-icon {
  font-size: 24px;
  font-weight: 700;
}

.success-text h3 {
  font-size: 16px;
  font-weight: bold;
  color: var(--success-color);
  margin-bottom: 4px;
}

.success-text p {
  font-size: 14px;
  color: var(--success-color);
}

.submit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.submit-message {
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    transform: translateX(20px);
    opacity: 0;
  }

  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.submit-message.success {
  background: linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%);
  border: 1px solid #b7eb8f;
  color: var(--success-color);
}

.submit-message.error {
  background: linear-gradient(135deg, #fff2f0 0%, #ffccc7 100%);
  border: 1px solid #ffccc7;
  color: var(--error-color);
}

.message-icon {
  font-weight: bold;
  font-size: 18px;
}

.submit-hint {
  padding: 16px;
  background: white;
  border-radius: var(--radius-sm);
  border-left: 4px solid var(--warning-color);
}

.submit-hint p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.challenge-section::-webkit-scrollbar,
.submit-section::-webkit-scrollbar {
  width: 6px;
}

.challenge-section::-webkit-scrollbar-track,
.submit-section::-webkit-scrollbar-track {
  background: transparent;
}

.challenge-section::-webkit-scrollbar-thumb,
.submit-section::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 3px;
}

.challenge-section::-webkit-scrollbar-thumb:hover,
.submit-section::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

@media (max-width: 1024px) {
  .modal-content {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr auto;
  }

  .challenge-section {
    border-right: none;
    border-bottom: 1px solid #f0f0f0;
  }
}

@media (max-width: 640px) {
  .modal-container {
    max-height: 100vh;
    border-radius: 0;
  }

  .modal-content {
    height: 100vh;
  }

  .challenge-section,
  .submit-section {
    padding: 20px;
  }

  .challenge-title {
    font-size: 22px;
  }
}
</style>
