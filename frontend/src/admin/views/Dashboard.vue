<template>
  <main class="governance-page" data-density="admin">
    <template v-if="allowed">
      <header class="governance-hero"><h1>{{ names.admin }}</h1><p class="governance-muted">核对待审核内容与资料处理记录，再进入对应工作区处理。</p></header>
      <div class="governance-heading"><h2>治理待办</h2><button class="governance-primary" :disabled="loading" @click="load">{{ loading ? '正在读取…' : '刷新待办' }}</button></div>
      <section class="governance-grid" aria-label="治理待办">
        <article v-for="tile in tiles" :key="tile.key" class="governance-card">
          <h3>{{ tile.title }}</h3>
          <p v-if="tile.loading" role="status">正在读取…</p>
          <p v-else-if="tile.error" class="governance-error" role="alert">{{ tile.error }} {{ tile.notice }}</p>
          <p v-else-if="tile.count === null">{{ tile.notice }}</p>
          <template v-else><strong>{{ tile.count }}</strong><p v-if="tile.count === 0">当前已读取范围内没有待办。</p></template>
          <p>{{ tile.description }}</p><small>{{ tile.scope }}</small>
          <router-link :to="tile.href">打开{{ tile.title }} <icon-arrow-right aria-hidden="true" /></router-link>
        </article>
      </section>
      <section class="governance-panel"><h2>平台核对入口</h2><div class="governance-actions"><router-link to="/admin/student-learning">{{ names.globalInsights }}</router-link><router-link to="/admin/legal/kb">{{ names.foundation }}</router-link><router-link to="/admin/submissions">提交记录</router-link></div><p class="governance-muted">平台使用统计和最新提交动态在全局洞察中读取；本页不推算未提供的新增人数、积分或正确率。</p></section>
    </template>
    <p v-else role="alert">本页仅供管理员使用，请使用与你身份相符的入口。</p>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { names } from '@/shared/navigation/names.js'
import { governanceCockpitApi } from '@/admin/cockpit/api.js'
import { governanceTiles } from '@/admin/cockpit/model.js'
import { useGovernanceSources } from '@/admin/governance/useSources.js'
const { allowed, sources, loading, load } = useGovernanceSources(governanceCockpitApi)
const tiles = computed(() => governanceTiles(sources))
</script>

<style scoped src="../governance/governance.css"></style>
