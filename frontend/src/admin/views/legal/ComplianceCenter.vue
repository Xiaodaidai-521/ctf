<template>
  <div class="compliance-center">
    <header class="center-header">
      <div>
        <h2>法律审计数据安全工作台</h2>
      </div>
      <button class="action-btn btn-default" :disabled="loading || running" @click="loadData">刷新</button>
    </header>

    <nav class="center-tabs" aria-label="合规中心视图">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <span>{{ tab.title }}</span>
        <small>{{ tab.hint }}</small>
      </button>
    </nav>

    <section class="metric-strip">
      <div v-for="metric in metrics" :key="metric.label" class="metric-item">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
      </div>
    </section>

    <p v-if="errorMessage" class="error-line">{{ errorMessage }}</p>

    <section v-if="activeTab === 'overview'" class="workspace-grid">
      <div class="work-panel wide">
        <div class="panel-head">
          <h3>近期分析任务</h3>
          <button class="text-action" type="button" @click="activeTab = 'review'">发起审查</button>
        </div>
        <div class="panel-scroll table-scroll">
          <table class="admin-table compact-table">
          <thead>
            <tr>
              <th>任务</th>
              <th>来源</th>
              <th>状态</th>
              <th>结论摘要</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in tasks" :key="task.id">
              <td>{{ task.title }}</td>
              <td>{{ formatSource(task.source_type) }}</td>
              <td><span class="status-pill" :class="badgeClass(task.status)">{{ formatStatus(task.status) }}</span></td>
              <td class="summary-cell">{{ taskSummary(task) }}</td>
              <td><button class="inline-action" type="button" @click="runTask(task)">重新分析</button></td>
            </tr>
          </tbody>
          </table>
        </div>
        <div v-if="!tasks.length && !loading" class="empty-state">
          <strong>还没有审查任务</strong>
          <p>可以先挑一个平台场景做快速检查，生成风险结论后再沉淀为报告。</p>
          <ul>
            <li>学生学习行为采集是否说明用途和保存期限</li>
            <li>题目靶场日志是否限定访问范围</li>
            <li>AI 答疑内容是否引用法规依据</li>
          </ul>
        </div>
      </div>

      <aside class="work-panel">
        <div class="panel-head">
          <h3>风险分布</h3>
        </div>
        <div class="risk-list panel-scroll small-scroll">
          <div v-for="item in riskBreakdown" :key="item.key" class="risk-row">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <p class="panel-note">优先处理严重和高危项，中低危问题可纳入月度复核。</p>
      </aside>
    </section>

    <section v-if="activeTab === 'review'" class="workspace-grid">
      <div class="work-panel dense-panel">
        <div class="panel-head">
          <div>
            <h3>演练合规审查</h3>
            <p class="panel-subtitle">用于题目发布、靶场开放、协议变更或数据处理上线前，核对法规依据、实验边界和证据留痕。</p>
          </div>
        </div>
        <div class="fact-mode" aria-label="事实输入方式">
          <button
            v-for="mode in factModes"
            :key="mode.key"
            type="button"
            :class="{ active: factInputMode === mode.key }"
            :aria-pressed="factInputMode === mode.key"
            @click="setFactMode(mode.key)"
          >
            {{ mode.label }}
          </button>
        </div>
        <form class="stack-form" @submit.prevent="createAndRun">
          <label>
            <span>审查对象</span>
            <input v-model="reviewForm.title" class="form-input" type="text" required />
          </label>
          <label v-if="factInputMode === 'manual'">
            <span>对象类型</span>
            <select v-model="reviewForm.source_type" class="form-input">
              <option value="challenge">题目或靶场演练</option>
              <option value="data_processing">数据处理活动</option>
              <option value="protocol">协议或告知文本</option>
              <option value="report">报告或处置记录</option>
              <option value="manual">其他场景</option>
            </select>
          </label>
          <label v-if="factInputMode === 'manual'">
            <span>已知事实</span>
            <textarea
              v-model="reviewForm.input_text"
              class="form-textarea"
              rows="9"
              placeholder="写清楚：演练目的、涉及的数据、参与用户、容器/端口/镜像、日志保存周期、授权或同意记录、已有审计证据。"
              required
            ></textarea>
          </label>
          <template v-else>
            <label>
              <span>靶场容器实例</span>
              <select v-model="selectedContainerId" class="form-input" required @change="clearFactPreview">
                <option :value="null" disabled>选择已有容器审计记录</option>
                <option v-for="item in containerOptions" :key="item.container_id" :value="item.container_id">
                  {{ item.challenge }} · {{ item.user }} · {{ item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '启动时间暂不可用' }}
                </option>
              </select>
            </label>
            <button
              class="action-btn btn-default"
              type="button"
              :disabled="previewLoading || !selectedContainerId"
              @click="previewExerciseFacts"
            >
              {{ previewLoading ? '正在归集...' : '预览系统事实' }}
            </button>
            <section v-if="factPreview" class="fact-preview">
              <div class="fact-preview__metrics">
                <div><span>审计事件</span><strong>{{ factPreview.facts.event_count }}</strong></div>
                <div><span>运行时长</span><strong>{{ formatRuntime(factPreview.facts.runtime_seconds) }}</strong></div>
                <div><span>Flag 提交</span><strong>{{ factPreview.facts.flag_submission_count }}</strong></div>
                <div><span>证据引用</span><strong>{{ factPreview.evidence_refs.length }}</strong></div>
              </div>
              <p><strong>容器：</strong>{{ ({ running: '运行中', stopped: '已停止', exited: '已退出', pending: '启动中', failed: '启动失败' })[factPreview.facts.container_status] || '状态待确认' }} · {{ factPreview.facts.image || '-' }}</p>
              <p><strong>资源限制：</strong>CPU {{ factPreview.facts.has_cpu_limit ? '已记录' : '未确认' }}，内存 {{ factPreview.facts.has_memory_limit ? '已记录' : '未确认' }}</p>
              <ul v-if="factPreview.warnings.length">
                <li v-for="warning in factPreview.warnings" :key="warning">{{ factWarningLabel(warning) }}</li>
              </ul>
            </section>
            <label v-if="factInputMode === 'hybrid'">
              <span>人工补充事实</span>
              <textarea
                v-model="manualFactNotes"
                class="form-textarea"
                rows="6"
                placeholder="补充授权范围、教学目的、是否涉及真实数据等无法从日志推断的事实。"
              ></textarea>
            </label>
          </template>
          <button class="action-btn btn-primary" type="submit" :disabled="reviewSubmitDisabled">
            {{ running ? '审查中...' : factInputMode === 'manual' ? '生成审查结论' : '确认快照并生成结论' }}
          </button>
        </form>
        <div v-if="factInputMode === 'manual'" class="helper-list" aria-label="常用审查场景">
          <span>常用场景</span>
          <button type="button" @click="useReviewExample('SQL 靶场容器开放审查', '演练目的：学生在授权靶场学习 SQL 注入防护。\n涉及数据：账号、提交记录、容器访问日志，不使用真实个人敏感信息。\n实验环境：Docker 镜像 ctf/sql-basic，映射临时端口，限制 CPU/内存，过期自动清理。\n留痕证据：容器启动、停止、Flag 提交、报告导出写入审计账本。\n待核对：日志保存周期、访问范围、异常容器事件处理和法规引用是否完整。')">靶场容器开放</button>
          <button type="button" @click="useReviewExample('AI 答疑边界审查', '演练目的：多智能体回答 CTF 题目时提供学习引导。\n涉及数据：用户问题、题目知识包、法规检索结果和对话日志。\n输出边界：不直接给 flag，不引导攻击真实系统，不暴露非授权目标。\n留痕证据：引用法规、题目知识包、模型输出和人工复核记录。\n待核对：是否清楚提示教学边界、是否需要未成年人保护或个人信息处理说明。')">AI 答疑边界</button>
          <button type="button" @click="useReviewExample('用户协议条款复核', '复核对象：平台用户协议和隐私告知文本。\n涉及数据：账号信息、学习记录、提交记录、日志和安全审计记录。\n处理目的：教学管理、成绩统计、安全审计和违规处置。\n留痕证据：协议版本、用户同意记录、内容哈希和审计账本。\n待核对：告知是否清晰、保存周期是否明确、删除和申诉路径是否完整。')">协议条款复核</button>
        </div>
      </div>

      <div class="work-panel dense-panel">
        <div class="panel-head compact-panel-head">
          <div>
            <h3>审查结果</h3>
            <p class="panel-subtitle">默认只看结论、依据和待办，证据明细可展开复核。</p>
          </div>
        </div>
        <div v-if="latestRun" class="review-result">
          <section class="review-summary">
            <div class="review-summary__top">
              <span class="status-pill" :class="badgeClass(latestAssessment?.severity)">
                {{ formatStatus(latestAssessment?.severity) || '已完成' }}
              </span>
              <small>{{ latestEvidence.length }} 条材料</small>
            </div>
            <strong>{{ compactReviewTitle }}</strong>
            <p>{{ reviewOutcomeLine }}</p>
          </section>

          <section class="review-snapshot" aria-label="审查摘要">
            <div>
              <span>关键依据</span>
              <strong>{{ reviewPrimaryReason }}</strong>
            </div>
            <div>
              <span>引用材料</span>
              <strong>{{ latestEvidence.length ? `${latestEvidence.length} 条已召回` : '暂无材料' }}</strong>
            </div>
          </section>

          <section class="review-section">
            <h4>下一步</h4>
            <ul>
              <li v-for="item in reviewVisibleActionItems" :key="item">{{ item }}</li>
            </ul>
          </section>

          <details class="review-details">
            <summary>展开证据、命中词和运行信息</summary>
            <div class="review-detail-block">
              <h4>命中原因</h4>
              <div class="reason-list">
                <span v-for="item in latestMatchedKeywords" :key="item">{{ item }}</span>
                <span v-if="!latestMatchedKeywords.length">未命中明确高风险关键词</span>
              </div>
            </div>

            <div class="review-detail-block">
              <h4>已引用材料</h4>
              <div v-if="latestEvidence.length" class="review-evidence-list panel-scroll small-scroll">
                <div v-for="item in latestEvidence" :key="item.title" class="review-evidence-item">
                  <strong>{{ item.title }}</strong>
                  <span>{{ formatSource(item.source_type || item.evidence_type || item.object_type) }} · {{ item.score || item.relevance_score || '-' }}</span>
                </div>
              </div>
              <p v-else class="quiet-copy">暂无可引用材料，需要先补充法规、题目知识包或容器审计记录。</p>
            </div>

            <div class="review-detail-block">
              <h4>完整处理动作</h4>
              <ul>
                <li v-for="item in reviewActionItems" :key="item">{{ item }}</li>
              </ul>
            </div>

            <dl class="technical-run">
              <div>
                <dt>执行角色</dt>
                <dd>合规审查智能体</dd>
              </div>
              <div>
                <dt>服务来源</dt>
                <dd>{{ providerLabel }}</dd>
              </div>
              <div>
                <dt>耗时</dt>
                <dd>{{ latestRun.duration_ms }} 毫秒</dd>
              </div>
            </dl>
          </details>
        </div>
        <div v-else class="empty-state compact-empty">
          <strong>先生成一次审查结论</strong>
          <p>结果会说明风险来自哪些事实、引用了哪些法规或平台材料，以及发布前需要补齐哪些证据。</p>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'knowledge'" class="workspace-grid">
      <div class="work-panel">
        <div class="panel-head">
          <h3>多智能体法律审计检索</h3>
          <span v-if="retrievalResult" class="audit-health neutral">{{ retrievalProviderLabel }}</span>
        </div>
        <form class="stack-form" @submit.prevent="retrieveKnowledge">
          <textarea
            v-model="kbQuery"
            class="form-textarea"
            rows="5"
            placeholder="输入要审计的靶场、题目、数据处理或用户权益问题"
            required
          ></textarea>
          <button class="action-btn btn-primary" type="submit" :disabled="retrieving || !kbQuery">
            {{ retrieving ? '审计检索中...' : '生成审计研判' }}
          </button>
        </form>
        <div class="helper-list" aria-label="常用检索词">
          <span>审计场景</span>
          <button type="button" @click="kbQuery = 'SQL 注入靶场启动容器并记录日志，如何满足数据安全和审计留痕要求'">SQL 靶场容器审计</button>
          <button type="button" @click="kbQuery = '未成年人参与网络安全演练时，平台应如何处理个人信息和学习记录'">未成年人演练保护</button>
          <button type="button" @click="kbQuery = '多智能体回答 CTF 题目时，如何引用法规并避免越界提示'">AI 答疑合规边界</button>
        </div>

        <div v-if="retrievalSections" class="audit-result">
          <p v-if="retrievalResult?.provider_error" class="llm-fallback-note">
            本次未能完成智能审查，以下为依据现有资料整理的参考意见，请人工复核。
          </p>
          <section class="result-block conclusion-block">
            <h4>审计结论</h4>
            <p>{{ retrievalSections.audit_conclusion }}</p>
          </section>

          <section class="result-block legal-basis-block">
            <h4>相关法规依据</h4>
            <div v-if="retrievalSections.legal_basis?.length" class="legal-basis-list">
              <article v-for="item in retrievalSections.legal_basis" :key="item.index" class="legal-basis-item">
                <div class="legal-basis-item__head">
                  <strong>[{{ item.index }}] {{ item.title }}</strong>
                  <span>{{ formatSource(item.source_type) }} · {{ item.score }}</span>
                </div>
                <p>{{ item.applicability || '该依据与本次审计问题相关，需结合条文原文确认适用范围。' }}</p>
                <small>{{ item.excerpt }}</small>
              </article>
            </div>
            <p v-else class="quiet-copy">本次没有召回可直接引用的法规条款，建议补充法规证据后再形成正式结论。</p>
          </section>

          <section v-if="retrievalSections.multi_agent_views?.length" class="result-block">
            <h4>多智能体协同意见</h4>
            <div class="agent-opinion-list">
              <div v-for="item in retrievalSections.multi_agent_views" :key="item.role" class="agent-opinion">
                <strong>{{ item.role }}</strong>
                <p>{{ item.content }}</p>
              </div>
            </div>
          </section>

          <section class="result-block split-block">
            <div>
              <h4>靶场实验合规建议</h4>
              <ul>
                <li v-for="item in retrievalSections.exercise_advice" :key="item">{{ item }}</li>
              </ul>
            </div>
            <div>
              <h4>平台数据安全建议</h4>
              <ul>
                <li v-for="item in retrievalSections.data_security_advice" :key="item">{{ item }}</li>
              </ul>
            </div>
          </section>

          <section class="result-block">
            <h4>不足证据或需人工确认事项</h4>
            <ul>
              <li v-for="item in retrievalSections.evidence_gaps" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>

        <div v-else-if="retrievalAnswer" class="answer-box">{{ retrievalAnswer }}</div>
      </div>

      <div class="work-panel">
        <div class="panel-head">
          <h3>证据底座</h3>
        </div>
        <div class="evidence-summary-grid">
          <div>
            <span>法规文档</span>
            <strong>{{ documents.length }}</strong>
          </div>
          <div>
            <span>容器审计</span>
            <strong>{{ containerAudits.length }}</strong>
          </div>
          <div>
            <span>异常事件</span>
            <strong>{{ abnormalContainerCount }}</strong>
          </div>
          <div>
            <span>链路状态</span>
            <strong>{{ ledgerHealthText }}</strong>
          </div>
        </div>

        <div v-if="retrievalCitations.length" class="citation-list compact-citations">
          <h4>本次引用证据</h4>
          <div v-for="item in retrievalCitations" :key="item.id || item.index" class="citation-item">
            <div class="citation-item__header">
              <strong>[{{ item.index }}] {{ item.title }}</strong>
              <span>{{ formatSource(item.source_type) }} · {{ item.score }}</span>
            </div>
            <p>{{ item.excerpt }}</p>
          </div>
        </div>

        <div v-else class="doc-list panel-scroll medium-scroll">
          <div v-for="doc in documents" :key="doc.id" class="doc-row">
            <strong>{{ doc.title }}</strong>
            <span>{{ legalLabel('documentType', doc.document_type) }} · {{ legalLabel('documentStatus', doc.status) }}</span>
          </div>
          <div v-if="!documents.length && !loading" class="empty-inline">暂无法规文档，导入后可用于审查引用和报告证据。</div>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'audit'" class="workspace-grid">
      <div class="work-panel">
        <div class="panel-head">
          <h3>报告</h3>
        </div>
        <div v-if="reports.length" class="panel-scroll compact-table-scroll">
          <table class="admin-table compact-table">
          <thead>
            <tr>
              <th>报告</th>
              <th>状态</th>
              <th>生成时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="report in reports" :key="report.id">
              <td>{{ report.title }}</td>
              <td><span class="status-pill" :class="badgeClass(report.status)">{{ formatStatus(report.status) }}</span></td>
              <td>{{ formatDate(report.generated_at) }}</td>
              <td><button class="inline-action" type="button" @click="exportReport(report)">导出</button></td>
            </tr>
          </tbody>
          </table>
        </div>
        <div v-else-if="!loading" class="empty-inline compact-inline-empty">暂无报告，完成审查后可在这里导出留档材料。</div>
      </div>

      <div class="work-panel">
        <div class="panel-head">
          <h3>违规记录</h3>
        </div>
        <div v-if="violations.length" class="risk-list panel-scroll compact-list-scroll">
          <div v-for="record in violations" :key="record.id" class="risk-row">
            <span>{{ record.title }}</span>
            <strong>{{ formatStatus(record.severity) }}</strong>
          </div>
        </div>
        <div v-else-if="!loading" class="empty-inline compact-inline-empty">暂无违规记录，后续会汇总审查发现和处置状态。</div>
      </div>

      <div class="work-panel wide dense-panel">
        <div class="panel-head">
          <h3>容器行为审计</h3>
          <span class="audit-health" :class="ledgerHealthClass">{{ ledgerHealthText }}</span>
        </div>
        <div v-if="containerAudits.length" class="panel-scroll compact-table-scroll">
          <table class="admin-table compact-table">
          <thead>
            <tr>
              <th>动作</th>
              <th>题目</th>
              <th>容器</th>
              <th>端口</th>
              <th>状态</th>
              <th>证据 Hash</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="event in containerAudits" :key="event.id">
              <td>{{ formatContainerAction(event.action) }}</td>
              <td>{{ event.challenge }}</td>
              <td class="summary-cell">{{ event.container_name }}</td>
              <td>{{ event.port || '-' }}</td>
              <td>
                <span class="status-pill" :class="containerBadgeClass(event)">
                  {{ event.error_message ? '异常' : formatContainerResult(event.result) }}
                </span>
                <small v-if="event.error_message" class="error-reason">{{ truncate(event.error_message, 48) }}</small>
              </td>
              <td class="hash-cell">{{ shortHash(event.ledger_hash) }}</td>
              <td>{{ formatDate(event.created_at) }}</td>
            </tr>
          </tbody>
          </table>
        </div>
        <div v-else-if="!loading" class="empty-state compact-empty audit-empty">
            <strong>暂无容器审计记录</strong>
            <p>学生启动靶场容器、停止容器或触发失败时，这里会沉淀镜像、端口、网络、资源限制与哈希链证据。</p>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'governance'" class="workspace-grid">
      <div class="work-panel">
        <div class="panel-head">
          <h3>协议与同意</h3>
        </div>
        <div class="risk-list panel-scroll small-scroll">
          <div class="risk-row">
            <span>协议版本</span>
            <strong>{{ protocolVersions.length }}</strong>
          </div>
          <div class="risk-row">
            <span>已发布</span>
            <strong>{{ protocolVersions.filter((item) => item.is_published).length }}</strong>
          </div>
          <div class="risk-row">
            <span>签署记录</span>
            <strong>{{ consents.length }}</strong>
          </div>
        </div>
        <p class="panel-note">这里保留协议发布、同意记录和复核状态，便于追溯版本变更。</p>
      </div>

      <div class="work-panel">
        <div class="panel-head">
          <h3>合规演练</h3>
        </div>
        <p class="quiet-copy">演练仍从题目管理进入，合规中心只汇总关联结果：审查结论、引用依据、整改记录和报告导出。</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import { legalLabel } from './displayLabels.js'

const tabs = [
  { key: 'overview', title: '审计总览', hint: '任务与风险' },
  { key: 'review', title: '智能体审查', hint: '协同研判' },
  { key: 'knowledge', title: '法律审计引擎', hint: 'RAG 与证据' },
  { key: 'audit', title: '证据链审计', hint: '报告与容器' },
  { key: 'governance', title: '治理配置', hint: '协议与边界' },
]

const activeTab = ref('overview')
const loading = ref(false)
const running = ref(false)
const retrieving = ref(false)
const errorMessage = ref('')
const factModes = [
  { key: 'manual', label: '手工事实' },
  { key: 'automated', label: 'Docker 自动事实' },
  { key: 'hybrid', label: '自动 + 人工补充' },
]
const factInputMode = ref('manual')
const selectedContainerId = ref(null)
const factPreview = ref(null)
const previewLoading = ref(false)
const manualFactNotes = ref('')

const tasks = ref([])
const findings = ref([])
const reports = ref([])
const agentRuns = ref([])
const documents = ref([])
const violations = ref([])
const protocolVersions = ref([])
const consents = ref([])
const containerAudits = ref([])
const retrievalAnswer = ref('')
const retrievalResult = ref(null)
const kbQuery = ref('')

const reviewForm = ref({
  title: '平台合规风险快速审查',
  source_type: 'manual',
  input_text: '',
})

const containerOptions = computed(() => {
  const seen = new Set()
  return containerAudits.value.filter((item) => {
    if (!item.container_id || seen.has(item.container_id)) return false
    seen.add(item.container_id)
    return true
  })
})

const reviewSubmitDisabled = computed(() => {
  if (running.value || !reviewForm.value.title) return true
  if (factInputMode.value === 'manual') return !reviewForm.value.input_text
  return !selectedContainerId.value || !factPreview.value
})

const metrics = computed(() => [
  { label: '数智审查任务', value: tasks.value.length },
  { label: '风险发现', value: currentFindings.value.length },
  { label: '法规证据', value: documents.value.length },
  { label: '容器演练证据', value: containerAudits.value.length },
  { label: '异常容器事件', value: abnormalContainerCount.value },
  { label: '链路状态', value: ledgerHealthText.value },
])

const currentFindings = computed(() => {
  const fromTasks = tasks.value
    .map((task) => task.risk_findings?.[0])
    .filter(Boolean)
  return fromTasks.length ? fromTasks : findings.value
})

const riskBreakdown = computed(() => {
  const count = { critical: 0, high: 0, medium: 0, low: 0 }
  currentFindings.value.forEach((item) => {
    count[item.severity] = (count[item.severity] || 0) + 1
  })
  return [
    { key: 'critical', label: '严重', value: count.critical },
    { key: 'high', label: '高危', value: count.high },
    { key: 'medium', label: '中危', value: count.medium },
    { key: 'low', label: '低危', value: count.low },
  ]
})

const latestRun = computed(() => agentRuns.value[0] || null)
const abnormalContainerCount = computed(() => (
  containerAudits.value.filter((event) => (
    event.level === 'ERROR'
    || event.error_message
    || String(event.action || '').includes('failed')
    || event.result === 'failed'
  )).length
))
const ledgerHealthText = computed(() => {
  if (!containerAudits.value.length) return '待沉淀'
  return containerAudits.value.every((event) => event.ledger_hash) ? '已上链' : '待校验'
})
const ledgerHealthClass = computed(() => {
  if (!containerAudits.value.length) return 'neutral'
  return ledgerHealthText.value === '已上链' ? 'ok' : 'warn'
})
const latestAssessment = computed(() => latestRun.value?.output_payload?.assessment || null)
const latestEvidence = computed(() => {
  const evidence = latestRun.value?.output_payload?.evidence
  return Array.isArray(evidence) ? evidence : []
})
const latestMatchedKeywords = computed(() => {
  const keywords = latestAssessment.value?.matched_keywords
  return Array.isArray(keywords) ? keywords : []
})
const latestFinding = computed(() => tasks.value.find((task) => task.id === latestRun.value?.task)?.risk_findings?.[0] || null)
const reviewFindingTitle = computed(() => {
  if (latestFinding.value?.title) return latestFinding.value.title
  const severity = formatStatus(latestAssessment.value?.severity)
  return severity ? `规则初评为${severity}风险` : '审查已完成'
})
const reviewFindingDescription = computed(() => {
  if (latestFinding.value?.description) return latestFinding.value.description
  const content = latestRun.value?.output_payload?.content || ''
  return firstContentLine(content, '审查完成，请根据下方动作补齐证据并复核。')
})
const compactReviewTitle = computed(() => truncate(reviewFindingTitle.value, 34))
const compactReviewDescription = computed(() => truncate(reviewFindingDescription.value, 110))
const reviewOutcomeLine = computed(() => {
  if (latestMatchedKeywords.value.length) {
    return `主要因为 ${latestMatchedKeywords.value.slice(0, 2).join('、')}，需复核事实和证据是否完整。`
  }
  if (latestEvidence.value.length) {
    return `已召回 ${latestEvidence.value.length} 条材料，当前没有命中明确高风险关键词。`
  }
  return compactReviewDescription.value
})
const reviewPrimaryReason = computed(() => {
  if (latestMatchedKeywords.value.length) return latestMatchedKeywords.value.slice(0, 2).join('、')
  if (latestEvidence.value.length) return '法规或平台材料已召回'
  return '待补充法规或平台证据'
})
const reviewActionItems = computed(() => {
  const recommendation = latestFinding.value?.recommendation || latestRun.value?.output_payload?.content || ''
  const items = String(recommendation)
    .split(/\n|。/)
    .map((item) => item.replace(/^[-\d.\s]+/, '').trim())
    .filter(Boolean)
    .filter((item) => !item.startsWith('初评结论') && !item.startsWith('命中要素') && !item.startsWith('判断说明'))
  return items.slice(0, 5).length
    ? items.slice(0, 5)
    : ['补充处理目的、数据范围、保存周期和安全措施。', '核对用户同意、审计账本和报告留痕是否完整。']
})
const reviewVisibleActionItems = computed(() => reviewActionItems.value.slice(0, 2))
const retrievalSections = computed(() => retrievalResult.value?.sections || null)
const retrievalCitations = computed(() => {
  const citations = retrievalResult.value?.citations
  return Array.isArray(citations) ? citations : []
})
const retrievalProviderLabel = computed(() => {
  if (!retrievalResult.value) return ''
  const provider = retrievalResult.value.provider || 'local'
  const model = retrievalResult.value.model || 'rag-template-v1'
  return `${provider} / ${model}`
})

async function loadData() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [
      taskRes,
      findingRes,
      reportRes,
      runRes,
      documentRes,
      violationRes,
      versionRes,
      consentRes,
      containerAuditRes,
    ] = await Promise.all([
      api.legal.analysisTasks({ page_size: 100 }),
      api.legal.findings({ page_size: 50 }),
      api.legal.reports({ page_size: 100 }),
      api.legal.agentRuns({ page_size: 10 }),
      api.legalKb.documents({ page_size: 100 }),
      api.legal.violations({ page_size: 100 }).catch(() => []),
      api.legal.protocolVersions({ page_size: 20 }).catch(() => []),
      api.legal.consents({ page_size: 20 }).catch(() => []),
      api.legal.containerAudits({ page_size: 100 }).catch(() => []),
    ])
    tasks.value = normalizeList(taskRes)
    findings.value = normalizeList(findingRes)
    reports.value = normalizeList(reportRes)
    agentRuns.value = normalizeList(runRes)
    documents.value = normalizeList(documentRes)
    violations.value = normalizeList(violationRes)
    protocolVersions.value = normalizeList(versionRes)
    consents.value = normalizeList(consentRes)
    containerAudits.value = normalizeList(containerAuditRes)
  } catch (error) {
    errorMessage.value = error?.response?.data?.detail || error?.message || '合规中心数据加载失败'
  } finally {
    loading.value = false
  }
}

async function createAndRun() {
  if (reviewSubmitDisabled.value) return
  running.value = true
  errorMessage.value = ''
  try {
    if (factInputMode.value === 'manual') {
      const task = await api.legal.createAnalysisTask({
        title: reviewForm.value.title,
        source_type: reviewForm.value.source_type,
        input_text: reviewForm.value.input_text,
        metadata: { entry: 'admin_compliance_center' },
      })
      await api.legal.runAnalysis(task.id)
    } else {
      await api.legal.confirmExerciseFacts({
        container_id: selectedContainerId.value,
        preview_hash: factPreview.value.preview_hash,
        manual_notes: factInputMode.value === 'hybrid' ? manualFactNotes.value : '',
        title: reviewForm.value.title,
        run_analysis: true,
      })
    }
    reviewForm.value.input_text = ''
    clearFactPreview()
    selectedContainerId.value = null
    manualFactNotes.value = ''
    activeTab.value = 'overview'
    await loadData()
  } catch (error) {
    if (error?.response?.data?.code === 'FACT_PREVIEW_CHANGED') {
      factPreview.value = error.response.data.preview
      errorMessage.value = '审计记录在预览后发生变化，已刷新事实，请重新确认。'
    } else {
      errorMessage.value = error?.response?.data?.detail || error?.message || '智能审查失败'
    }
  } finally {
    running.value = false
  }
}

function setFactMode(mode) {
  factInputMode.value = mode
  clearFactPreview()
}

function clearFactPreview() {
  factPreview.value = null
}

async function previewExerciseFacts() {
  if (!selectedContainerId.value) return
  previewLoading.value = true
  errorMessage.value = ''
  try {
    factPreview.value = await api.legal.previewExerciseFacts({
      container_id: selectedContainerId.value,
    })
  } catch (error) {
    errorMessage.value = error?.response?.data?.detail || error?.message || '事实归集失败'
  } finally {
    previewLoading.value = false
  }
}

function formatRuntime(seconds) {
  return seconds == null ? '无法计算' : `${Math.round(seconds / 60)} 分钟`
}

function factWarningLabel(code) {
  return {
    missing_start_event: '缺少成功启动事件',
    missing_terminal_event: '缺少停止或清理事件',
    missing_resource_limit: '资源限制记录不完整',
    container_operation_failure: '存在启动或停止失败',
    legacy_event_schema: '包含旧版审计事件',
  }[code] || code
}

async function runTask(task) {
  running.value = true
  try {
    await api.legal.runAnalysis(task.id)
    await loadData()
  } finally {
    running.value = false
  }
}

async function retrieveKnowledge() {
  if (!kbQuery.value) return
  retrieving.value = true
  try {
    const response = await api.legalKb.retrieve({ query: kbQuery.value, top_k: 5 })
    retrievalResult.value = response && !Array.isArray(response) ? response : null
    retrievalAnswer.value = response?.answer || normalizeList(response).map((item) => item.text).join('\n\n')
  } finally {
    retrieving.value = false
  }
}

function useReviewExample(title, inputText) {
  reviewForm.value.title = title
  reviewForm.value.input_text = inputText
}

async function exportReport(report) {
  await api.legal.exportReport(report.id)
  await loadData()
}

function normalizeList(response) {
  return response?.results || response || []
}

function truncate(value, size) {
  if (!value) return '-'
  const text = String(value)
  return text.length > size ? `${text.slice(0, size)}...` : text
}

function taskSummary(task) {
  const finding = task.risk_findings?.[0]
  const source = finding?.description || task.result_summary
  return truncate(String(source || '-').replace(/\s+/g, ' '), 96)
}

function firstContentLine(content, fallback) {
  const line = String(content || '')
    .split('\n')
    .map((item) => item.trim())
    .find(Boolean)
  return line || fallback
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

function formatSource(value) {
  const map = {
    manual: '手动',
    challenge: '题目',
    data_processing: '数据处理',
    protocol: '协议',
    report: '报告',
    article: '文章',
    resource: '资源',
    legal_clause: '法规条款',
    legal_document: '法规文档',
    legal_case: '法律案例',
    legal_template: '合规模板',
    challenge_knowledge_pack: '题目知识包',
  }
  return map[value] || '来源待确认'
}

const providerLabel = computed(() => {
  const provider = latestRun.value?.provider
  if (!provider) return '未记录'
  return provider === 'local' ? '本地规则' : '云端智能体服务'
})

function formatStatus(value) {
  const map = {
    pending: '待处理',
    running: '运行中',
    completed: '完成',
    failed: '失败',
    draft: '草稿',
    exported: '已导出',
    open: '待处理',
    closed: '已关闭',
    low: '低风险',
    medium: '需补充',
    high: '高风险',
    critical: '严重风险',
  }
  return map[value] || '状态待确认'
}

function badgeClass(value) {
  const normalized = String(value || '').toLowerCase()
  if (['completed', 'exported', 'closed', 'low'].includes(normalized)) return 'ok'
  if (['pending', 'running', 'draft', 'medium'].includes(normalized)) return 'warn'
  if (['failed', 'high', 'critical', 'open'].includes(normalized)) return 'danger'
  return 'neutral'
}

function formatContainerAction(value) {
  const map = {
    start_requested: '启动请求',
    start_succeeded: '启动成功',
    start_failed: '启动失败',
    stop_requested: '停止请求',
    stop_succeeded: '停止成功',
    stop_failed: '停止失败',
    expired_cleanup: '过期清理',
    status_checked: '状态检查',
  }
  return map[value] || '操作待确认'
}

function formatContainerResult(value) {
  const map = {
    requested: '已记录',
    success: '正常',
    failed: '失败',
    running: '运行中',
    stopped: '已停止',
    destroyed: '已销毁',
    not_found: '无会话',
  }
  return map[value] || '结果待确认'
}

function containerBadgeClass(event) {
  if (event.error_message || event.level === 'ERROR' || String(event.action || '').includes('failed')) return 'danger'
  if (event.result === 'requested' || event.action === 'status_checked') return 'neutral'
  return 'ok'
}

function shortHash(value) {
  return value ? `${String(value).slice(0, 12)}...` : '-'
}

onMounted(loadData)
</script>

<style scoped>
.compliance-center {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.center-header {
  align-items:flex-start;
  display:flex;
  gap:var(--space-2);
  justify-content:space-between;
}

.center-header h2 {
  color:var(--action);
  font-size:var(--text-section);
  margin:0 0 var(--space-1);
}

.center-header p {
  color:var(--ink-secondary);
  line-height:1.6;
  margin:0;
  max-width:64ch;
}

.center-tabs {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  display:grid;
  grid-template-columns:repeat(5, minmax(0, 1fr));
  overflow:hidden;
}

.center-tabs button {
  background:transparent;
  border:0;
  border-right:var(--stroke) solid var(--line);
  color:var(--ink-secondary);
  cursor:pointer;
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
  min-height:var(--space-8);
  padding:var(--space-1) var(--space-2);
  text-align:left;
}

.center-tabs button:last-child {
  border-right:0;
}

.center-tabs button.active {
  background:var(--surface);
  color:var(--action);
}

.center-tabs span {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.center-tabs small {
  color:var(--ink-secondary);
}

.metric-strip {
  display:grid;
  gap:var(--space-1);
  grid-template-columns:repeat(6, minmax(0, 1fr));
}

.metric-item,
.work-panel {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
}

.metric-item {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
  padding:var(--space-2) var(--space-2);
}

.metric-item span {
  color:var(--ink-secondary);
}

.metric-item strong {
  color:var(--action);
  font-size:var(--text-section);
}

.workspace-grid {
  display:grid;
  gap:var(--space-2);
  grid-template-columns:minmax(0, 1.7fr) minmax(var(--panel-width), 0.8fr);
}

.work-panel {
  min-height:var(--content-short-height);
  padding:var(--space-3);
}

.dense-panel {
  min-height:0;
  padding:var(--space-2) var(--space-2);
}

.work-panel.wide {
  min-width:0;
}

.panel-head {
  align-items:center;
  display:flex;
  justify-content:space-between;
  margin-bottom:var(--space-2);
}

.compact-panel-head {
  margin-bottom:var(--space-2);
}

.panel-head h3 {
  color:var(--action);
  font-size:var(--text-card);
  margin:0;
}

.panel-subtitle {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  line-height:1.5;
  margin:calc(var(--space-1) / 2) 0 0;
  max-width:60ch;
}

.compact-table th,
.compact-table td {
  font-size:var(--text-caption);
  vertical-align:top;
}

.panel-scroll {
  overflow-x:auto;
  overflow-y:scroll;
  overscroll-behavior:contain;
  padding-right:calc(var(--space-1) / 2);
  scrollbar-gutter:stable;
}

.table-scroll {
  height:var(--chart-height);
}

.compact-table-scroll {
  max-height:var(--content-short-height);
  min-height:0;
}

.table-scroll .admin-table {
  min-width:var(--search-width);
}

.compact-table-scroll .admin-table {
  min-width:var(--search-width);
}

.table-scroll thead th {
  background:var(--surface);
  position:sticky;
  top:0;
  z-index:1;
}

.compact-table-scroll thead th {
  background:var(--surface);
  position:sticky;
  top:0;
  z-index:1;
}

.small-scroll {
  height:var(--tile-tall-height);
}

.medium-scroll {
  height:var(--chart-height);
}

.compact-list-scroll {
  max-height:var(--content-short-height);
  min-height:0;
}

.summary-cell {
  color:var(--ink);
  line-height:1.5;
  max-width:var(--message-width);
}

.hash-cell {
  color:var(--ink-secondary);
  font-family:ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size:var(--text-caption);
}

.error-reason {
  color:var(--negative);
  display:block;
  line-height:1.4;
  margin-top:calc(var(--space-1) / 2);
  max-width:var(--sidebar-width);
}

.audit-health {
  border-radius:var(--radius-pill);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  padding:calc(var(--space-1) / 2) var(--space-1);
}

.audit-health.ok {
  background:var(--positive-soft);
  color:var(--positive);
}

.audit-health.warn {
  background:var(--warning-soft);
  color:var(--warning);
}

.audit-health.neutral {
  background:var(--surface);
  color:var(--ink-secondary);
}

.status-pill {
  border-radius:var(--radius-pill);
  display:inline-flex;
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  padding:var(--focus-width) var(--space-1);
}

.status-pill.ok {
  background:var(--positive-soft);
  color:var(--positive);
}

.status-pill.warn {
  background:var(--warning-soft);
  color:var(--warning);
}

.status-pill.danger {
  background:var(--negative-soft);
  color:var(--negative);
}

.status-pill.neutral {
  background:var(--surface);
  color:var(--ink-secondary);
}

.inline-action,
.text-action {
  background:transparent;
  border:0;
  color:var(--action);
  cursor:pointer;
  font-weight: var(--weight-strong);
}

.stack-form {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.stack-form label {
  color:var(--ink);
  display:flex;
  flex-direction:column;
  font-weight: var(--weight-strong);
  gap:calc(var(--space-1) / 2);
}

.fact-mode {
  display:grid;
  grid-template-columns:repeat(3, minmax(0, 1fr));
  margin-bottom:var(--space-2);
  border:var(--stroke) solid var(--line);
  background:var(--surface);
}

.fact-mode button {
  min-height:var(--space-5);
  border:0;
  border-right:var(--stroke) solid var(--line);
  background:transparent;
  color:var(--ink-secondary);
  cursor:pointer;
}

.fact-mode button:last-child {
  border-right:0;
}

.fact-mode button.active {
  background:var(--surface);
  color:var(--action);
  font-weight: var(--weight-strong);
  box-shadow: none;
}

.fact-preview {
  border-left:var(--focus-width) solid var(--line);
  background:var(--surface);
  padding:var(--space-2);
  color:var(--ink);
}

.fact-preview p {
  margin:var(--space-1) 0 0;
}

.fact-preview ul {
  margin:var(--space-1) 0 0;
  padding-left:var(--space-2);
  color:var(--ink-secondary);
}

.fact-preview__metrics {
  display:grid;
  grid-template-columns:repeat(4, minmax(0, 1fr));
  gap:var(--space-1);
}

.fact-preview__metrics div {
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
}

.fact-preview__metrics span {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.fact-preview__metrics strong {
  color:var(--action);
}

.trace-box dl {
  display:grid;
  gap:var(--space-1);
  grid-template-columns:repeat(3, minmax(0, 1fr));
  margin:0 0 var(--space-2);
}

.trace-box dt {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.trace-box dd {
  color:var(--action);
  font-weight: var(--weight-strong);
  margin:calc(var(--space-1) / 2) 0 0;
}

.trace-box p,
.answer-box,
.quiet-copy {
  color:var(--ink);
  line-height:1.65;
  white-space:pre-wrap;
}

.review-result {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.review-summary {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-2);
}

.review-summary__top {
  align-items:center;
  display:flex;
  justify-content:space-between;
}

.review-summary__top small {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.review-summary strong {
  color:var(--action);
  display:block;
  font-size:var(--text-body);
  line-height:1.45;
  margin:var(--space-1) 0 calc(var(--space-1) / 2);
}

.review-summary p {
  color:var(--ink);
  font-size:var(--text-caption);
  line-height:1.55;
  margin:0;
}

.review-snapshot {
  display:grid;
  gap:var(--space-1);
  grid-template-columns:repeat(2, minmax(0, 1fr));
}

.review-snapshot div {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-1) var(--space-1);
}

.review-snapshot span {
  color:var(--ink-secondary);
  display:block;
  font-size:var(--text-caption);
  margin-bottom:calc(var(--space-1) / 2);
}

.review-snapshot strong {
  color:var(--action);
  display:block;
  font-size:var(--text-caption);
  line-height:1.45;
}

.review-section {
  border-top:var(--stroke) solid var(--line);
  padding-top:var(--space-1);
}

.review-section h4 {
  color:var(--action);
  font-size:var(--text-caption);
  margin:0 0 calc(var(--space-1) / 2);
}

.review-section ul {
  color:var(--ink);
  display:grid;
  gap:calc(var(--space-1) / 2);
  line-height:1.5;
  margin:0;
  padding-left:var(--space-2);
}

.reason-list {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
}

.reason-list span {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-pill);
  color:var(--ink);
  font-size:var(--text-caption);
  padding:calc(var(--space-1) / 2) var(--space-1);
}

.review-details {
  border-top:var(--stroke) solid var(--line);
  color:var(--ink-secondary);
  padding-top:var(--space-1);
}

.review-details summary {
  cursor:pointer;
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.review-detail-block {
  margin-top:var(--space-1);
}

.review-detail-block h4 {
  color:var(--action);
  font-size:var(--text-caption);
  margin:0 0 var(--space-1);
}

.review-detail-block ul {
  color:var(--ink);
  display:grid;
  gap:calc(var(--space-1) / 2);
  line-height:1.55;
  margin:0;
  padding-left:var(--space-2);
}

.review-evidence-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.review-evidence-item {
  align-items:flex-start;
  border-bottom:var(--stroke) solid var(--line);
  display:flex;
  gap:var(--space-1);
  justify-content:space-between;
  padding-bottom:var(--space-1);
}

.review-evidence-item strong {
  color:var(--action);
  font-size:var(--text-caption);
}

.review-evidence-item span {
  color:var(--ink-secondary);
  flex:0 0 auto;
  font-size:var(--text-caption);
}

.technical-run {
  display:grid;
  gap:var(--space-1);
  grid-template-columns:repeat(3, minmax(0, 1fr));
  margin:var(--space-2) 0 0;
  padding-top:var(--space-1);
  border-top:var(--stroke) solid var(--line);
}

.technical-run dt {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.technical-run dd {
  color:var(--action);
  font-weight: var(--weight-strong);
  margin:calc(var(--space-1) / 2) 0 0;
}

.answer-box {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  margin-top:var(--space-2);
  max-height:var(--content-short-height);
  overflow:auto;
  padding:var(--space-1);
}

.audit-result {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
  margin-top:var(--space-2);
}

.llm-fallback-note {
  background:var(--warning-soft);
  border:var(--stroke) solid var(--warning);
  border-radius:var(--radius-control);
  color:var(--warning);
  font-size:var(--text-caption);
  line-height:1.5;
  margin:0;
  padding:var(--space-1) var(--space-1);
}

.result-block {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-2);
}

.result-block h4 {
  color:var(--action);
  font-size:var(--text-caption);
  margin:0 0 var(--space-1);
}

.result-block p {
  color:var(--ink);
  line-height:1.65;
  margin:0;
}

.result-block ul {
  color:var(--ink);
  display:grid;
  gap:calc(var(--space-1) / 2);
  line-height:1.6;
  margin:0;
  padding-left:var(--space-2);
}

.conclusion-block {
  background:var(--surface);
  border-color:var(--line);
}

.legal-basis-block {
  background:var(--surface);
  border-color:var(--line);
}

.legal-basis-list {
  display:grid;
  gap:var(--space-1);
}

.legal-basis-item {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-1);
}

.legal-basis-item__head {
  align-items:flex-start;
  display:flex;
  gap:var(--space-1);
  justify-content:space-between;
  margin-bottom:calc(var(--space-1) / 2);
}

.legal-basis-item__head strong {
  color:var(--action);
  font-size:var(--text-caption);
}

.legal-basis-item__head span {
  color:var(--ink-secondary);
  flex:0 0 auto;
  font-size:var(--text-caption);
}

.legal-basis-item p {
  color:var(--ink);
  font-size:var(--text-caption);
  line-height:1.6;
  margin:0 0 calc(var(--space-1) / 2);
}

.legal-basis-item small {
  color:var(--ink-secondary);
  display:-webkit-box;
  line-height:1.55;
  overflow:hidden;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:3;
}

.agent-opinion-list {
  display:grid;
  gap:var(--space-1);
  grid-template-columns:repeat(3, minmax(0, 1fr));
}

.agent-opinion {
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-1);
}

.agent-opinion strong {
  color:var(--action);
  display:block;
  font-size:var(--text-caption);
  margin-bottom:calc(var(--space-1) / 2);
}

.agent-opinion p {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.split-block {
  display:grid;
  gap:var(--space-2);
  grid-template-columns:repeat(2, minmax(0, 1fr));
}

.evidence-summary-grid {
  display:grid;
  gap:var(--space-1);
  grid-template-columns:repeat(2, minmax(0, 1fr));
  margin-bottom:var(--space-2);
}

.evidence-summary-grid div {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  padding:var(--space-1);
}

.evidence-summary-grid span {
  color:var(--ink-secondary);
  display:block;
  font-size:var(--text-caption);
  margin-bottom:calc(var(--space-1) / 2);
}

.evidence-summary-grid strong {
  color:var(--action);
  font-size:var(--text-card);
}

.citation-list {
  border-top:var(--stroke) solid var(--line);
  padding-top:var(--space-1);
}

.citation-list h4 {
  color:var(--action);
  font-size:var(--text-caption);
  margin:0 0 var(--space-1);
}

.citation-item {
  border-bottom:var(--stroke) solid var(--line);
  padding:var(--space-1) 0;
}

.citation-item__header {
  align-items:flex-start;
  display:flex;
  gap:var(--space-1);
  justify-content:space-between;
}

.citation-item__header strong {
  color:var(--action);
  font-size:var(--text-caption);
}

.citation-item__header span {
  color:var(--ink-secondary);
  flex:0 0 auto;
  font-size:var(--text-caption);
}

.citation-item p {
  color:var(--ink-secondary);
  display:-webkit-box;
  font-size:var(--text-caption);
  line-height:1.55;
  margin:calc(var(--space-1) / 2) 0 0;
  overflow:hidden;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:4;
}

.compact-citations {
  max-height:var(--content-height);
  overflow:auto;
}

.helper-list {
  align-items:center;
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  margin-top:var(--space-2);
}

.helper-list span {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  margin-right:calc(var(--stroke) * 2);
}

.helper-list button {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-pill);
  color:var(--ink);
  cursor:pointer;
  font-size:var(--text-caption);
  padding:calc(var(--space-1) / 2) var(--space-1);
}

.helper-list button:hover {
  background:var(--surface);
  border-color:var(--line);
  color:var(--action);
}

.panel-note {
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  line-height:1.6;
  margin:var(--space-2) 0 0;
}

.risk-list,
.doc-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.risk-row,
.doc-row {
  align-items:center;
  border-bottom:var(--stroke) solid var(--line);
  display:flex;
  gap:var(--space-1);
  justify-content:space-between;
  padding-bottom:var(--space-1);
}

.doc-row {
  align-items:flex-start;
  flex-direction:column;
}

.doc-row span,
.risk-row span {
  color:var(--ink-secondary);
}

.empty-inline {
  color:var(--ink-secondary);
  padding:var(--space-2) 0;
}

.compact-inline-empty {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  line-height:1.5;
  padding:var(--space-1) var(--space-2);
}

.empty-state {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  color:var(--ink-secondary);
  margin-top:var(--space-1);
  padding:var(--space-2);
}

.empty-state strong {
  color:var(--action);
  display:block;
  margin-bottom:calc(var(--space-1) / 2);
}

.empty-state p {
  line-height:1.6;
  margin:0 0 var(--space-1);
}

.empty-state ul {
  display:grid;
  gap:calc(var(--space-1) / 2);
  margin:0;
  padding-left:var(--space-2);
}

.compact-empty {
  margin-top:0;
}

.audit-empty {
  padding:var(--space-2);
}

.audit-empty p {
  max-width:72ch;
}

.error-line {
  background:var(--negative-soft);
  border:var(--stroke) solid var(--negative);
  border-radius:var(--radius-control);
  color:var(--negative);
  margin:0;
  padding:var(--space-1) var(--space-1);
}

@media (max-width: 1120px) {
  .center-tabs,
  .metric-strip,
  .workspace-grid,
  .agent-opinion-list,
  .split-block,
  .fact-preview__metrics,
  .review-snapshot,
  .technical-run,
  .trace-box dl {
    grid-template-columns:1fr;
  }

  .fact-mode {
    grid-template-columns:1fr;
  }

  .fact-mode button {
    border-bottom:var(--stroke) solid var(--line);
    border-right:0;
  }

  .fact-mode button:last-child {
    border-bottom:0;
  }

  .center-tabs button {
    border-bottom:var(--stroke) solid var(--line);
    border-right:0;
  }
}
</style>
