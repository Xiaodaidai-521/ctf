<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">教师处理</span>
        <h1 class="fb-title">{{ detail ? `${feedbackLabel('category', detail.category)} · ${feedbackLabel('issue', detail.issue_type)}` : '反馈处理' }}</h1>
        <p class="fb-sub" v-if="detail">
          学生：{{ detail.student_name }} · {{ formatDate(detail.created_at) }} · 状态：{{ feedbackLabel('status', detail.status) }}
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/teacher/feedback" class="fb-btn">返回待办</router-link>
        <button class="fb-btn" type="button" @click="load">刷新</button>
      </div>
    </div>

    <div class="fb-notice">
      <strong>处理完成不等于教学效果已验证，也不等于新规则已生效。</strong>
      本页记录人工处理、证据和转交，不会修改学生成绩、核验结论或课程规则。
      评分争议交核验与评分复核，目录或推荐问题交目录与推荐维护，技术故障交平台维护。
    </div>

    <div v-if="error" class="fb-error">{{ error }}</div>
    <div v-if="message" class="fb-success">{{ message }}</div>
    <div v-if="!detail" class="fb-empty">正在读取反馈详情...</div>

    <template v-else>
      <div class="fb-grid">
        <section class="fb-panel">
          <h2>反馈摘要</h2>
          <div class="fb-row"><span>状态</span><strong>{{ feedbackLabel('status', detail.status) }}</strong></div>
          <div class="fb-row"><span>学生/提交人</span><strong>{{ detail.student_name }} / {{ detail.submitter_name }}（{{ feedbackLabel('role', detail.submitter_role) }}）</strong></div>
          <div class="fb-row"><span>关联任务</span><strong>{{ detail.task_title || (detail.task_key ? '任务名称暂不可用' : '未关联任务') }}</strong></div>
          <div class="fb-row"><span>目录/任务版本</span><strong>{{ detail.catalog_version || '未提供' }} / {{ detail.task_version || '未提供' }}</strong></div>
          <div class="fb-row"><span>练习记录</span><strong>{{ detail.attempt_id || detail.attempt_ref ? '已关联原练习' : '未关联练习' }}</strong></div>
          <div class="fb-row"><span>能力/知识点</span><strong>{{ detail.capability_title || (detail.capability_id ? '能力名称暂不可用' : '未关联能力') }} / {{ detail.knowledge_point_name || (detail.knowledge_point_id ? '知识点名称暂不可用' : '未关联知识点') }}</strong></div>
          <div class="fb-row"><span>处理去向</span><strong>{{ feedbackLabel('destination', detail.handling_destination) }}</strong></div>
          <div class="fb-row"><span>责任人</span><strong>{{ detail.owner_name || '未分配' }}（{{ feedbackLabel('owner', detail.owner_role) }}）</strong></div>
          <div class="fb-row"><span>证据/关联资料</span><strong>{{ detail.evidence_complete ? '完整' : '缺证' }} / {{ detail.mapping_complete ? '完整' : '待补充' }}</strong></div>
          <div class="fb-row"><span>候选依据</span><strong>{{ detail.candidate_eligible ? '满足' : '不满足' }}</strong></div>
          <div class="fb-row"><span>教学效果</span><strong>{{ feedbackLabel('effect', detail.effect_status) }}</strong></div>
          <div class="fb-row">
            <span>重复反馈</span>
            <strong>
              <router-link v-if="detail.duplicate_of" :to="`/teacher/feedback/${detail.duplicate_of}`" class="fb-link">{{ feedbackTitle(mainTicket) }}</router-link>
              <template v-else>未关联主反馈</template>（{{ detail.duplicate_count }} 条重复）
            </strong>
          </div>
          <div v-if="mainTicketError" class="fb-error" role="alert">
            {{ mainTicketError }}
            <button class="fb-btn" type="button" @click="loadMainTicket">重试读取主反馈标题</button>
          </div>

          <h3>具体争议</h3>
          <p class="fb-pre">{{ detail.dispute }}</p>
          <h3>期望结果 / 理由</h3>
          <p class="fb-pre">{{ detail.expected_result || '—' }}
{{ detail.reason || '—' }}</p>

          <div v-if="detail.missing_evidence?.length" class="fb-missing">
            <strong>缺失证据</strong>
            <ul>
              <li v-for="slot in detail.missing_evidence" :key="slot">{{ feedbackLabel('slot', slot) }}</li>
            </ul>
          </div>
          <div v-if="detail.missing_mapping?.length" class="fb-missing">
            <strong>待补充的关联资料</strong>
            <ul><li v-for="field in detail.missing_mapping" :key="field">{{ feedbackLabel('mapping', field) }}</li></ul>
          </div>
        </section>

        <section class="fb-panel">
          <h2>证据与附件</h2>
          <div v-if="!detail.evidence?.length" class="fb-empty">暂无证据。</div>
          <div v-else class="fb-list">
            <article v-for="item in detail.evidence" :key="item.evidence_id" class="fb-card">
              <div class="fb-card-head">
                <strong>{{ feedbackLabel('slot', item.slot) }}</strong>
                <span class="fb-badge" :class="item.status === 'provided' ? 'fb-badge-ok' : 'fb-badge-warn'">
                  {{ feedbackLabel('evidence', item.status) }}
                </span>
              </div>
              <p class="fb-muted">{{ item.summary || '—' }}</p>
              <div class="fb-meta">
                <span>关联资料：{{ item.ref ? '已关联' : '未提供' }}</span>
                <span>版本：{{ item.version || '—' }}</span>
                <span>来源：{{ feedbackLabel('source', item.source) }}</span>
                <span>可见：{{ feedbackLabel('visibility', item.visibility) }}</span>
              </div>
              <RecordView :value="item" title="反馈证据" />
              <div v-if="item.attachment" class="fb-actions">
                <button class="fb-btn" type="button" @click="download(item.attachment)">下载 {{ item.attachment.original_name }}</button>
              </div>
            </article>
          </div>

          <h3>提交时的任务资料</h3>
          <div class="fb-row"><span>任务</span><strong>{{ detail.context_snapshot?.task?.title || '未提供任务名称' }}</strong></div>
          <div class="fb-row"><span>任务版本</span><strong>{{ detail.context_snapshot?.task?.version || '未提供' }}</strong></div>
          <div class="fb-row"><span>开始练习</span><strong>{{ formatDate(detail.context_snapshot?.attempt?.claimed_at) }}</strong></div>
          <div class="fb-row"><span>提交练习</span><strong>{{ formatDate(detail.context_snapshot?.attempt?.submitted_at) }}</strong></div>
          <details class="fb-mt">
            <summary>原始判定与完整取证资料</summary>
            <p class="fb-muted">部分原始资料尚未提供可读说明；可查看已说明的内容，并下载完整原记录核对，不会遗漏原有核查依据。</p>
            <RecordView :value="detail.original_decision_snapshot" title="原始判定" />
            <RecordView :value="detail.context_snapshot" title="取证资料" />
            <h3>原始判定摘要</h3>
            <dl class="fb-definition">
              <dt>判定关联资料</dt><dd>{{ detail.original_decision_ref || detail.original_decision_snapshot?.ref ? '已关联，完整记录可下载核对' : '未提供' }}</dd>
              <dt>判定版本</dt><dd>{{ detail.original_decision_version || '未提供' }}</dd>
              <dt>任务</dt><dd>{{ detail.context_snapshot?.task?.title || '未提供任务名称' }}</dd>
              <dt>任务版本</dt><dd>{{ detail.context_snapshot?.task?.version || '未提供' }}</dd>
              <dt>练习状态</dt><dd>{{ feedbackLabel('status', detail.context_snapshot?.attempt?.status) }}</dd>
              <dt>开始与提交</dt><dd>{{ formatDate(detail.context_snapshot?.attempt?.claimed_at) }} · {{ formatDate(detail.context_snapshot?.attempt?.submitted_at) }}</dd>
            </dl>
          </details>
        </section>
      </div>

      <section class="fb-panel">
        <h2>人工处理动作</h2>
        <p class="fb-muted">每次处理都会保留理由、证据和责任人；若反馈已被他人更新，请先刷新再操作。</p>

        <details class="fb-card fb-mt">
          <summary><strong>认领 / 分配</strong></summary>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="run('claim', { reason: '负责人认领待办。' })">认领给自己</button>
          </div>
          <ReferenceImport title="分配负责人" :fields="ownerFields" :model-value="{ owner_id: actionForms.assign.owner_id }" @update:model-value="Object.assign(actionForms.assign, $event)" />
          <div class="fb-form-grid fb-mt">
            <label>责任角色
              <select v-model="actionForms.assign.owner_role" class="fb-select">
                <option v-for="item in options.owner_roles" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-full">理由<textarea v-model="actionForms.assign.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="submitAssign">分配</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>登记冲突 / 影响 / 新颖性</strong></summary>
          <div class="fb-form-grid">
            <label>影响
              <select v-model="actionForms.triage.impact_level" class="fb-select">
                <option v-for="item in options.impact_levels" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>新颖性
              <select v-model="actionForms.triage.novelty" class="fb-select">
                <option v-for="item in options.novelty" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-check"><input v-model="actionForms.triage.conflict_flag" type="checkbox" /> 存在证据冲突</label>
            <label class="fb-full">理由<textarea v-model="actionForms.triage.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions"><button class="fb-btn" type="button" @click="run('triage', actionForms.triage)">保存优先级</button></div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>要求补证</strong></summary>
          <p class="fb-muted">只选择确实缺失的必需证据；补证责任人、期限和理由会保留。</p>
          <div class="fb-missing fb-stack" v-if="detail.missing_evidence?.length">
            <label v-for="slot in detail.missing_evidence" :key="slot" class="fb-check">
              <input v-model="selectedMissing" type="checkbox" :value="slot" />
              {{ feedbackLabel('slot', slot) }}
            </label>
          </div>
          <div v-else class="fb-muted">当前没有缺失证据。</div>
          <ReferenceImport title="补证负责人" :fields="ownerFields" :model-value="{ owner_id: actionForms.request.owner_id }" @update:model-value="Object.assign(actionForms.request, $event)" />
          <div class="fb-form-grid">
            <label>期限<input v-model="actionForms.request.due_at" class="fb-input" type="datetime-local" /></label>
            <label class="fb-full">理由<textarea v-model="actionForms.request.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="requestEvidence">要求补证</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>确认 / 驳回</strong></summary>
          <div class="fb-form-grid">
            <label>处理去向
              <select v-model="actionForms.confirm.handling_destination" class="fb-select">
                <option v-for="item in options.destinations" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>责任角色
              <select v-model="actionForms.confirm.owner_role" class="fb-select">
                <option v-for="item in options.owner_roles" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <div class="fb-full"><ReferenceImport title="复核证据" :fields="evidenceFields" :model-value="{ evidence_refs: splitRefs(actionForms.confirm.evidence_refs) }" @update:model-value="actionForms.confirm.evidence_refs = $event.evidence_refs" /></div>
            <label class="fb-full">确认理由<textarea v-model="actionForms.confirm.reason" class="fb-textarea" rows="2"></textarea></label>
            <label class="fb-full">驳回理由<textarea v-model="actionForms.reject.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="confirmTicket">确认</button>
            <button class="fb-btn fb-btn-danger" type="button" @click="run('reject', { reason: actionForms.reject.reason, evidence_refs: splitRefs(actionForms.confirm.evidence_refs) })">驳回</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>追加复核更正</strong></summary>
          <p class="fb-muted">只追加新结论，原复核人、理由、时间和原始判定保留。</p>
          <div class="fb-form-grid">
            <label>新结论
              <select v-model="actionForms.revise.conclusion" class="fb-select">
                <option value="confirmed">已确认</option>
                <option value="rejected">已驳回</option>
              </select>
            </label>
            <div class="fb-full"><ReferenceImport title="更正证据" :fields="evidenceFields" :model-value="{ evidence_refs: splitRefs(actionForms.revise.evidence_refs) }" @update:model-value="actionForms.revise.evidence_refs = $event.evidence_refs" /></div>
            <label class="fb-full">更正理由<textarea v-model="actionForms.revise.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('revise_review', { conclusion: actionForms.revise.conclusion, reason: actionForms.revise.reason, evidence_refs: splitRefs(actionForms.revise.evidence_refs) })">追加更正</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>开始人工处理</strong></summary>
          <div class="fb-form-grid">
            <label>处理动作<input v-model="actionForms.handling.handling_action" class="fb-input" placeholder="补充解释 / 安排审核任务 / 转交" /></label>
            <label>处理去向
              <select v-model="actionForms.handling.handling_destination" class="fb-select">
                <option v-for="item in options.destinations" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-full">处理说明<textarea v-model="actionForms.handling.handling_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="run('start_handling', actionForms.handling)">开始处理</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>转交 / 接收确认</strong></summary>
          <p class="fb-muted">评分争议须交核验与评分复核；目录或推荐问题交目录与推荐维护；技术故障交平台维护。接收方确认前不能标记已处理。</p>
          <div class="fb-form-grid">
            <label>转交去向
              <select v-model="actionForms.refer.destination" class="fb-select">
                <option value="module6">核验与评分复核</option>
                <option value="module1">目录与推荐维护</option>
                <option value="course_material">课程材料</option>
                <option value="platform">平台维护</option>
              </select>
            </label>
            <div><ReferenceImport title="转交关联资料" :fields="externalFields" :model-value="{ external_ref: actionForms.refer.external_ref }" @update:model-value="Object.assign(actionForms.refer, $event)" /></div>
            <label class="fb-full">转交说明<textarea v-model="actionForms.refer.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('refer', { destination: actionForms.refer.destination, reason: actionForms.refer.reason, external_ref: actionForms.refer.external_ref })">登记转交</button>
          </div>
          <div v-if="pendingReferrals.length" class="fb-form-grid fb-mt">
            <label>待确认转交
              <select v-model="actionForms.ack.referral_id" class="fb-select">
                <option value="">请选择</option>
                <option v-for="referral in pendingReferrals" :key="referral.referral_id" :value="referral.referral_id">
                  {{ feedbackLabel('destination', referral.destination) }} · {{ formatDate(referral.created_at) }}
                </option>
              </select>
            </label>
            <div><ReferenceImport title="接收关联资料" :fields="externalFields" :model-value="{ external_ref: actionForms.ack.external_ref }" @update:model-value="Object.assign(actionForms.ack, $event)" /></div>
            <label class="fb-full">确认说明<textarea v-model="actionForms.ack.ack_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('ack_referral', { referral_id: actionForms.ack.referral_id, referral_status: 'acknowledged', ack_note: actionForms.ack.ack_note, external_ref: actionForms.ack.external_ref })">确认接收</button>
            <button class="fb-btn fb-btn-danger" type="button" @click="run('ack_referral', { referral_id: actionForms.ack.referral_id, referral_status: 'declined', ack_note: actionForms.ack.ack_note || '接收方退回。', external_ref: actionForms.ack.external_ref })">退回转交</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>标记已处理 / 登记教学效果</strong></summary>
          <p class="fb-muted">所有转交必须已确认接收才能标记已处理。教学效果单独登记，不随工单关闭自动变成“已验证”。</p>
          <div class="fb-form-grid">
            <label class="fb-full">处理说明<textarea v-model="actionForms.handle.handling_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="run('handle', { handling_note: actionForms.handle.handling_note })">标记已处理</button>
          </div>
          <p class="fb-muted">验证教学效果需引用该学生真实的复测记录。以下保留复测任务与状态；完整核验对照可按格式模板导入，不会用任务状态代替核验结果。</p>
          <ReferenceImport title="复测核验对照" :fields="retestFields" :model-value="{ retest_fact_ref: actionForms.effect.retest_fact_ref, retest_attempt_ref: actionForms.effect.retest_attempt_ref }" @update:model-value="Object.assign(actionForms.effect, $event)" />
          <div class="fb-form-grid fb-mt">
            <label>教学效果
              <select v-model="actionForms.effect.effect_status" class="fb-select">
                <option v-for="item in options.effect_statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>复测记录
              <select v-model="actionForms.effect.retest" class="fb-select">
                <option value="">不关联复测记录</option>
                <option v-for="retest in studentRetests" :key="retest.assignment_id" :value="retest.assignment_id">
                  {{ retest.task_title }} · {{ retest.status_label }} · {{ formatDate(retest.due_at) }}{{ retest.fact_ref ? '' : '（缺少核验对照）' }}
                </option>
              </select>
            </label>
            <label class="fb-full">效果说明<textarea v-model="actionForms.effect.effect_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="submitEffect">登记教学效果</button>
          </div>
        </details>

        <details class="fb-card fb-mt">
          <summary><strong>重开 / 内部备注 / 重复处理</strong></summary>
          <div class="fb-form-grid">
            <label class="fb-full">重开理由<textarea v-model="actionForms.reopen.reason" class="fb-textarea" rows="2"></textarea></label>
            <label class="fb-full">内部备注（仅教师可见）<textarea v-model="actionForms.note.reason" class="fb-textarea" rows="2"></textarea></label>
            <div class="fb-full">
              <label>主反馈
                <select v-model="actionForms.duplicate.main_ticket_id" class="fb-select">
                  <option value="">请选择主反馈</option>
                  <option v-for="ticket in duplicateTickets" :key="ticket.feedback_id" :value="ticket.feedback_id">{{ feedbackTitle(ticket) }}</option>
                </select>
              </label>
              <div class="fb-actions">
                <button class="fb-btn" type="button" :disabled="duplicateLoading" @click="loadDuplicateTickets">{{ duplicateLoading ? '读取中…' : '读取可选主反馈' }}</button>
              </div>
              <p class="fb-muted">可选同一学生的全部非重复反馈，不限于待办列表当前页。</p>
              <div v-if="duplicateError" class="fb-error" role="alert">{{ duplicateError }}</div>
              <p v-else-if="duplicateLoaded && !duplicateTickets.length" class="fb-muted">暂无可选主反馈。</p>
            </div>
            <label class="fb-full">重复处理理由<textarea v-model="actionForms.duplicate.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('reopen', { reason: actionForms.reopen.reason })">重开</button>
            <button class="fb-btn" type="button" @click="run('note', { reason: actionForms.note.reason })">保存内部备注</button>
            <button class="fb-btn" type="button" @click="run('confirm_duplicate', { main_ticket_id: actionForms.duplicate.main_ticket_id, reason: actionForms.duplicate.reason })">确认重复</button>
            <button class="fb-btn" type="button" @click="run('split_duplicate', { reason: actionForms.duplicate.reason || '拆分重复记录。' })">拆分重复</button>
          </div>
        </details>
      </section>

      <section class="fb-panel">
        <h2>复核与转交记录</h2>
        <h3>复核结论</h3>
        <div v-if="!detail.reviews?.length" class="fb-empty">暂无复核结论。</div>
        <div v-else class="fb-list">
          <article v-for="review in detail.reviews" :key="review.review_id" class="fb-card">
            <div class="fb-card-head">
              <strong>{{ feedbackLabel('status', review.conclusion) }}</strong>
              <span class="fb-badge" :class="review.is_current ? 'fb-badge-info' : 'fb-badge-muted'">{{ review.is_current ? '当前' : '历史' }}</span>
            </div>
            <p class="fb-muted">{{ review.reason }}</p>
            <div class="fb-meta">
              <span>复核人：{{ review.reviewer_name }}</span>
              <span>{{ formatDate(review.created_at) }}</span>
            </div>
          </article>
        </div>
        <h3>转交</h3>
        <div v-if="!detail.referrals?.length" class="fb-empty">暂无转交记录。</div>
        <div v-else class="fb-list">
          <article v-for="referral in detail.referrals" :key="referral.referral_id" class="fb-card">
            <div class="fb-card-head">
              <strong>{{ feedbackLabel('destination', referral.destination) }}</strong>
              <span class="fb-badge" :class="referral.status === 'acknowledged' ? 'fb-badge-ok' : 'fb-badge-warn'">{{ feedbackLabel('referral', referral.status) }}</span>
            </div>
            <p class="fb-muted">{{ referral.note || '—' }}</p>
            <RecordView :value="referral" title="转交资料" />
            <div class="fb-meta">
              <span>接收关联资料：{{ referral.external_ref ? '已关联，完整记录可下载核对' : '未提供' }}</span>
              <span>{{ formatDate(referral.created_at) }}</span>
            </div>
          </article>
        </div>
        <h3>事件核对</h3>
        <p class="fb-muted">检查处理记录是否完整；未同步的记录可以重试，内容不一致时请人工核对。</p>
        <div class="fb-actions">
          <button class="fb-btn" type="button" @click="retryEvents">重试待同步事件</button>
        </div>
        <div class="fb-meta">
          <span v-for="(count, status) in detail.reconciliation?.counts" :key="status">{{ feedbackLabel('eventStatus', status) }}：{{ count }}</span>
        </div>
        <div v-if="!detail.reconciliation?.items?.length" class="fb-empty">暂无核对记录。</div>
        <div v-else class="fb-table-wrap">
          <table class="fb-table">
            <thead><tr><th>处理动作</th><th>记录内容</th><th>核对状态</th><th>重试次数</th><th>最近核对</th><th>处理建议</th></tr></thead>
            <tbody>
              <tr v-for="item in detail.reconciliation.items" :key="item.action_id">
                <td>{{ feedbackLabel('action', item.action) }}</td>
                <td>{{ feedbackLabel('event', item.event_type) }}</td>
                <td>{{ feedbackLabel('eventStatus', item.status) }}</td>
                <td>{{ item.attempts }}</td>
                <td>{{ formatDate(item.checked_at) }}</td>
                <td>{{ reconciliationNote(item) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import service from './feedback/api.js'
import ReferenceImport from '@/shared/forms/ReferenceImport.vue'
import RecordView from '@/shared/forms/RecordView.vue'
import { feedbackDate as formatDate, feedbackError, feedbackLabel, feedbackOptions, feedbackTitle, mergeFeedbackItems, nextFeedbackPage, reconciliationNote } from './feedbackPresentation.js'

const route = useRoute()
const detail = ref(null)
const error = ref('')
const message = ref('')
const selectedMissing = ref([])
const mainTicket = ref(null)
const mainTicketError = ref('')
const duplicateTickets = ref([])
const duplicateLoading = ref(false)
const duplicateLoaded = ref(false)
const duplicateError = ref('')
const ownerCandidates = ref([])
const studentRetests = ref([])
let mainTicketGeneration = 0
const options = reactive({
  categories: [],
  conditional_slots: [],
  destinations: [],
  owner_roles: [],
  impact_levels: [],
  novelty: [],
  effect_statuses: [],
})

const actionForms = reactive({
  assign: { owner_id: '', owner_role: 'teacher', reason: '' },
  triage: { impact_level: 'unknown', novelty: 'unknown', conflict_flag: false, reason: '' },
  request: { owner_id: '', due_at: '', reason: '' },
  confirm: { handling_destination: '', owner_role: '', evidence_refs: '', reason: '' },
  reject: { reason: '' },
  revise: { conclusion: 'confirmed', evidence_refs: '', reason: '' },
  handling: { handling_action: '', handling_note: '', handling_destination: '' },
  refer: { destination: 'module6', reason: '', external_ref: '' },
  ack: { referral_id: '', ack_note: '', external_ref: '' },
  handle: { handling_note: '' },
  effect: { effect_status: 'awaiting_retest', effect_note: '', retest: '', retest_fact_ref: '', retest_attempt_ref: '' },
  reopen: { reason: '' },
  note: { reason: '' },
  duplicate: { main_ticket_id: '', reason: '' },
})

const ownerFields = [{ key: 'owner_id', label: '负责人', type: 'number' }]
const evidenceFields = [{ key: 'evidence_refs', label: '引用证据', type: 'list' }]
const externalFields = [{ key: 'external_ref', label: '接收方关联资料' }]
const retestFields = [{ key: 'retest_fact_ref', label: '复测核验' }, { key: 'retest_attempt_ref', label: '复测练习' }]
const pendingReferrals = computed(() => (detail.value?.referrals || []).filter((item) => item.status === 'pending_ack'))

async function loadMainTicket() {
  const generation = ++mainTicketGeneration
  const id = detail.value?.duplicate_of
  mainTicketError.value = ''
  if (mainTicket.value?.feedback_id === id) return
  mainTicket.value = null
  if (!id) return
  try {
    const result = await service.feedback.teacherDetail(id)
    if (generation === mainTicketGeneration) mainTicket.value = result
  } catch (err) {
    if (generation === mainTicketGeneration) mainTicketError.value = feedbackError(err, '主反馈标题未能读取，仍可打开主反馈。')
  }
}

async function loadDuplicateTickets() {
  if (duplicateLoading.value || !detail.value) return
  const current = detail.value.feedback_id
  const student = detail.value.student_id
  duplicateLoading.value = true
  duplicateLoaded.value = false
  duplicateError.value = ''
  let page = 1
  let items = []
  try {
    do {
      const res = await service.feedback.teacherQueue({ page, page_size: 100, sort: 'newest' })
      if (current !== detail.value?.feedback_id) return
      const candidates = (res.items || []).filter(item => item.student_id === student && item.feedback_id !== current)
      items = mergeFeedbackItems(items, candidates)
      duplicateTickets.value = mergeFeedbackItems(
        duplicateTickets.value.filter(item => item.feedback_id === actionForms.duplicate.main_ticket_id), items,
      )
      page = nextFeedbackPage(res)
    } while (page !== null)
    duplicateLoaded.value = true
  } catch (err) {
    duplicateError.value = feedbackError(err, '可选主反馈尚未全部读取，已选项仍保留，请重试。')
  } finally {
    duplicateLoading.value = false
  }
}

function splitRefs(value) {
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean)
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

async function load() {
  error.value = ''
  try {
    const [detailRes, optionsRes] = await Promise.all([
      service.feedback.teacherDetail(route.params.id),
      service.feedback.options(),
    ])
    detail.value = detailRes
    Object.assign(options, optionsRes, {
      destinations: feedbackOptions(optionsRes.destinations, 'destination'),
      owner_roles: feedbackOptions(optionsRes.owner_roles, 'owner'),
      impact_levels: feedbackOptions(optionsRes.impact_levels, 'impact'),
      novelty: feedbackOptions(optionsRes.novelty, 'novelty'),
      effect_statuses: feedbackOptions(optionsRes.effect_statuses, 'effect'),
    })
    selectedMissing.value = [...(detailRes.missing_evidence || [])]
    if (!actionForms.confirm.handling_destination) {
      actionForms.confirm.handling_destination = detailRes.handling_destination || 'unassigned'
    }
    if (!actionForms.handling.handling_destination) {
      actionForms.handling.handling_destination = detailRes.handling_destination || 'unassigned'
    }
    if (!actionForms.confirm.owner_role) actionForms.confirm.owner_role = detailRes.owner_role || 'teacher'
    if (!actionForms.ack.referral_id && pendingReferrals.value.length) {
      actionForms.ack.referral_id = pendingReferrals.value[0].referral_id
    }
    void loadMainTicket()
    void loadStudentRetests()
  } catch (err) {
    error.value = feedbackError(err, '加载反馈详情失败，请重试。')
  }
}

async function loadStudentRetests() {
  try {
    const payload = await service.skillReview.teacherRetests()
    studentRetests.value = (payload.items || [])
      .filter(item => String(item.student?.id) === String(detail.value?.student_id))
      .map(item => ({
        assignment_id: item.assignment_id,
        task_title: item.task?.title || item.original_task_title || '复测任务',
        status_label: item.status_label,
        due_at: item.due_at,
        fact_ref: '',
        attempt_ref: item.started_attempt_id || '',
      }))
  } catch {
    studentRetests.value = []
  }
}

async function run(action, payload = {}) {
  error.value = ''
  message.value = ''
  try {
    const res = await service.feedback.teacherAction(detail.value.feedback_id, {
      action,
      expected_version: detail.value.version,
      ...payload,
    })
    detail.value = res
    message.value = `已记录：${feedbackLabel('action', action)}；当前状态：${feedbackLabel('status', res.status)}。`
    selectedMissing.value = [...(res.missing_evidence || [])]
    await load()
  } catch (err) {
    error.value = feedbackError(err, '处理动作失败，请重试。')
  }
}

function requestEvidence() {
  if (!selectedMissing.value.length) {
    error.value = '请选择需要补充的证据。'
    return
  }
  run('request_evidence', {
    missing_slots: selectedMissing.value,
    ...(actionForms.request.owner_id ? { owner_id: actionForms.request.owner_id } : {}),
    due_at: actionForms.request.due_at ? new Date(actionForms.request.due_at).toISOString() : null,
    reason: actionForms.request.reason,
  })
}

function submitAssign() {
  if (!actionForms.assign.owner_id) {
    error.value = '请先导入分配负责人资料。'
    return
  }
  run('assign', {
    owner_id: actionForms.assign.owner_id,
    owner_role: actionForms.assign.owner_role,
    reason: actionForms.assign.reason,
  })
}

function submitEffect() {
  const selected = studentRetests.value.find(item => item.assignment_id === actionForms.effect.retest)
  const fact = actionForms.effect.retest_fact_ref || selected?.fact_ref || ''
  const attempt = actionForms.effect.retest_attempt_ref || selected?.attempt_ref || ''
  run('set_effect', {
    effect_status: actionForms.effect.effect_status,
    effect_note: actionForms.effect.effect_note,
    ...(fact ? { retest_fact_ref: fact } : {}),
    ...(attempt ? { retest_attempt_ref: attempt } : {}),
  })
}

function confirmTicket() {
  run('confirm', {
    reason: actionForms.confirm.reason,
    handling_destination: actionForms.confirm.handling_destination,
    owner_role: actionForms.confirm.owner_role,
    evidence_refs: splitRefs(actionForms.confirm.evidence_refs),
  })
}

async function retryEvents() {
  error.value = ''
  message.value = ''
  try {
    await service.feedback.retryEvents({ ticket_id: detail.value.feedback_id })
    message.value = '事件同步重试完成；请查看核对结果。'
    await load()
  } catch (err) {
    error.value = feedbackError(err, '事件同步重试失败，请稍后再试。')
  }
}

async function download(attachment) {
  try {
    const response = await service.feedback.downloadAttachment(detail.value.feedback_id, attachment.attachment_id)
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.original_name
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    error.value = feedbackError(err, '下载附件失败，请稍后再试。')
  }
}

onMounted(load)
</script>

<style src="@/assets/feedback.css"></style>
