<template>
  <div class="profile-page">
    <div class="container">
      <div class="profile-container">
        <!-- 左侧边栏 -->
        <div class="profile-sidebar">
          <!-- 用户信息卡片 -->
          <div class="user-card">
            <div class="user-avatar">{{ userStore.userName.charAt(0).toUpperCase() }}</div>
            <div class="user-info">
              <h2 class="user-name">{{ userStore.userName }}</h2>
              <div class="user-role" :class="`role-${userStore.userInfo?.role}`">
                {{ userStore.userInfo?.role_display || '用户' }}
              </div>
            </div>
            <div class="user-bio" v-if="userStore.userInfo?.bio">
              {{ userStore.userInfo.bio }}
            </div>
            <div class="user-stats-mini">
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ userStore.userInfo?.score || 0 }}</span>
                <span class="stat-mini-label">积分</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.solved_challenges || 0 }}</span>
                <span class="stat-mini-label">解题</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.total_submissions || 0 }}</span>
                <span class="stat-mini-label">提交</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.success_rate || 0 }}%</span>
                <span class="stat-mini-label">正确率</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.collects || 0 }}</span>
                <span class="stat-mini-label">收藏</span>
              </div>
              <div class="stat-mini-item">
                <span class="stat-mini-value">{{ stats.completion_rate || 0 }}%</span>
                <span class="stat-mini-label">进度</span>
              </div>
            </div>
          </div>

          <!-- 左侧导航菜单 -->
          <div class="sidebar-menu">
            <div
              v-for="menu in menus"
              :key="menu.value"
              class="menu-item"
              :class="{ active: activeTab === menu.value }"
              @click="activeTab = menu.value"
            >
              <span class="menu-icon"><AppIcon :name="menu.icon" /></span>
              <span class="menu-label">{{ menu.label }}</span>
              <span class="menu-count" v-if="menu.count !== undefined">{{ menu.count }}</span>
            </div>
          </div>
        </div>

        <!-- 右侧内容区 -->
        <div class="profile-main">
          <!-- 标题栏 -->
          <div class="content-header">
            <h2 class="content-title">{{ currentMenu?.label }}</h2>
          </div>

          <!-- 收藏列表 -->
          <div v-if="activeTab === 'favorites'" class="tab-content">
            <div v-if="favorites.length > 0" class="list-grid">
              <div
                v-for="item in favorites"
                :key="item.id"
                class="list-card"
              >
                <div class="card-badge" v-if="item.type">{{ item.type }}</div>
                <h3 class="card-title">{{ item.title }}</h3>
                <p class="card-summary">{{ item.summary || item.description }}</p>
                <div class="card-meta">
                  <span class="meta-time">{{ formatTime(item.created_at) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon"><AppIcon name="bi-bookmark" /></div>
              <p class="empty-text">还没有收藏任何内容</p>
            </div>
          </div>

          <!-- 完成题目 -->
          <div v-if="activeTab === 'solved'" class="tab-content">
            <div class="stats-overview">
              <div class="overview-card">
                <div class="overview-value">{{ stats.solved_challenges || 0 }}</div>
                <div class="overview-label">已解决题目</div>
              </div>
              <div class="overview-card">
                <div class="overview-value">{{ userStore.userInfo?.score || 0 }}</div>
                <div class="overview-label">总积分</div>
              </div>
              <div class="overview-card rank-card">
                <div class="overview-rank" :class="`rank-${userGrade.level}`">
                  {{ userGrade.level }}
                </div>
                <div class="overview-label">{{ userGrade.title }}</div>
              </div>
            </div>

            <div v-if="solvedChallenges.length > 0" class="challenges-grid">
              <div
                v-for="challenge in solvedChallenges"
                :key="challenge.id"
                class="challenge-card"
                @click="handleChallengeClick(challenge)"
              >
                <div class="challenge-card-header">
                  <div class="challenge-status-badge">
                    <span class="status-icon"><AppIcon name="bi-check2" /></span>
                    <span class="status-text">已解决</span>
                  </div>
                  <span class="challenge-score">{{ challenge.score }} 分</span>
                </div>
                <h3 class="challenge-card-title">{{ challenge.title }}</h3>
                <p class="challenge-card-desc">{{ challenge.description || '暂无描述' }}</p>
                <div class="challenge-card-footer">
                  <span class="card-tag">{{ challenge.category_name }}</span>
                  <span class="card-difficulty" :class="`diff-${challenge.difficulty}`">
                    {{ challenge.difficulty_display }}
                  </span>
                  <span class="card-time">{{ formatTime(challenge.solved_at) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon"><AppIcon name="bi-bullseye" /></div>
              <p class="empty-text">还没有解决任何题目，开始挑战吧！</p>
            </div>

            <!-- 最近提交记录 -->
            <div v-if="stats.recent_submissions?.length" class="recent-subs-section">
              <h3 class="section-subtitle">最近提交</h3>
              <div class="recent-subs-list">
                <div v-for="(s,i) in stats.recent_submissions" :key="i" class="recent-sub-item">
                  <span :aria-label="s.is_correct ? '正确' : '错误'" :class="s.is_correct ? 'sub-badge-correct' : 'sub-badge-wrong'"><AppIcon :name="s.is_correct ? 'bi-check2' : 'bi-x-lg'" /></span>
                  <span class="sub-name">{{ s.challenge }}</span>
                  <span class="sub-time">{{ formatTime(s.submitted_at) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 学习进度 -->
          <div v-if="activeTab === 'progress'" class="tab-content">
            <div v-if="learningPaths.length > 0" class="paths-list">
              <div
                v-for="path in learningPaths"
                :key="path.id"
                class="path-item"
              >
                <div class="path-header">
                  <h3 class="path-title">{{ path.title }}</h3>
                  <div class="path-progress">
                    <div class="progress-bar">
                      <div
                        class="progress-fill"
                        :style="{ width: `${path.progress}%` }"
                      ></div>
                    </div>
                    <span class="progress-text">{{ path.progress }}%</span>
                  </div>
                </div>
                <div class="path-meta">
                  <span class="meta-modules">模块: {{ path.completed_modules }}/{{ path.total_modules }}</span>
                  <span class="meta-experiments">实验: {{ path.completed_experiments }}/{{ path.total_experiments }}</span>
                </div>
                <div v-if="path.progress < 100" class="path-actions">
                  <button class="btn btn-primary btn-sm" @click="handleTrackPath(path)">
                    继续学习
                  </button>
                </div>
                <div v-else class="path-actions">
                  <span class="completed-badge"><AppIcon name="bi-check2" /> 已完成</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon"><AppIcon name="bi-journal-bookmark" /></div>
              <p class="empty-text">还没有加入{{ names.paths }}</p>
              <button class="btn btn-link" @click="router.push('/learning-paths')">
                查看{{ names.paths }} →
              </button>
            </div>
          </div>

          <!-- 提交记录 -->
          <div v-if="activeTab === 'submissions'" class="tab-content">
            <div v-if="submissions.length > 0" class="submissions-list">
              <div
                v-for="submission in submissions"
                :key="submission.id"
                class="submission-item"
                :class="{ correct: submission.is_correct }"
              >
                <div class="submission-icon" role="img" :aria-label="submission.is_correct ? '正确' : '错误'">
                  <AppIcon :name="submission.is_correct ? 'bi-check2' : 'bi-x-lg'" />
                </div>
                <div class="submission-content">
                  <div class="submission-title">{{ submission.challenge_title }}</div>
                  <div class="submission-meta">
                    <span class="meta-tag">{{ submission.category_name }}</span>
                    <span class="meta-time">{{ formatTime(submission.created_at) }}</span>
                  </div>
                  <div v-if="submission.is_correct" class="submission-flag">{{ submission.flag }}</div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <div class="empty-icon"><AppIcon name="bi-inbox" /></div>
              <p class="empty-text">暂无提交记录</p>
            </div>
          </div>

          <!-- 学习画像 -->
          <div v-if="activeTab === 'persona'" class="tab-content">
            <a-spin :loading="personaLoading">
              <div v-if="personaData" class="persona-section">
                <section v-if="!initialReport" class="persona-card onboarding-cta">
                  <div>
                    <h3 class="persona-card-title">完成初始学习画像</h3>
                    <p>通过 8 轮自然问答建立可追溯的能力基线，完成后将自动形成画像报表。</p>
                  </div>
                  <a-button type="primary" @click="router.push('/profile/setup')">开始画像访谈</a-button>
                </section>

                <section class="persona-card dynamic-growth-card" :class="{ 'dynamic-growth-empty': growthInsufficient }">
                  <div class="persona-card-head">
                    <div>
                      <h3 class="persona-card-title">动态成长画像</h3>
                      <span v-if="growthInsufficient">暂未产生有效学习数据，完成练习后将生成动态成长画像。</span>
                      <span v-else>基于学习时长、练习与答题结果计算。</span>
                    </div>
                    <a-button v-if="growthInsufficient" type="primary" size="small" @click="router.push('/learning-paths')">开始学习</a-button>
                  </div>
                  <div class="evidence-metrics dynamic-growth-metrics">
                    <div><strong>{{ learningMinutes }} 分钟</strong><span>有效学习时长</span></div>
                    <div><strong>{{ growthData.completed_question_count || 0 }}</strong><span>完成练习</span></div>
                    <div><strong>{{ growthData.correct_rate || 0 }}%</strong><span>正确率</span></div>
                    <div><strong>{{ growthAbilityText }}</strong><span>能力等级</span></div>
                  </div>
                  <p v-if="growthInsufficient" class="dynamic-growth-hint">
                    AI 分析门槛：至少完成 {{ growthData.minimum_requirements?.completed_questions || 3 }} 道练习，或累计学习 {{ Math.ceil((growthData.minimum_requirements?.learning_seconds || 600) / 60) }} 分钟；当前还差 {{ growthData.remaining?.completed_questions || 0 }} 道练习或 {{ remainingLearningMinutes }} 分钟。
                  </p>
                </section>
                <section class="persona-hero-card">
                  <div class="persona-hero-main">
                    <h3 class="persona-title">{{ personaLabelText(personaData.persona_label) || '画像生成中' }}</h3>
                    <p class="persona-summary">{{ personaSummary }}</p>
                  </div>
                  <div class="persona-hero-side">
                    <div class="confidence-ring" :style="{ '--confidence': confidencePercent }">
                      <strong>{{ confidencePercent }}%</strong>
                      <span>画像置信度</span>
                    </div>
                    <span class="persona-status">{{ personaStatusText }}</span>
                  </div>
                </section>

                <div class="persona-grid">
                  <section class="persona-card stage-compare-card advantage-compare-card">
                    <div class="persona-card-head">
                      <h3 class="persona-card-title">优势方向</h3>
                      <span>对比两个阶段中可迁移到实战解题的能力</span>
                    </div>
                    <div class="stage-compare-grid">
                      <div class="stage-column initial-stage">
                        <div class="stage-column-head"><strong>初始画像</strong></div>
                        <div class="direction-list">
                          <div v-for="item in initialStrengthItems" :key="`initial-strength-${item.key}`" class="direction-row">
                            <div class="direction-row-main"><strong>{{ item.label }}</strong><span>{{ item.reason }}</span></div>
                            <div class="level-bar"><i :style="{ width: `${skillPercent(item.level)}%` }"></i></div>
                            <em>{{ formatAbilityScore(item.level) }}</em>
                          </div>
                          <div v-if="!initialStrengthItems.length" class="quiet-empty">完成入学画像问答后生成。</div>
                        </div>
                      </div>
                      <div class="stage-column learned-stage">
                        <div class="stage-column-head"><strong>动态成长画像</strong></div>
                        <div class="direction-list">
                          <template v-if="growthInsufficient">
                            <div class="direction-row dynamic-empty-row">
                              <div class="direction-row-main"><strong>暂未产生有效学习数据</strong><span>等待后续有效测评形成优势方向。</span></div>
                              <div class="level-bar"><i :style="{ width: '0%' }"></i></div>
                              <em>0 分</em>
                            </div>
                            <div class="direction-row dynamic-empty-row">
                              <div class="direction-row-main"><strong>暂未产生有效学习数据</strong><span>等待后续有效测评形成优势方向。</span></div>
                              <div class="level-bar"><i :style="{ width: '0%' }"></i></div>
                              <em>0 分</em>
                            </div>
                          </template>
                          <template v-else v-for="item in learnedStrengthItems" :key="`learned-strength-${item.key}`">
                          <div class="direction-row">
                            <div class="direction-row-main"><strong>{{ item.label }}</strong><span>{{ item.reason }}</span></div>
                            <div class="level-bar"><i :style="{ width: `${skillPercent(item.level)}%` }"></i></div>
                            <em>{{ formatAbilityScore(item.level) }}</em>
                          </div>
                          </template>
                          <div v-if="!growthInsufficient && !learnedStrengthItems.length" class="quiet-empty">等待后续有效测评形成优势对比。</div>
                        </div>
                      </div>
                    </div>
                  </section>

                  <section class="persona-card stage-compare-card priority-compare-card">
                    <div class="persona-card-head">
                      <h3 class="persona-card-title">优先补强</h3>
                      <span>分别展示当时的薄弱方向和下一轮重点</span>
                    </div>
                    <div class="stage-compare-grid">
                      <div class="stage-column initial-stage">
                        <div class="stage-column-head"><strong>初始画像</strong></div>
                        <div class="direction-list">
                          <div v-for="item in initialWeaknessItems" :key="`initial-weakness-${item.key}`" class="direction-row weak">
                            <div class="direction-row-main"><strong>{{ item.label }}</strong><span>{{ item.reason }}</span></div>
                            <div class="level-bar"><i :style="{ width: `${skillPercent(item.level)}%` }"></i></div>
                            <em>{{ formatAbilityScore(item.level) }}</em>
                          </div>
                          <div v-if="!initialWeaknessItems.length" class="quiet-empty">完成入学画像问答后生成。</div>
                        </div>
                      </div>
                      <div class="stage-column learned-stage">
                        <div class="stage-column-head"><strong>动态成长画像</strong></div>
                        <div class="direction-list">
                          <template v-if="growthInsufficient">
                            <div class="direction-row dynamic-empty-row weak">
                              <div class="direction-row-main"><strong>暂未产生有效学习数据</strong><span>等待后续有效测评形成优先补强。</span></div>
                              <div class="level-bar"><i :style="{ width: '0%' }"></i></div>
                              <em>0 分</em>
                            </div>
                            <div class="direction-row dynamic-empty-row weak">
                              <div class="direction-row-main"><strong>暂未产生有效学习数据</strong><span>等待后续有效测评形成优先补强。</span></div>
                              <div class="level-bar"><i :style="{ width: '0%' }"></i></div>
                              <em>0 分</em>
                            </div>
                          </template>
                          <template v-else v-for="item in learnedWeaknessItems" :key="`learned-weakness-${item.key}`">
                          <div class="direction-row weak">
                            <div class="direction-row-main"><strong>{{ item.label }}</strong><span>{{ item.reason }}</span></div>
                            <div class="level-bar"><i :style="{ width: `${skillPercent(item.level)}%` }"></i></div>
                            <em>{{ formatAbilityScore(item.level) }}</em>
                          </div>
                          </template>
                          <div v-if="!growthInsufficient && !learnedWeaknessItems.length" class="quiet-empty">等待后续有效测评形成补强对比。</div>
                        </div>
                      </div>
                    </div>
                  </section>
                </div>

                <section class="persona-card">
                  <div class="persona-card-head">
                    <h3 class="persona-card-title">AI 调整建议</h3>
                    <span>{{ scoreBasis }}</span>
                  </div>
                  <div class="advice-layout">
                    <div class="advice-block">
                      <h4>学习节奏</h4>
                      <p>{{ paceAdvice }}</p>
                    </div>
                    <div class="advice-block">
                      <h4>下一步动作</h4>
                      <ul>
                        <li v-for="item in nextActions" :key="item">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="advice-block">
                      <h4>注意事项</h4>
                      <ul>
                        <li v-for="item in riskAlerts" :key="item">{{ item }}</li>
                      </ul>
                    </div>
                  </div>
                </section>

                <section class="persona-card">
                  <div class="persona-card-head">
                    <h3 class="persona-card-title">推荐智能体</h3>
                    <span>按当前画像匹配</span>
                  </div>
                  <div class="agent-chip-row">
                    <span v-for="a in personaData.recommended_agent_roster" :key="a" class="agent-chip">{{ agentNameText(a) }}</span>
                  </div>
                </section>

                <section v-if="studentProfile" class="persona-card evidence-dashboard">
                  <div class="persona-card-head evidence-dashboard-head">
                    <div>
                      <h3 class="persona-card-title">数据依据</h3>
                      <p>展示画像结论的数据覆盖度、客观来源与形成过程，所有结果均可追溯。</p>
                    </div>
                    <span class="traceable-badge">数据可追溯</span>
                  </div>

                  <div class="evidence-phase-grid">
                    <section class="evidence-phase initial-evidence-phase">
                      <div class="evidence-phase-head">
                        <div><strong>初始画像</strong><span>注册问答形成的能力基线</span></div>
                        <div class="evidence-confidence"><b>{{ initialConfidencePercent }}%</b><span>画像置信度</span></div>
                      </div>
                      <div class="evidence-metrics">
                        <div><strong>{{ initialQuestionCount }} / 8</strong><span>自然问答完成度</span></div>
                        <div><strong>{{ initialDirectionCount }} 项</strong><span>能力方向覆盖</span></div>
                        <div><strong>{{ initialReport ? 4 : 0 }} 类</strong><span>画像信息维度</span></div>
                        <div><strong>{{ formatShortDate(initialReport?.created_at) }}</strong><span>生成日期</span></div>
                      </div>
                      <div class="evidence-source-list">
                        <div class="evidence-source-row"><i></i><div><strong>原始自然问答</strong><span>目标、技术经历、解题思路、学习偏好</span></div></div>
                        <div class="evidence-source-row"><i></i><div><strong>AI 结构化分析</strong><span>六维能力、证据、置信度与推荐路径</span></div></div>
                      </div>
                    </section>

                    <section class="evidence-phase learned-evidence-phase">
                      <div class="evidence-phase-head">
                        <div><strong>动态成长画像</strong><span>真实学习行为形成的成长结论</span></div>
                        <div class="evidence-confidence"><b>{{ confidencePercent }}%</b><span>画像置信度</span></div>
                      </div>
                      <div class="evidence-metrics">
                        <div><strong>{{ stats.total_submissions || 0 }}</strong><span>累计提交题目</span></div>
                        <div><strong>{{ stats.success_rate || 0 }}%</strong><span>练习正确率</span></div>
                        <div><strong>{{ stats.solved_challenges || 0 }}</strong><span>已解题目</span></div>
                        <div><strong>{{ stats.completion_rate || 0 }}%</strong><span>模块完成率</span></div>
                      </div>
                      <div class="evidence-source-list">
                        <div class="evidence-source-row"><i></i><div><strong>客观学习数据</strong><span>答题结果、完成进度、错题与阶段测评</span></div></div>
                        <div class="evidence-source-row"><i></i><div><strong>持续校正机制</strong><span>达到有效数据阈值后更新，不重复生成</span></div></div>
                      </div>
                    </section>
                  </div>

                  <div class="evidence-chain-head"><strong>画像证据链</strong><span>从原始数据到画像结论的形成过程</span></div>
                  <div class="evidence-chain">
                    <div class="evidence-chain-node initial-node"><strong>01&nbsp; 原始输入</strong><span>8 轮自然问答</span></div><i>→</i>
                    <div class="evidence-chain-node initial-node"><strong>02&nbsp; 初始分析</strong><span>AI 提取能力与证据</span></div><i>→</i>
                    <div class="evidence-chain-node learned-node"><strong>03&nbsp; 行为校验</strong><span>练习、测评与进度</span></div><i>→</i>
                    <div class="evidence-chain-node learned-node"><strong>04&nbsp; 动态更新</strong><span>形成成长画像</span></div>
                  </div>

                  <div class="evidence-status-strip">
                    <span>完整性&nbsp; {{ initialQuestionCount === 8 ? '已通过' : '待补充' }}</span>
                    <span>时效性&nbsp; {{ dataFreshnessText }}</span>
                    <span>客观性&nbsp; {{ stats.total_submissions ? '学习数据已接入' : '待积累' }}</span>
                    <em>最近更新：{{ formatStageDate(personaData.last_computed || initialReport?.created_at) }}</em>
                  </div>
                </section>

                <AbilityRadarCard class="persona-radar-card" />
              </div>
              <div v-else class="empty-state">
                <div class="empty-icon"><AppIcon name="bi-person" /></div>
                <p class="empty-text">尚未设置学习画像</p>
                <a-button type="primary" @click="router.push('/profile/setup')">去设置</a-button>
              </div>
            </a-spin>
          </div>

          <!-- 个人资料 -->
          <div v-if="activeTab === 'profile'" class="tab-content">
            <div class="edit-form">
              <div class="form-group">
                <label class="form-label">用户名</label>
                <input
                  v-model="editForm.username"
                  type="text"
                  class="input"
                  disabled
                />
                <small class="form-hint">用户名不可修改</small>
              </div>

              <div class="form-group">
                <label class="form-label">昵称</label>
                <input
                  v-model="editForm.nickname"
                  type="text"
                  class="input"
                  placeholder="请输入昵称"
                />
              </div>

              <div class="form-group">
                <label class="form-label">邮箱</label>
                <input
                  v-model="editForm.email"
                  type="email"
                  class="input"
                  placeholder="请输入邮箱"
                />
              </div>

              <div class="form-group">
                <label class="form-label">战队</label>
                <input
                  v-model="editForm.team"
                  type="text"
                  class="input"
                  placeholder="请输入战队名称"
                />
              </div>

              <div class="form-group">
                <label class="form-label">班级</label>
                <input
                  v-model="editForm.class_name"
                  type="text"
                  class="input"
                  placeholder="请输入班级"
                />
              </div>

              <div class="form-group">
                <label class="form-label">学号</label>
                <input
                  v-model="editForm.student_id"
                  type="text"
                  class="input"
                  placeholder="请输入学号"
                />
              </div>

              <div class="form-group">
                <label class="form-label">个人简介</label>
                <textarea
                  v-model="editForm.bio"
                  class="input textarea"
                  rows="4"
                  placeholder="请输入个人简介"
                ></textarea>
              </div>

              <button
                class="btn btn-primary"
                @click="handleSave"
                :disabled="saving"
              >
                {{ saving ? '保存中...' : '保存修改' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { names } from '@/shared/navigation/names'

import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import api from '@/api'
import AbilityRadarCard from '@/components/AbilityRadarCard.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const PROFILE_TABS = ['favorites', 'solved', 'progress', 'submissions', 'profile', 'persona']
const tabFromQuery = value => (PROFILE_TABS.includes(value) ? value : 'solved')
const activeTab = ref(tabFromQuery(route.query.tab))
const submissions = ref([])
const favorites = ref([])
const solvedChallenges = ref([])
const learningPaths = ref([])
const stats = ref({})
const saving = ref(false)
const personaData = ref(null)
const studentProfile = ref(null)
const profileReports = ref([])
const personaLoading = ref(false)
const growthData = ref({})
const growthInsufficient = computed(() => growthData.value?.analysis_status === 'insufficient_data')
const learningMinutes = computed(() => Math.floor((growthData.value?.total_learning_seconds || 0) / 60))
const remainingLearningMinutes = computed(() => Math.ceil((growthData.value?.remaining?.learning_seconds || 0) / 60))
const growthAbilityText = computed(() => growthInsufficient.value ? '待评估' : `${Math.round(growthData.value?.ability_level || 0)} 分`)

const personaLabelMap = {
  initial_interview: '初始学习画像',
  code_first: '实践派学员',
  theory_driven: '理论型学员',
  visual_learner: '视觉型学员',
  hands_on: '动手型学员',
  practice_builder: '实战拆解型学习者',
  foundation_rebuilder: '基础巩固型学习者',
  balanced_planner: '均衡规划型学习者',
  challenge_sprinter: '题目冲刺型学习者',
  research_mapper: '研究探索型学习者'
}
const agentNameMap = {
  tutor: '学习导师',
  curriculum: '课程设计师',
  content_gen: '内容创作者',
  code_mentor: '代码导师',
  assessor: '评估专家',
  analyst: '学习分析师'
}
const styleLabelMap = {
  hands_on: '动手实践型',
  theory_first: '理论先行型',
  visual: '视觉学习型',
  balanced: '均衡发展型'
}
const personaLabelText = (v) => personaLabelMap[v] || v
const agentNameText = (v) => agentNameMap[v] || v
const dirLabelMap = {
  web: 'Web安全',
  crypto: '密码学',
  pwn: '二进制安全',
  reverse: '逆向工程',
  forensics: '数字取证',
  misc: '综合杂项'
}
const paceLabelMap = {
  self_paced: '自主学习',
  scheduled: '计划学习',
  intensive: '强化学习'
}
const dirLabel = (key) => dirLabelMap[key] || key
const paceText = (value) => paceLabelMap[value] || value || '未设置'
const personaTraits = computed(() => personaData.value?.persona_traits || {})
const personaSummary = computed(() => (
  personaTraits.value.summary || '完成自评后，系统会结合评分表生成你的学习画像。'
))
const initialReport = computed(() => profileReports.value.find((item) => item.report_type === 'initial') || null)
const initialReportData = computed(() => initialReport.value?.report_data || {})
const initialAbilityScores = computed(() => initialReportData.value.ability_scores || {})
const initialEvidence = computed(() => initialReportData.value.evidence || {})
const buildInitialDirectionItems = (reverse = false) => Object.entries(initialAbilityScores.value)
  .map(([key, score]) => ({
    key,
    label: dirLabel(key),
    level: (Number(score) || 0) / 20,
    reason: initialEvidence.value[key] || '来自注册后自然问答的初始判断',
  }))
  .sort((a, b) => reverse ? a.level - b.level : b.level - a.level)
  .slice(0, 2)
const initialStrengthItems = computed(() => buildInitialDirectionItems(false))
const initialWeaknessItems = computed(() => buildInitialDirectionItems(true))
const normalizePersonaItems = (items, fallbackReason) => (Array.isArray(items) ? items : []).map((item) => {
  if (typeof item === 'string') {
    const score = personaTraits.value.ability_scores?.[item] ?? initialAbilityScores.value[item] ?? 0
    return { key: item, label: dirLabel(item), level: Number(score) / 20, reason: fallbackReason }
  }
  const key = item.key || item.name || item.label
  const rawLevel = item.level ?? item.score ?? personaTraits.value.ability_scores?.[key] ?? 0
  return {
    ...item,
    key,
    label: item.label || dirLabel(key),
    level: Number(rawLevel) > 5 ? Number(rawLevel) / 20 : Number(rawLevel),
    reason: item.reason || fallbackReason,
  }
})
const hasLearningStageData = computed(() => Boolean(growthData.value?.eligible_for_ai))
const dynamicDirectionItems = computed(() => Object.entries(growthData.value?.dynamic_scores || {})
  .filter(([key]) => growthData.value?.growth_evidence?.[key]?.status === 'grown')
  .map(([key, score]) => {
    const evidence = growthData.value.growth_evidence[key] || {}
    const delta = Number(growthData.value?.growth_deltas?.[key] || 0)
    return {
      key,
      label: dirLabel(key),
      level: Number(score) / 20,
      reason: `较初始画像 +${delta} 分；${evidence.correct || 0}/${evidence.attempts || 0} 次答对`,
    }
  }))
const learnedStrengthItems = computed(() => hasLearningStageData.value
  ? [...dynamicDirectionItems.value].sort((a, b) => b.level - a.level).slice(0, 2)
  : [])
const learnedWeaknessItems = computed(() => {
  if (!hasLearningStageData.value) return []
  const items = [...dynamicDirectionItems.value].sort((a, b) => a.level - b.level).slice(0, 2)
  const initialOrder = initialWeaknessItems.value.map((item) => item.key)
  return [...items].sort((a, b) => {
    const aIndex = initialOrder.indexOf(a.key)
    const bIndex = initialOrder.indexOf(b.key)
    return (aIndex < 0 ? 999 : aIndex) - (bIndex < 0 ? 999 : bIndex)
  })
})
const initialQuestionCount = computed(() => initialReport.value?.raw_interview?.filter((item) => item.answer)?.length || 0)
const initialConfidencePercent = computed(() => {
  const values = Object.values(initialReportData.value.confidence || {}).map(Number).filter(Number.isFinite)
  return values.length ? Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100) : 0
})
const initialDirectionCount = computed(() => Object.keys(initialAbilityScores.value).length)
const dataFreshnessText = computed(() => {
  const latest = stats.value.recent_submissions?.[0]?.submitted_at || personaData.value?.last_computed
  if (!latest || !stats.value.total_submissions) return '待积累'
  const days = Math.max(0, Math.floor((Date.now() - new Date(latest).getTime()) / 86400000))
  return days <= 30 ? '近 30 天' : `${days} 天前`
})
const paceAdvice = computed(() => personaTraits.value.pace_advice || '保持稳定练习节奏，每轮学习后复盘卡点。')
const nextActions = computed(() => personaTraits.value.next_actions || [])
const riskAlerts = computed(() => personaTraits.value.risk_alerts || [])
const scoreBasis = computed(() => personaTraits.value.score_basis || '基于当前自评表生成')
const confidencePercent = computed(() => Math.round((personaData.value?.confidence_score || 0) * 100))
const personaStatusText = computed(() => {
  const status = personaData.value?.generation_status
  if (personaData.value?.from_cache || status === 'cached') return '画像已同步'
  if (status === 'generated') return '首次生成完成'
  if (status === 'regenerated') return '评分变化后已更新'
  if (status === 'fallback') return '已用本地规则兜底'
  return '画像已生成'
})
const skillPercent = (level) => Math.max(0, Math.min(Number(level) || 0, 5)) * 20
const formatAbilityScore = (level) => `${Math.round((Number(level) || 0) * 20)} 分`
const formatStageDate = (value) => value ? new Date(value).toLocaleDateString('zh-CN') : '暂无'
const formatShortDate = (value) => value
  ? new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  : '--/--'

const isAdminUser = computed(() => userStore.userInfo?.role === 'admin')

const baseMenus = [
  { label: '收藏', value: 'favorites', icon: 'bi bi-bookmark', count: computed(() => favorites.value.length) },
  { label: '完成题目', value: 'solved', icon: 'bi bi-check2-square', count: computed(() => solvedChallenges.value.length) },
  { label: '学习进度', value: 'progress', icon: 'bi bi-bar-chart', count: computed(() => learningPaths.value.length) },
  { label: '提交记录', value: 'submissions', icon: 'bi bi-file-earmark-text', count: computed(() => submissions.value.length) },
  { label: '个人资料', value: 'profile', icon: 'bi bi-person' },
  { label: '学习画像', value: 'persona', icon: 'bi bi-cpu' }
]

const menus = computed(() => (
  isAdminUser.value
    ? baseMenus.filter((menu) => menu.value !== 'persona')
    : baseMenus
))

const currentMenu = computed(() => menus.value.find(m => m.value === activeTab.value))

// `?tab=` 只是个人资料原有分区的直达方式：切页时同步地址，返回/刷新/收藏都回到同一区。
watch(menus, list => {
  if (!list.some(menu => menu.value === activeTab.value)) activeTab.value = 'solved'
}, { immediate: true })

watch(
  () => route.query.tab,
  value => {
    const requested = tabFromQuery(value)
    if (requested === 'persona' && isAdminUser.value) return
    if (requested !== activeTab.value) activeTab.value = requested
  }
)

watch(activeTab, value => {
  if (route.query.tab === value) return
  const query = { ...route.query }
  if (value && value !== 'solved') query.tab = value
  else delete query.tab
  router.replace({ path: '/profile', query })
})

// 用户评级计算
const userGrade = computed(() => {
  const score = userStore.userInfo?.score || 0
  const solvedCount = stats.value.solved_challenges || 0

  // 评级系统
  if (score >= 5000 && solvedCount >= 20) {
    return { level: 'SSS', title: '顶尖玩家' }
  } else if (score >= 3000 && solvedCount >= 15) {
    return { level: 'SS', title: '高手' }
  } else if (score >= 2000 && solvedCount >= 10) {
    return { level: 'S', title: '专家' }
  } else if (score >= 1000 && solvedCount >= 5) {
    return { level: 'A', title: '高级' }
  } else if (score >= 500 && solvedCount >= 3) {
    return { level: 'B', title: '中级' }
  } else if (solvedCount > 0) {
    return { level: 'C', title: '初级' }
  } else {
    return { level: '-', title: '未评级' }
  }
})

const editForm = ref({
  username: '',
  nickname: '',
  email: '',
  team: '',
  class_name: '',
  student_id: '',
  bio: ''
})

const fetchSubmissions = async () => {
  try {
    const response = await api.submission.mySubmissions()
    submissions.value = Array.isArray(response) ? response : (response.results || [])
  } catch (error) {
    console.error('获取提交记录失败:', error)
  }
}

const fetchFavorites = async () => {
  try {
    // 获取收藏的文章
    const response = await api.article.myFavorites()
    // 处理响应数据，确保是数组
    const articles = Array.isArray(response) ? response : (response.results || [])
    favorites.value = articles.map(item => ({
      id: item.id,
      type: '文章',
      title: item.title,
      summary: item.summary,
      created_at: item.created_at
    }))
  } catch (error) {
    console.error('获取收藏失败:', error)
    favorites.value = []
  }
}

const fetchSolvedChallenges = async () => {
  try {
    const response = await api.challenge.mySolved()
    // 处理响应数据，确保是数组
    const challenges = Array.isArray(response) ? response : (response.results || [])
    solvedChallenges.value = challenges
  } catch (error) {
    console.error('获取已解决题目失败:', error)
    solvedChallenges.value = []
  }
}

const fetchLearningPaths = async () => {
  try {
    // 修复 API 调用路径：learningPaths (复数) 而不是 learningPath (单数)
    const paths = await api.learningPaths.my()
    // 处理响应数据，确保是数组
    const pathsArray = Array.isArray(paths) ? paths : (paths.results || [])
    learningPaths.value = pathsArray.map(path => ({
      id: path.learning_path,
      title: path.path_title,
      progress: path.progress_percentage || 0,
      completed_modules: path.completed_modules || 0,
      total_modules: path.total_modules || 0,
      completed_experiments: path.completed_labs || 0,
      total_experiments: path.total_labs || 0
    }))
  } catch (error) {
    console.error('获取学习进度失败:', error)
    learningPaths.value = []
  }
}

const fetchPersona = async () => {
  personaLoading.value = true
  try {
    const [profile, persona, reports, growth] = await Promise.all([
      api.studentProfile.get(),
      api.studentProfile.persona(),
      api.studentProfile.reports(),
      api.studentProfile.growth()
    ])
    studentProfile.value = profile
    personaData.value = persona
    profileReports.value = Array.isArray(reports) ? reports : []
    growthData.value = persona?.dynamic_growth || growth || {}
  } catch {
    personaData.value = null
    profileReports.value = []
    growthData.value = {}
  } finally {
    personaLoading.value = false
  }
}

const fetchStats = async () => {
  try {
    stats.value = await api.submission.stats()
  } catch (error) {
    console.error('获取统计信息失败:', error)
  }
}

const initEditForm = () => {
  editForm.value = {
    username: userStore.userInfo?.username || '',
    nickname: userStore.userInfo?.nickname || '',
    email: userStore.userInfo?.email || '',
    team: userStore.userInfo?.team || '',
    class_name: userStore.userInfo?.class_name || '',
    student_id: userStore.userInfo?.student_id || '',
    bio: userStore.userInfo?.bio || ''
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const result = await userStore.updateProfile(editForm.value)
    if (result.success) {
      await userStore.fetchProfile()
      alert('保存成功')
    }
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

const formatTime = (time) => {
  if (!time) return ''
  const date = new Date(time)
  const now = new Date()
  const diff = now - date

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString()
}

const handleTrackPath = (path) => {
  // 跳转到学习路径详情页
  router.push(`/learning-paths/${path.id}`)
}

const handleChallengeClick = (challenge) => {
  // 跳转到题目详情页
  router.push(`/challenge/${challenge.id}`)
}

onMounted(async () => {
  await Promise.all([
    userStore.fetchProfile(),
    fetchSubmissions(),
    fetchFavorites(),
    fetchSolvedChallenges(),
    fetchLearningPaths(),
    fetchStats(),
    fetchPersona()
  ])
  initEditForm()
})
</script>

<style scoped>
.profile-page {
  padding: var(--space-4) 0 var(--space-8);
  min-height: calc(100vh - var(--header-height));
  background: var(--surface-page);
  color: var(--ink);
  font-family: var(--font-family);
  font-size: var(--text-body);
  line-height: var(--leading-body);
}

.container {
  margin: 0 auto;
  max-width: var(--page-width);
  padding: 0 var(--page-gutter);
}

.profile-container {
  display: grid;
  align-items: start;
  grid-template-columns: var(--menu-width) minmax(0, 1fr);
  gap: var(--space-3);
}

/* 左侧边栏 */
.profile-sidebar {
  position: sticky;
  display: flex;
  flex-direction: column;
  top: calc(var(--header-height) + var(--space-2));
  gap: var(--space-2);
}

.user-card {
  text-align: center;
  padding: var(--space-3);
  border-radius: var(--radius-panel);
  background: var(--surface);
}

.user-avatar {
  font-size: var(--text-section);
  font-weight: var(--weight-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--space-1);
  width: var(--space-8);
  height: var(--space-8);
  background: var(--action-soft);
  color: var(--action);
  border-radius: var(--radius-pill);
}

.user-info {
  margin-bottom: var(--space-1);
}

.user-name {
  font-size: var(--text-card);
  font-weight: var(--weight-strong);
  color: var(--ink);
  margin-bottom: var(--space-1);
  margin: 0 0 var(--space-1);
  overflow-wrap: anywhere;
}

.user-role {
  display: inline-block;
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  font-weight: var(--weight-medium);
  background: var(--surface-muted);
  color: var(--ink-secondary);
  padding: 0 var(--space-1);
}

.role-admin {
  background: var(--surface-muted);
  color: var(--ink-secondary);
}

.role-teacher {
  background: var(--surface-muted);
  color: var(--ink-secondary);
}

.role-student {
  background: var(--surface-muted);
  color: var(--ink-secondary);
}

.user-bio {
  font-size: var(--text-caption);
  color: var(--ink-secondary);
  line-height: var(--leading-body);
  margin-bottom: var(--space-1);
  padding: 0 var(--space-1);
}

.user-stats-mini {
  justify-content: space-around;
  padding-top: var(--space-1);
  border-top: var(--stroke) solid var(--line);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
}

.stat-mini-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.stat-mini-value {
  font-size: var(--text-body);
  font-weight: var(--weight-strong);
  color: var(--ink);
}

.stat-mini-label {
  font-size: var(--text-caption);
  color: var(--ink-muted);
}

/* 左侧菜单 */
.sidebar-menu {
  background: var(--surface);
  overflow: hidden;
  border-radius: var(--radius-panel);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  cursor: pointer;
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
  width: 100%;
  box-sizing: border-box;
  border: none;
  border-left: var(--focus-width) solid transparent;
  background: transparent;
  text-align: left;
  color: var(--ink);
  font-family: inherit;
}

.menu-item:hover {
  background: var(--surface-muted);
}

.menu-item.active {
  background: var(--action-soft);
  border-left-color: var(--action);
  color: var(--action);
  font-weight: var(--weight-strong);
}

.menu-icon {
  font-size: var(--text-body);
  width: var(--icon-size);
  text-align: center;
}

.menu-label {
  flex: 1;
  color: inherit;
  font-size: var(--text-body);
}

.menu-count {
  font-size: var(--text-caption);
  color: var(--ink-muted);
  background: var(--surface-muted);
  padding: 0 var(--space-1);
  border-radius: var(--radius-pill);
}

/* 右侧内容区 */
.profile-main {
  background: var(--surface);
  min-width: 0;
  min-height: 520px;
  border-radius: var(--radius-panel);
}

.content-header {
  border-bottom: var(--stroke) solid var(--line);
  padding: var(--space-3);
}

.content-title {
  font-weight: var(--weight-strong);
  color: var(--ink);
  margin: 0;
  font-size: var(--text-page);
  line-height: var(--leading-tight);
}

.tab-content {
  padding: var(--space-3);
}

/* 统计概览 */
.stats-overview {
  display: grid;
  margin-bottom: var(--space-2);
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
}

.overview-card {
  padding: var(--space-2);
  text-align: center;
  background: var(--surface-muted);
  border-radius: var(--radius-control);
}

.overview-value {
  font-weight: var(--weight-strong);
  margin-bottom: var(--space-1);
  font-size: var(--text-section);
  color: var(--ink);
}

.overview-label {
  font-size: var(--text-caption);
  color: var(--ink-secondary);
}

/* 评级卡片 */
.rank-card {
  background: var(--surface-muted);
}

.overview-rank {
  font-weight: var(--weight-strong);
  margin-bottom: var(--space-1);
  letter-spacing: normal;
  font-size: var(--text-section);
  color: var(--ink);
}

/* 列表卡片 */
.list-grid {
  display: grid;
  gap: var(--space-1);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
}

.list-card {
  border: var(--stroke) solid var(--line);
  cursor: pointer;
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
  border-radius: var(--radius-control);
  background: var(--surface);
  padding: var(--space-2);
}

.list-card:hover {
  border-color: var(--action);
  box-shadow: none;
}

.card-badge {
  display: inline-block;
  padding: var(--space-1) var(--space-1);
  background: var(--surface-muted);
  color: var(--ink-secondary);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  margin-bottom: var(--space-1);
}

.card-title {
  font-weight: var(--weight-strong);
  color: var(--ink);
  margin-bottom: var(--space-1);
  font-size: var(--text-card);
  line-height: var(--leading-tight);
}

.card-summary {
  color: var(--ink-secondary);
  line-height: var(--leading-body);
  margin-bottom: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  font-size: var(--text-body);
}

.card-meta {
  font-size: var(--text-caption);
  color: var(--ink-muted);
}

/* 题目卡片 */
.challenges-grid {
  display: grid;
  gap: var(--space-2);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
}

.challenge-card {
  border: var(--stroke) solid var(--line);
  cursor: pointer;
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
  border-radius: var(--radius-control);
  background: var(--surface);
  padding: var(--space-2);
}

.challenge-card:hover {
  border-color: var(--action);
  box-shadow: none;
}

.challenge-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-1);
}

.challenge-status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-1);
  background: var(--positive-soft);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
}

.status-icon {
  color: var(--positive);
  font-size: var(--text-caption);
}

.status-text {
  color: var(--positive);
  font-weight: var(--weight-medium);
}

.challenge-score {
  font-size: var(--text-body);
  font-weight: var(--weight-strong);
  color: var(--ink);
}

.challenge-card-title {
  font-weight: var(--weight-strong);
  color: var(--ink);
  margin-bottom: var(--space-1);
  font-size: var(--text-card);
  line-height: var(--leading-tight);
}

.challenge-card-desc {
  color: var(--ink-secondary);
  line-height: var(--leading-body);
  margin-bottom: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: calc(var(--text-body) * var(--leading-body) * 2);
  font-size: var(--text-body);
}

.challenge-card-footer {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  flex-wrap: wrap;
  padding-top: var(--space-1);
  border-top: var(--stroke) solid var(--line);
}

.card-tag {
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  background: var(--surface-muted);
  color: var(--ink-secondary);
}

.card-difficulty {
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
}

.card-time {
  margin-left: auto;
  color: var(--ink-muted);
  font-size: var(--text-caption);
}

.diff-easy {
  background: var(--positive-soft);
  color: var(--positive);
}

.diff-medium {
  background: var(--warning-soft);
  color: var(--warning);
}

.diff-hard {
  background: var(--negative-soft);
  color: var(--negative);
}

.diff-expert {
  background: var(--surface-muted);
  color: var(--ink-secondary);
}

/* 学习路径 */
.paths-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.path-item {
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  padding: var(--space-2);
}

.path-header {
  margin-bottom: var(--space-1);
}

.path-title {
  font-weight: var(--weight-strong);
  color: var(--ink);
  margin-bottom: var(--space-1);
  font-size: var(--text-card);
  line-height: var(--leading-tight);
}

.path-progress {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--surface-muted);
  overflow: hidden;
  border-radius: var(--radius-pill);
}

.progress-fill {
  height: 100%;
  transition: width var(--motion-normal) var(--motion-ease);
  background: var(--action);
}

.progress-text {
  font-size: var(--text-caption);
  font-weight: var(--weight-strong);
  min-width: 4ch;
  text-align: right;
  color: var(--ink-secondary);
}

.path-meta {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-caption);
  color: var(--ink-secondary);
  flex-wrap: wrap;
}

.path-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-top: var(--space-1);
  padding-top: var(--space-1);
  border-top: var(--stroke) solid var(--line);
}

.completed-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-1);
  background: var(--positive-soft);
  color: var(--positive);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  font-weight: var(--weight-medium);
}

.btn-sm {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-caption);
}

/* 提交记录 */
.submissions-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.submission-item {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-2);
  border-radius: var(--radius-control);
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
  background: var(--negative-soft);
  border-left: var(--stroke) solid var(--negative);
}

.submission-item.correct {
  background: var(--positive-soft);
  border-left-color: var(--positive);
}

.submission-icon {
  width: var(--space-4);
  height: var(--space-4);
  border-radius: var(--radius-pill);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-caption);
  flex-shrink: 0;
}

.submission-item.correct .submission-icon {
  background: var(--positive);
  color: var(--on-action);
}

.submission-item:not(.correct) .submission-icon {
  background: var(--negative);
  color: var(--on-action);
}

.submission-content {
  flex: 1;
  min-width: 0;
}

.submission-title {
  font-weight: var(--weight-strong);
  color: var(--ink);
  margin-bottom: var(--space-1);
  font-size: var(--text-card);
  line-height: var(--leading-tight);
}

.submission-meta {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
  flex-wrap: wrap;
}

.submission-flag {
  font-family: monospace;
  font-size: var(--text-caption);
  color: var(--ink-secondary);
  background: var(--surface);
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  word-break: break-all;
}

/* 学习画像 */
.persona-section {
  display: grid;
  gap: var(--space-3);
}

.onboarding-cta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  border-color: var(--line);
  background: var(--surface);
}

.onboarding-cta p {
  margin: var(--space-1) 0 0;
  color: var(--ink-secondary);
  line-height: var(--leading-body);
}

.persona-hero-card,
.persona-card {
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.persona-hero-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-2);
  align-items: center;
  background: var(--surface-muted);
  border-radius: var(--radius-panel);
  padding: var(--space-3);
}

.persona-title {
  margin: 0 0 var(--space-1);
  color: var(--ink);
  font-weight: var(--weight-strong);
  font-size: var(--text-section);
  line-height: var(--leading-tight);
}

.persona-summary {
  max-width: 70ch;
  margin: 0;
  color: var(--ink-secondary);
  line-height: var(--leading-body);
  font-size: var(--text-body);
}

.persona-hero-side {
  display: grid;
  justify-items: center;
  gap: var(--space-1);
}

.confidence-ring {
  width: 96px;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  align-content: center;
  gap: var(--space-1);
  border-radius: var(--radius-pill);
  background: radial-gradient(circle at center, var(--surface) 56%, transparent 57%),
    conic-gradient(var(--action) calc(var(--confidence, 0) * 1%), var(--line) 0);
  box-shadow: none;
}

.confidence-ring strong {
  font-size: var(--text-card);
  line-height: var(--leading-tight);
  color: var(--ink);
}

.confidence-ring span,
.persona-status {
  color: var(--ink-secondary);
  font-size: var(--text-caption);
}

.persona-status {
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  font-weight: var(--weight-strong);
  color: var(--ink-secondary);
  background: var(--surface);
}

.persona-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.persona-card {
  padding: var(--space-3) 0;
  border-bottom: var(--stroke) solid var(--line);
}

.stage-compare-card {
  grid-column: 1 / -1;
}

.stage-compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: var(--stroke) solid var(--line);
}

.stage-column {
  min-width: 0;
  padding: var(--space-2);
}

.stage-column + .stage-column {
  border-left: var(--stroke) solid var(--line);
}

.stage-column-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.stage-column-head strong {
  color: var(--ink);
  font-size: var(--text-body);
}

.stage-column-head span {
  color: var(--ink-muted);
  font-size: var(--text-caption);
}

.learned-stage .stage-column-head strong {
  color: var(--ink);
}

.initial-stage .direction-row {
  background: var(--surface-muted);
}

.learned-stage .direction-row {
  background: var(--surface-muted);
}

.initial-stage .level-bar i,
.initial-stage .direction-row.weak .level-bar i {
  background: var(--action);
}

.learned-stage .level-bar i,
.learned-stage .direction-row.weak .level-bar i {
  background: var(--action);
}

.evidence-dashboard {
  padding: var(--space-3) 0;
}

.evidence-dashboard-head {
  padding-bottom: var(--space-2);
  border-bottom: var(--stroke) solid var(--line);
}

.evidence-dashboard-head p {
  margin: var(--space-1) 0 0;
  color: var(--ink-secondary);
  font-size: var(--text-caption);
  line-height: var(--leading-body);
}

.persona-card-head .traceable-badge {
  flex: none;
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  font-weight: var(--weight-strong);
  background: var(--surface-muted);
  color: var(--ink-secondary);
}

.evidence-phase-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

.evidence-phase {
  min-width: 0;
  padding: var(--space-2);
  border: none;
  border-radius: var(--radius-control);
}

.initial-evidence-phase {
  border-color: var(--line);
  background: var(--surface-muted);
}

.learned-evidence-phase {
  border-color: var(--line);
  background: var(--surface-muted);
}

.evidence-phase-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  align-items: flex-start;
}

.evidence-phase-head > div:first-child strong,
.evidence-phase-head > div:first-child span,
.evidence-confidence b,
.evidence-confidence span {
  display: block;
}

.evidence-phase-head > div:first-child strong {
  font-size: var(--text-body);
  color: var(--ink);
}

.learned-evidence-phase .evidence-phase-head > div:first-child strong {
  color: var(--ink);
}

.evidence-phase-head > div:first-child span,
.evidence-confidence span {
  margin-top: var(--space-1);
  color: var(--ink-secondary);
  font-size: var(--text-caption);
}

.evidence-confidence {
  text-align: right;
}

.evidence-confidence b {
  font-size: var(--text-section);
  color: var(--ink);
}

.learned-evidence-phase .evidence-confidence b {
  color: var(--ink);
}

.evidence-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-1);
  margin: var(--space-2) 0;
}

.evidence-metrics strong,
.evidence-metrics span {
  display: block;
}

.evidence-metrics strong {
  font-size: var(--text-card);
  color: var(--ink);
}

.learned-evidence-phase .evidence-metrics strong {
  color: var(--ink);
}

.evidence-metrics span {
  margin-top: var(--space-1);
  color: var(--ink-secondary);
  font-size: var(--text-caption);
  line-height: var(--leading-tight);
}

.evidence-source-list {
  display: grid;
  gap: var(--space-1);
}

.evidence-source-row {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  border-radius: var(--radius-control);
  border: none;
  background: transparent;
  padding: var(--space-1) 0;
  min-height: var(--control-height);
}

.evidence-source-row i {
  border-radius: var(--radius-pill);
  width: var(--space-1);
  height: var(--space-1);
  flex: 0 0 var(--space-1);
  background: var(--ink-muted);
}

.learned-evidence-phase .evidence-source-row i {
  background: var(--ink-muted);
}

.evidence-source-row strong,
.evidence-source-row span {
  display: block;
}

.evidence-source-row strong {
  color: var(--ink);
  font-size: var(--text-caption);
}

.evidence-source-row span {
  margin-top: var(--space-1);
  color: var(--ink-secondary);
  font-size: var(--text-caption);
  line-height: var(--leading-tight);
}

.evidence-chain-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding-bottom: var(--space-1);
  border-bottom: var(--stroke) solid var(--line);
}

.evidence-chain-head strong {
  font-size: var(--text-caption);
}

.evidence-chain-head span {
  color: var(--ink-secondary);
  font-size: var(--text-caption);
}

.evidence-chain {
  display: grid;
  align-items: center;
  padding: var(--space-2) 0;
  gap: var(--space-1);
  grid-template-columns: minmax(0, 1fr) var(--icon-size) minmax(0, 1fr) var(--icon-size) minmax(0, 1fr) var(--icon-size) minmax(0, 1.25fr);
}

.evidence-chain > i {
  color: var(--ink-muted);
  font-size: var(--text-card);
  font-style: normal;
  text-align: center;
}

.evidence-chain-node {
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  border: none;
  background: var(--surface-muted);
  min-height: var(--space-8);
}

.evidence-chain-node strong,
.evidence-chain-node span {
  display: block;
}

.evidence-chain-node strong {
  font-size: var(--text-caption);
}

.evidence-chain-node span {
  margin-top: var(--space-1);
  color: var(--ink-secondary);
  font-size: var(--text-caption);
}
.initial-node strong {
  color: var(--ink); }
.learned-node strong {
  color: var(--ink); }

.evidence-status-strip {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  background: var(--surface-muted);
  border: none;
  flex-wrap: wrap;
}

.evidence-status-strip span {
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  font-weight: var(--weight-strong);
  background: var(--surface);
  color: var(--ink-secondary);
}

.evidence-status-strip em {
  margin-left: auto;
  color: var(--ink-secondary);
  font-size: var(--text-caption);
  font-style: normal;
}

.advantage-compare-card .direction-row {
  box-sizing: border-box;
  min-height: 96px;
}

.priority-compare-card .direction-row {
  box-sizing: border-box;
  min-height: 96px;
}

.persona-card-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-1);
  align-items: center;
  margin-bottom: var(--space-1);
}

.persona-card-title {
  margin: 0;
  color: var(--ink);
  font-weight: var(--weight-strong);
  font-size: var(--text-card);
  line-height: var(--leading-tight);
}

.persona-card-head span {
  color: var(--ink-muted);
  font-size: var(--text-caption);
}

.direction-list {
  display: grid;
  gap: var(--space-1);
}

.direction-row {
  display: grid;
  gap: var(--space-1);
  align-items: center;
  padding: var(--space-1);
  border-radius: var(--radius-control);
  background: var(--surface-muted);
  grid-template-columns: minmax(0, 1fr) 92px minmax(4ch, auto);
}

.direction-row-main {
  min-width: 0;
}

.direction-row-main strong {
  display: block;
  color: var(--ink);
  font-size: var(--text-caption);
  margin-bottom: var(--space-1);
}

.direction-row-main span {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--ink-secondary);
  font-size: var(--text-caption);
  line-height: var(--leading-body);
}

.level-bar {
  height: 6px;
  overflow: hidden;
  border-radius: var(--radius-pill);
  background: var(--line);
}

.level-bar i {
  display: block;
  height: 100%;
  border-radius: var(--radius-control);
  background: var(--action);
}

.direction-row.weak .level-bar i {
  background: var(--action);
}

.direction-row em {
  color: var(--ink-secondary);
  font-size: var(--text-caption);
  font-style: normal;
  font-weight: var(--weight-strong);
  text-align: right;
}

.quiet-empty {
  padding: var(--space-1);
  color: var(--ink-muted);
  font-size: var(--text-caption);
  text-align: center;
}

.dynamic-empty-row {
  min-height: 96px;
}

.dynamic-empty-row .direction-row-main strong {
  font-size: var(--text-caption);
  margin-bottom: var(--space-1);
}

.dynamic-empty-row .direction-row-main span {
  font-size: var(--text-caption);
  line-height: var(--leading-body);
}

.advice-layout {
  display: grid;
  grid-template-columns: 1fr 1.1fr 1.1fr;
  gap: var(--space-1);
}

.advice-block {
  min-width: 0;
  padding: var(--space-1);
  border-radius: var(--radius-control);
  background: var(--surface-muted);
}

.advice-block h4 {
  margin: 0 0 var(--space-1);
  color: var(--ink);
  font-size: var(--text-body);
}

.advice-block p,
.advice-block li {
  color: var(--ink-secondary);
  line-height: var(--leading-body);
  font-size: var(--text-body);
}

.advice-block p {
  margin: 0;
}

.advice-block ul {
  margin: 0;
  padding-left: var(--space-2);
}

.agent-chip-row,
.rating-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.agent-chip,
.rating-chip {
  display: inline-flex;
  align-items: center;
  padding: 0 var(--space-1);
  border-radius: var(--radius-control);
  font-size: var(--text-caption);
  font-weight: var(--weight-strong);
  height: auto;
  min-height: var(--space-4);
}

.agent-chip {
  color: var(--agent-accent);
  background: var(--agent-soft);
}

@media (max-width: 820px) {
  .stage-compare-grid {
    grid-template-columns: 1fr;
  }

  .stage-column + .stage-column {
    border-left: 0;
    border-top: var(--stroke) solid var(--line);
    margin-top: var(--space-1);
  }

  .direction-row {
    grid-template-columns: minmax(0, 1fr) 72px 44px;
  }

  .evidence-phase-grid,
  .evidence-chain {
    grid-template-columns: 1fr;
  }

  .evidence-chain > i {
    transform: rotate(90deg);
  }

  .evidence-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .evidence-status-strip {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .evidence-status-strip em {
    width: 100%;
    margin-left: 0;
  }
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: var(--space-7) var(--space-2);
  color: var(--ink-muted);
}

.empty-icon {
  font-size: var(--text-page);
  margin-bottom: var(--space-1);
}

.empty-text {
  font-size: var(--text-caption);
  margin-bottom: var(--space-1);
}

.btn-link {
  color: var(--action);
  background: none;
  border: none;
  font-size: var(--text-caption);
  cursor: pointer;
  padding: 0;
}

.btn-link:hover {
  text-decoration: underline;
}

/* 编辑表单 */
.edit-form {
  max-width: var(--form-width);
}

.form-group {
  margin-bottom: var(--space-2);
}

.form-label {
  display: block;
  margin-bottom: var(--space-1);
  font-size: var(--text-caption);
  font-weight: var(--weight-medium);
  color: var(--ink);
}

.input {
  width: 100%;
  padding: var(--space-1) var(--space-1);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-control);
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
  box-sizing: border-box;
  min-height: var(--control-height);
  font-family: inherit;
  font-size: var(--text-body);
  background: var(--surface);
  color: var(--ink);
}

.input:focus {
  outline-offset:var(--focus-offset);
  border-color: var(--action);
  box-shadow: none;
}

.input:disabled {
  background: var(--surface-muted);
  cursor: not-allowed;
}

.textarea {
  resize: vertical;
  min-height: var(--space-10);
}

.form-hint {
  display: block;
  margin-top: var(--space-1);
  font-size: var(--text-caption);
  color: var(--ink-muted);
}

.btn {
  padding: var(--space-1) var(--space-2);
  border: none;
  border-radius: var(--radius-control);
  font-weight: var(--weight-medium);
  cursor: pointer;
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
  min-height: var(--control-height);
  font-family: inherit;
  font-size: var(--text-body);
}

.btn-primary {
  background: var(--action);
  color: var(--on-action);
}

.btn-primary:hover {
  background: var(--action-hover);
}

.btn-primary:disabled {
  cursor: not-allowed;
  background: var(--disabled);
  color: var(--disabled-ink);
}

@media (max-width: 768px) {
  .profile-container {
    grid-template-columns: 1fr;
  }

  .profile-sidebar {
    position: static;
  }

  .stats-overview {
    grid-template-columns: 1fr;
  }

  .persona-hero-card,
  .persona-grid,
  .advice-layout {
    grid-template-columns: 1fr;
  }

  .persona-hero-side {
    justify-items: start;
  }

  .direction-row {
    grid-template-columns: 1fr;
  }

  .direction-row em {
    text-align: left;
  }

  .list-grid {
    grid-template-columns: 1fr;
  }
}

.btn-primary:active:not(:disabled) {
  background: var(--action-pressed);
}

.recent-subs-section { margin-top: var(--space-3); }

.section-subtitle { font-size: var(--text-card); font-weight: var(--weight-strong); margin: 0 0 var(--space-2); }

.recent-subs-list { display: grid; gap: var(--space-1); }

.recent-sub-item { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); padding: var(--space-1) 0; border-bottom: var(--stroke) solid var(--line); }

.sub-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }

.sub-time { color: var(--ink-muted); font-size: var(--text-caption); }

.sub-badge-correct, .sub-badge-wrong { padding: 0 var(--space-1); border-radius: var(--radius-control); }

.sub-badge-correct { color: var(--positive); background: var(--positive-soft); }

.sub-badge-wrong { color: var(--negative); background: var(--negative-soft); }

.profile-page :is(button, input, textarea, a):focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }

.profile-page :is(input, textarea)::placeholder { color: var(--ink-muted); }

.profile-page input:disabled { background: var(--disabled); color: var(--disabled-ink); }

.profile-page :deep(.arco-spin) { display: block; }

@media (max-width: 768px) { .content-header, .tab-content { padding: var(--space-2); } .persona-card-head { flex-wrap: wrap; } .direction-row { grid-template-columns: minmax(0, 1fr); } .evidence-phase-grid, .evidence-chain { grid-template-columns: 1fr; } }
</style>
