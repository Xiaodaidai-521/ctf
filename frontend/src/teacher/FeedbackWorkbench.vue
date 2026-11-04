<template>
  <main class="feedback-workbench">
    <header class="workbench-header">
      <div>
        <h1>反馈处理</h1>
        <p>先核查反馈与抽查样本，再整理问题组与教学配置候选。</p>
      </div>
      <router-link to="/teacher/feedback/reconciliation" class="audit-link">事件核对</router-link>
    </header>
    <nav class="section-links" aria-label="反馈处理分区">
      <a href="#queue" @click.prevent="goToSection('#queue')">反馈待办</a>
      <a href="#sampling" @click.prevent="goToSection('#sampling')">随机抽查</a>
      <a href="#candidates" @click.prevent="goToSection('#candidates')">问题组与候选</a>
    </nav>
    <section id="queue" ref="queueSection" class="workbench-zone" tabindex="-1" aria-labelledby="queue-heading">
      <h2 id="queue-heading">反馈待办</h2>
      <FeedbackQueue embedded @ready="sectionReady('queue')" />
    </section>
    <section id="candidates" ref="candidateSection" class="workbench-zone" tabindex="-1" aria-labelledby="candidates-heading">
      <details class="length-disclosure" :open="candidateOpen" @toggle="candidateOpen = $event.currentTarget.open">
        <summary class="length-disclosure__summary"><h2 id="candidates-heading">问题组与候选</h2></summary>
        <div class="length-disclosure__body"><FeedbackCandidates embedded @ready="sectionReady('candidates')" /></div>
      </details>
    </section>
  </main>
</template>

<script setup>
import { nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FeedbackQueue from './FeedbackQueue.vue'
import FeedbackCandidates from './FeedbackCandidates.vue'
import '@/shared/layout/disclosure.css'

const route = useRoute()
const router = useRouter()
const queueSection = ref(null)
const candidateSection = ref(null)
const candidateOpen = ref(route.hash === '#candidates')
const readySections = new Set()
let alive = true
let focusRead = 0
onBeforeUnmount(() => { alive = false; ++focusRead })
async function focusSection() {
  const current = ++focusRead
  if (route.hash === '#candidates') candidateOpen.value = true
  await nextTick()
  if (alive && current === focusRead && route.hash === '#sampling') {
    const sampling = queueSection.value?.querySelector?.('#feedback-sampling')
    if (sampling) sampling.open = true
  }
  // Let the router's post-navigation scroll finish before applying this anchor.
  await new Promise(resolve => requestAnimationFrame(resolve))
  if (!alive || current !== focusRead) return
  const section = route.hash === '#candidates' ? candidateSection.value : route.hash === '#sampling' ? queueSection.value?.querySelector?.('#feedback-sampling > summary') : route.hash === '#queue' ? queueSection.value : null
  section?.focus({ preventScroll: true })
  section?.scrollIntoView({ block: 'start', behavior: 'auto' })
}
function sectionReady(name) {
  if (readySections.has(name)) return
  readySections.add(name)
  // Queue and batch reads change the height above the candidate section.
  if (readySections.size === 2) void focusSection()
}
async function goToSection(hash) {
  await router.replace({ path: route.path, query: route.query, hash })
  if (alive) await focusSection()
}
watch(() => route.hash, focusSection)
onMounted(focusSection)
</script>

<style scoped>
.feedback-workbench { max-width: var(--page-width); margin: 0 auto; padding: var(--density-gap); color: var(--ink); font-family: var(--font-family); }
.workbench-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--density-gap); }
h1 { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); font-weight: var(--weight-strong); }
.workbench-header p { margin: 0; color: var(--ink-secondary); }
.audit-link, .section-links a { color: var(--ink); background: var(--surface); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); text-decoration: none; }
.section-links { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-bottom: var(--density-gap); }
.feedback-workbench :deep(.fb-btn-primary) { background: var(--button-primary); border-color: var(--button-primary); border-radius: var(--radius-pill); color: var(--on-action); }
.feedback-workbench :deep(.fb-btn-primary:hover:not(:disabled)) { background: var(--button-primary-hover); }
.feedback-workbench :deep(.fb-btn-primary:active:not(:disabled)) { background: var(--button-primary-pressed); }
.workbench-zone { padding: var(--density-gap); background: var(--surface); border-radius: var(--radius-panel); margin-bottom: var(--density-gap); min-width: 0; scroll-margin-top: calc(var(--header-height) + var(--space-2)); }
h2 { margin: 0 0 var(--space-2); font-size: var(--text-section); line-height: var(--leading-tight); }
a:hover { background: var(--surface-hover); }
a:focus-visible, .workbench-zone:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 768px) { .feedback-workbench { padding: var(--space-1); } .workbench-zone { padding: var(--space-2); } }
</style>
