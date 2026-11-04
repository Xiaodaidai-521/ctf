<template>
  <section class="mastery-overview" aria-labelledby="mastery-heading">
    <header class="section-head">
      <div>
        <h2 id="mastery-heading">掌握与方向</h2>
        <p class="section-note">六方向来自画像基线与真实学习证据；数据不足的方向保持“待积累”，不以 0 分参与优劣比较。</p>
      </div>
      <router-link to="/capability-map" class="text-link">进入能力图谱 →</router-link>
    </header>

    <div class="mastery-grid">
      <AbilityRadarCard
        :initial-scores="initialScores"
        :dynamic-scores="dynamicScores"
        :eligible-for-ai="Boolean(growth?.eligible_for_ai)"
      />

      <aside class="direction-panel" aria-labelledby="direction-heading">
        <h3 id="direction-heading" class="panel-title">方向小结</h3>
        <dl class="extreme-grid">
          <div>
            <dt>优势方向</dt>
            <dd>{{ strongest ? strongest.label : '暂无足够数据' }}</dd>
            <span v-if="strongest" class="extreme-value">{{ strongest.current }} 分</span>
          </div>
          <div>
            <dt>待加强</dt>
            <dd>{{ weakest ? weakest.label : '暂无足够数据' }}</dd>
            <span v-if="weakest" class="extreme-value">{{ weakest.current }} 分</span>
          </div>
          <div>
            <dt>提升最大</dt>
            <dd>{{ improved ? improved.label : '暂无两次评分对比' }}</dd>
            <span v-if="improved" class="extreme-value">+{{ improved.delta }} 分</span>
          </div>
        </dl>
        <p class="panel-note">{{ sourceNote }}</p>
        <p v-if="growth?.risk_level" class="risk-note">学习关注提示：{{ riskLabel(growth.risk_level) }}</p>
      </aside>
    </div>

    <details class="direction-table" open>
      <summary>逐方向依据与时间</summary>
      <div class="table-scroll">
        <table>
          <caption>根据已记录的练习查看方向得分与依据，未记录的方向不以 0 补齐</caption>
          <thead>
            <tr><th scope="col">方向</th><th scope="col">初始基线</th><th scope="col">当前得分</th><th scope="col">变化</th><th scope="col">证据</th><th scope="col">最近更新</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key">
              <th scope="row">{{ row.label }}</th>
              <td>{{ row.initial === null ? '待评估' : `${row.initial} 分` }}</td>
              <td>{{ row.current === null ? '待积累' : `${row.current} 分` }}</td>
              <td>{{ row.delta === null ? '—' : `${row.delta >= 0 ? '+' : ''}${row.delta}` }}</td>
              <td>{{ evidenceText(row) }}</td>
              <td>{{ updatedAt }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>

    <section v-if="effectiveScores.length" class="score-panel" aria-labelledby="score-heading">
      <h3 id="score-heading" class="panel-title">教师最近评分</h3>
      <ul class="score-list">
        <li v-for="score in effectiveScores" :key="`${score.measured_at}-${score.total_score}`">
          <span>{{ formatDate(score.measured_at) }}</span>
          <strong>总分 {{ score.total_score ?? '—' }}</strong>
          <RecordView class="score-dims" :value="score.dimension_scores" title="本次方向评分" />
        </li>
      </ul>
      <p class="panel-note">来源：教学方案输入快照；只有一次评分时不做前后差值。</p>
    </section>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import AbilityRadarCard from '@/components/AbilityRadarCard.vue'
import RecordView from '@/shared/forms/RecordView.vue'
import { directionRows, extremeDirections, formatDate, improvedDirection } from '../presentation.js'

const props = defineProps({
  directions: { type: Array, default: () => [] },
  growth: { type: Object, default: null },
  teachingPlan: { type: Object, default: null },
})

const rows = computed(() => directionRows(props.directions, props.growth, { hasSelfAssessment: false }))
const strongest = computed(() => extremeDirections(rows.value).strongest)
const weakest = computed(() => extremeDirections(rows.value).weakest)
const improved = computed(() => improvedDirection(rows.value))
// 雷达与表格共用同一份“已知/未知”判断：缺证据的方向不传分，避免图上出现 0 分。
const scoreMap = field => {
  const map = {}
  for (const row of rows.value) {
    if (row[field] !== null && row[field] !== undefined) map[row.key] = row[field]
  }
  return map
}
const initialScores = computed(() => scoreMap('initial'))
const dynamicScores = computed(() => scoreMap('current'))
const updatedAt = computed(() => formatDate(props.growth?.updated_at || props.growth?.snapshot_at || null))
const effectiveScores = computed(() => {
  const scores = props.teachingPlan?.input_snapshot?.effective_scores
  return Array.isArray(scores) ? scores.filter(Boolean).slice(0, 2) : []
})
const sourceNote = computed(() => {
  const evidence = props.growth?.growth_evidence
  if (!evidence || typeof evidence !== 'object') return '暂未提供方向练习记录。'
  const counts = Object.values(evidence).filter(item => item?.status && item.status !== 'insufficient_data').length
  return `已有 ${counts} 个方向的真实练习记录；依据不足的方向不参与优势/短板判断。`
})
const riskLabel = value => ({ at_risk: '需要关注', normal: '正常', low: '低', high: '高' }[value] || value)
const evidenceText = row => {
  if (row.attempts === null) return '无记录'
  const rate = row.correctRate === null ? '' : `，正确率 ${row.correctRate}%`
  return `作答 ${row.attempts} 次${rate}`
}
</script>
<style scoped>
.mastery-overview { display: grid; gap: var(--space-2); }
.section-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.section-head h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.section-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.text-link { display: inline-flex; align-items: center; min-height: var(--control-height); color: var(--action); font-size: var(--text-caption); text-decoration: none; }
.mastery-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: var(--space-2); align-items: start; }
.direction-panel, .score-panel { min-width: 0; padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.panel-title { margin: 0 0 var(--space-2); font-size: var(--text-card); }
.extreme-grid { display: grid; gap: var(--space-1); margin: 0; }
.extreme-grid div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px var(--space-1); padding: var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); }
.extreme-grid dt { grid-column: 1; color: var(--ink-secondary); font-size: var(--text-caption); }
.extreme-grid dd { grid-column: 1; margin: 0; font-weight: var(--weight-strong); overflow-wrap: anywhere; }
.extreme-value { grid-column: 2; grid-row: 1 / span 2; align-self: center; color: var(--action); font-size: var(--text-caption); }
.panel-note { margin: var(--space-2) 0 0; color: var(--ink-muted); font-size: var(--text-caption); }
.risk-note { margin: var(--space-1) 0 0; color: var(--warning); font-size: var(--text-caption); }
.direction-table { padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.direction-table summary { min-height: var(--control-height); cursor: pointer; }
.table-scroll { overflow-x: auto; }
.direction-table table { width: 100%; border-collapse: collapse; font-size: var(--text-caption); text-align: left; }
.direction-table caption { padding: var(--space-1) 0; color: var(--ink-secondary); text-align: left; }
.direction-table th, .direction-table td { padding: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
.score-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.score-list li { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: var(--space-2); padding: var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); }
.score-dims { color: var(--ink-secondary); overflow-wrap: anywhere; }
.is-compact .mastery-grid { grid-template-columns: minmax(0, 1fr); }
.is-compact .score-list li { grid-template-columns: minmax(0, 1fr); }
.text-link:focus-visible, .direction-table summary:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
