# 宠物形象删除边界

按用户 2026-11-13 的删除指令，仅删除宠物形象、选择/偏好、浮窗及专用会话桥接和测试，共 20 个 Git 跟踪文件。删除前已逐项核对入口引用及 assets 目录，五套目录内均只有 manifest，没有原图。

## 删除清单

- `frontend/public/pets/index.json`
- `frontend/public/pets/dundun/pet.json`
- `frontend/public/pets/gugu/pet.json`
- `frontend/public/pets/xiaoju/pet.json`
- `frontend/public/pets/xiaoqing/pet.json`
- `frontend/public/pets/yeye/pet.json`
- `frontend/src/components/PetSelector.vue`
- `frontend/src/components/PlatformPet.vue`
- `frontend/src/learning/agent/TutorPet.vue`
- `frontend/src/learning/agent/petBridge.js`
- `frontend/src/learning/agent/petIntegration.test.js`
- `frontend/src/learning/agent/petWindow.js`
- `frontend/src/learning/agent/petWindow.test.js`
- `frontend/src/store/pet.js`
- `frontend/src/store/pet.test.js`
- `frontend/src/utils/pet.js`
- `frontend/src/utils/pet.test.js`
- `frontend/src/utils/petAssets.test.js`
- `frontend/src/utils/petRegistry.js`
- `frontend/src/utils/petRegistry.test.js`

## 配套修改和保留边界

- App.vue 移除宠物挂载和偏好 reset；保留账号切换时的共享教学会话清理、学生 TutorDrawer 和正式考试禁用抽屉规则。
- GlobalHeader.vue 移除唤出宠物菜单；保留智能体搜索、完整对话和导学入口。
- 共享入口/导航/设计测试移除对宠物专用文件的断言，继续检查教学入口、考试边界和会话控制器。
- 移除宠物尺寸/层级专用 token；跳到正文链接改用通用 overlay token。
- 保留 learning/agent 的 runtime、sessionController、host、public、draft、components 和完整智能体页面：这些属于教学会话，不属于宠物形象资产。
- 保留历史审计报告与复现证据，报告中的宠物缺图描述是修复前历史记录。
- `backend/resources/test_phase6_formal_competition.py` 名称中的 competition 包含 pet 字符串，但属于正式比赛资源验收，不能按模糊文件名删除。

此删除不需要恢复原图。历史已保存在 Git 中，可按文件级别恢复；本次不提交 Git。
