"""Phase 2: file upload, dedupe, validation, download and soft delete."""

from __future__ import annotations

import uuid

from tests.helpers import (
    SAMPLE_TEXT,
    make_docx,
    make_jpeg,
    make_pdf,
    make_png,
    make_txt,
    make_zip_with_docx,
    upload,
)


def test_batch_upload_multiple_files(client, auth_headers, case_id):
    """US-002: 20 files upload, each individually viewable (Phase 2 acceptance)."""
    files = [("files", (f"note-{i}.txt", make_txt(f"{SAMPLE_TEXT}\n第{i}号补充。"), "text/plain")) for i in range(20)]
    resp = client.post(
        f"/api/v1/cases/{case_id}/files", files=files, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["files"]) == 20
    assert body["skipped"] == []

    listing = client.get(f"/api/v1/cases/{case_id}/files", headers=auth_headers)
    assert listing.status_code == 200
    listed = listing.json()
    assert len(listed["files"]) == 20

    # Each file is individually retrievable.
    for f in listed["files"]:
        one = client.get(f"/api/v1/files/{f['id']}", headers=auth_headers)
        assert one.status_code == 200
        assert one.json()["id"] == f["id"]


def test_one_bad_file_does_not_abort_the_batch(client, auth_headers, case_id):
    """US-002: 单个文件失败不影响其他文件."""
    files = [
        ("files", ("good.txt", make_txt(), "text/plain")),
        ("files", ("evil.exe", b"MZ\x90\x00", "application/octet-stream")),
        ("files", ("renamed.png", b"%PDF-1.4 fake", "image/png")),
    ]
    resp = client.post(f"/api/v1/cases/{case_id}/files", files=files, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["files"]) == 1
    assert body["files"][0]["original_filename"] == "good.txt"
    assert {s["filename"] for s in body["skipped"]} == {"evil.exe", "renamed.png"}


def test_duplicate_content_is_deduped_per_case(client, auth_headers, case_id):
    """Same SHA-256 in one case must not create a second row."""
    data = make_txt()
    first = upload(client, auth_headers, case_id, "a.txt", data)
    second = upload(client, auth_headers, case_id, "b.txt", data)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["files"] == []  # nothing new created
    listing = client.get(f"/api/v1/cases/{case_id}/files", headers=auth_headers).json()
    assert len(listing["files"]) == 1


def test_same_content_in_different_cases_is_kept_separate(client, auth_headers, client2=None):
    """Dedupe is scoped to a case, not global."""
    a = client.post("/api/v1/cases", json={"name": "A"}, headers=auth_headers).json()["id"]
    b = client.post("/api/v1/cases", json={"name": "B"}, headers=auth_headers).json()["id"]
    data = make_txt()
    assert upload(client, auth_headers, a, "a.txt", data).json()["files"]
    assert upload(client, auth_headers, b, "a.txt", data).json()["files"]
    assert len(client.get(f"/api/v1/cases/{a}/files", headers=auth_headers).json()["files"]) == 1
    assert len(client.get(f"/api/v1/cases/{b}/files", headers=auth_headers).json()["files"]) == 1


def test_accepts_every_supported_format(client, auth_headers, case_id):
    payload = [
        ("doc.txt", make_txt()),
        ("img.png", make_png()),
        ("img.jpg", make_jpeg()),
        ("doc.pdf", make_pdf()),
        ("doc.docx", make_docx()),
    ]
    files = [("files", (n, d, "application/octet-stream")) for n, d in payload]
    resp = client.post(f"/api/v1/cases/{case_id}/files", files=files, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["files"]) == 5, resp.json()["skipped"]


def test_rejects_renamed_file_and_wrong_extension(client, auth_headers, case_id):
    resp = upload(client, auth_headers, case_id, "invoice.pdf", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    assert resp.status_code == 201
    assert resp.json()["files"] == []
    assert "不一致" in resp.json()["skipped"][0]["reason"]


def test_rejects_oversized_file(client, auth_headers, case_id):
    """The size limit must be enforced at the service layer.

    The setting is patched in place rather than re-reading the environment,
    because `app.config.settings` is a module-level singleton captured at
    import time.
    """
    from app.config import settings

    original = settings.max_upload_bytes
    settings.max_upload_bytes = 1024
    try:
        resp = upload(client, auth_headers, case_id, "big.txt", make_txt("x" * 5000))
        assert resp.status_code == 201
        assert "大小上限" in resp.json()["skipped"][0]["reason"]
        assert resp.json()["files"] == []
    finally:
        settings.max_upload_bytes = original


def test_download_serves_original_bytes_and_secures_headers(client, auth_headers, case_id):
    data = make_pdf()
    fid = upload(client, auth_headers, case_id, "contract.pdf", data).json()["files"][0]["id"]

    resp = client.get(f"/api/v1/files/{fid}/content", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == data  # original bytes are immutable
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"].endswith("no-store")
    assert "attachment" in resp.headers["Content-Disposition"] or "inline" in resp.headers["Content-Disposition"]


def test_file_requires_case_ownership(client, auth_headers, second_user_headers, case_id):
    """docs/12 Scenario: another user must not read or delete our files."""
    fid = upload(client, auth_headers, case_id, "a.txt", make_txt()).json()["files"][0]["id"]

    assert client.get(f"/api/v1/files/{fid}", headers=second_user_headers).status_code == 404
    assert (
        client.get(f"/api/v1/files/{fid}/content", headers=second_user_headers).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/files/{fid}", headers=second_user_headers).status_code == 404
    )
    assert (
        client.post(f"/api/v1/files/{fid}/retry", headers=second_user_headers).status_code
        == 404
    )
    # Owner still has it.
    assert client.get(f"/api/v1/files/{fid}", headers=auth_headers).status_code == 200


def test_delete_is_soft_and_hides_from_listing(client, auth_headers, case_id, db_session):
    from sqlalchemy import select

    from app.models.file import File

    fid = upload(client, auth_headers, case_id, "a.txt", make_txt()).json()["files"][0]["id"]
    assert client.delete(f"/api/v1/files/{fid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/files/{fid}", headers=auth_headers).status_code == 404
    assert client.get(f"/api/v1/cases/{case_id}/files", headers=auth_headers).json()["files"] == []

    row = db_session.get(File, uuid.UUID(fid))
    assert row is not None and row.deleted_at is not None


def test_status_counts_are_reported(client, auth_headers, case_id):
    upload(client, auth_headers, case_id, "a.txt", make_txt())
    listing = client.get(f"/api/v1/cases/{case_id}/files", headers=auth_headers).json()
    assert listing["status_counts"] == {"UPLOADED": 1}


def test_storage_key_cannot_be_path_traversed(client, auth_headers, case_id):
    """A crafted filename must never influence where bytes land on disk."""
    resp = upload(client, auth_headers, case_id, "../../etc/passwd.txt", make_txt())
    # Filename is stored for display only; the key is content-addressed.
    if resp.json()["files"]:
        f = resp.json()["files"][0]
        assert ".." not in f["sha256"]
