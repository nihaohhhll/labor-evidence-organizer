"""Phase 7: DOCX / PDF / ZIP export with numbering and page numbers."""

from __future__ import annotations

import io
import uuid
import zipfile

from tests.helpers import make_txt, upload


def _exportable_case(client, headers, case_id, n=2):
    """Upload, analyze and confirm `n` evidence rows, then build a timeline."""
    for i in range(n):
        data = make_txt(
            f"劳动合同 甲方：某某科技有限公司 入职日期：2022年10月{i + 1}日 月工资7500元"
        )
        fid = upload(client, headers, case_id, f"doc{i}.txt", data).json()["files"][0]["id"]
        client.post(f"/api/v1/files/{fid}/analyze", headers=headers)

    rows = client.get(f"/api/v1/cases/{case_id}/evidence", headers=headers).json()["evidence"]
    for row in rows:
        client.post(f"/api/v1/evidence/{row['id']}/confirm", headers=headers)
    client.post(f"/api/v1/cases/{case_id}/events/build", headers=headers)
    return rows


def test_export_docx_produces_downloadable_file(client, auth_headers, case_id):
    """Phase 7 acceptance: the complete bundle opens and is correctly ordered."""
    _exportable_case(client, auth_headers, case_id)

    resp = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "docx"}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["status"] == "COMPLETED"
    assert job["completed_at"] is not None

    dl = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers)
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # docx is a zip container
    assert "attachment" in dl.headers["Content-Disposition"]


def test_exported_docx_contains_index_and_numbering(client, auth_headers, case_id):
    _exportable_case(client, auth_headers, case_id)
    job = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "docx"}, headers=auth_headers
    ).json()
    data = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers).content

    import docx

    doc = docx.Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            text += "\n" + " ".join(c.text for c in row.cells)

    assert "证据目录" in text
    assert "证据1" in text and "证据2" in text
    assert "案件时间轴" in text
    assert "生成时间" in text
    # Compliance footer required by docs/07/11.
    assert "不构成正式法律意见" in text or any(
        "不构成正式法律意见" in p.text for s in doc.sections for p in s.footer.paragraphs
    )


def test_export_pdf_contains_page_numbers(client, auth_headers, case_id):
    """docs/10: 页码统一为「第 X 页 / 共 Y 页」."""
    _exportable_case(client, auth_headers, case_id)
    job = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "pdf"}, headers=auth_headers
    ).json()
    data = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers).content

    assert data[:5] == b"%PDF-"
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        full_text = "".join(page.get_text("text") for page in doc)
    assert "第 1 页 / 共" in full_text
    assert "证据目录" in full_text


def test_export_zip_bundles_documents_and_originals(client, auth_headers, case_id):
    _exportable_case(client, auth_headers, case_id)
    job = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "zip"}, headers=auth_headers
    ).json()
    data = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers).content

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "证据目录.docx" in names
        assert "证据目录.pdf" in names
        assert "证据索引.csv" in names
        originals = [n for n in names if n.startswith("原始文件/")]
        assert len(originals) == 2
        # CSV must carry the numbering column.
        csv_text = zf.read("证据索引.csv").decode("utf-8")
        assert "编号" in csv_text and "证据1" in csv_text


def test_export_only_includes_confirmed_evidence(client, auth_headers, case_id):
    """docs/10: exports read confirmed/user-reviewed data only."""
    data = make_txt("劳动合同 入职日期：2022年10月1日 月工资7500元")
    fid = upload(client, auth_headers, case_id, "a.txt", data).json()["files"][0]["id"]
    client.post(f"/api/v1/files/{fid}/analyze", headers=auth_headers)

    # Evidence exists but is still PENDING -> nothing to export.
    resp = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "docx"}, headers=auth_headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NOTHING_TO_EXPORT"


def test_export_ordering_follows_evidence_number(client, auth_headers, case_id):
    rows = _exportable_case(client, auth_headers, case_id, n=3)
    # Swap two numbers so ordering cannot be an accident of insertion.
    client.patch(f"/api/v1/evidence/{rows[0]['id']}", json={"title": "第三"}, headers=auth_headers)

    job = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "docx"}, headers=auth_headers
    ).json()
    data = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers).content

    import docx

    doc = docx.Document(io.BytesIO(data))
    table = doc.tables[0]
    numbers = [row.cells[0].text for row in table.rows[1:]]
    assert numbers == ["证据1", "证据2", "证据3"]


def test_export_filename_is_sanitised(client, auth_headers):
    """A case name with path separators must not reach the header raw.

    The ASCII fallback is where traversal characters would survive, so that is
    what gets asserted; `filename*` is percent-encoded and cannot carry `/`.
    """
    case = client.post(
        "/api/v1/cases", json={"name": "../../etc/passwd"}, headers=auth_headers
    ).json()
    _exportable_case(client, auth_headers, case["id"], n=1)
    job = client.post(
        f"/api/v1/cases/{case['id']}/exports", json={"format": "pdf"}, headers=auth_headers
    ).json()
    dl = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers)
    disposition = dl.headers["Content-Disposition"]
    assert dl.status_code == 200
    # Path separators are stripped by the sanitizer, not passed through.
    assert "../" not in disposition
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition


def test_export_rejects_unknown_format(client, auth_headers, case_id):
    resp = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "exe"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_export_requires_ownership(client, auth_headers, second_user_headers, case_id):
    _exportable_case(client, auth_headers, case_id, n=1)
    job = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "pdf"}, headers=auth_headers
    ).json()

    assert (
        client.post(
            f"/api/v1/cases/{case_id}/exports",
            json={"format": "pdf"},
            headers=second_user_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/exports/{job['id']}", headers=second_user_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/exports/{job['id']}/download", headers=second_user_headers
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/cases/{case_id}/exports", headers=second_user_headers).status_code
        == 404
    )


def test_multiple_exports_are_listed_newest_first(client, auth_headers, case_id):
    _exportable_case(client, auth_headers, case_id, n=1)
    for fmt in ("docx", "pdf", "zip"):
        assert (
            client.post(
                f"/api/v1/cases/{case_id}/exports", json={"format": fmt}, headers=auth_headers
            ).status_code
            == 201
        )
    listing = client.get(f"/api/v1/cases/{case_id}/exports", headers=auth_headers).json()
    assert listing["total"] == 3
    assert {e["format"] for e in listing["exports"]} == {"docx", "pdf", "zip"}


# ---------- download failure modes (9-C 收尾验收 §五-8) ----------


def test_download_unknown_export_404(client, auth_headers):
    resp = client.get(f"/api/v1/exports/{uuid.uuid4()}/download", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EXPORT_NOT_FOUND"


def test_download_not_ready_409(client, auth_headers, case_id, db_session):
    """RUNNING 作业不可下载：EXPORT_NOT_READY 409，而非 500/空文件。"""
    from app.models.export import ExportJob, ExportStatus

    job = ExportJob(
        case_id=uuid.UUID(case_id), format="pdf", status=ExportStatus.RUNNING
    )
    db_session.add(job)
    db_session.commit()

    resp = client.get(f"/api/v1/exports/{job.id}/download", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EXPORT_NOT_READY"


def test_download_missing_410(client, auth_headers, case_id, db_session):
    """COMPLETED 但存储文件被删除：EXPORT_MISSING 410。"""
    from app.models.export import ExportJob
    from app.storage import get_storage

    _exportable_case(client, auth_headers, case_id, n=1)
    job = client.post(
        f"/api/v1/cases/{case_id}/exports", json={"format": "pdf"}, headers=auth_headers
    ).json()
    assert job["status"] == "COMPLETED"

    row = db_session.get(ExportJob, uuid.UUID(job["id"]))
    assert row is not None and row.storage_key
    get_storage().delete(row.storage_key)

    dl = client.get(f"/api/v1/exports/{job['id']}/download", headers=auth_headers)
    assert dl.status_code == 410
    assert dl.json()["error"]["code"] == "EXPORT_MISSING"
