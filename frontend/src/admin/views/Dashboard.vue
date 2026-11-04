<template>
  <main class="governance-page" data-density="admin">
    <template v-if="allowed">
      <header class="governance-hero"><h1>{{ names.admin }}</h1><p class="governance-muted">按来源处理内容、资料与权限待办，教学决定交给教师。</p></header>
      <div class="governance-heading"><div><h2>治理待办</h2><p class="governance-muted">各项范围独立，不相加为平台待办总数。</p></div><button class="governance-primary" :disabled="loading" @click="load">{{ loading ? '正在读取…' : '刷新待办' }}</button></div>
      <div class="governance-grid">
        <router-link v-for="tile in tiles" :key="tile.key" :to="tile.href" class="governance-card">
          <h3>{{ tile.title }}</h3><strong>{{ tile.loading ? '…' : tile.count === null ? '—' : `${tile.count} 项` }}</strong>
          <p v-if="tile.error" class="governance-error" role="alert">{{ tile.error }}</p>
          <p v-else-if="tile.loading" role="status">正在读取待办…</p>
          <p v-else>{{ tile.count === null ? tile.notice : tile.count === 0 ? '当前已读取范围内没有待办。' : tile.description }}</p>
          <small>来源：{{ tile.scope }}</small><span>打开核对 <icon-arrow-right /></span>
        </router-link>
      </div>
      <section class="governance-panel"><h2>平台治理记录</h2><p class="governance-muted">平台统计、题目分类与难度分布、提交记录在全局洞察集中查看。</p><div class="governance-actions"><router-link to="/admin/student-learning">打开{{ names.globalInsights }}</router-link><router-link to="/admin/learning-scores">评测监督</router-link><router-link to="/admin/legal/kb">{{ names.foundation }}</router-link></div></section>
    </template>
    <p v-else role="alert">此工作区仅供管理员使用，请使用与你身份相符的入口。</p>
  </main>
</template>
<script setup>
import { computed } from 'vue'
import { names } from '@/shared/navigation/names.js'
import { useGovernanceSources } from '../governance/useSources.js'
import { governanceCockpitApi } from '../cockpit/api.js'
import { governanceTiles } from '../cockpit/model.js'
const { allowed, sources, loading, load } = useGovernanceSources(governanceCockpitApi)
const tiles = computed(() => governanceTiles(sources))
</script>
<style scoped src="../governance/governance.css"></style>
