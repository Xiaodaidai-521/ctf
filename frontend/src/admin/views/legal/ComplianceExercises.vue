<template>
  <LegalWorkspace
    title="演练入口"
    subtitle="聚合 Compliance 分类下的合规演练题目，连接 CTF 实训与法律合规场景。"
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
        <strong>{{ complianceCategory?.name || 'Compliance' }}</strong>
        <p>{{ complianceCategory?.description || '合规演练分类会通过后端数据迁移自动创建。' }}</p>
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
  { key: 'difficulty', label: '难度', badge: true },
  { key: 'score', label: '分值' },
  { key: 'solve_count', label: '解出数' },
  { key: 'is_active', label: '状态', formatter: (value) => value ? 'active' : 'inactive', badge: true },
]

const metrics = computed(() => [
  { label: '演练题目', value: exercises.value.length, hint: 'Compliance' },
  { label: '启用中', value: exercises.value.filter((item) => item.is_active).length, hint: 'active' },
  { label: '分类题数', value: complianceCategory.value?.challenge_count || 0, hint: 'category' },
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
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: #334155;
}
</style>
