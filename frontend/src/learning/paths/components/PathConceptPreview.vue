<template>
  <section class="concept-preview" aria-labelledby="concept-preview-title">
    <header class="preview-head">
      <h2 id="concept-preview-title">本航线知识点</h2>
      <button type="button" class="text-btn" @click="noteVisible = !noteVisible">
        {{ noteVisible ? '收起说明' : '查看完整图谱说明' }}
      </button>
    </header>
    <p class="preview-note">
      现有概念接口不支持按航线过滤，也不返回本航线的掌握状态；这里不拿全部概念或固定条数冒充本航线图谱。
    </p>
    <p v-if="noteVisible" class="preview-gap" role="status">
      完整航线图谱接口尚未提供，当前无法渲染。原入口保留，待后端给出航线节点、先修边与本人掌握字段后再接入。
    </p>
    <router-link v-if="pathId" :to="`/learning-paths/${pathId}`" class="text-btn">返回航线详情查看章节结构</router-link>
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({ pathId: { type: [String, Number], default: '' } })
const noteVisible = ref(false)
</script>

<style scoped>
.concept-preview { display: grid; gap: var(--space-1); min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.preview-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1); }
h2 { margin: 0; font-size: var(--text-card); }
.preview-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; }
.preview-gap { margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--warning-soft); color: var(--warning); font-size: var(--text-caption); line-height: 1.6; }
.text-btn { justify-self: start; border: 0; background: transparent; color: var(--action); font: inherit; font-size: var(--text-caption); cursor: pointer; padding: 0; }
.text-btn:hover { color: var(--action-hover); text-decoration: underline; }
.text-btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
