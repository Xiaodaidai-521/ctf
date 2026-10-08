<template>
  <div class="student-learning-page">
    <div class="page-header-bar">
      <h2>用户学习进度与掌握报表</h2>
      <div class="toolbar">
        <a-select v-model="sortMode" style="width:180px" placeholder="排序方式">
          <a-option value="self_assessed_at">按自评时间排序</a-option>
          <a-option value="mastery">按掌握度排序</a-option>
        </a-select>
        <a-input-search v-model="searchText" placeholder="搜索用户姓名..." style="width:240px" allow-clear />
      </div>
    </div>

    <!-- 汇总卡片 -->
    <div class="summary-row">
      <div class="summary-card"><span class="s-num">{{ students.length }}</span><span class="s-label">用户总数</span></div>
      <div class="summary-card"><span class="s-num">{{ onboardedCount }}</span><span class="s-label">已完成引导</span></div>
      <div class="summary-card"><span class="s-num">{{ avgMastery }}%</span><span class="s-label">平均掌握度</span></div>
      <div class="summary-card"><span class="s-num">{{ totalSolved }}</span><span class="s-label">总解题数</span></div>
    </div>

    <!-- 用户列表 -->
    <a-table :data="filteredStudents" :columns="columns" :loading="loading" row-key="id"
      :pagination="{ pageSize: 10, showTotal: true }" @row-click="openDetail" style="cursor:pointer">
      <template #onboarded="{ record }">
        <a-tag :color="record.onboarded ? 'green' : 'orange'" size="small">{{ record.onboarded ? '已引导' : '未引导' }}</a-tag>
      </template>
      <template #skills="{ record }">
        <div class="skill-mini">
          <span v-for="(v,k) in record.skills" :key="k" class="s-dot" :style="{background:v>=4?'#52c41a':v>=2?'#faad14':'#f5222d'}" :title="dirLabel(k)+':'+v"></span>
        </div>
      </template>
      <template #mastery="{ record }">
        <a-progress :percent="record.mastery" :size="18" :show-text="false" :stroke-width="6" style="width:100px" />
        <span style="margin-left:6px;font-size:13px">{{ record.mastery }}%</span>
      </template>
      <template #solved="{ record }">
        <span class="solved-badge">{{ record.solved_count }}</span>
      </template>
    </a-table>

    <!-- 用户详情弹窗 — 学习看板 -->
    <a-modal v-model:visible="modalVisible" :title="modalTitle" :footer="false" width="800px">
      <div v-if="detail">
        <a-descriptions :column="3" bordered size="small" style="margin-bottom:16px">
          <a-descriptions-item label="用户名">{{ detail.username }}</a-descriptions-item>
          <a-descriptions-item label="引导状态">{{ detail.onboarded ? '已完成' : '未完成' }}</a-descriptions-item>
          <a-descriptions-item label="总分数">{{ detail.score }}</a-descriptions-item>
          <a-descriptions-item label="解题数">{{ detail.solved_count }}</a-descriptions-item>
          <a-descriptions-item label="掌握度">{{ detail.mastery }}%</a-descriptions-item>
        </a-descriptions>

        <!-- 学习目标 -->
        <div v-if="detail.goals" class="info-block">
          <h4>学习目标</h4><p>{{ detail.goals || '未设置' }}</p>
        </div>

        <!-- CTF 六方向自评 -->
        <h4 style="margin:12px 0 8px">CTF 六方向自评</h4>
        <div v-if="hasSkills">
          <div v-for="(v,k) in detail.skills" :key="k" class="skill-row">
            <span class="skill-label">{{ dirLabel(k) }}</span>
            <a-rate :model-value="v" :count="5" disabled :size="14" style="flex:1" />
            <span class="skill-score">{{ v }}/5</span>
          </div>
        </div>
        <div v-else class="empty-hint">未设置技能自评</div>

        <!-- 知识概念掌握度 -->
        <h4 style="margin:16px 0 8px">知识概念掌握度</h4>
        <div v-if="detail.concepts?.length">
          <div v-for="c in detail.concepts" :key="c.name" class="concept-row">
            <span class="concept-name">{{ c.name }}</span>
            <div class="concept-bar-bg"><div class="concept-bar" :style="{width:c.mastery*100+'%',background:c.mastery>.7?'#52c41a':c.mastery>.4?'#faad14':'#f5222d'}"></div></div>
            <span class="concept-val">{{ Math.round(c.mastery*100) }}%</span>
          </div>
        </div>
        <div v-else class="empty-hint">暂无知识状态数据</div>

        <!-- 学习洞察 -->
        <h4 style="margin:16px 0 8px">学习洞察</h4>
        <div v-if="detailInsights.length" class="insight-list">
          <div v-for="(ins,i) in detailInsights" :key="i" class="insight-card" :class="'sev-'+ins.severity">
            <span class="ins-type">{{ typeLabel(ins.insight_type) }}</span>
            <strong>{{ ins.title }}</strong>
            <p>{{ ins.description }}</p>
          </div>
        </div>
        <div v-else><a-spin :loading="insightsLoading"><span class="empty-hint">加载中...</span></a-spin></div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

const students = ref([])
const loading = ref(false)
const searchText = ref('')
const sortMode = ref('self_assessed_at')
const modalVisible = ref(false)
const detail = ref(null)
const detailInsights = ref([])
const insightsLoading = ref(false)

const dirLabel = (k) => ({web:'Web安全',crypto:'密码学',pwn:'二进制安全',reverse:'逆向工程',forensics:'数字取证',misc:'综合杂项'}[k]||k)
const typeLabel = (t) => ({strength:'强项',weakness:'弱项',plateau:'平台期',acceleration:'加速期',recommendation:'建议'}[t]||t)

const columns = [
  { title:'用户名', dataIndex:'username', width:120 },
  { title:'引导', slotName:'onboarded', width:80 },
  { title:'CTF方向', slotName:'skills', width:140 },
  { title:'掌握度', slotName:'mastery', width:150 },
  { title:'解题', slotName:'solved', width:70 },
]

const filteredStudents = computed(() => {
  const q = searchText.value.toLowerCase()
  const list = q ? students.value.filter(s => s.username.toLowerCase().includes(q)) : students.value
  return [...list].sort((a, b) => {
    if (sortMode.value === 'mastery') {
      return (b.mastery || 0) - (a.mastery || 0) || getSelfAssessmentTime(b) - getSelfAssessmentTime(a)
    }
    return getSelfAssessmentTime(b) - getSelfAssessmentTime(a) || (b.mastery || 0) - (a.mastery || 0)
  })
})

const getSelfAssessmentTime = (record) => {
  const time = record.self_assessed_at ? new Date(record.self_assessed_at).getTime() : 0
  return Number.isFinite(time) ? time : 0
}
const hasSkills = computed(() => detail.value?.skills && Object.keys(detail.value.skills).length > 0)
const onboardedCount = computed(() => students.value.filter(s => s.onboarded).length)
const avgMastery = computed(() => {
  const vals = students.value.filter(s => s.mastery > 0).map(s => s.mastery)
  return vals.length ? Math.round(vals.reduce((a,b)=>a+b,0)/vals.length) : 0
})
const totalSolved = computed(() => students.value.reduce((a,b)=>a+(b.solved_count||0),0))
const modalTitle = computed(() => detail.value ? `${detail.value.username} - 学习报表` : '')

const fetchStudents = async () => {
  loading.value = true
  try {
    const loadReport = userStore.userInfo?.role === 'teacher'
      ? api.analytics.teacherStudentReport
      : api.analytics.adminStudentReport
    students.value = await loadReport() || []
  } catch(e){ console.error(e) }
  finally { loading.value = false }
}

const openDetail = async (record) => {
  detail.value = record
  modalVisible.value = true
  insightsLoading.value = true
  detailInsights.value = []
  try {
    const rec = await api.learningAgent.recommend()
    const recs = rec?.recommendations || []
    const ins = await api.analytics.insights()
    const all = [...recs.map(r=>({insight_type:r.type,title:r.title,description:r.reason,severity:'info'})),...(Array.isArray(ins)?ins:[])]
    detailInsights.value = all.slice(0,8)
  } catch(e){}
  finally { insightsLoading.value = false }
}

onMounted(fetchStudents)
</script>

<style scoped>
.page-header-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.page-header-bar h2{margin:0;font-size:20px;font-weight:600}
.toolbar{display:flex;align-items:center;gap:12px}
.summary-row{display:flex;gap:16px;margin-bottom:24px}
.summary-card{flex:1;background:#fff;border-radius:8px;padding:16px 20px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.s-num{display:block;font-size:24px;font-weight:700;color:#1f1f1f}
.s-label{display:block;font-size:12px;color:#9499a0;margin-top:4px}
.skill-mini{display:flex;gap:3px}
.s-dot{width:10px;height:10px;border-radius:50%}
.solved-badge{display:inline-block;min-width:24px;text-align:center;background:#e6f7ff;color:#1890ff;border-radius:10px;padding:1px 8px;font-size:12px;font-weight:600}
.skill-row{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.skill-label{width:80px;font-size:13px;text-align:right}
.skill-score{font-size:13px;font-weight:600;width:30px}
.concept-row{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.concept-name{width:100px;font-size:12px;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.concept-bar-bg{flex:1;height:12px;background:#f0f0f0;border-radius:6px;overflow:hidden}
.concept-bar{height:100%;border-radius:6px;transition:width .3s}
.concept-val{width:36px;font-size:12px;font-weight:600;text-align:right}
.empty-hint{color:#9499a0;font-size:13px;text-align:center;padding:16px 0}
.info-block{margin-bottom:8px}
.info-block h4{font-size:14px;margin:0 0 4px}
.info-block p{font-size:13px;color:#61666d;margin:0}
.insight-list{display:flex;flex-direction:column;gap:8px}
.insight-card{padding:10px 14px;border-radius:6px;border-left:3px solid #165dff;background:#f6f8ff}
.insight-card.sev-warning{border-left-color:#faad14;background:#fffbe6}
.insight-card.sev-critical{border-left-color:#f5222d;background:#fff1f0}
.insight-card strong{font-size:13px;display:block;margin:2px 0}
.insight-card p{font-size:12px;color:#61666d;margin:0}
.ins-type{display:inline-block;padding:0 6px;border-radius:3px;font-size:11px;background:#e6f7ff;color:#1890ff;margin-right:6px}
</style>
