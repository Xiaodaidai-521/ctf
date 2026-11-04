<template>
  <section class="module-content" aria-labelledby="module-content-title">
    <header class="content-head">
      <h2 id="module-content-title">教材内容</h2>
      <span class="type-pill">{{ view.typeLabel }}</span>
    </header>
    <div v-if="view.hasContent" class="markdown-body" v-html="html"></div>
    <div v-else class="empty-content">
      <icon-file aria-hidden="true" />
      <p>本章节暂未提供教材内容；不需要空等，可先查看实验与先修说明。</p>
    </div>
  </section>
</template>

<script setup>
defineProps({
  view: { type: Object, required: true },
  html: { type: String, default: '' },
})
</script>

<style scoped>
.module-content { display: grid; gap: var(--space-2); min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.content-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1); }
h2 { margin: 0; font-size: var(--text-card); }
.type-pill { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); }
.markdown-body { min-width: 0; line-height: var(--leading-body); overflow-wrap: anywhere; }
.markdown-body :deep(h1) { margin: var(--space-3) 0 var(--space-2); font-size: var(--text-section); }
.markdown-body :deep(h2), .markdown-body :deep(h3), .markdown-body :deep(h4) { margin: var(--space-3) 0 var(--space-2); font-size: var(--text-card); line-height: var(--leading-tight); }
.markdown-body :deep(p), .markdown-body :deep(ul), .markdown-body :deep(ol) { margin-bottom: var(--space-2); }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: var(--space-3); }
.markdown-body :deep(pre) { max-width: 100%; overflow-x: auto; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink); font-size: var(--text-caption); }
.markdown-body :deep(code) { background: var(--surface-muted); color: var(--ink); overflow-wrap: anywhere; }
.markdown-body :deep(blockquote) { margin: var(--space-2) 0; padding-left: var(--space-2); border-left: var(--focus-width) solid var(--line); color: var(--ink-secondary); }
.markdown-body :deep(img), .markdown-body :deep(video) { max-width: 100%; height: auto; }
.markdown-body :deep(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: var(--space-1); border-bottom: var(--stroke) solid var(--line); text-align: left; }
.markdown-body :deep(a) { color: var(--action); text-decoration: underline; }
.markdown-body :deep(a:hover) { color: var(--action-hover); }
.markdown-body :deep(a:focus-visible) { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.empty-content { display: grid; justify-items: center; gap: var(--space-1); padding: var(--space-5) var(--space-2); color: var(--ink-muted); text-align: center; }
.empty-content :deep(.arco-icon) { font-size: var(--text-page); }
.empty-content p { margin: 0; font-size: var(--text-caption); }
</style>
