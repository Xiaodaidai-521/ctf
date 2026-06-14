"""
多智能体服务扩展 - 添加到 ai_assistant/service.py
"""

# 在 AIAssistantService 类中添加以下方法

def chat_with_agent(
    self,
    agent_config: dict,
    user_message: str,
    conversation_history: Optional[List[Dict]] = None,
    challenge_info: Optional[Dict] = None
) -> str:
    """
    使用指定智能体进行对话
    
    Args:
        agent_config: 智能体配置 {'name', 'system_prompt', ...}
        user_message: 用户消息
        conversation_history: 对话历史
        challenge_info: 题目信息
        
    Returns:
        str: AI回复
    """
    # 使用智能体专用系统提示
    system_prompt = agent_config.get('system_prompt', self.DEFAULT_PROMPT)
    
    # 添加题目信息
    if challenge_info:
        system_prompt += f"""

当前题目信息：
- 标题：{challenge_info.get('title', '')}
- 分类：{challenge_info.get('category_name', '')}
- 难度：{challenge_info.get('difficulty', '')}
- 描述：{challenge_info.get('description', '')[:500]}...
"""
        if challenge_info.get('hint'):
            system_prompt += f"- 提示：{challenge_info.get('hint', '')}\n"
    
    # 添加智能体身份
    agent_name = agent_config.get('name', 'AI助手')
    system_prompt += f"\n\n当前身份：{agent_name}\n请在回复开头表明你的身份。"
    
    # 构建消息列表
    messages = [SystemMessage(content=system_prompt)]
    
    # 添加对话历史
    if conversation_history:
        for msg in conversation_history[-10:]:  # 保留最近10轮
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                messages.append(AIMessage(content=msg['content']))
    
    # 添加当前用户消息
    messages.append(HumanMessage(content=user_message))
    
    try:
        # 调用 LLM
        response = self.client.invoke(
            messages=messages,
            model="doubao-seed-1-8-251228",
            temperature=0.7,
            thinking="disabled"
        )
        
        return self.get_text_content(response.content)
        
    except Exception as e:
        return f"抱歉，{agent_name}暂时无法响应。错误：{str(e)}"


def analyze_for_handoff(self, message: str, current_agent_id: str) -> Optional[Dict]:
    """
    分析消息是否需要委托给其他智能体
    
    Args:
        message: 用户消息
        current_agent_id: 当前智能体ID
        
    Returns:
        Optional[Dict]: 委托信息或 None
    """
    HANDOFF_RULES = {
        'analyst': {
            'security': ['安全', '漏洞', '注入', 'XSS', 'CSRF', '渗透'],
            'architect': ['架构', '设计', '性能', '扩展性', '高可用'],
            'developer': ['代码', '实现', 'bug', '调试', '编写'],
        },
        'developer': {
            'security': ['安全漏洞', '漏洞利用', '安全修复'],
            'architect': ['架构设计', '设计模式', '重构'],
            'tester': ['测试', '用例', '自动化'],
        },
        'security': {
            'developer': ['代码实现', '漏洞修复'],
            'architect': ['安全架构', '防护设计'],
        },
        'architect': {
            'developer': ['代码实现', '具体细节'],
            'security': ['安全评估', '风险分析'],
            'tester': ['测试策略', '质量保障'],
        },
        'tester': {
            'developer': ['测试代码', '自动化实现'],
            'security': ['安全测试', '渗透测试'],
        }
    }
    
    rules = HANDOFF_RULES.get(current_agent_id, {})
    
    for target_agent, keywords in rules.items():
        for keyword in keywords:
            if keyword.lower() in message.lower():
                return {
                    'to_agent_id': target_agent,
                    'reason': f'检测到关键词 "{keyword}"，建议由专业智能体处理'
                }
    
    return None


# 智能体协同模式
def collaborative_chat(
    self,
    user_message: str,
    agents: List[str],
    conversation_history: List[Dict],
    challenge_info: Optional[Dict] = None
) -> List[Dict]:
    """
    多智能体协作模式
    
    Args:
        user_message: 用户消息
        agents: 参与的智能体ID列表
        conversation_history: 对话历史
        challenge_info: 题目信息
        
    Returns:
        List[Dict]: 所有智能体的回复
    """
    responses = []
    
    for agent_id in agents[:3]:  # 最多同时激活3个智能体
        agent_config = AGENT_CONFIGS.get(agent_id)
        if not agent_config:
            continue
            
        response = self.chat_with_agent(
            agent_config=agent_config,
            user_message=user_message,
            conversation_history=conversation_history,
            challenge_info=challenge_info
        )
        
        responses.append({
            'agent_id': agent_id,
            'agent_name': agent_config['name'],
            'content': response
        })
    
    return responses


def sequential_process(
    self,
    user_message: str,
    agents: List[str],
    conversation_history: List[Dict],
    challenge_info: Optional[Dict] = None
) -> List[Dict]:
    """
    串行处理模式 - 智能体依次处理
    
    Args:
        user_message: 用户消息
        agents: 智能体ID列表（按顺序）
        conversation_history: 对话历史
        challenge_info: 题目信息
        
    Returns:
        List[Dict]: 处理流程和结果
    """
    results = []
    current_message = user_message
    
    for i, agent_id in enumerate(agents):
        agent_config = AGENT_CONFIGS.get(agent_id)
        if not agent_config:
            continue
        
        # 如果不是第一个智能体，添加上下文传递信息
        if i > 0 and results:
            prev_result = results[-1]
            current_message = f"[承接上一个智能体 {prev_result['agent_name']} 的分析]\n{prev_result['content']}\n\n请基于以上分析继续处理：\n{user_message}"
        
        response = self.chat_with_agent(
            agent_config=agent_config,
            user_message=current_message,
            conversation_history=conversation_history,
            challenge_info=challenge_info
        )
        
        results.append({
            'step': i + 1,
            'agent_id': agent_id,
            'agent_name': agent_config['name'],
            'content': response,
            'status': 'completed'
        })
    
    return results


# 智能体配置（放到文件顶部）
AGENT_CONFIGS = {
    'analyst': {
        'name': '分析师',
        'role': '数据分析与问题诊断',
        'icon': '📊',
        'color': '#00f5ff',
        'system_prompt': """你是一个数据分析专家，专门帮助用户进行问题诊断和分析。
你的职责：
1. 分析问题的根本原因
2. 提供数据支持的分析结果
3. 识别关键问题和优先级
4. 给出分析报告和建议

请始终表明你是【分析师】，并保持专业和客观。""",
        'capabilities': ['数据分析', '问题诊断', '趋势预测', '报告生成']
    },
    'architect': {
        'name': '架构师',
        'role': '系统设计与架构优化',
        'icon': '🏗️',
        'color': '#ff00ff',
        'system_prompt': """你是一个系统架构师，专门帮助用户进行系统设计和架构优化。
你的职责：
1. 设计系统架构方案
2. 评估技术选型
3. 提供架构优化建议
4. 分析系统瓶颈

请始终表明你是【架构师】，并提供专业的架构视角。""",
        'capabilities': ['系统设计', '架构优化', '技术选型', '性能分析']
    },
    'developer': {
        'name': '开发专家',
        'role': '代码实现与调试',
        'icon': '💻',
        'color': '#39ff14',
        'system_prompt': """你是一个开发专家，专门帮助用户进行代码实现和调试。
你的职责：
1. 编写高质量的代码
2. 解决技术难题
3. 进行代码优化
4. 提供最佳实践建议

请始终表明你是【开发专家】，并提供可执行的代码方案。""",
        'capabilities': ['代码实现', '调试修复', '性能优化', '代码审查']
    },
    'security': {
        'name': '安全专家',
        'role': '安全审计与漏洞分析',
        'icon': '🔒',
        'color': '#ff0055',
        'system_prompt': """你是一个安全专家，专门帮助用户进行安全审计和漏洞分析。
你的职责：
1. 识别安全漏洞
2. 提供安全加固方案
3. 分析攻击路径
4. 编写安全测试脚本

请始终表明你是【安全专家】，并在CTF场景下提供渐进式提示。""",
        'capabilities': ['安全审计', '漏洞分析', '加固方案', '渗透测试']
    },
    'tester': {
        'name': '测试专家',
        'role': '测试设计与质量保障',
        'icon': '🧪',
        'color': '#ff6b35',
        'system_prompt': """你是一个测试专家，专门帮助用户进行测试设计和质量保障。
你的职责：
1. 设计测试方案
2. 编写测试用例
3. 分析测试结果
4. 提出质量改进建议

请始终表明你是【测试专家】，并提供全面的测试视角。""",
        'capabilities': ['测试设计', '用例编写', '自动化测试', '质量保障']
    }
}
