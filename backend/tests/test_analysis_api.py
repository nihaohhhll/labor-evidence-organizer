"""Phase 3: analysis pipeline through the API."""

from __future__ import annotations

from tests.helpers import SAMPLE_TEXT, make_png, make_txt, upload


def _uploaded(client, headers, case_id, name="contract.txt", data=None):
    resp = upload(client, headers, case_id, name, data or make_txt())
    assert resp.status_code == 201, resp.text
    files = resp.json()["files"]
    assert files, resp.json()["skipped"]
    return files[0]["id"]


def test_analyze_file_produces_structured_analysis(client, auth_headers, case_id):
    """Phase 3 acceptance: uploading a test file yields a structured analysis."""
    fid = _uploaded(client, auth_headers, case_id)
    resp = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["provider"] == "mock"
    assert body["model"] == "mock-rules-1"
    assert body["prompt_version"] == "evidence-extraction-v1"
    assert body["classification"] == "labor_contract"
    assert body["dates"], "日期应当被提取"
    assert body["amounts"], "金额应当被提取"
    assert body["organizations"], "组织应当被提取"
    assert body["raw_text"]


def test_analyze_emits_an_evidence_suggestion(client, auth_headers, case_id):
    """Analysis must produce a PENDING, human-confirmable evidence row."""
    fid = _uploaded(client, auth_headers, case_id)
    client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)

    evidence = client.get(f"/api/v1/cases/{case_id}/evidence", headers=auth_headers).json()
    assert evidence["total"] == 1
    row = evidence["evidence"][0]
    assert row["review_status"] == "PENDING"
    assert row["evidence_number"] == 1
    assert row["confidence"] is not None
    assert row["source_file_id"] == fid


def test_file_status_becomes_completed(client, auth_headers, case_id):
    fid = _uploaded(client, auth_headers, case_id)
    client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)
    listing = client.get(f"/api/v1/cases/{case_id}/files", headers=auth_headers).json()
    assert listing["files"][0]["status"] == "COMPLETED"


def test_failed_parse_marks_file_failed_and_allows_retry(client, auth_headers, case_id):
    """docs/12 Scenario 3: AI fails -> retry -> succeeds."""
    # A PNG with the mock OCR provider yields no text; analysis still succeeds
    # but with low confidence. Force a failure via an unsupported-in-practice
    # path instead: corrupt the stored object so parsing cannot start.
    fid = _uploaded(client, auth_headers, case_id)

    from app.storage import get_storage
    from sqlalchemy import select
    from app.models.file import File
    import uuid as _uuid

    row = client.get(f"/api/v1/files/{fid}", headers=auth_headers).json()
    store = get_storage()
    # Remove the original object to simulate a missing/corrupt source.
    store.delete(f"cases/{case_id}/originals/{row['sha256']}.txt")

    resp = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONTENT_MISSING"

    status = client.get(f"/api/v1/files/{fid}", headers=auth_headers).json()["status"]
    assert status == "FAILED"

    # Retry re-queues the file.
    retried = client.post(f"/api/v1/files/{fid}/retry", headers=auth_headers)
    assert retried.status_code == 200
    assert retried.json()["status"] == "QUEUED"
    assert retried.json()["error_message"] is None


def test_reanalysis_appends_never_mutates(client, auth_headers, case_id, db_session):
    """docs/04 rule 5: model/prompt history must stay intact."""
    from sqlalchemy import select

    from app.models.analysis import DocumentAnalysis

    fid = _uploaded(client, auth_headers, case_id)
    first = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers).json()
    second = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers).json()

    assert first["id"] != second["id"], "重新分析必须产生新的分析记录"

    rows = list(
        db_session.scalars(select(DocumentAnalysis).where(DocumentAnalysis.file_id == __import__("uuid").UUID(fid))).all()
    )
    assert len(rows) == 2
    assert all(r.provider == "mock" and r.prompt_version for r in rows)


def test_get_analysis_returns_latest(client, auth_headers, case_id):
    fid = _uploaded(client, auth_headers, case_id)
    created = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers).json()
    fetched = client.get(f"/api/v1/files/{fid}/analysis", headers=auth_headers).json()
    assert fetched["id"] == created["id"]


def test_get_analysis_404_when_never_analyzed(client, auth_headers, case_id):
    fid = _uploaded(client, auth_headers, case_id)
    resp = client.get(f"/api/v1/files/{fid}/analysis", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_case_level_batch_analysis(client, auth_headers, case_id):
    """Batch path: several files analysed in one call."""
    ids = [
        _uploaded(client, auth_headers, case_id, name=f"doc-{i}.txt", data=make_txt(f"{SAMPLE_TEXT}\n补充{i}"))
        for i in range(3)
    ]
    resp = client.post(f"/api/v1/cases/{case_id}/analyze", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["analyzed"] == 3

    evidence = client.get(f"/api/v1/cases/{case_id}/evidence", headers=auth_headers).json()
    assert evidence["total"] == 3
    # Numbers are unique and sequential.
    numbers = sorted(e["evidence_number"] for e in evidence["evidence"])
    assert numbers == [1, 2, 3]


def test_analysis_requires_file_ownership(client, auth_headers, second_user_headers, case_id):
    fid = _uploaded(client, auth_headers, case_id)
    assert (
        client.post(f"/api/v1/files/{fid}/analyze", headers=second_user_headers).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/files/{fid}/analysis", headers=second_user_headers).status_code
        == 404
    )


def test_image_without_ocr_capability_still_succeeds(client, auth_headers, case_id):
    """An image must not crash the pipeline when OCR is unavailable."""
    fid = _uploaded(client, auth_headers, case_id, name="shot.png", data=make_png())
    resp = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["classification"] == "other"


def test_never_asserts_illegality_in_proof_purpose(client, auth_headers, case_id):
    """docs/03 §7: proof purpose must be factual, not a legal conclusion."""
    text = "公司于2024年1月1日通知我离职，月工资8000元，微信聊天记录"
    fid = _uploaded(client, auth_headers, case_id, data=make_txt(text))
    body = client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers).json()

    for word in ("违法", "应当", "仲裁请求成立", "公司违反"):
        assert word not in body["proof_purpose"], body["proof_purpose"]
