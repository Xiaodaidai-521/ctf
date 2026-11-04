<template>
  <section v-if="capability" class="detail" aria-labelledby="detail-heading">
    <header class="detail-head">
      <p class="detail-breadcrumb">{{ capability.trackLabel }} · {{ capability.dimensionLabel }}</p>
      <h2 id="detail-heading">{{ capability.title }}</h2>
      <div class="detail-tags">
        <span class="state-pill" :class="`tone-${capability.state.tone}`">{{ capability.state.label }}</span>
        <span class="status-tag" :class="capability.open ? 'tag-open' : 'tag-muted'">{{ capability.availabilityLabel }}</span>
        <span class="difficulty">难度 {{ capability.difficulty ?? '未知' }}/5</span>
      </div>
    </header>

    <div class="detail-section">
      <h3>练成后能做到</h3>
      <p>{{ capability.objective || '暂未提供这项能力的练习目标说明。' }}</p>
    </div>

    <div class="detail-section">
      <h3>知识点</h3>
      <p v-if="!capability.knownPoints.length" class="muted">暂未关联知识点。</p>
      <ul v-else class="point-list">
        <li v-for="point in capability.knownPoints" :key="point">{{ point }}</li>
      </ul>
    </div>

    <div class="detail-section">
      <h3>先修</h3>
      <p v-if="!capability.prerequisites.length" class="muted">未设置先修能力。</p>
      <ul v-else class="prereq-list">
        <li v-for="item in capability.prerequisites" :key="item.title" :class="`tone-${item.tone}`">
          <span class="prereq-mark" aria-hidden="true">{{ item.satisfied ? '已成' : '未成' }}</span>
          <span>{{ item.title }}</span>
          <span class="prereq-state">{{ item.stateLabel }}</span>
        </li>
      </ul>
      <p v-if="capability.prerequisites.length" class="muted">先修能力显示“独立通过”时，才算已完成。</p>
    </div>

    <div class="detail-section">
      <h3>最近的练习结果</h3>
      <dl class="evidence-grid">
        <div><dt>练习记录</dt><dd>{{ capability.evidence.count }} 条</dd></div>
        <div><dt>最近结果</dt><dd>{{ capability.evidence.result }}</dd></div>
        <div><dt>任务</dt><dd>{{ capability.evidence.task || '—' }}</dd></div>
        <div><dt>是否用过提示或讲解</dt><dd>{{ assistLabel }}</dd></div>
        <div><dt>时间</dt><dd>{{ capability.evidence.timeLabel }}</dd></div>
      </dl>
      <p v-if="capability.retestLabel" class="retest-note">复测时间：{{ capability.retestLabel }} · 到期没做也不会被记为错误。</p>
      <p class="muted">还没批完、暂无记录或环境出问题时，会分开说明，不会算作没通过。</p>
    </div>

    <div v-if="$slots.default" class="detail-section detail-related">
      <h3>任务与学习内容</h3>
      <slot />
    </div>
  </section>
  <section v-else class="detail detail-empty">
    <p>选择左侧一项能力，查看练习目标、先修能力和最近的练习结果。</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ capability: { type: Object, default: null } })

const assistLabel = computed(() => {
  const assisted = props.capability?.evidence?.assisted
  if (assisted === true) return '用过提示或讲解，不算独立通过'
  if (assisted === false) return '没有用过提示或讲解'
  return '无记录'
})
</script>

<style scoped>
.detail { display: grid; gap: var(--space-2); min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.detail-empty { color: var(--ink-secondary); font-size: var(--text-caption); }
.detail-head { display: grid; gap: var(--space-1); border-bottom: var(--stroke) solid var(--line); padding-bottom: var(--space-2); }
.detail-breadcrumb { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.detail-head h2 { margin: 0; font-size: var(--text-section); overflow-wrap: anywhere; }
.detail-tags { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }
.state-pill { padding: 0 var(--space-1); border: var(--stroke) solid currentColor; border-radius: var(--radius-pill); font-size: var(--text-caption); font-weight: var(--weight-strong); }
.status-tag, .difficulty { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); }
.tag-open { border-color: var(--positive); color: var(--positive); }
.tag-muted { color: var(--ink-muted); }
.detail-section { display: grid; gap: var(--space-1); }
.detail-section h3 { margin: 0; font-size: var(--text-card); }
.detail-section p { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.7; }
.muted { color: var(--ink-muted); }
.point-list, .prereq-list { display: flex; flex-wrap: wrap; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.point-list li { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.prereq-list { flex-direction: column; gap: calc(var(--space-1) / 2); }
.prereq-list li { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-1); font-size: var(--text-caption); color: var(--ink-secondary); }
.prereq-mark { color: var(--ink-muted); }
.prereq-list li.tone-success .prereq-mark { color: var(--positive); }
.prereq-state { color: var(--ink-muted); }
.evidence-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: var(--space-1) var(--space-2); margin: 0; }
.evidence-grid div { display: grid; gap: calc(var(--space-1) / 2); }
.evidence-grid dt { color: var(--ink-muted); font-size: var(--text-caption); }
.evidence-grid dd { margin: 0; font-size: var(--text-caption); overflow-wrap: anywhere; }
.retest-note { color: var(--warning); }
.tone-success { color: var(--positive); }
.tone-danger { color: var(--negative); }
.tone-warning { color: var(--warning); }
.tone-muted { color: var(--ink-muted); }
.tone-neutral { color: var(--ink-secondary); }
.state-pill.tone-success { background: var(--positive-soft); }
.state-pill.tone-danger { background: var(--negative-soft); }
.state-pill.tone-warning { background: var(--warning-soft); }
.state-pill.tone-muted, .state-pill.tone-neutral { background: var(--surface-muted); }
.detail-related { border-top: var(--stroke) solid var(--line); padding-top: var(--space-2); }
@media (max-width: 480px) {
  .detail { padding: var(--space-2); }
}
</style>
