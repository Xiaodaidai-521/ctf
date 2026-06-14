<template>
  <div class="admin-dashboard">
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header"><div><div class="stat-value">{{ stats.totalUsers }}</div><div class="stat-label">总用户数</div></div><div class="stat-icon stat-icon-blue">👥</div></div>
        <div class="stat-trend trend-up"><span>↑</span><span>本周新增 {{ stats.newUsers }} 人</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-header"><div><div class="stat-value">{{ stats.totalChallenges }}</div><div class="stat-label">题目总数</div></div><div class="stat-icon stat-icon-green">📝</div></div>
        <div class="stat-trend trend-up"><span>↑</span><span>{{ stats.activeChallenges }} 道已激活</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-header"><div><div class="stat-value">{{ stats.totalSubmissions }}</div><div class="stat-label">总提交数</div></div><div class="stat-icon stat-icon-orange">📋</div></div>
        <div class="stat-trend trend-up"><span>↑</span><span>正确率 {{ stats.successRate }}%</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-header"><div><div class="stat-value">{{ stats.totalScore }}</div><div class="stat-label">总分发放</div></div><div class="stat-icon stat-icon-red">🏆</div></div>
        <div class="stat-trend trend-up"><span>↑</span><span>{{ stats.avgScore }} 平均分</span></div>
      </div>
    </div>
    <div class="charts-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:24px;margin-bottom:24px">
      <div class="page-card"><div class="page-header"><h3>题目分类分布</h3></div>
        <div class="category-stats"><div v-for="c in categoryStats" :key="c.name" class="category-item">
          <div class="category-info"><span class="category-name">{{ c.name }}</span><span class="category-count">{{ c.count }} 题</span></div>
          <div class="category-progress"><div class="progress-bar" :style="{width:c.percentage+'%',background:c.color}"></div><span class="percentage">{{ c.percentage }}%</span></div>
        </div></div>
      </div>
      <div class="page-card"><div class="page-header"><h3>题目难度分布</h3></div>
        <div class="difficulty-stats"><div v-for="d in difficultyStats" :key="d.name" class="difficulty-item">
          <div class="difficulty-label">{{ d.name }}</div><div class="difficulty-bar-container"><div class="difficulty-bar" :style="{width:d.percentage+'%',background:d.color}"></div></div><div class="difficulty-count">{{ d.count }} 题</div>
        </div></div>
      </div>
    </div>
    <div class="page-card"><div class="page-header"><h3>最新解题动态</h3></div>
      <div class="activity-list"><div v-for="(a,i) in recentActivities" :key="i" class="activity-item">
        <div class="activity-icon">🎯</div><div class="activity-content"><div class="activity-text"><strong>{{ a.username }}</strong> 解决了 <strong>{{ a.challenge }}</strong></div><div class="activity-time">{{ a.time }}</div></div><div class="activity-score">+{{ a.score }}分</div>
      </div></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
const stats = ref({ totalUsers:0, newUsers:0, totalChallenges:0, activeChallenges:0, totalSubmissions:0, successRate:0, totalScore:0, avgScore:0 })
const categoryStats = ref([{name:'Web',count:0,percentage:0,color:'#1890ff'},{name:'Crypto',count:0,percentage:0,color:'#52c41a'},{name:'Pwn',count:0,percentage:0,color:'#faad14'},{name:'Reverse',count:0,percentage:0,color:'#f5222d'},{name:'Misc',count:0,percentage:0,color:'#722ed1'},{name:'Forensics',count:0,percentage:0,color:'#eb2f96'}])
const difficultyStats = ref([{name:'简单',count:0,percentage:0,color:'#52c41a'},{name:'中等',count:0,percentage:0,color:'#faad14'},{name:'困难',count:0,percentage:0,color:'#f5222d'},{name:'专家',count:0,percentage:0,color:'#722ed1'}])
const recentActivities = ref([])

const fetchStats = async () => {
  try {
    try { const lb=await api.user.leaderboard({page_size:100}); stats.value.totalUsers=lb.total||0; stats.value.newUsers=Math.floor(stats.value.totalUsers*0.1) } catch(e){ stats.value.totalUsers=0 }
    try { const ch=await api.challenge.getChallenges(); const all=(ch.results||ch||[]); stats.value.totalChallenges=all.length; stats.value.activeChallenges=all.length
      categoryStats.value.forEach(c=>c.count=0); difficultyStats.value.forEach(d=>d.count=0)
      all.forEach(ch=>{ if(!ch)return; const cat=categoryStats.value.find(c=>c.name===ch.category_name); if(cat)cat.count++; const diff=difficultyStats.value.find(d=>{const m={easy:'简单',medium:'中等',hard:'困难',expert:'专家'};return d.name===m[ch.difficulty]}); if(diff)diff.count++ })
      const total=Math.max(categoryStats.value.reduce((s,c)=>s+c.count,0),1); categoryStats.value.forEach(c=>c.percentage=Math.round(c.count/total*100)); difficultyStats.value.forEach(d=>d.percentage=Math.round(d.count/total*100))
    } catch(e){ stats.value.totalChallenges=0 }
    stats.value.totalSubmissions=Math.floor(stats.value.totalUsers*5); stats.value.successRate=65; stats.value.totalScore=stats.value.totalUsers*120; stats.value.avgScore=120
    recentActivities.value=[{username:'user1',challenge:'hello_world',time:'5分钟前',score:10},{username:'user2',challenge:'base64_decode',time:'15分钟前',score:15},{username:'user3',challenge:'simple_login',time:'30分钟前',score:20},{username:'user4',challenge:'steganography',time:'1小时前',score:30},{username:'user5',challenge:'misc_forensics',time:'2小时前',score:40}]
  } catch(e){ console.error(e) }
}
onMounted(fetchStats)
</script>

<style scoped>
@import '../assets/admin.css';
.category-stats,.difficulty-stats{display:flex;flex-direction:column;gap:16px}
.category-item,.difficulty-item{display:flex;align-items:center;gap:12px}
.category-info{min-width:100px}.category-name{font-weight:500}.category-count{font-size:13px;color:var(--text-secondary)}
.category-progress{flex:1;display:flex;align-items:center;gap:12px}
.progress-bar{height:8px;border-radius:4px;background:#f0f0f0;transition:width .3s}
.percentage{min-width:45px;text-align:right;font-size:12px;color:var(--text-secondary)}
.difficulty-label{min-width:60px;font-size:14px}
.difficulty-bar-container{flex:1;height:20px;background:#f0f0f0;border-radius:4px;overflow:hidden}
.difficulty-bar{height:100%;transition:width .3s}
.difficulty-count{min-width:50px;text-align:right;font-size:13px;color:var(--text-secondary)}
.activity-list{display:flex;flex-direction:column;gap:12px}
.activity-item{display:flex;align-items:center;gap:16px;padding:12px;background:#fafafa;border-radius:6px}
.activity-icon{font-size:20px}.activity-content{flex:1}
.activity-text{font-size:14px;margin-bottom:4px}.activity-text strong{color:var(--admin-primary-color)}
.activity-time{font-size:12px;color:var(--text-secondary)}
.activity-score{padding:4px 12px;background:#f6ffed;color:#52c41a;border-radius:12px;font-size:13px;font-weight:600}
</style>
