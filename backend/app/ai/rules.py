"""Deterministic rule-based extraction.

Kept separate from any AI provider so the pipeline has a fallback that never
hallucinates: it only reports strings that literally appear in the source.

Chinese date expressions are searched on *both* sides of a trigger word, so
"于2022年10月入职" and "入职日期：2022年10月" both resolve (engineering log §3.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# Trigger words that make a nearby date meaningful as an event date.
DATE_TRIGGERS = ("入职", "离职", "解除", "通知", "签订", "发薪", "辞退", "仲裁", "入职日期", "合同")

# 2022年10月1日 / 2022年10月 / 2022-10-01 / 2022/10/01
_FULL_CN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_MONTH_CN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
_ISO = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")

# 人民币金额：7000元 / 7,500.50元 / ¥7000 / 人民币 7000
# A currency symbol makes the unit suffix optional, so "¥300" is still caught.
_AMOUNT = re.compile(
    r"(?:人民币\s*|¥\s*|￥\s*)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d{1,2})?)\s*(?:万元|元|块钱)?"
    r"|(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d{1,2})?)\s*(?:万元|元|块钱)"
)

# 常见中文姓名（2-4 个汉字，前面常有“本人/员工/经理”等称谓）
_NAME = re.compile(r"(?:^|[\s，,。:：])([一-龥]{2,4})(?=\s*(?:先生|女士|经理|主管|HR|的)|$)")

# 组织：XX公司 / XX有限公司 / XX科技（XX）有限公司
_ORG = re.compile(r"([\u4e00-\u9fa5A-Za-z（）()]{2,20}?(?:有限公司|有限责任公司|公司|事务所|银行))")


@dataclass
class ExtractedFact:
    kind: str  # date | amount | person | organization
    value: str
    source: str  # the surrounding snippet, for traceability


@dataclass
class ExtractionResult:
    dates: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    persons: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    facts: list[ExtractedFact] = field(default_factory=list)


def _snippet(text: str, start: int, end: int, pad: int = 16) -> str:
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    return text[lo:hi].replace("\n", " ").strip()


def _parse_date(year: str, month: str, day: str | None) -> date | None:
    try:
        if day is None:
            return date(int(year), int(month), 1)
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def extract_dates(text: str) -> list[ExtractedFact]:
    """Find date expressions, preferring the one nearest a trigger word.

    Both trigger-before-date and trigger-after-date word orders are covered.
    """
    hits: list[ExtractedFact] = []
    seen: set[str] = set()

    for pattern, has_day in ((_FULL_CN, True), (_ISO, True), (_MONTH_CN, False)):
        for m in pattern.finditer(text):
            groups = m.groups()
            parsed = _parse_date(groups[0], groups[1], groups[2] if has_day else None)
            if parsed is None:
                continue
            key = parsed.isoformat()
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                ExtractedFact(
                    kind="date",
                    value=key,
                    source=_snippet(text, m.start(), m.end()),
                )
            )

    # Rank by proximity to a trigger word so "入职日期" beats an unrelated date.
    def distance(f: ExtractedFact) -> int:
        best = 10_000
        for trigger in DATE_TRIGGERS:
            idx = text.find(trigger)
            while idx != -1:
                pos = text.find(f.value.replace("-", "年", 1), 0)
                best = min(best, abs(idx - (pos if pos != -1 else idx)))
                idx = text.find(trigger, idx + 1)
        return best

    hits.sort(key=distance)
    return hits


def extract_amounts(text: str) -> list[ExtractedFact]:
    """Collect monetary amounts, preserving the original unit wording."""
    out: list[ExtractedFact] = []
    seen: set[str] = set()
    for m in _AMOUNT.finditer(text):
        # Group 1 is the currency-symbol form, group 2 the bare number + unit.
        number = m.group(1) or m.group(2)
        if not number:
            continue
        raw = m.group(0).strip()
        if raw in seen:
            continue
        seen.add(raw)
        out.append(ExtractedFact(kind="amount", value=raw, source=_snippet(text, m.start(), m.end())))
    return out


def extract_persons(text: str) -> list[ExtractedFact]:
    out: list[ExtractedFact] = []
    seen: set[str] = set()
    for m in _NAME.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        out.append(ExtractedFact(kind="person", value=name, source=_snippet(text, m.start(), m.end())))
    return out


def extract_organizations(text: str) -> list[ExtractedFact]:
    out: list[ExtractedFact] = []
    seen: set[str] = set()
    for m in _ORG.finditer(text):
        org = m.group(1).strip()
        if org in seen:
            continue
        seen.add(org)
        out.append(ExtractedFact(kind="organization", value=org, source=_snippet(text, m.start(), m.end())))
    return out


def collect_hits(text: str) -> ExtractionResult:
    """Run every extractor once and return deduplicated, ordered results."""
    date_hits = extract_dates(text)
    amount_hits = extract_amounts(text)
    person_hits = extract_persons(text)
    org_hits = extract_organizations(text)
    return ExtractionResult(
        dates=[f.value for f in date_hits],
        amounts=[f.value for f in amount_hits],
        persons=[f.value for f in person_hits],
        organizations=[f.value for f in org_hits],
        facts=date_hits + amount_hits + person_hits + org_hits,
    )
