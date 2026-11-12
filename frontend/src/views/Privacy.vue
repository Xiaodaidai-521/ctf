<template>
  <main class="privacy-page">
    <h1>隐私与数据保护</h1>
    <p>以下介绍系统支持的保护能力。具体内容是否已加密，以对应页面的核验状态为准。</p>
    <p v-if="error" role="status">{{ error }}</p>
    <p v-else-if="capabilities">字段存储保护：{{ capabilityLabel(capabilities.field_storage) }}；私有文件：{{ capabilityLabel(capabilities.private_files) }}；受控导出：{{ capabilityLabel(capabilities.controlled_export) }}。</p>
    <div class="table-scroll"><table><thead><tr><th>保护对象</th><th>支持的保护方式</th></tr></thead><tbody>
      <tr v-for="item in objects" :key="item[0]"><th scope="row">{{ item[0] }}</th><td>{{ item[1] }}</td></tr>
    </tbody></table></div>
    <p>页面上的邮箱脱敏展示与服务器加密保存分别表示两种处理。历史记录尚未迁移、核验失败或状态缺失时，页面不会显示“已加密”。</p>
    <p>下载到自己设备后的文件，需要自行妥善保存。服务器存储加密不会自动保护本机副本。</p>
    <details><summary>查看技术说明</summary><p>字段和私有文件使用 AES-256-GCM 加密与认证，并通过 HKDF-SHA256 派生数据密钥。数据库备份的 age 加密与恢复验证由管理端单独记录。</p><p>加密保存保护的是服务器存储。AI 处理仍会按功能需要读取获准使用的内容；具体模型服务的处理规则需另行说明。</p></details>
    <router-link to="/profile">返回个人资料</router-link>
  </main>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import api from '@/api'
const capabilities = ref(null), error = ref('')
const objects = [
  ['邮箱', '邮箱加密保存；页面展示可以另行脱敏。'],
  ['对话与 AI 记忆', '对话正文、消息扩展元数据、长期记忆内容及其扩展元数据加密保存。'],
  ['入学访谈', '访谈回答及画像报告中的原始访谈快照加密保存；分析摘要采用脱敏处理。'],
  ['考试答案', '用户提交的考试答案加密保存。'],
  ['法律分析', '分析原文、报告正文及人工备注加密保存；标题和摘要等内容按策略脱敏。'],
  ['私有文件', '已接入私有存储的资源文件、封面与反馈附件加密保存。'],
  ['受控导出', '经授权的导出内容脱敏后生成，服务器保存的文件采用加密保护。'],
]
const capabilityLabel = state => state === 'enabled-unverified' ? '已配置，具体记录仍需核验' : state === 'disabled' ? '当前未启用' : '状态待确认'
onMounted(async () => { try { capabilities.value = await api.privacy.capabilities() } catch { error.value = '当前功能配置暂时无法确认，请以具体记录的保护状态为准。' } })
</script>
<style scoped>
.privacy-page { max-width: 900px; margin: 30px auto; padding: 24px; line-height: 1.8; color: var(--ink, #222); }
.table-scroll { overflow-x: auto; } table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid var(--line, #ddd); text-align: left; vertical-align: top; } details { margin: 20px 0; } summary { cursor: pointer; }
</style>
