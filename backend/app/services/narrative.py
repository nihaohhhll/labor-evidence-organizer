"""Case narrative generation: turn analyzed materials into a factual story.

The narrative is a *draft only* — this service never writes to the case; the
client shows it to the user who saves it through PATCH /cases/{id}, so a bad
generation can never silently overwrite a human-written account.

Rules follow docs/08_PROMPT_SPEC: facts only, chronological, no legal
conclusions. When the LLM is unavailable (mock provider, network failure) a
deterministic template built from evidence summaries and timeline events is
returned instead, tagged provider="template".
"""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.registry import get_ai_provider
from app.models.case import Case
from app.models.evidence import Evidence
from app.models.event import Event

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是劳动仲裁案件的事实叙述撰写助手。\n"
    "根据用户提供的案件材料解析结果，按时间顺序写一段案件事实叙述。\n"
    "严格要求：\n"
    "- 只陈述材料中明确存在的事实，不得编造；\n"
    "- 按时间顺序组织：入职 → 工作与合同情况 → 争议起因与经过 → "
    "关键节点（调岗/降薪/解除/离职）→ 目前状态与诉求（如材料中有）；\n"
    "- 包含关键要素：时间、岗位、工资、单位名称、争议行为；\n"
    "- 不得包含法律评价或结论性判断（如“违法”“应当赔偿”），只写事实；\n"
    "- 语言平实简明，300-500字；\n"
    "- 只输出叙述正文纯文本，不要标题、不要 markdown、不要任何解释。"
)


class NarrativeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run_async(coro):
    """Run a provider coroutine from a worker thread (routes are plain `def`)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("narrative generation 被在事件循环线程中调用。")


def gather_materials(db: Session, case: Case) -> tuple[list[Evidence], list[Event]]:
    evidence = list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id)
            .order_by(Evidence.evidence_number.asc())
        ).all()
    )
    events = list(
        db.scalars(
            select(Event)
            .where(Event.case_id == case.id, Event.merged_into_id.is_(None))
            .order_by(Event.event_date.asc().nulls_last())
        ).all()
    )
    return evidence, events


def build_user_prompt(case: Case, evidence: list[Evidence], events: list[Event]) -> str:
    lines = [f"案件：{case.name}", ""]
    if evidence:
        lines.append(f"【证据材料】（{len(evidence)}项）")
        for ev in evidence:
            date = ev.event_date.isoformat() if ev.event_date else "日期不详"
            summary = (ev.summary or "").strip() or "（无摘要）"
            lines.append(f"{ev.evidence_number}. {ev.title}（{date}）：{summary}")
        lines.append("")
    if events:
        lines.append(f"【时间轴事件】（{len(events)}项）")
        for ev in events:
            date = ev.event_date.isoformat() if ev.event_date else "日期不详"
            desc = f"：{ev.description}" if ev.description else ""
            lines.append(f"- {date} {ev.title}{desc}")
    return "\n".join(lines)


def _template_narrative(evidence: list[Evidence], events: list[Event]) -> str:
    """Deterministic fallback: chronological events + evidence summaries."""
    sentences: list[str] = []
    for ev in events:
        date = ev.event_date.isoformat() if ev.event_date else "日期不详"
        sentences.append(f"{date} {ev.title}。")
    for e in evidence:
        summary = (e.summary or "").strip()
        if summary:
            sentences.append(summary if summary.endswith("。") else summary + "。")
    if not sentences:
        raise NarrativeError("NO_MATERIALS", "案件还没有可用来生成叙述的材料。")
    return "".join(sentences)


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:text|markdown)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return text


def generate_case_narrative(db: Session, case: Case) -> tuple[str, str, str]:
    """Return (narrative, provider, model). Never persists — the client saves."""
    evidence, events = gather_materials(db, case)
    if not evidence and not events:
        raise NarrativeError(
            "NO_MATERIALS", "案件还没有已解析的材料，先上传并解析文件。"
        )

    provider = get_ai_provider()
    generate = getattr(provider, "generate_text", None)
    if generate is not None:
        prompt = build_user_prompt(case, evidence, events)
        try:
            raw = _run_async(generate(_SYSTEM_PROMPT, prompt))
            text = _strip_fences(str(raw))
            if text:
                return text[:5000], provider.name, provider.model
        except Exception:
            logger.exception(
                "narrative generation via %s failed, falling back to template",
                provider.name,
            )

    return _template_narrative(evidence, events), "template", "rules"
