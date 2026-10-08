"""Public chat response contracts.

These types document the backward-compatible response envelope. Internal
request-only fields such as workflowId and agentContext are intentionally not
part of any public response type.
"""

from __future__ import annotations

from typing import Dict, List, NotRequired, TypeAlias, TypedDict, Union


JSONValue: TypeAlias = Union[
    None,
    bool,
    int,
    float,
    str,
    List["JSONValue"],
    Dict[str, "JSONValue"],
]
JSONObject: TypeAlias = Dict[str, JSONValue]


class ChatResourcePayload(TypedDict):
    id: str
    title: str
    type: str
    entry: str
    summary: str
    ai_generated_label: str
    location: str


LearningAnalysisPayload: TypeAlias = JSONObject
RecommendationPayload: TypeAlias = Union[str, JSONObject]


class CompatibleChatResponsePayload(TypedDict):
    answer: str
    content: NotRequired[str]
    role: NotRequired[str]
    conversation_id: NotRequired[JSONValue]
    responses: NotRequired[List[JSONObject]]
    challenge_info: NotRequired[JSONValue]
    resources: NotRequired[List[ChatResourcePayload]]
    resourceList: NotRequired[List[ChatResourcePayload]]
    noMatchedResource: NotRequired[bool]
    learningAnalysis: NotRequired[LearningAnalysisPayload]
    knowledgeDiagnosis: NotRequired[JSONObject]
    studyStrategy: NotRequired[JSONObject]
    recommendations: NotRequired[List[RecommendationPayload]]
    metadata: NotRequired[JSONObject]