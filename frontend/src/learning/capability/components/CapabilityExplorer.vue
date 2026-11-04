<template>
  <section class="explorer" aria-labelledby="explorer-heading">
    <header class="explorer-head">
      <div>
        <h2 id="explorer-heading">目录与能力</h2>
        <p>按主线选一项能力，看看要练成什么、需要哪些基础，以及最近的练习结果。</p>
      </div>
      <span v-if="selectedKey" class="select-note">已选：{{ selectedTitle || '一项能力' }}</span>
    </header>

    <div class="notice-row">
      <span class="notice" :class="catalog.published ? 'notice-ok' : 'notice-warn'">{{ catalog.statusLabel }}</span>
      <span class="notice notice-warn">动手操作类能力暂未开放</span>
    </div>

    <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">开放能力</span>
        <strong>{{ summary.openCapabilities }}</strong>
        <span class="summary-meta">数据安全与网络安全两条主线</span>
      </article>
      <article class="summary-card">
        <span class="summary-label">独立通过</span>
        <strong>{{ summary.independentCount }}</strong>
        <span class="summary-meta">自己独立完成并通过</span>
      </article>
      <article class="summary-card">
        <span class="summary-label">提示后待复测</span>
        <strong>{{ summary.assistedCount }}</strong>
        <span class="summary-meta">换一道新题再独立做一次</span>
      </article>
      <article class="summary-card">
        <span class="summary-label">继续练习</span>
        <strong>{{ summary.needsPracticeCount }}</strong>
        <span class="summary-meta">这次没有通过，继续练</span>
      </article>
    </div>

    <section v-for="track in tracks" :key="track.track" class="track-card">
      <div class="track-head">
        <div>
          <h3>{{ track.label }}</h3>
          <p>{{ trackDescription(track.track) }}</p>
        </div>
        <button type="button" class="btn btn-ghost" @click="$emit('diagnose', track.track)">
          <AppIcon name="bi-clipboard-pulse" /> 做一次诊断
        </button>
      </div>

      <div v-if="track.dimensions.length" class="dimension-row">
        <div v-for="dimension in track.dimensions" :key="dimension.key" class="dimension-chip">
          <span>{{ dimension.label }}<template v-if="dimension.count !== null"> · {{ dimension.count }} 项</template></span>
          <strong :class="`tone-${dimension.tone}`">{{ dimension.displayLabel }}</strong>
        </div>
      </div>

      <p v-if="!track.capabilities.length" class="empty-note">该主线暂时还没有开放的能力。</p>
      <ul v-else class="capability-list">
        <li v-for="capability in track.capabilities" :key="capability.key">
          <button
            type="button"
            class="capability-card"
            :class="{ 'is-selected': capability.key === selectedKey }"
            :aria-pressed="capability.key === selectedKey"
            @click="$emit('select', capability.key)"
          >
            <span class="capability-main">
              <span class="capability-title-row">
                <strong>{{ capability.title }}</strong>
                <span class="dimension-tag">{{ capability.dimensionLabel }}</span>
                <span class="status-tag" :class="capability.open ? 'tag-open' : 'tag-muted'">{{ capability.availabilityLabel }}</span>
              </span>
              <span class="objective">{{ capability.objective || '暂未提供这项能力的练习目标说明。' }}</span>
              <span class="capability-meta">
                <span>难度 {{ capability.difficulty ?? '未知' }}/5</span>
                <span v-for="point in capability.knownPoints" :key="point" class="kp">{{ point }}</span>
              </span>
            </span>
            <span class="capability-side">
              <span class="state-pill" :class="`tone-${capability.state.tone}`">{{ capability.state.label }}</span>
              <span class="evidence">
                <template v-if="capability.evidence.hasEvidence">
                  {{ capability.evidence.count }} 条 · {{ capability.evidence.result }}
                  <span v-if="capability.evidence.assisted" class="assist-note">用过提示或讲解</span>
                  <span class="date-note">{{ capability.evidence.timeLabel }}</span>
                </template>
                <template v-else>{{ capability.evidence.result }}</template>
              </span>
            </span>
          </button>
        </li>
      </ul>
    </section>

    <section class="legend" aria-labelledby="legend-heading">
      <h3 id="legend-heading">状态图例</h3>
      <ul>
        <li v-for="entry in legend" :key="entry.key"><strong>{{ entry.label }}</strong>：{{ entry.note }}</li>
      </ul>
      <p class="legend-note">还没做或还在批阅中的，不会显示成低分；没有练习记录时状态保持未知。</p>
    </section>

    <p class="data-source">来源：{{ summary.dataSource }} · 更新于 {{ summary.updatedLabel }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { STATE_LEGEND } from '../presentation.js'

const props = defineProps({
  catalog: { type: Object, required: true },
  summary: { type: Object, required: true },
  tracks: { type: Array, default: () => [] },
  selectedKey: { type: String, default: '' },
})
defineEmits(['select', 'diagnose'])

const legend = STATE_LEGEND
const selectedTitle = computed(() => props.tracks.flatMap(track => track.capabilities)
  .find(capability => capability.key === props.selectedKey)?.title || '')

function trackDescription(track) {
  return track === 'data'
    ? '分类分级依据、敏感项复核与风险决策回放。'
    : '授权边界、对象级授权与修复验证。'
}
</script>

<style scoped>
.explorer { display: grid; gap: var(--space-2); min-width: 0; }
.explorer-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.explorer-head h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.explorer-head p { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.select-note { color: var(--ink-secondary); font-size: var(--text-caption); }
.notice-row { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.notice { display: inline-flex; align-items: center; gap: var(--space-1); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); background: var(--surface); color: var(--ink-secondary); font-size: var(--text-caption); }
.notice-ok { border-color: var(--positive); color: var(--positive); }
.notice-warn { border-color: var(--warning); color: var(--warning); }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-2); }
.summary-card { display: grid; gap: var(--space-1); padding: var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.summary-label { color: var(--ink-muted); font-size: var(--text-caption); letter-spacing: .06em; }
.summary-card strong { font-size: var(--text-section); line-height: 1.1; }
.summary-meta { color: var(--ink-secondary); font-size: var(--text-caption); }
.track-card { border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); overflow: hidden; }
.track-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-1) var(--space-2); padding: var(--space-2); border-bottom: var(--stroke) solid var(--line); }
.track-head h3 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.track-head p { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.dimension-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-bottom: var(--stroke) solid var(--line); }
.dimension-chip { display: grid; gap: var(--space-1); padding: var(--space-1) var(--space-2); border-right: var(--stroke) solid var(--line); }
.dimension-chip:last-child { border-right: 0; }
.dimension-chip span { color: var(--ink-muted); font-size: var(--text-caption); }
.dimension-chip strong { font-size: var(--text-caption); }
.capability-list { display: grid; margin: 0; padding: 0; list-style: none; }
.capability-list li { border-bottom: var(--stroke) solid var(--line); }
.capability-list li:last-child { border-bottom: 0; }
.capability-card { display: grid; grid-template-columns: minmax(0, 1fr) minmax(10rem, .5fr); gap: var(--space-2); width: 100%; padding: var(--space-2); border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.capability-card:hover { background: var(--surface-muted); }
.capability-card.is-selected { background: var(--action-soft); box-shadow: inset var(--focus-width) 0 0 var(--action); }
.capability-card:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: calc(var(--focus-offset) * -1); }
.capability-main { display: grid; gap: var(--space-1); min-width: 0; }
.capability-title-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }
.capability-title-row strong { font-size: var(--text-body); overflow-wrap: anywhere; }
.dimension-tag, .status-tag { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); }
.tag-open { border-color: var(--positive); color: var(--positive); }
.tag-muted { color: var(--ink-muted); }
.objective { color: var(--ink-secondary); font-size: var(--text-caption); }
.capability-meta { display: flex; flex-wrap: wrap; gap: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.kp { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); }
.capability-side { display: grid; align-content: start; gap: var(--space-1); padding-left: var(--space-2); border-left: var(--stroke) solid var(--line); }
.state-pill { justify-self: start; padding: 0 var(--space-1); border: var(--stroke) solid currentColor; border-radius: var(--radius-pill); font-size: var(--text-caption); font-weight: var(--weight-strong); }
.evidence { display: grid; gap: calc(var(--space-1) / 2); color: var(--ink-secondary); font-size: var(--text-caption); overflow-wrap: anywhere; }
.assist-note { color: var(--warning); }
.date-note { color: var(--ink-muted); }
.tone-success { color: var(--positive); }
.tone-danger { color: var(--negative); }
.tone-warning { color: var(--warning); }
.tone-muted { color: var(--ink-muted); }
.tone-neutral { color: var(--ink-secondary); }
.state-pill.tone-success { background: var(--positive-soft); }
.state-pill.tone-danger { background: var(--negative-soft); }
.state-pill.tone-warning { background: var(--warning-soft); }
.state-pill.tone-muted { background: var(--surface-muted); }
.state-pill.tone-neutral { background: var(--surface-muted); }
.empty-note { margin: 0; padding: var(--space-2); color: var(--ink-muted); font-size: var(--text-caption); }
.legend { padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.legend h3 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.legend ul { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-3); margin: 0; padding: 0; list-style: none; color: var(--ink-secondary); font-size: var(--text-caption); }
.legend-note { margin: var(--space-1) 0 0; color: var(--ink-muted); font-size: var(--text-caption); }
.data-source { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.btn { display: inline-flex; align-items: center; gap: calc(var(--space-1) / 2); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-ghost { border-color: transparent; color: var(--action); }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 960px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dimension-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dimension-chip:nth-child(2n) { border-right: 0; }
  .capability-card { grid-template-columns: 1fr; }
  .capability-side { padding-left: 0; border-left: 0; grid-template-columns: auto 1fr; align-items: start; }
}
@media (max-width: 480px) {
  .summary-grid { grid-template-columns: 1fr; }
}
</style>
