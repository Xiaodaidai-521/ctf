<template>
  <LegalWorkspace
    title="演练入口"
    subtitle="浏览合规演练题目，将网络安全实训与法律合规场景结合。"
    table-title="合规演练题目"
    aside-title="分类状态"
    :metrics="metrics"
    :columns="columns"
    :rows="exercises"
    :loading="loading"
    :row-actions="[{ key: 'open', label: '打开' }]"
    :actions="[{ key: 'reload', label: '刷新分类', primary: true }]"
    @refresh="loadData"
    @action="loadData"
    @row-action="openExercise"
  >
    <template #aside>
      <div class="category-note">
        <strong>合规演练</strong>
        <p>{{ complianceCategory?.description || '合规演练分类由平台统一维护。' }}</p>
        <span>题目数：{{ exercises.length }}</span>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const router = useRouter()
const loading = ref(false)
const categories = ref([])
const exercises = ref([])

const complianceCategory = computed(() => categories.value.find((item) => item.name === 'Compliance'))

const columns = [
  { key: 'title', label: '题目' },
  { key: 'difficulty', label: '难度', labelKey: 'difficulty', badge: true },
  { key: 'score', label: '分值' },
  { key: 'solve_count', label: '解出数' },
  { key: 'is_active', label: '状态', formatter: (value) => value ? '启用中' : '已停用', badge: true },
]

const metrics = computed(() => [
  { label: '演练题目', value: exercises.value.length, hint: '合规分类' },
  { label: '启用中', value: exercises.value.filter((item) => item.is_active).length, hint: '当前可练' },
  { label: '分类题数', value: complianceCategory.value?.challenge_count || 0, hint: '本分类' },
])

async function loadData() {
  loading.value = true
  try {
    const categoryRes = await api.challenge.getCategories()
    categories.value = normalizeList(categoryRes)
    const category = complianceCategory.value
    if (!category) {
      exercises.value = []
      return
    }
    const challengeRes = await api.challenge.getChallenges({ category: category.id, page_size: 50 })
    exercises.value = normalizeList(challengeRes)
  } finally {
    loading.value = false
  }
}

function openExercise(key, row) {
  router.push(`/challenge/${row.id}`)
}

function normalizeList(response) {
  return response?.results || response || []
}

onMounted(loadData)
</script>

<style scoped>
.category-note {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
  color:var(--ink);
}
</style>
