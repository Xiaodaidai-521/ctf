<template>
  <div class="not-found-page">
    <div class="not-found-container">
      <div class="not-found-content">
        <div class="not-found-code">404</div>
        <h1 class="not-found-title">页面不存在</h1>
        <p class="not-found-description">抱歉，您访问的页面不存在或已被删除</p>
        <router-link to="/" class="btn btn-primary">
          返回首页
        </router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.not-found-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-gray);
}

.not-found-container {
  text-align: center;
  padding: 40px;
}

.not-found-code {
  font-size: 120px;
  font-weight: bold;
  color: var(--primary-color);
  line-height: 1;
  margin-bottom: 20px;
}

.not-found-title {
  font-size: 32px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.not-found-description {
  font-size: 16px;
  color: var(--text-secondary);
  margin-bottom: 32px;
}
</style>
