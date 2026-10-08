<template>
  <div class="teacher-layout">
    <aside class="teacher-sidebar">
      <RouterLink to="/teacher" class="brand">教学工作台</RouterLink>
      <nav>
        <RouterLink to="/teacher" class="nav-link">概览</RouterLink>
        <RouterLink to="/teacher/learning-paths" class="nav-link">学习路径</RouterLink>
        <RouterLink to="/teacher/learning-scores" class="nav-link">动态评分</RouterLink>
        <RouterLink to="/teacher/learning-effect" class="nav-link">学习效果分析</RouterLink>
        <RouterLink to="/teacher/challenges" class="nav-link">题目管理</RouterLink>
        <RouterLink to="/teacher/resources" class="nav-link">资源中心</RouterLink>
      </nav>
    </aside>
    <main class="teacher-main">
      <header><span>教师中心</span><RouterLink to="/" class="back-link">返回平台</RouterLink></header>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.teacher-layout { min-height: 100vh; display: flex; background-color: #faf7f0; background-image: linear-gradient(#e9e1d4 1px, transparent 1px), linear-gradient(90deg, #e9e1d4 1px, transparent 1px); background-size: 38px 38px; color: #1e1c18; }
.teacher-sidebar { width: 228px; padding: 28px 16px; background: rgba(250,247,240,.96); border-right: 1px solid #d9cfbe; }.brand { display: block; margin: 0 10px 26px; color: #1e1c18; font-size: 20px; font-weight: 800; letter-spacing: -.03em; text-decoration: none; }nav { display: grid; gap: 5px; }.nav-link { padding: 11px 12px; border: 1px solid transparent; border-radius: 5px; color: #625a4d; text-decoration: none; font-weight: 600; }.nav-link.router-link-exact-active, .nav-link:hover { background: #e9dfcf; border-color: #d8cbb8; color: #1e1c18; }.teacher-main { flex: 1; min-width: 0; }header { display: flex; justify-content: space-between; align-items: center; padding: 18px 32px; background: rgba(250,247,240,.92); border-bottom: 1px solid #d9cfbe; font-weight: 700; }.back-link { color: #b42318; text-decoration: none; font-weight: 700; }
@media (max-width: 720px) { .teacher-layout { display: block; }.teacher-sidebar { width: auto; padding: 16px; border-right: 0; border-bottom: 1px solid #d9cfbe; }nav { grid-template-columns: repeat(2, 1fr); }.brand { margin-bottom: 12px; } }
</style>
