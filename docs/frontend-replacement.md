# 前端替换与路由边界（2026-11-13）

历史合并 `b9c4997` 将部分已改造页面覆盖为旧实现。此次以 `feat/frontend-overhaul` 中的新前端为依据恢复首页、靶场、学习航线列表、成长资料、社区、资源和管理页面，逐项保留主线后续的权限、请求竞态、隐私保护及导出限制。未整目录回滚历史提交。

## 正式入口

| 地址 | 页面或行为 |
| --- | --- |
| `/` | 访客看到“从理解原理，到独立完成一次安全练习”新版首页；已登录用户按角色分流 |
| `/guide` | 学生智航工作台；教师、管理员返回各自工作台 |
| `/challenges` | 新版靶场，访客可浏览公开题目 |
| `/challenge/:id` | 题目详情，数字题目 ID，登录后返回原题目 |
| `/resources` | 智库；保持公开资料和受保护文件的原权限边界 |
| `/learning-paths` | 学习航线 |
| `/dashboard` | 学生成长图谱；教师保留教学数据视图；管理员转治理工作台 |
| `/teacher` | 教学驾驶舱，仅教师 |
| `/admin/dashboard` | 治理驾驶舱，仅管理员 |
| `/exam-center/history`、`/exam-center/result/:id` | 新版测评记录和结果 |

首页“开启智航”直接声明 `/guide`；未登录时由统一守卫携带完整目标转到 `/login?redirect=...`。登录成功恢复路径、查询参数和 hash，外部地址、认证循环、未知页面及无权访问的目标回到当前角色的默认入口。首页精选卡片通过 `ChallengeDetail` 命名路由进入题目。

`/analytics`、`/my-results`、`/exam-history`、`/exam-result/:id`、旧教学入口、能力历史及数据案例入口保留兼容解析，并保持各自角色边界。

## 服务器与开发环境

Nginx 和 Vite 仅将 `/challenge/<数字用户ID>-<容器标识>/...` 代理到实验容器后端，包括容器内部 CSS、JS、WebSocket；数字题目 `/challenge/7` 使用前端 SPA。Nginx 的 `index.html` 使用 `no-cache`，发布后重新验证入口文档。

## 旧文件清理

删除了以下 14 个无运行引用的旧 Vue 文件，原 URL 的兼容记录独立保留：

- `components/Navbar.vue`、`AnnouncementButton.vue`、`AnnouncementBanner.vue`
- `components/AIAssistant.vue`、`AITutorChat.vue`、`KnowledgeMap.vue`
- `components/PersonalizedRecommendationCard.vue`、`MultiAgent/MultiAgentChat.vue`
- `views/ExamHistory.vue`、`ExamResult.vue`、`Leaderboard.vue`
- `teacher/DashboardEntry.vue`
- `admin/views/legal/ComplianceDashboard.vue`、`KnowledgeBase.vue`

仍被教师和管理员使用的 `MultiAgent/legacy` 协作实现保留。隐私、记忆、导出及数据保护页保留现行业务实现。

## 验证

- 97 种内部跳转目标可解析，176 个运行 Vue 组件无缺失导入，删除文件无残余引用。
- `npm run build` 通过，已重新生成 `frontend/dist`；构建仍提示已有大体积代码块。
- `node --test --test-reporter=tap`：939 项中 937 项通过。剩余 2 项为原仓库缺失 `evidence/frontend-overhaul/phase6/assets.json` 和宠物 spritesheet 图片导致的既有失败，未跳过或放宽这些测试。
- Vite 实际 HTTP 验证覆盖 3 个 SPA 深链接和 3 个容器页面/资源，返回成功并保留请求参数。
- 浏览器 11 项回归全部通过，覆盖登录后原路返回、题目卡片鼠标/键盘跳转、深链接刷新、三角色入口与越权落点、旧入口兼容。桌面 1666px 与手机 390px 均无横向溢出；无页面异常或控制台错误。业务 API 使用隔离的测试数据，未登录或写入真实账号。结果及截图见 `artifacts/frontend-replacement-browser.json` 和同目录截图。

当前机器 Docker daemon 未启动且没有 Nginx 二进制，因此 Nginx 仅完成配置边界测试，未声称完成生产容器部署。
