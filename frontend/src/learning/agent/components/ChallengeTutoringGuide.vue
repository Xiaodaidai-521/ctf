<template>
  <details class="challenge-tutoring" :open="expanded" :aria-label="policy.target ? `题内辅导说明：${policy.target}` : '题内辅导说明'" @toggle="onToggle">
    <summary class="guide-heading">
      <span class="guide-title"><AppIcon name="bi-bullseye" aria-hidden="true" />本题提示口径</span>
      <span class="guide-source">{{ policy.authorHint.available ? '作者提示已显示' : '本题无作者提示' }}</span>
      <span class="guide-compact">{{ compactLine }}</span>
    </summary>

    <div class="guide-content">
      <div class="guide-author">
        <span class="author-label">题面提示</span>
        <p>{{ policy.authorHint.available ? '题目说明了作者公开提示，已显示在题面区。' : '本题没有作者公开提示。' }}</p>
        <p class="guide-note">{{ policy.authorHint.note }}</p>
      </div>

      <div class="guide-tiers">
        <span class="tier-label">智能体分级提示</span>
        <ol class="tier-list">
          <li v-for="tier in policy.tiers" :key="tier.key" :class="`is-${tier.state}`">
            <span class="tier-name">{{ tier.label }}</span>
            <span class="tier-desc">{{ tier.description }}</span>
          </li>
        </ol>
        <p class="guide-level" :class="{ 'has-level': policy.level }">{{ policy.levelLabel }}</p>
      </div>

      <p class="guide-note">{{ policy.note }}</p>
    </div>
  </details>
</template>
<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
const props = defineProps({
  // 由 tutoringPolicy 生成；组件不自行推导层级。
  policy: { type: Object, required: true },
})
// 默认收起：摘要行已给出分层顺序，展开再看逐条说明与层级来源（桌面与手机一致）。
const expanded = ref(false)
const compactLine = computed(() => {
  const tiers = props.policy.tiers.map(tier => tier.label).join(' → ')
  const level = props.policy.level ? ` · 后台记录第 ${props.policy.level} 级` : ' · 后台未返回当前层级'
  return `分级：${tiers}${level}`
})
function onToggle(event) {
  // 用户手动展开/收起后以控件真实状态为准。
  expanded.value = event.target.open
}
</script>
<style scoped>
.challenge-tutoring { padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface-muted); min-width: 0; }
.guide-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-1) var(--space-2); cursor: pointer; min-height: var(--control-height); padding-block: var(--space-1); }
.guide-title { display: flex; align-items: center; gap: var(--space-1); min-width: 0; font-size: var(--text-caption); font-weight: var(--weight-medium); overflow-wrap: anywhere; }
.guide-source { flex: none; color: var(--ink-secondary); font-size: var(--text-caption); }
.guide-compact { flex-basis: 100%; color: var(--ink-muted); font-size: var(--text-caption); overflow-wrap: anywhere; }
/* 展开后逐条列出，摘要行不再重复。 */
.challenge-tutoring[open] .guide-compact { display: none; }
.guide-content { display: grid; gap: var(--space-1); padding-bottom: var(--space-1); }
.guide-author { display: grid; gap: 2px; }
.author-label, .tier-label { color: var(--ink-secondary); font-size: var(--text-caption); }
.guide-author p { margin: 0; font-size: var(--text-caption); }
.tier-list { margin: 0; padding-left: var(--space-3); display: grid; gap: 2px; }
.tier-list li { font-size: var(--text-caption); color: var(--ink-secondary); }
.tier-list li.is-available { color: var(--ink); }
.tier-list li.is-later { color: var(--ink-muted); }
.tier-list li.is-policy { color: var(--ink-secondary); }
.tier-name { margin-right: var(--space-1); font-weight: var(--weight-medium); }
.tier-desc { color: var(--ink-muted); }
.guide-level { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.guide-level.has-level { color: var(--agent-accent); }
.guide-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
</style>
