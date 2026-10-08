"""
学习编排器 — 协调多智能体完成自适应学习流程

依赖：StudentProfile, UserKnowledgeState, LearningPersona (已在 student_profiles/learning_paths 中定义)
"""

import logging
import random
from typing import Dict, List, Optional

from .service import get_multi_agent_service

logger = logging.getLogger(__name__)


class LearningOrchestrator:
    """学习编排器，聚合学生数据并调度学习智能体"""

    RECOMMENDATION_LIMIT = 3

    def __init__(self):
        self._service = None

    @property
    def service(self):
        if self._service is None:
            self._service = get_multi_agent_service()
        return self._service

    # ---- 数据聚合辅助 ----

    def _get_student_profile(self, student_id: int):
        """获取或创建用户画像"""
        from student_profiles.models import StudentProfile

        profile, _ = StudentProfile.objects.get_or_create(
            user_id=student_id,
            defaults={'learning_goals': '', 'self_assessed_skills': {}},
        )
        return profile

    def _get_knowledge_states(self, student_id: int) -> List[Dict]:
        """获取用户知识状态摘要"""
        from learning_paths.models import UserKnowledgeState

        qs = UserKnowledgeState.objects.filter(
            user_id=student_id
        ).select_related('concept').order_by('-mastery_level')

        return [
            {
                'concept_name': ks.concept.name,
                'concept_type': ks.concept.concept_type,
                'mastery_level': round(ks.mastery_level, 2),
                'recall_probability': round(ks.recall_probability, 2),
                'lab_success_rate': (
                    round(ks.lab_successes / max(ks.lab_attempts, 1), 2)
                ),
                'struggle_indicators': ks.struggle_indicators,
            }
            for ks in qs
        ]

    def _get_learning_preferences(self, student_id: int) -> Optional[Dict]:
        """获取学习偏好"""
        try:
            from student_profiles.models import StudentProfile

            profile = StudentProfile.objects.filter(
                user_id=student_id
            ).select_related('preference').first()
            if profile and hasattr(profile, 'preference'):
                pref = profile.preference
                return {
                    'pace': pref.preferred_pace,
                    'modality': pref.preferred_modality,
                    'daily_hours': pref.daily_study_hours,
                    'difficulty_bias': pref.difficulty_bias,
                }
        except Exception as exc:
            logger.warning(
                'learning_orchestrator_preference_lookup_failed',
                extra={
                    'event': 'learning_orchestrator_preference_lookup_failed',
                    'error_type': type(exc).__name__,
                    'student_id': student_id,
                },
            )
        return None

    def _get_teaching_plan_snapshot(self, student_id: int) -> Dict:
        """Get a teaching-plan snapshot built from filtered valid admin scores."""
        try:
            from users.models import CTFUser
            from learning_analytics.views import generate_teaching_plan

            student = CTFUser.objects.get(id=student_id)
            plan = generate_teaching_plan(student)
            return {
                'title': plan.title,
                'summary': plan.summary,
                'plan_items': plan.plan_items,
                'validity_label': plan.validity_label,
                'data_age_days': plan.data_age_days,
                'source_score_ids': plan.source_score_ids,
                'input_snapshot': plan.input_snapshot,
            }
        except Exception as exc:
            logger.warning("Failed to build teaching plan snapshot for student_id=%s: %s", student_id, exc)
            return {}

    # ---- 核心编排方法 ----

    def _build_student_snapshot(self, student_id: int) -> Dict:
        """同步构建学生数据快照，供规则引擎使用"""
        profile = self._get_student_profile(student_id)
        knowledge_states = self._get_knowledge_states(student_id)
        preferences = self._get_learning_preferences(student_id)
        teaching_plan = self._get_teaching_plan_snapshot(student_id)

        skills = profile.self_assessed_skills or {}
        # 计算各方向平均分
        direction_scores = {}
        direction_map = {'web': 'Web安全', 'crypto': '密码学', 'pwn': '二进制安全',
                         'reverse': '逆向工程', 'forensics': '数字取证', 'misc': '综合杂项'}
        for key, label in direction_map.items():
            val = skills.get(key, None)
            direction_scores[key] = {'label': label, 'score': val if val is not None else -1}

        # 知识状态汇总
        ks_summary = {
            'total': len(knowledge_states),
            'strong': [k for k in knowledge_states if k['mastery_level'] >= 0.7],
            'weak': [k for k in knowledge_states if k['mastery_level'] < 0.4],
            'avg_mastery': sum(k['mastery_level'] for k in knowledge_states) / max(len(knowledge_states), 1),
        }

        return {
            'student_id': student_id,
            'learning_goals': profile.learning_goals or '',
            'onboarding_completed': profile.onboarding_completed,
            'direction_scores': direction_scores,
            'knowledge_summary': ks_summary,
            'preferences': preferences or {},
            'teaching_plan': teaching_plan,
        }

    def _get_rule_recommendations(self, snap: Dict) -> List[Dict]:
        """基于规则的推荐引擎 — 20+ 条推荐规则"""
        recs = []
        dirs = snap['direction_scores']
        ks = snap['knowledge_summary']
        goals = snap['learning_goals']
        onboarded = snap['onboarding_completed']
        teaching_plan = snap.get('teaching_plan') or {}

        if teaching_plan:
            recs.append({
                'type': 'teaching_plan',
                'title': teaching_plan.get('title') or '个性化教学方案',
                'reason': f"{teaching_plan.get('validity_label') or '基于用户自评生成'}：{teaching_plan.get('summary', '')}",
                'action_link': '/dashboard',
                'priority': 0,
                'estimated_time': '按阶段执行',
                'expected_gain': '使用最新有效评分聚焦短板训练',
                'source_score_ids': teaching_plan.get('source_score_ids', []),
            })

        scored = [(k, v) for k, v in dirs.items() if v['score'] >= 0]
        scored.sort(key=lambda x: x[1]['score'])
        weak_dirs = [s for s in scored if s[1]['score'] <= 2]
        strong_dirs = [s for s in scored if s[1]['score'] >= 4]
        mid_dirs = [s for s in scored if 3 <= s[1]['score'] <= 4]
        all_zero = all(v['score'] <= 0 for v in dirs.values())

        # === 新手阶段 ===
        if not onboarded or all_zero:
            recs.append({
                'type': 'onboarding', 'title': '🎯 完成学习引导，开启学习之旅',
                'reason': '你尚未完成学习引导。引导流程只需3分钟，完成后系统将根据你的CTF各方向基础水平，为你生成专属的个性化学习路径和每日学习计划。',
                'action_link': '/profile/setup', 'priority': 1,
                'estimated_time': '3分钟', 'expected_gain': '获取专属学习路径'
            })
            recs.append({
                'type': 'onboarding', 'title': '📋 了解CTF六大方向',
                'reason': 'CTF竞赛涵盖Web安全、密码学、二进制安全、逆向工程、数字取证和综合杂项六大方向。作为新手，建议先了解每个方向的基本概念和典型题型，找到自己感兴趣的方向开始学习。',
                'action_link': '/learning-paths', 'priority': 1,
                'estimated_time': '30分钟', 'expected_gain': '建立CTF全局认知地图'
            })
            recs.append({
                'type': 'weakness_fix', 'title': '🌐 从Web安全开始你的CTF之旅',
                'reason': 'Web安全是CTF中入门门槛最低、知识点最直观的方向。从HTTP协议和浏览器工作原理开始，逐步学习前端漏洞如XSS、CSRF等。这是大多数CTF选手的起点。',
                'action_link': '/learning-paths', 'priority': 2,
                'estimated_time': '2-3周', 'expected_gain': '掌握Web安全核心概念和5种常见漏洞类型'
            })
            recs.append({
                'type': 'weakness_fix', 'title': '🧩 通过Misc题目培养CTF思维',
                'reason': 'Misc（综合杂项）题目涉及编码转换、隐写分析、流量分析、取证等多种类型，不需要太深的技术背景就能上手，是培养CTF解题思维的最佳入门方向。',
                'action_link': '/challenges', 'priority': 2,
                'estimated_time': '1-2周', 'expected_gain': '熟悉CTF解题流程，培养分析思维'
            })
            recs.append({
                'type': 'next_step', 'title': '📚 加入学习路径，系统化学习',
                'reason': '随性刷题效率低下，建议加入平台预设的学习路径。学习路径按难度递进排列，每个模块包含理论讲解和实战题目，帮助你从零基础逐步成长为CTF选手。',
                'action_link': '/learning-paths', 'priority': 3,
                'estimated_time': '持续', 'expected_gain': '系统化知识体系，避免遗漏关键知识点'
            })

        # === 各方向针对推荐 ===
        direction_details = {
            'web': {
                'low': {'title': '🌐 Web安全：从HTTP到SQL注入', 'reason': '你在Web安全方向的自评较低。Web安全是CTF最大类别，建议从HTTP协议、Cookie/Session机制开始，再到SQL注入、文件上传、命令注入等经典漏洞，每个漏洞类型配合至少5道实操题目巩固理解。', 'gain': '掌握HTTP协议基础和6种常见Web漏洞的检测与利用'},
                'mid': {'title': '🌐 Web安全进阶：绕过WAF与逻辑漏洞', 'reason': '你的Web安全已有一定基础，是时候深入WAF绕过技术、SSRF攻击链、反序列化漏洞等进阶主题了。这些是高水平CTF竞赛中的核心考点。', 'gain': '掌握WAF绕过技巧和3种进阶Web漏洞'},
                'high': {'title': '🌐 Web安全专家：漏洞挖掘与研究', 'reason': '你的Web安全已达较高水平，建议挑战真实世界的Web安全研究，如框架级漏洞分析、协议层攻击、浏览器安全等前沿方向。', 'gain': '具备独立进行Web安全研究的能力'},
            },
            'crypto': {
                'low': {'title': '🔐 密码学入门：古典密码与现代编码', 'reason': '密码学是CTF中逻辑性最强的方向。入门路线：Base家族编码→古典密码（凯撒/维吉尼亚/栅栏）→对称加密（AES/DES）→非对称加密（RSA基础）。每个阶段配合编程实现加深理解。', 'gain': '理解5种编码方式和4种加密算法原理'},
                'mid': {'title': '🔐 密码学进阶：RSA攻击与格密码', 'reason': '你在密码学方向已有基础，建议深入学习RSA的多种攻击方法（共模攻击、维纳攻击、Coppersmith等）和格密码初步，这些都是高水平CTF密码题的常见考点。', 'gain': '掌握RSA的6种攻击方法和格密码基础'},
                'high': {'title': '🔐 密码学专家：椭圆曲线与后量子密码', 'reason': '你的密码学能力出众，可以挑战椭圆曲线密码、格基密码分析、侧信道攻击等前沿方向，为CTF决赛和学术研究做准备。', 'gain': '掌握前沿密码学知识体系'},
            },
            'pwn': {
                'low': {'title': '💥 二进制安全启蒙：从汇编到栈溢出', 'reason': '二进制安全（Pwn）是CTF中最具挑战性的方向。入门路线：x86/x64汇编基础→栈帧结构与调用约定→栈溢出原理→ret2text/ret2shellcode→ret2libc→ROP基础。建议使用pwntools库进行实操练习。', 'gain': '理解汇编基础并能编写简单栈溢出exploit'},
                'mid': {'title': '💥 二进制进阶：堆利用与格式化字符串', 'reason': '你在二进制方向已有基础，可以挑战堆内存管理机制（fastbin/tcache）、格式化字符串漏洞利用、FSOP等进阶技术。这些是现代二进制漏洞利用的核心技能。', 'gain': '掌握堆利用基础和3种进阶漏洞利用技术'},
                'high': {'title': '💥 二进制专家：内核漏洞与浏览器利用', 'reason': '你的二进制安全已达高级水平，建议挑战Linux内核漏洞利用、浏览器沙箱逃逸、虚拟机逃逸等前沿二进制安全方向。', 'gain': '具备高级二进制安全研究能力'},
            },
            'reverse': {
                'low': {'title': '🔍 逆向工程入门：静态分析与动态调试', 'reason': '逆向工程需要耐心和对程序运行机制的理解。入门路线：ELF/PE文件格式→IDA Pro/Ghidra静态分析→x64dbg/gdb动态调试→常见算法识别（base64/AES/RC4）→简单CrackMe实战。', 'gain': '熟练使用IDA和x64dbg，能逆向简单程序'},
                'mid': {'title': '🔍 逆向进阶：反混淆与自动化分析', 'reason': '你在逆向工程方向已有基础，建议深入学习代码混淆技术识别（ollvm/flattening）、符号执行（angr框架）、二进制diffing等进阶主题。', 'gain': '掌握反混淆技术和自动化逆向分析能力'},
                'high': {'title': '🔍 逆向专家：固件分析与APT样本研究', 'reason': '你已具备扎实的逆向功底，可以挑战IoT固件逆向、APT恶意样本深度分析、虚拟化保护绕过等高端方向。', 'gain': '具备工业级逆向分析能力'},
            },
            'forensics': {
                'low': {'title': '📁 数字取证入门：文件分析与数据恢复', 'reason': '数字取证考察从各种数据载体中提取隐藏信息的能力。入门路线：文件格式识别（file/magic bytes）→图片隐写分析（LSB/exif/图层）→压缩包分析→内存镜像取证（volatility基础）→流量包分析（Wireshark/tshark）。', 'gain': '掌握5种取证工具和常见隐写分析技术'},
                'mid': {'title': '📁 取证进阶：内存分析与APT溯源', 'reason': '你在取证方向已有基础，建议深入学习Windows/Linux内存取证、恶意文档分析、日志分析与攻击溯源、磁盘镜像深度恢复等进阶技术。', 'gain': '掌握内存取证和攻击溯源分析能力'},
                'high': {'title': '📁 取证专家：高级威胁狩猎与事件响应', 'reason': '你的取证能力已达高级水平，可以挑战APT威胁狩猎、网络流量深度分析、云环境取证、移动设备取证等前沿方向。', 'gain': '具备企业级数字取证和事件响应能力'},
            },
            'misc': {
                'low': {'title': '🧩 Misc入门：编码、隐写与协议分析', 'reason': 'Misc题目类型最丰富。入门路线：常见编码（Base/Morse/ASCII/URL）→图片隐写→压缩包加密→流量分析→协议逆向→脚本编写。每题都在锻炼不同的知识点，是培养CTF综合能力的好方式。', 'gain': '熟悉8种常见编码和4种隐写分析技术'},
                'mid': {'title': '🧩 Misc进阶：自动化分析与深度隐写', 'reason': '你在Misc方向已有基础，建议深入学习自动化脚本编写（Python提取/解密/爆破）、高级隐写技术（频域隐写/DCT）、协议逆向与fuzzing等。', 'gain': '具备编写自动化分析脚本的能力'},
                'high': {'title': '🧩 Misc专家：跨领域综合挑战', 'reason': '你的Misc能力已达高级水平，可以挑战跨领域综合题目，如结合逆向+密码的混合题型、真实场景应急响应模拟、自定义协议分析等。', 'gain': '具备解决复杂跨领域综合题的能力'},
            },
        }

        for key, details in direction_details.items():
            s = dirs[key]['score']
            if s < 0:
                continue
            if s <= 1:
                recs.append({
                    'type': 'weakness_fix', 'title': details['low']['title'],
                    'reason': details['low']['reason'],
                    'action_link': '/learning-paths', 'priority': 2,
                    'estimated_time': '3-5周', 'expected_gain': details['low']['gain']
                })
            elif s <= 2:
                recs.append({
                    'type': 'weakness_fix', 'title': details['low']['title'],
                    'reason': details['low']['reason'],
                    'action_link': '/learning-paths', 'priority': 2,
                    'estimated_time': '2-4周', 'expected_gain': details['low']['gain']
                })
            elif s <= 3:
                recs.append({
                    'type': 'next_step', 'title': details['mid']['title'],
                    'reason': details['mid']['reason'],
                    'action_link': '/challenges', 'priority': 3,
                    'estimated_time': '3-6周', 'expected_gain': details['mid']['gain']
                })
            elif s <= 4:
                recs.append({
                    'type': 'next_step', 'title': details['mid']['title'],
                    'reason': details['mid']['reason'],
                    'action_link': '/challenges', 'priority': 3,
                    'estimated_time': '2-4周', 'expected_gain': details['mid']['gain']
                })
            else:
                recs.append({
                    'type': 'exploration', 'title': details['high']['title'],
                    'reason': details['high']['reason'],
                    'action_link': '/challenges', 'priority': 4,
                    'estimated_time': '持续', 'expected_gain': details['high']['gain']
                })

        # 知识概念推荐
        if ks['weak'] and len(ks['weak']) >= 2:
            concepts = [k['concept_name'] for k in ks['weak'][:3]]
            recs.append({
                'type': 'weakness_fix', 'title': f'🔧 重点突破：{concepts[0]}等{len(ks["weak"])}个薄弱概念',
                'reason': f'系统检测到你在「{", ".join(concepts)}」等概念的掌握度偏低。这些概念是后续学习的必要基础，建议每天安排30分钟专项练习，从概念理解到实操题目逐步攻克。',
                'action_link': '/learning-paths', 'priority': 2,
                'estimated_time': f'{len(ks["weak"]) * 3}天', 'expected_gain': f'补强{len(ks["weak"])}个薄弱概念，整体掌握度提升15%以上'
            })

        if ks['strong'] and len(ks['strong']) >= 2:
            names = [k['concept_name'] for k in ks['strong'][:3]]
            recs.append({
                'type': 'strength', 'title': f'⭐ 巩固优势：{names[0]}已达熟练水平',
                'reason': f'你对「{", ".join(names)}」的掌握度较高。建议挑战更高难度的综合题目，将已掌握的知识应用到复杂场景中，同时可以尝试为其他同学讲解这些概念，教学相长。',
                'action_link': '/challenges', 'priority': 4,
                'estimated_time': '1周', 'expected_gain': '将知识从"熟练"提升到"精通"，向更高水平迈进'
            })

        # 混合题型推荐
        if len(weak_dirs) >= 2 and len(strong_dirs) >= 1:
            w_names = [d[1]['label'] for d in weak_dirs[:2]]
            s_name = strong_dirs[0][1]['label']
            recs.append({
                'type': 'next_step', 'title': f'🔄 交叉训练：以{s_name}带动{w_names[0]}',
                'reason': f'你的{s_name}基础扎实，可以尝试做一些结合{s_name}和{w_names[0]}知识点的混合题型，利用强项带动弱项，这种交叉训练方式被证明能有效加速薄弱方向的提升。',
                'action_link': '/challenges', 'priority': 3,
                'estimated_time': '1-2周', 'expected_gain': f'在巩固{s_name}的同时提升{w_names[0]}'
            })

        # 刷题量推荐
        if ks['total'] >= 8:
            recs.append({
                'type': 'exploration', 'title': '🏆 挑战CTF竞赛真题',
                'reason': f'你已学习{ks["total"]}个知识概念，基础扎实。建议参加CTFtime.org上近期举办的公开赛，在真实竞赛环境中检验学习成果，积累实战经验。比赛过程中注意复盘错题和未解题。',
                'action_link': '/challenges', 'priority': 5,
                'estimated_time': '每次比赛4-48小时', 'expected_gain': '积累竞赛经验，发现知识盲区'
            })
        elif ks['total'] >= 3:
            recs.append({
                'type': 'next_step', 'title': '📝 增加刷题量，巩固知识体系',
                'reason': f'你已掌握{ks["total"]}个核心概念，建议每周至少完成5-10道CTF题目来巩固所学知识。推荐按"简单→中等→困难"的顺序刷题，避免挫败感，保持学习动力。',
                'action_link': '/challenges', 'priority': 3,
                'estimated_time': '每周3-5小时', 'expected_gain': '知识从"知道"变为"会用"'
            })

        # 学习目标匹配
        if goals:
            recs.append({
                'type': 'goal_aligned', 'title': '🎯 目标导向：你的学习地图',
                'reason': f'你的学习目标是「{goals[:60]}」。系统将持续跟踪你的进度，动态调整推荐内容。建议将大目标拆解为每周可执行的小目标，每完成一个里程碑就给自己一个小奖励，保持长期学习动力。',
                'action_link': '/profile', 'priority': 5,
                'estimated_time': '持续', 'expected_gain': '稳步向着目标前进'
            })

        recs.sort(key=lambda x: (x['priority'], x['type']))
        # 新手多给几条
        return recs[:8] if (not onboarded or all_zero) else recs[:6]

    def _pick_student_recommendations(self, recs: List[Dict], student_id: int) -> List[Dict]:
        if len(recs) <= self.RECOMMENDATION_LIMIT:
            return recs

        rng = random.Random(f'learning-dashboard:{student_id}')
        indexes = sorted(rng.sample(range(len(recs)), self.RECOMMENDATION_LIMIT))
        return [recs[i] for i in indexes]

    def _get_sequence_recommendations(self, student_id: int) -> List[Dict]:
        """Use knowledge tracking + sequential recommendation for next-step picks."""
        try:
            from users.models import CTFUser
            from learning_paths.sequence_recommender import KnowledgeSequenceRecommender

            user = CTFUser.objects.get(id=student_id)
            return KnowledgeSequenceRecommender(user).next_learning_recommendations(
                limit=self.RECOMMENDATION_LIMIT
            )
        except Exception as exc:
            logger.warning("Failed to build sequence recommendations for student_id=%s: %s", student_id, exc)
            return []

    def _merge_sequence_and_rule_recommendations(
        self,
        sequence_recs: List[Dict],
        rule_recs: List[Dict],
        student_id: int,
    ) -> List[Dict]:
        """Keep sequence-model next steps visible and fill remaining slots with rules."""
        if not sequence_recs:
            return self._pick_student_recommendations(rule_recs, student_id)

        selected = sequence_recs[:2]
        selected_titles = {item.get('title') for item in selected}
        rule_pool = [
            item for item in rule_recs
            if item.get('title') not in selected_titles
        ]
        slots = max(0, self.RECOMMENDATION_LIMIT - len(selected))
        selected.extend(self._pick_student_recommendations(rule_pool, student_id)[:slots])
        return selected[:self.RECOMMENDATION_LIMIT]

    def _get_rule_insights(self, snap: Dict, student_id: int) -> List[Dict]:
        """基于规则的洞察引擎 — 20+ 条洞察规则"""
        insights = []
        dirs = snap['direction_scores']
        ks = snap['knowledge_summary']
        prefs = snap['preferences']
        onboarded = snap['onboarding_completed']

        scored = {k: v for k, v in dirs.items() if v['score'] >= 0}
        avg_score = sum(v['score'] for v in scored.values()) / max(len(scored), 1)
        all_zero = all(v['score'] <= 0 for v in dirs.values())

        # === 新手评估 ===
        if not onboarded or all_zero:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'warning',
                'title': '📝 尚未完成能力评估',
                'description': '你还没有完成CTF各方向的能力自评，系统无法为你精准推荐学习内容。完成3分钟的自评引导后，你将看到针对性的学习建议、个性化推荐和动态难度调整。',
                'actionable': True, 'action_link': '/profile/setup'
            })
            insights.append({
                'insight_type': 'weakness', 'severity': 'info',
                'title': '初始水平：各方向待评估',
                'description': '作为CTF新人，你现在处于能力地图的空白阶段。这是完全正常的——每个CTF选手都从这里开始。建议先花1周时间了解六大方向的基础概念，确定自己最感兴趣的方向后再深入学习。',
                'actionable': True, 'action_link': '/learning-paths'
            })
            insights.append({
                'insight_type': 'recommendation', 'severity': 'info',
                'title': '💡 学习建议：先广后深',
                'description': '在初始阶段，不必急于深入某单一方向。建议用1-2周时间快速浏览Web、Misc、Crypto三个入门门槛较低的方向，找到自己真正感兴趣的方向后再制定专项学习计划。兴趣是最好的老师。',
                'actionable': True, 'action_link': '/challenges'
            })

        # === 强项分析 ===
        strong = [(k, v) for k, v in dirs.items() if v['score'] >= 4]
        if strong:
            for key, val in strong[:2]:
                insights.append({
                    'insight_type': 'strength', 'severity': 'info',
                    'title': f'💪 核心优势：{val["label"]}（{val["score"]}/5）',
                    'description': f'{val["label"]}是你的最强方向。建议在保持该优势的同时，利用该方向的知识关联性辐射带动其他方向。例如{"Web安全的渗透思维可以迁移到逆向工程" if key == "web" else "密码学的数学基础对二进制安全也有帮助" if key == "crypto" else "该方向的解题思路可以应用到综合题型中"}。',
                    'actionable': False, 'action_link': ''
                })
        elif avg_score <= 2 and not all_zero:
            insights.append({
                'insight_type': 'weakness', 'severity': 'warning',
                'title': '各方向基础均较薄弱',
                'description': f'你的平均自评分为{avg_score:.1f}/5，各方向都处于入门水平。不要气馁，这说明你有很大的成长空间。建议先集中精力突破Web安全方向，建立信心后再拓展其他方向。专注一点比分散精力更有效。',
                'actionable': True, 'action_link': '/learning-paths'
            })

        # === 薄弱点详细分析 ===
        weak = [(k, v) for k, v in dirs.items() if 0 <= v['score'] <= 2]
        for key, val in weak[:3]:
            reasons = {
                'web': 'Web安全是CTF中题目数量最多的方向，薄弱的Web基础会限制你的整体解题能力。建议从HTTP协议和常见Web漏洞开始系统学习。',
                'crypto': '密码学需要在数学基础和编码知识上有一定积累。建议从古典密码和Base编码开始，逐步过渡到现代密码算法。',
                'pwn': '二进制安全的学习曲线较陡峭，需要汇编语言基础和程序内存布局的理解。建议从栈溢出基础开始，循序渐进。',
                'reverse': '逆向工程需要工具使用经验和程序分析思维。建议从简单CrackMe开始，配合IDA/Ghidra教程逐步建立分析框架。',
                'forensics': '数字取证工具种类繁多，需要广泛涉猎。建议先掌握文件格式识别和常见隐写分析工具，再逐步深入。',
                'misc': 'Misc题目覆盖面广，需要较广的知识面。建议多刷不同类型题目来积累经验和解题直觉。',
            }
            insights.append({
                'insight_type': 'weakness', 'severity': 'warning' if val['score'] <= 1 else 'info',
                'title': f'待提升：{val["label"]}（{val["score"]}/5）',
                'description': reasons.get(key, f'你在{val["label"]}方向存在明显的提升空间。'),
                'actionable': True, 'action_link': '/learning-paths'
            })

        # === 均衡性分析 ===
        if len(scored) >= 4:
            vals = [v['score'] for v in scored.values()]
            variance = max(vals) - min(vals)
            if variance >= 4:
                insights.append({
                    'insight_type': 'plateau', 'severity': 'warning',
                    'title': '⚠️ 能力严重偏科',
                    'description': f'各方向最大差距达{variance}分。CTF竞赛通常需要2-3个方向的综合能力协同解题。严重偏科会导致在某些题型上完全无法下手。建议将20%的时间用于维持强项，80%的时间用于补短板。',
                    'actionable': True, 'action_link': '/analytics'
                })
            elif variance >= 2:
                insights.append({
                    'insight_type': 'recommendation', 'severity': 'info',
                    'title': '📊 存在一定偏科，建议均衡发展',
                    'description': f'各方向差距{variance}分，属于正常范围。适度的偏科是允许的—事实上大多数CTF选手都有自己擅长的方向。只需确保薄弱方向不至于完全无法解题即可。',
                    'actionable': True, 'action_link': '/learning-paths'
                })
            elif variance <= 1 and avg_score >= 3:
                insights.append({
                    'insight_type': 'strength', 'severity': 'info',
                    'title': '✅ 能力均衡发展，基础扎实',
                    'description': '你各方向能力分布均匀，这种"六边形战士"式的均衡基础在CTF竞赛中极为珍贵。很多高水平题目需要跨方向知识，你的均衡能力将使你在面对综合题型时具有天然优势。',
                    'actionable': False, 'action_link': ''
                })

        # === 学习投入分析 ===
        daily = prefs.get('daily_hours', 0)
        if daily >= 4:
            insights.append({
                'insight_type': 'strength', 'severity': 'info',
                'title': f'🔥 高投入模式：每日{daily}小时',
                'description': f'你计划每天投入{daily}小时学习，属于高强度学习模式。按此节奏，预计3-6个月可达到CTF中级水平。注意采用番茄工作法（25分钟专注+5分钟休息），每90分钟安排15分钟的长时间休息，保护视力和颈椎。',
                'actionable': False, 'action_link': ''
            })
        elif daily >= 2:
            insights.append({
                'insight_type': 'strength', 'severity': 'info',
                'title': f'📚 稳定投入：每日{daily}小时',
                'description': f'每天{daily}小时的学习节奏稳定且可持续。研究表明，稳定的小时量学习比偶尔的长时间突击学习效果更好。建议固定学习时间段（如每晚20:00-22:00），形成学习习惯后进步会更加明显。',
                'actionable': False, 'action_link': ''
            })
        elif daily > 0:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'warning',
                'title': f'⏰ 学习投入偏低：每日仅{daily}小时',
                'description': f'当前每日学习时长仅{daily}小时，学习密度偏低。CTF技能的积累需要时间投入，建议将每日学习时间增加到2小时以上。可以尝试利用碎片时间（通勤、午休）观看CTF教学视频或阅读Writeup来补充学习量。',
                'actionable': True, 'action_link': '/profile'
            })

        # === 知识概念分析 ===
        if ks['strong']:
            names = [k['concept_name'] for k in ks['strong'][:3]]
            insights.append({
                'insight_type': 'strength', 'severity': 'info',
                'title': f'📗 已掌握{len(ks["strong"])}个核心概念',
                'description': f'「{", ".join(names)}」等概念已达到掌握水平。掌握了这些核心概念，你在相关题型的解题速度和正确率都会明显优于平均水平。建议尝试将这些知识串联起来，形成自己的知识网络图谱。',
                'actionable': False, 'action_link': ''
            })

        if ks['weak']:
            names = [k['concept_name'] for k in ks['weak'][:3]]
            insights.append({
                'insight_type': 'weakness', 'severity': 'warning',
                'title': f'📕 {len(ks["weak"])}个概念需重点复习',
                'description': f'「{", ".join(names)}」等概念掌握度低于40%。这些概念是进阶学习的前置知识，不补上这些短板，后续学习会遇到瓶颈。建议每天安排45分钟专项时间攻克{names[0]}，预计{max(3,len(ks["weak"]))}天内可以看到明显改善。',
                'actionable': True, 'action_link': '/learning-paths'
            })

        # === 学习方法匹配 ===
        pace = prefs.get('pace', '')
        pace_map = {
            'self_paced': {'title': '🏃 自主学习节奏', 'desc': '你选择了自主学习模式。这种模式适合自律性强的学习者。建议每周日晚上做好下周学习计划，设定明确的周目标（如"完成5道Web题目+学习1个密码算法"），周末复盘完成情况。'},
            'scheduled': {'title': '📅 计划学习节奏', 'desc': '你选择了计划学习模式。系统化的学习计划能最大化学习效率。建议将学习内容按照"理论→实操→复盘"的三段式安排，每完成一个模块就在系统中标记进度。'},
            'intensive': {'title': '⚡ 集训冲刺节奏', 'desc': '你选择了集训冲刺模式，适合备考或赛前突击。高强度学习需要注意：(1)每45分钟休息5分钟 (2)保持充足睡眠 (3)每天留30分钟轻量复习巩固前一天内容。'},
        }
        if pace in pace_map:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'info',
                'title': pace_map[pace]['title'],
                'description': pace_map[pace]['desc'],
                'actionable': False, 'action_link': ''
            })

        # === 学习方式建议 ===
        modality = prefs.get('modality', [])
        if 'code' in modality and 'diagram' not in modality:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'info',
                'title': '🖼️ 建议结合图解学习',
                'description': '你偏好代码实践，动手能力强的优势明显。但在学习网络协议栈、攻击流程等复杂概念时，配合Mermaid流程图或网络拓扑图可以让抽象结构更加直观。系统可以在学习中心为你生成相关图解。',
                'actionable': True, 'action_link': '/multi-agent?mode=learning'
            })
        if 'text' in modality and 'code' not in modality:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'info',
                'title': '⌨️ 建议增加动手实践',
                'description': '你偏好文本阅读，理论基础可能比较扎实。但CTF最终考察的是实践能力——能够阅读100篇Writeup不如亲手写出一个exploit。建议每学完一个概念，至少完成3道相关实操题目来巩固。',
                'actionable': True, 'action_link': '/challenges'
            })
        if 'diagram' in modality and 'text' not in modality:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'info',
                'title': '📖 建议补充文本学习',
                'description': '你偏好图解学习，视觉化思维有助于快速理解流程。但图解通常只展示核心逻辑，可能会遗漏细节。建议配合阅读官方文档和技术博客，补充图解中未展示的技术细节和边界条件。',
                'actionable': True, 'action_link': '/resources'
            })

        # === 难度偏好分析 ===
        bias = prefs.get('difficulty_bias', 0)
        if bias < -0.3:
            insights.append({
                'insight_type': 'plateau', 'severity': 'info',
                'title': '🛡️ 舒适区偏好明显',
                'description': '你明显偏好简单难度内容（bias<-0.3）。长期待在舒适区可能导致进步缓慢。建议每周安排1-2道中等难度的题目作为"挑战任务"，即使不能独立完成，尝试的过程本身就是很好的学习。',
                'actionable': True, 'action_link': '/challenges'
            })
        elif bias > 0.3:
            insights.append({
                'insight_type': 'acceleration', 'severity': 'info',
                'title': '🚀 进取型学习者',
                'description': '你偏好挑战高难度内容，这种进取精神值得赞赏。但请注意：高难度题目往往需要多个前置知识的综合运用。如果频繁遇到完全无法下手的题目，建议暂时降级到中等难度，建立解题信心后再升级。',
                'actionable': False, 'action_link': ''
            })

        # === 综合状态评估 ===
        if avg_score >= 4:
            insights.append({
                'insight_type': 'acceleration', 'severity': 'info',
                'title': '🌟 优秀水平：具备竞赛能力',
                'description': f'你的平均自评分为{avg_score:.1f}/5，已达到CTF竞赛水平。建议参加CTFtime上的公开赛事，在实战中检验和提升自己。同时可以尝试撰写Writeup分享解题思路，教学输出是最高效的学习方式之一。',
                'actionable': False, 'action_link': ''
            })
        elif avg_score >= 2.5:
            insights.append({
                'insight_type': 'acceleration', 'severity': 'info',
                'title': '📈 处于快速成长期',
                'description': f'你的平均自评分为{avg_score:.1f}/5，处于中级水平。这是进步最快的阶段——你已有足够的基础理解新概念，又还有大量未探索的知识领域。继续保持当前的节奏，预计1-2个月可以看到显著进步。',
                'actionable': False, 'action_link': ''
            })
        elif avg_score < 2 and not all_zero:
            insights.append({
                'insight_type': 'plateau', 'severity': 'warning',
                'title': '🌱 起步阶段：打好基础最重要',
                'description': f'你的平均自评分为{avg_score:.1f}/5，处于入门水平。现阶段最重要的是建立正确的学习方法和知识框架，而非追求解题数量。建议跟着学习路径系统学习，不要跳跃式学习——基础不牢会导致后续学习事倍功半。',
                'actionable': True, 'action_link': '/learning-paths'
            })

        # === 目标提醒 ===
        goals = snap['learning_goals']
        if goals:
            insights.append({
                'insight_type': 'recommendation', 'severity': 'info',
                'title': '🎯 目标追踪',
                'description': f'你的学习目标是「{goals[:80]}」。建议将这个目标写在便签上贴在显眼位置，每完成一个阶段性小目标就在上面打勾。可视化的进度追踪能有效提升学习动力和坚持率。',
                'actionable': False, 'action_link': '/profile'
            })

        return insights[:8]

    def profile_student(self, student_id: int) -> Dict:
        """同步版 — 构建学生数据快照（不调AI）"""
        snap = self._build_student_snapshot(student_id)
        return {
            'student_id': student_id,
            'profile_summary': snap['learning_goals'],
            'knowledge_count': snap['knowledge_summary']['total'],
            'preferences': snap['preferences'],
            'direction_scores': snap['direction_scores'],
            'analysis': '',  # 不再调用AI
            'provider': 'rule_engine',
        }

    def recommend_next_step(self, student_id: int) -> Dict:
        """同步版 — 基于规则引擎推荐（不调AI）"""
        snap = self._build_student_snapshot(student_id)
        sequence_recs = self._get_sequence_recommendations(student_id)
        rule_recs = self._get_rule_recommendations(snap)
        recs = self._merge_sequence_and_rule_recommendations(
            sequence_recs,
            rule_recs,
            student_id,
        )
        return {
            'student_id': student_id,
            'recommendations': recs,
            'provider': 'knowledge_tracking_sequence_recommender',
        }

    def get_insights(self, student_id: int) -> List[Dict]:
        """同步版 — 基于规则引擎生成洞察（不调AI）"""
        snap = self._build_student_snapshot(student_id)
        return self._get_rule_insights(snap, student_id)

    async def tutoring_session(
        self,
        student_id: int,
        concept_name: str,
        question: str,
        student_level: str = 'beginner',
        model_id: str = None,
        teaching_context: Optional[Dict] = None,
        context_summary: str = '',
    ) -> Dict:
        """委托 service.tutoring_session 执行4步教学闭环"""
        results = await self.service.tutoring_session(
            student_id=student_id,
            concept_name=concept_name,
            question=question,
            student_level=student_level,
            model_id=model_id,
            teaching_context=teaching_context,
            context_summary=context_summary,
        )
        return {
            'student_id': student_id,
            'concept_name': concept_name,
            'student_level': student_level,
            'steps': results,
        }

    async def compute_persona(self, student_id: int) -> Dict:
        """
        聚合数据 → 调 analyst → 更新 LearningPersona 表

        如果 LearningPersona 模型不可用，仅返回分析结果不持久化
        """
        from asgiref.sync import sync_to_async
        from django.utils import timezone
        from student_profiles.models import StudentProfile, LearningPersona

        profile = await sync_to_async(self._get_student_profile)(student_id)
        knowledge_states = await sync_to_async(self._get_knowledge_states)(student_id)
        preferences = await sync_to_async(self._get_learning_preferences)(student_id)

        prompt = (
            f"请根据以下学生数据，推断其学习人格类型：\n\n"
            f"学习目标：{profile.learning_goals}\n"
            f"知识掌握情况：{knowledge_states[:20]}\n"
            f"学习偏好：{preferences}\n\n"
            f"请输出：\n"
            f"1. 学习人格标签（如：「稳健型学习者」「激进型探索者」「理论型研究者」等）\n"
            f"2. 人格特征描述（JSON格式，包含主要特征和次要特征）\n"
            f"3. 推荐的AI导师组合（从 tutor/curriculum/content_gen/code_mentor/assessor/analyst 中选择2-4个）\n"
            f"4. 与该人格最匹配的教学策略建议"
        )

        result = await self.service.chat_with_agent('analyst', prompt)

        persona_data = {
            'student_id': student_id,
            'analysis_raw': result.get('content', ''),
            'provider': result.get('provider', ''),
            'persona_label': '',
            'traits': {},
            'recommended_agents': [],
        }

        try:
            profile_obj, _ = await sync_to_async(StudentProfile.objects.get_or_create)(
                user_id=student_id,
                defaults={'learning_goals': '', 'self_assessed_skills': {}},
            )

            persona, created = await sync_to_async(LearningPersona.objects.update_or_create)(
                profile=profile_obj,
                defaults={
                    'persona_label': persona_data['persona_label'] or '未分类',
                    'confidence_score': 0.75,
                    'persona_traits': persona_data['traits'],
                    'recommended_agent_roster': persona_data['recommended_agents'],
                    'last_computed': timezone.now(),
                },
            )
            persona_data['persona_id'] = persona.id
            persona_data['created'] = created
        except Exception as e:
            logger.warning(f"compute_persona 持久化失败 (student_id={student_id}): {e}")
            persona_data['persist_error'] = str(e)

        return persona_data
