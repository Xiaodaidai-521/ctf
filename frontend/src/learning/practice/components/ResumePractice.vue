<template>
  <section v-if="candidate" class="resume-practice" aria-label="继续上次练习">
    <div class="resume-copy">
      <p class="resume-eyebrow"><AppIcon name="bi-arrow-counterclockwise" />{{ label }}</p>
      <h3>{{ candidate.title || '上次练习的题目' }}</h3>
      <p>{{ reason }}</p>
    </div>
    <div class="resume-actions">
      <button v-if="candidate.available" class="btn btn-primary" @click="$emit('resume', candidate)">继续练习</button>
      <router-link v-else class="btn" :to="`/challenge/${candidate.id}`">查看题目</router-link>
      <router-link class="btn" to="/challenges">返回题目列表</router-link>
    </div>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
const props = defineProps({
  candidate: { type: Object, default: null },
  // local = 本机记录的上次进入；recent = 最近一次未解提交的替代
  source: { type: String, default: 'local' },
})
defineEmits(['resume'])
const label = computed(() => props.source === 'local' ? '继续上次' : '继续最近练习')
const reason = computed(() => {
  if (!props.candidate) return ''
  if (!props.candidate.available) return '这道题暂时无法确认是否可访问，可以回到列表重新选择。'
  return props.source === 'local' ? '按本机记录恢复上次进入的题目，不保存 Flag。' : '本机没有访问记录，按最近一次未通过提交推荐。'
})
</script>
<style scoped>
.resume-practice { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-2) var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.resume-eyebrow { display: flex; align-items: center; gap: var(--space-1); margin: 0 0 var(--space-1); color: var(--agent-accent); font-size: var(--text-caption); }
.resume-copy h3 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.resume-copy p { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.resume-actions { display: flex; flex-wrap: wrap; gap: var(--space-1); flex-shrink: 0; }
@media (max-width: 768px) {
  .resume-practice { flex-direction: column; align-items: stretch; }
}
</style>
