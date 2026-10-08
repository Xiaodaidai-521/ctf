<template>
  <section class="dashboard">
    <div class="hero">
      <h1>教学工作台</h1>
      <p>管理学习内容、实训题目和教学资源。</p>
    </div>
    <div class="cards">
      <RouterLink to="/teacher/learning-paths" class="card"><strong>学习路径</strong><span>创建与维护课程路径、模块和实验。</span></RouterLink>
      <RouterLink to="/teacher/learning-scores" class="card"><strong>动态评分</strong><span>录入学生测评并生成教学方案。</span></RouterLink>
      <RouterLink to="/teacher/learning-effect" class="card"><strong>学习效果分析</strong><span>查看八项学习指标、趋势和学习建议。</span></RouterLink>
      <RouterLink to="/teacher/challenges" class="card"><strong>题目管理</strong><span>维护 CTF 题目及其靶场配置。</span></RouterLink>
      <RouterLink to="/teacher/resources" class="card"><strong>教学资源</strong><span>上传资源并查看资源中心内容。</span></RouterLink>
    </div>
  </section>
</template>

<style scoped>
.dashboard { padding: 42px 32px; }.hero { margin-bottom: 30px; }.hero h1 { margin: 0 0 8px; font-size: 38px; letter-spacing: -.05em; }.hero p { margin: 0; color: #6b6256; }
.cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.card { display: grid; gap: 12px; min-height: 142px; padding: 22px; border: 1px solid #d9cfbe; border-radius: 7px; background: rgba(250,247,240,.9); color: #1e1c18; text-decoration: none; }.card:hover { background: #f2ebdf; border-color: #a59682; }.card strong { font-size: 19px; }.card span { color: #6b6256; line-height: 1.6; }
@media (max-width: 860px) { .cards { grid-template-columns: 1fr; } }
</style>
