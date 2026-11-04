<template>
  <section class="access-denied">
    <icon-lock class="access-icon" aria-hidden="true" />
    <h1>当前账号暂无访问权限</h1>
    <p>此页面仅向获授权的教师或管理员开放。学习资料可在智库查找，也可以在导学对话中提问。</p>
    <router-link :to="user.isAuthenticated ? landingFor(user.userInfo?.role) : '/login'" class="btn btn-primary">返回我的工作台</router-link>
  </section>
</template>
<script setup>
import { useUserStore } from '@/store/user'
import { landingFor } from '../navigation/names.js'
const user = useUserStore()
</script>
<style scoped>
.access-denied { max-width: var(--reading-width); margin: var(--space-8) auto; padding: var(--page-gutter); }
.access-icon { color: var(--ink-secondary); font-size: var(--text-page); margin-bottom: var(--space-3); }
p { color: var(--ink-secondary); margin-bottom: var(--space-4); }
</style>
