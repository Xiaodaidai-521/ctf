"""Closed, versioned teaching resources. Nothing here is a published course."""
import hashlib
import json
from pathlib import Path

NOTICE = "教学演练：只看决策，不执行导出"
SYNTHETIC = "课程编制合成内容；无生产副本、真实自然人、学生资料或凭证。"
TASK_A = "TASK-DS-CUSTOMER-TABLE-001"
TASK_B = "TASK-DS-LOG-RETEST-001"
TASK_VERSION = "1.0.0-candidate"
ROOT = Path(__file__).resolve().parent / "materials"
BASIS_IDS = ("BC-DS-001", "BC-DS-002", "BC-DS-003", "BC-DS-004")


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


CASES = {
    TASK_A: {
        "task_key": TASK_A, "task_version": TASK_VERSION,
        "title": "合成客户表依据与风险决策", "fixture_id": "customer-v1",
        "asset_version_id": "DL-CUSTOMER-1", "filename": "customer-v1.csv",
        "sha256": "dcf4ffff7bdce31f886a90750125384c4c761b98fb0a9d38cad13d7b5011f02d",
        "material_version": "customer-material-v1", "answer_version": "customer-answer-v1",
        "validator_version": "data-lab-customer-v1", "rubric_version": "data-lab-basis-v1",
        "rule_version": "demo-rules-v1", "scenario_version": "customer-replay-v1",
        "facts": {
            "F-PURPOSE": "仅向 DEMO-ANALYST-A 提供地区和工单数量统计；联系方式及自由文本不是必要字段。",
            "F-PERSON": "DEMO-U-0001/0002/0003/0005/0006 假设映射虚构客户，不对应真实自然人。",
            "F-DEVICE": "DEMO-U-9001 为虚构设备型号，不是人关联标识。",
            "F-COVERAGE": "仅检测数据行前3列；service_note不在原规则扫描范围，须人工检查。表头不检测。",
            "F-AUTH": "预置允许接收者 DEMO-ANALYST-A；其他接收者不在范围内；未知与越权分开判断。",
        },
        "scan_columns": [1, 2, 3],
        "hints": ["先区分识别形态、个人信息属性与分类分级三个问题。",
                  "引用依据卡时写清处理目的、可识别性假设与缺失行业目录。",
                  "检查 service_note 的覆盖缺口；设备型号不能只靠前缀判断。",
                  "以业务事实复核设备误报，按逻辑行和码点补录自由文本；累计阈值比较严格大于。"],
    },
    TASK_B: {
        "task_key": TASK_B, "task_version": TASK_VERSION,
        "title": "合成业务日志新场景复测", "fixture_id": "log-v1",
        "asset_version_id": "DL-LOG-1", "filename": "log-v1.csv",
        "sha256": "943ba09621a17c3b7b5c5a5d79ffc38204ce6f918979d17e6e64b170e41f3368",
        "material_version": "log-material-v1", "answer_version": "log-answer-v1",
        "validator_version": "data-lab-log-v1", "rubric_version": "data-lab-basis-v1",
        "rule_version": "demo-rules-v1", "scenario_version": "log-replay-v1",
        "facts": {
            "F-PURPOSE": "日志只用于 DEMO-OPS-B 的故障数量统计，不需要 actor.ref 或 reply。",
            "F-PERSON": "嵌套 actor.ref 假设映射虚构工单发起者；含全角前缀，未经规范化。",
            "F-DEVICE": "嵌套 device.model DEMO-U-9101 是设备编号，非人关联标识。",
            "F-COVERAGE": "检测数据行全部4列；只识别两个ASCII合成模式，全角同形前缀有规则缺口。",
            "F-AUTH": "允许接收者改为 DEMO-OPS-B，客户案例中的 DEMO-ANALYST-A 在此不获授权。",
        },
        "scan_columns": [1, 2, 3, 4],
        "hints": ["日志布局变了，先找业务用途与授权事实。",
                  "嵌套字段命中不等于完成分类分级。",
                  "区分 actor 与 device，留意全角前缀和空字段。",
                  "补录同形标识时保留原文码点位置；不要把客户案例的接收者权限搬来。"],
    },
}


def case_spec(task_key):
    try:
        return CASES[task_key]
    except KeyError:
        raise ValueError("CASE_NOT_REGISTERED") from None


def asset_bytes(task_key):
    spec = case_spec(task_key)
    content = (ROOT / spec["filename"]).read_bytes()
    if len(content) > 64 * 1024 or digest(content) != spec["sha256"]:
        raise ValueError("ASSET_DIGEST_MISMATCH")
    return content


def student_material(task_key):
    spec = case_spec(task_key)
    visible = ("task_key", "task_version", "title", "fixture_id", "asset_version_id",
               "sha256", "material_version", "validator_version", "rubric_version",
               "rule_version", "scenario_version", "facts", "scan_columns")
    return {**{k: spec[k] for k in visible}, "basis_ids": list(BASIS_IDS),
            "synthetic_declaration": SYNTHETIC, "notice": NOTICE,
            "execution_mode": "readonly_decision", "requires_milestone_i": False,
            "execution_status": "not_started", "protection_status": "not_assessed",
            "review_status": "pending_two_teachers", "policy_status": "draft",
            "position_contract": "行列一基；CSV表头占逻辑行；字符零基Unicode码点半开区间；identity映射",
            "classification": {"entity_category": "合成形态候选，待复核",
                               "personal_information": "基于可识别性假设查证，不宣称合成标识是法定个人信息",
                               "data_classification": "行业目录未核定；仅练通用方法，不给真实等级"},
            "uncertainties": ["行业目录未选定", "检测不等于分类", "所有措施仅为建议"],
            "teacher_example": {"evidence_kind": "teacher_example", "before": "learner01@example.invalid",
                                "after": "[合成联系方式]", "label": "教师预制讲解样例；非学生执行证据"}}
