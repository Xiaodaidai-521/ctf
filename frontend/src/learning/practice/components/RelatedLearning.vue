<template>
  <section class="related-learning" aria-label="相关学习">
    <h2>相关学习</h2>
    <div v-if="groups.articles.length" class="related-group">
      <h3>相关阅读</h3>
      <ul>
        <li v-for="item in groups.articles" :key="item.key">
          <a :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>
          <p v-if="item.reason" class="related-reason">{{ item.reason }}</p>
          <p v-if="item.summary" class="related-summary">{{ item.summary }}</p>
        </li>
      </ul>
    </div>
    <div v-if="groups.resources.length" class="related-group">
      <h3>相关资源</h3>
      <ul>
        <li v-for="item in groups.resources" :key="item.key">
          <a :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>
          <p v-if="item.reason" class="related-reason">{{ item.reason }}</p>
          <p v-if="item.category || item.relation" class="related-meta">{{ [item.category, item.relation].filter(Boolean).join(' · ') }}</p>
        </li>
      </ul>
    </div>
    <div v-if="groups.sameCategory.length" class="related-group">
      <h3>同分类练习</h3>
      <ul>
        <li v-for="item in groups.sameCategory" :key="item.key">
          <router-link :to="`/challenge/${item.id}`">{{ item.title }}</router-link>
          <p class="related-meta">{{ item.difficulty }} · {{ item.reason }}<span v-if="item.solved"> · 已解出</span></p>
        </li>
      </ul>
    </div>
    <p v-if="!groups.articles.length && !groups.resources.length && !groups.sameCategory.length" class="related-empty">
      这道题暂未关联阅读或同分类练习，可先完成本题，再到智库按主题查找。
    </p>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { relatedGroups } from '@/learning/practice/workspaceView.js'
const props = defineProps({
  challenge: { type: Object, default: null },
  sameCategory: { type: Array, default: () => [] },
})
const groups = computed(() => relatedGroups(props.challenge, props.sameCategory))
</script>
<style scoped>
.related-learning { padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); min-width: 0; }
.related-learning h2 { margin: 0 0 var(--space-2); font-size: var(--text-card); }
.related-group + .related-group { margin-top: var(--space-3); }
.related-group h3 { margin: 0 0 var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); font-weight: var(--weight-medium); }
.related-group ul { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.related-group a { color: var(--action); text-decoration: underline; text-underline-offset: var(--stroke); overflow-wrap: anywhere; }
.related-reason { margin: var(--space-1) 0 0; color: var(--ink); font-size: var(--text-caption); }
.related-summary, .related-meta, .related-empty { margin: var(--space-1) 0 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.related-empty { margin: 0; }
.related-group a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
