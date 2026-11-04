<template>
  <FoundationFrame current="library">
    <p class="foundation-purpose">资料库负责资料与出处；索引工具维护检索，索引健康核对处理记录，授权监督核对课程权限。教师备课使用知识基座与材料工坊。</p>
    <KnowledgeLibrary />
  </FoundationFrame>
</template>
<script setup>
import FoundationFrame from './FoundationFrame.vue'
// This is the historical staff capability, not a teacher page or layout.
import KnowledgeLibrary from '@/learningKnowledge/KnowledgeLibrary.vue'
</script>
<style scoped>
.foundation-purpose { max-width: var(--page-width); margin: var(--space-2) auto 0; padding-inline: var(--page-gutter); color: var(--ink-secondary); font-size: var(--text-caption); }
</style>
