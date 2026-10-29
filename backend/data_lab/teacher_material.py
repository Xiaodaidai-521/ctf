"""Server-only answer keys. Never imported by student material serializers."""
from .catalog import TASK_A, TASK_B

# Logical CSV rows include the header. Targets authored independently of detector output.
TARGETS = {
    TASK_A: [
        (2, 1, "DEMO-U-0001", "DEMO_PERSON_REF"),
        (2, 3, "learner01@example.invalid", "DEMO_CONTACT"),
        (3, 1, "DEMO-U-0002", "DEMO_PERSON_REF"),
        (3, 3, "learner02@example.invalid", "DEMO_CONTACT"),
        (4, 1, "DEMO-U-0003", "DEMO_PERSON_REF"),
        (4, 4, "DEMO-U-0003", "DEMO_PERSON_REF"),
        (6, 1, "DEMO-U-0005", "DEMO_PERSON_REF"),
        (6, 3, "learner01@example.invalid", "DEMO_CONTACT"),
        (6, 4, "DEMO-U-0005", "DEMO_PERSON_REF"),
        (7, 1, "DEMO-U-0006", "DEMO_PERSON_REF"),
    ],
    TASK_B: [
        (2, 3, "DEMO-U-0101", "DEMO_PERSON_REF"),
        (4, 3, "DEMO-U-0103", "DEMO_PERSON_REF"),
        (4, 3, "learner03@example.invalid", "DEMO_CONTACT"),
        (6, 3, "ＤＥＭＯ-U-0105", "DEMO_PERSON_REF"),
        (7, 3, "DEMO-U-0106", "DEMO_PERSON_REF"),
        (7, 4, "learner03@example.invalid", "DEMO_CONTACT"),
    ],
}
NEGATIVES = {TASK_A: [(5, 1, "DEMO-U-9001")], TASK_B: [(3, 3, "DEMO-U-9101")]}
EXPECTED_REPLAYS = {"A1": ["mask"], "A2": ["deny"], "A3": ["defer"],
                    "A4": ["mask", "require_approval"]}
RUBRIC = {
    "version": "data-lab-basis-v1", "review_status": "pending_two_teachers",
    "dimensions": {
        "basis": ["0：未引用适用依据", "1：引用但适用事实不完整", "2：条款、版本与事实逐项对应"],
        "causality": ["0：混淆检测与分类", "1：结论区分但缺原因", "2：三个结论分开且说明授权/必要性"],
        "evidence": ["0：无受控证据", "1：证据不完整", "2：逻辑位置、版本、复核与回放可核对"],
        "improvement": ["0：未说明不确定项", "1：有缺口无责任人", "2：缺口、拟议措施、待复核责任明确"],
    },
    "execution": "not_started", "protection": "not_assessed",
}
STUDENT_EXPLANATION = {
    TASK_A: "识别仅提供候选。结合设备业务事实复核误报，人工检查未扫描自由文本。授权未知不能默认允许；50次并未超过>50的教学门槛。所有措施均未执行。",
    TASK_B: "依据actor/device语义区分标识，同形全角字符串需人工补录；不能提高原检测器召回。日志使用独立接收者授权，客户案例权限不能继承。",
}
