<template>
  <div class="challenge-page">
    <div class="container">
      <nav class="page-breadcrumb" aria-label="返回">
        <button type="button" class="back-link" @click="handleClose">
          <AppIcon name="bi-chevron-left" aria-hidden="true" />返回靶场
        </button>
      </nav>
      <!-- 换题时重建工作台：会话、草稿与环境轮询都绑定单一题目，绝不沿用上一题状态。 -->
      <ChallengeWorkspace :key="challengeId" :challenge-id="challengeId" mode="page" @close="handleClose" @solved="handleSolved" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/shared/design/AppIcon.vue'
import ChallengeWorkspace from '@/learning/practice/ChallengeWorkspace.vue'

const route = useRoute()
const router = useRouter()
const challengeId = computed(() => Number(route.params.id))

function handleClose() { router.push('/challenges') }
function handleSolved() { /* 工作台内部已读回统计与记录。 */ }
</script>

<style scoped>
.challenge-page { padding: var(--space-3) 0 var(--space-6); }
.page-breadcrumb { margin-bottom: var(--space-2); }
.back-link { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid transparent; border-radius: var(--radius-control); background: transparent; color: var(--ink-secondary); font: inherit; cursor: pointer; }
.back-link:hover { background: var(--surface-hover); color: var(--ink); }
.back-link:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
