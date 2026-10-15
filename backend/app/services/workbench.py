"""Workbench progress — derived case stage + task list (no invented data).

`derive_progress` is a pure function over counts the caller gathered with
SQL, so it is unit-testable and the API stays a thin aggregate. Stage never
claims legal outcomes; it only describes how far the *material* work has
gone (docs/19).
"""

from __future__ import annotations

TRIAL_CHECKLIST: list[tuple[str, str]] = [
    ("originals_safe", "证据原件/原始载体已妥善保存"),
    ("id_document", "本人身份证明已准备"),
    ("company_info", "企业工商登记信息已核对"),
    ("claim_amount", "仲裁请求金额与计算依据已复核"),
    ("timeline", "事实时间线已通读并核对"),
    ("copies_printed", "开庭材料份数已备齐"),
]

STAGE_LABELS = [
    "案件初始化",
    "材料收集",
    "证据审核",
    "事实核对",
    "请求与证据整理",
    "材料生成",
    "庭审准备",
    "案件归档",
]


def trial_prep_complete(trial_prep: dict | None) -> bool:
    if not trial_prep:
        return False
    checklist = trial_prep.get("checklist") or {}
    return all(checklist.get(item_id) for item_id, _ in TRIAL_CHECKLIST)


def derive_progress(counts: dict[str, int], *, case_status: str, trial_prep: dict | None) -> dict:
    """Return {stage, stage_label, tasks, next_action_href} from real counts.

    Count keys (all ints):
      files_total, files_ready, files_processing, files_failed,
      review_pending,
      evidence_total, evidence_pending, evidence_confirmed,
      events_total, events_pending, events_confirmed,
      claims_total, claims_unlinked,
      packages_total, exports_done,
      narrative (0/1), gap_reports (unused here).
    """
    files_total = counts.get("files_total", 0)
    files_ready = counts.get("files_ready", 0)
    files_processing = counts.get("files_processing", 0)
    files_failed = counts.get("files_failed", 0)
    review_pending = counts.get("review_pending", 0)
    evidence_total = counts.get("evidence_total", 0)
    evidence_pending = counts.get("evidence_pending", 0)
    evidence_confirmed = counts.get("evidence_confirmed", 0)
    events_total = counts.get("events_total", 0)
    events_pending = counts.get("events_pending", 0)
    events_confirmed = counts.get("events_confirmed", 0)
    claims_total = counts.get("claims_total", 0)
    claims_unlinked = counts.get("claims_unlinked", 0)
    packages_total = counts.get("packages_total", 0)
    exports_done = counts.get("exports_done", 0)

    archived = case_status in ("ARCHIVED", "CLOSED")
    prep_done = trial_prep_complete(trial_prep)

    tasks: list[dict] = [
        {
            "id": "upload_files",
            "title": "上传案件材料",
            "done": files_total > 0,
            "action_href": "/files",
            "hint": "在资料库上传 PDF/图片等原始材料",
        },
        {
            "id": "wait_processing",
            "title": "等待材料处理完成",
            "done": files_total > 0 and files_processing == 0,
            "action_href": "/files",
            "hint": "处理失败的文件可在资料库重试",
        },
        {
            "id": "analyze_files",
            "title": "生成证据建议",
            "done": evidence_total > 0 or (files_ready == 0 and files_total == 0),
            "action_href": "/files",
            "hint": "在资料库对已就绪文件运行 AI 分析",
        },
        {
            "id": "review_ai_items",
            "title": "审核 AI 字段建议",
            "done": review_pending == 0,
            "action_href": "/review",
            "hint": "逐条确认或驳回 AI 建议值",
        },
        {
            "id": "confirm_evidence",
            "title": "确认证据条目",
            "done": evidence_total == 0 or evidence_pending == 0,
            "action_href": "/evidence",
            "hint": "核对名称、分类与证明目的后确认",
        },
        {
            "id": "build_timeline",
            "title": "核对事实时间线",
            "done": events_pending == 0 and (events_total > 0 or evidence_confirmed == 0),
            "action_href": "/timeline",
            "hint": "从已确认证据构建事件并核对",
        },
        {
            "id": "add_claims",
            "title": "新增仲裁请求",
            "done": claims_total > 0 or archived,
            "action_href": "/claims",
            "hint": "写明请求事项、金额与计算依据",
        },
        {
            "id": "link_claims",
            "title": "为请求关联证据",
            "done": claims_total == 0 or claims_unlinked == 0,
            "action_href": "/claims",
            "hint": "每项请求至少关联一条证据",
        },
        {
            "id": "build_package",
            "title": "生成材料包",
            "done": packages_total > 0,
            "action_href": "/material-packages/new",
            "hint": "编排证据并生成版本快照",
        },
        {
            "id": "export_case",
            "title": "导出案件材料",
            "done": exports_done > 0,
            "action_href": "/export",
            "hint": "导出 Word/PDF/ZIP 供打印或存档",
        },
        {
            "id": "trial_prep",
            "title": "完成庭审准备清单",
            "done": prep_done,
            "action_href": "/trial-prep",
            "hint": "记录庭审日期并逐项核对准备情况",
        },
        {
            "id": "archive",
            "title": "归档案件",
            "done": archived,
            "action_href": "/archive",
            "hint": "确认材料齐备后归档",
        },
    ]

    if archived:
        stage = 7
    elif files_total == 0:
        stage = 0
    elif files_processing > 0:
        stage = 1
    elif evidence_total == 0 and files_ready == 0:
        # Nothing analyzable yet (all failed / none ready) — stay collecting.
        stage = 1
    elif evidence_total == 0 or review_pending > 0 or evidence_pending > 0:
        stage = 2
    elif events_pending > 0 or (evidence_confirmed > 0 and events_total == 0):
        stage = 3
    elif claims_total == 0 or claims_unlinked > 0:
        stage = 4
    elif packages_total == 0:
        stage = 5
    else:
        stage = 6

    # If everything including prep is done but not archived, still stage 6.
    next_task = next((t for t in tasks if not t["done"]), None)
    return {
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "tasks": tasks,
        "next_action_href": (next_task or {}).get("action_href") if next_task else None,
    }
