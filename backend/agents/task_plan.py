"""Canonical task types and specialist execution plan."""

QUESTION_ANSWER = "question_answer"
LEARNING_ANALYSIS = "learning_analysis"
KNOWLEDGE_EXPLANATION = "knowledge_explanation"
STUDY_PLAN = "study_plan"
RESOURCE_RECOMMENDATION = "resource_recommendation"

TASK_EXECUTION_PLAN = {
    QUESTION_ANSWER: [],
    LEARNING_ANALYSIS: [
        "learning_analysis_agent",
        "knowledge_diagnosis_agent",
        "resource_agent",
    ],
    KNOWLEDGE_EXPLANATION: ["knowledge_agent"],
    STUDY_PLAN: [
        "learning_analysis_agent",
        "resource_agent",
        "study_strategy_agent",
    ],
    RESOURCE_RECOMMENDATION: ["resource_agent"],
}

SUPPORTED_TASK_TYPES = tuple(TASK_EXECUTION_PLAN)


def execution_plan_for(task_type):
    """Return an isolated plan and safely fall back to question answering."""
    canonical = task_type if task_type in TASK_EXECUTION_PLAN else QUESTION_ANSWER
    return list(TASK_EXECUTION_PLAN[canonical])
