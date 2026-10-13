#!/usr/bin/env bash
# Phase 9-D-2: end-to-end verification of the real desensitised material
# suite (M1-M12) against a *running* backend, over the real HTTP interface.
#
# Covers:
#   1. 材料矩阵 M1-M12 逐份上传/解析/状态断言（含失败与拒绝样本）
#   2. M1 七跳可追溯链：file → analysis → evidence → 人工修订/确认
#      → 时间轴 → 材料包条目 → 快照 content → 导出 DOCX/PDF 文本
#   3. mock OCR 空文本行为固化（M5/M6/M7）
#   4. 文件名中英文回退（M11）
#
# Exits non-zero on the first failed assertion.
set -euo pipefail

API=${API:-http://127.0.0.1:8000/api/v1}
PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY=${PY:-"$PROJ/backend/.venv/bin/python"}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() { echo "❌ $*" >&2; exit 1; }
step() { echo; echo "▶ $*"; }

json() {  # json <file|-> <python-expr using d>
  if [ "$1" = "-" ]; then
    "$PY" -c "
import json,sys
d=json.load(sys.stdin)
print($2)
"
  else
    "$PY" -c "
import json,sys
d=json.load(open('$1'))
print($2)
"
  fi
}

req() {  # req <method> <path> [body]  → sets CODE and BODY
  local method=$1 path=$2 body=${3:-}
  if [ -n "$body" ]; then
    BODY=$(curl -s -w '\n%{http_code}' -X "$method" "$API$path" -H "$AUTH" \
      -H 'Content-Type: application/json' -d "$body")
  else
    BODY=$(curl -s -w '\n%{http_code}' -X "$method" "$API$path" -H "$AUTH")
  fi
  CODE=$(tail -n1 <<<"$BODY")
  BODY=$(sed '$d' <<<"$BODY")
}

# ---------- setup ----------

step "注册并登录"
EMAIL="e2e-real-$(date +%s)@example.com"
curl -fsS -X POST "$API/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery\"}" >"$TMP/reg.json"
TOKEN=$(json "$TMP/reg.json" "d['access_token']")
AUTH="Authorization: Bearer $TOKEN"
echo "  ✅ token 已获取"

step "生成材料套件 M1-M12"
"$PY" "$PROJ/scripts/make-real-materials.py" "$TMP/mat" >"$TMP/gen.log" \
  || { cat "$TMP/gen.log" >&2; fail "材料生成失败"; }
grep -q "已生成 13 份材料" "$TMP/gen.log" || fail "生成数量不对：$(cat "$TMP/gen.log")"
echo "  ✅ 13 份材料已生成"

step "创建案件"
CASE=$(curl -fsS -X POST "$API/cases" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"9-D 真实材料验证","description":"M1-M12 端到端"}' | json - "d['id']")
echo "  ✅ case=$CASE"

# ---------- uploads ----------

step "上传 10 份合法材料（M1-M8, M11, M12）"
UP_ARGS=()
for f in "劳动合同.pdf" "工资条.txt" "聊天记录.txt" "考勤表.docx" \
         "聊天截图.png" "工资条照片.jpg" "扫描件.pdf" "损坏文件.pdf" \
         "劳动合同（最终版）；附页 v2.pdf" "多页混合.pdf"; do
  UP_ARGS+=(-F "files=@$TMP/mat/$f")
done
curl -fsS -X POST "$API/cases/$CASE/files" -H "$AUTH" "${UP_ARGS[@]}" >"$TMP/up_good.json"
GOOD_N=$(json "$TMP/up_good.json" "len(d['files'])")
SKIP_N=$(json "$TMP/up_good.json" "len(d['skipped'])")
[ "$GOOD_N" = "10" ] || fail "应上传 10 个合法文件，实际 $GOOD_N，skipped=$SKIP_N: $(cat "$TMP/up_good.json")"
[ "$SKIP_N" = "0" ] || fail "合法批次不应有 skipped：$(cat "$TMP/up_good.json")"
echo "  ✅ 10 个文件全部创建"

# Map material id → file id via manifest sha256 / filename.
"$PY" - "$TMP" <<'PY'
import json, sys
tmp = sys.argv[1]
manifest = {m["id"]: m for m in json.load(open(f"{tmp}/mat/manifest.json"))}
uploaded = json.load(open(f"{tmp}/up_good.json"))["files"]
by_name = {f["original_filename"]: f for f in uploaded}
ids = {}
for mid, m in manifest.items():
    if m["expect"]["kind"] != "good":
        continue
    f = by_name[m["filename"]]
    assert f["sha256"] == m["sha256"], f"{mid} sha256 不一致"
    ids[mid] = f["id"]
json.dump(ids, open(f"{tmp}/file_ids.json", "w"))
print(f"  ✅ sha256 全部与 manifest 一致，映射 {len(ids)} 个文件")
PY

step "上传 3 份拒绝样本（M9 超大 / M10a HTML 伪装 / M10b 脚本伪装）"
curl -s -X POST "$API/cases/$CASE/files" -H "$AUTH" \
  -F "files=@$TMP/mat/超大文件.txt" \
  -F "files=@$TMP/mat/伪装.txt" \
  -F "files=@$TMP/mat/伪装截图.png" >"$TMP/up_bad.json"
"$PY" - "$TMP" <<'PY'
import json, sys
tmp = sys.argv[1]
d = json.load(open(f"{tmp}/up_bad.json"))
assert len(d["files"]) == 0, f"拒绝样本不应创建文件：{d}"
assert len(d["skipped"]) == 3, f"应 skipped 3 个：{d}"
reasons = {s["filename"]: s["reason"] for s in d["skipped"]}
assert "大小上限" in reasons["超大文件.txt"], reasons
assert reasons["伪装.txt"] == "文件内容与扩展名不一致。", reasons
assert reasons["伪装截图.png"] == "文件内容与扩展名不一致。", reasons
print("  ✅ M9/M10a/M10b 全部拒绝，原因正确")
PY

# ---------- batch analyze ----------

step "批量解析（M8 预期失败，其余成功）"
AN=$(curl -fsS -X POST "$API/cases/$CASE/analyze" -H "$AUTH")
ANALYZED=$(json - "d['analyzed']" <<<"$AN")
FAILED_N=$(json - "d['failed']" <<<"$AN")
[ "$ANALYZED" = "9" ] || fail "应解析成功 9 个（10-M8），实际 $ANALYZED"
[ "$FAILED_N" = "1" ] || fail "应失败 1 个（M8），实际 $FAILED_N"
echo "  ✅ analyzed=9 failed=1"

# ---------- per-material assertions ----------

step "逐份断言分析结果（M1-M7, M11, M12）"
"$PY" - "$TMP" "$API" <<'PY'
import json, sys, urllib.request
tmp, api = sys.argv[1], sys.argv[2]
token = json.load(open(f"{tmp}/reg.json"))["access_token"]
ids = json.load(open(f"{tmp}/file_ids.json"))
manifest = {m["id"]: m for m in json.load(open(f"{tmp}/mat/manifest.json"))}

def get(path):
    req = urllib.request.Request(api + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def get_status(path):
    """Return (status_code, parsed_body_or_None)."""
    req = urllib.request.Request(api + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

for mid, fid in ids.items():
    exp = manifest[mid]["expect"]
    if mid == "M8":
        f = get(f"/files/{fid}")
        assert f["status"] == "FAILED", f"{mid} 状态应 FAILED，实际 {f['status']}"
        assert f["error_message"], f"{mid} 应有错误信息"
        # A failed file has no successful analysis row → 404 is the expected outcome.
        code, body = get_status(f"/files/{fid}/analysis")
        assert code == 404, f"{mid} analysis 应 404，实际 {code}: {body}"
        print(f"  ✅ {mid} FAILED + error_message 可见 + analysis 404")
        continue
    a = get(f"/files/{fid}/analysis")
    assert a["classification"] == exp["classification"], \
        f"{mid} classification={a['classification']}，预期 {exp['classification']}"
    if "confidence_min" in exp:
        assert a["confidence"] >= exp["confidence_min"], \
            f"{mid} confidence={a['confidence']} < {exp['confidence_min']}"
    if "confidence" in exp:
        assert a["confidence"] == exp["confidence"], \
            f"{mid} confidence={a['confidence']}，预期 {exp['confidence']}"
    if "dates_include" in exp:
        for dt in exp["dates_include"]:
            assert dt in a["dates"], f"{mid} dates 缺 {dt}: {a['dates']}"
    if "amounts_include" in exp:
        for am in exp["amounts_include"]:
            assert am in a["amounts"], f"{mid} amounts 缺 {am}: {a['amounts']}"
    if "amounts_min" in exp:
        assert len(a["amounts"]) >= exp["amounts_min"], \
            f"{mid} amounts={len(a['amounts'])} < {exp['amounts_min']}: {a['amounts']}"
    if "orgs_include" in exp:
        for og in exp["orgs_include"]:
            assert og in a["organizations"], f"{mid} orgs 缺 {og}: {a['organizations']}"
    if exp.get("raw_text_empty"):
        assert not (a.get("raw_text") or "").strip(), \
            f"{mid} raw_text 应为空，实际 {a.get('raw_text')!r:.80}"
    for s in exp.get("raw_text_include", []):
        assert s in (a.get("raw_text") or ""), f"{mid} raw_text 缺 {s!r}"
    for s in exp.get("raw_text_exclude", []):
        assert s not in (a.get("raw_text") or ""), f"{mid} raw_text 不应含 {s!r}"
    print(f"  ✅ {mid} 分析断言通过（{exp.get('classification', 'FAILED')}）")
PY

step "M8 失败态：直接解析 409 → 重试 → 再解析 422（状态机闭环）"
M8=$(json "$TMP/file_ids.json" "d['M8']")
req POST "/files/$M8/analyze"
[ "$CODE" = "409" ] || fail "M8 失败态直接解析应 409，实际 $CODE"
grep -q "INVALID_TRANSITION" <<<"$BODY" \
  || fail "M8 错误码应为 INVALID_TRANSITION：$BODY"
req POST "/files/$M8/retry"
[ "$CODE" = "200" ] || fail "M8 重试应 200，实际 $CODE"
[ "$(json - "d['status']" <<<"$BODY")" = "QUEUED" ] || fail "M8 重试后应 QUEUED：$BODY"
req POST "/files/$M8/analyze"
[ "$CODE" = "422" ] || fail "M8 重试后解析应 422，实际 $CODE"
grep -q "PARSE_FAILED" <<<"$BODY" \
  || fail "M8 错误码应为 PARSE_FAILED：$BODY"
req GET "/files/$M8"
[ "$(json - "d['status']" <<<"$BODY")" = "FAILED" ] || fail "M8 二次解析后应 FAILED"
[ -n "$(json - "d['error_message']" <<<"$BODY")" ] || fail "M8 应保留错误信息"
echo "  ✅ 409 INVALID_TRANSITION → retry QUEUED → 422 PARSE_FAILED → FAILED"

step "M5/M6/M7 证据自动创建且为空文本兜底"
"$PY" - "$TMP" "$API" <<'PY'
import json, sys, urllib.request
tmp, api = sys.argv[1], sys.argv[2]
token = json.load(open(f"{tmp}/reg.json"))["access_token"]
ids = json.load(open(f"{tmp}/file_ids.json"))
case = json.load(open(f"{tmp}/up_good.json"))["files"][0]["case_id"]

def get(path):
    req = urllib.request.Request(api + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

ev = get(f"/cases/{case}/evidence")["evidence"]
by_file = {e["source_file_id"]: e for e in ev if e.get("source_file_id")}
for mid in ("M5", "M6", "M7"):
    e = by_file[ids[mid]]
    assert e["category"] == "other", f"{mid} category={e['category']}"
    assert e["summary"] == "材料内容为空或无法识别。", f"{mid} summary={e['summary']!r}"
    assert e["review_status"] == "PENDING", f"{mid} review_status={e['review_status']}"
    assert e["event_date"] is None, f"{mid} event_date 应为空：{e['event_date']}"
print("  ✅ M5/M6/M7 证据 PENDING、category=other、空文本兜底摘要")
PY

step "M11 文件名精确回退 + 下载头"
M11=$(json "$TMP/file_ids.json" "d['M11']")
M11_NAME='劳动合同（最终版）；附页 v2.pdf'
req GET "/files/$M11"
[ "$(json - "d['original_filename']" <<<"$BODY")" = "$M11_NAME" ] || fail "M11 文件名不一致：$BODY"
HDR=$(curl -s -o /dev/null -D - "$API/files/$M11/content" -H "$AUTH")
"$PY" - "$HDR" "$M11_NAME" <<'PY'
import sys
from urllib.parse import unquote
hdr, name = sys.argv[1], sys.argv[2]
line = next(l for l in hdr.splitlines() if l.lower().startswith("content-disposition"))
assert 'filename="v2.pdf"' in line, f"ASCII 回退应为 v2.pdf：{line}"
assert "filename*=UTF-8''" in line, f"缺 filename*：{line}"
encoded = line.split("filename*=UTF-8''", 1)[1].strip()
assert unquote(encoded) == name, f"filename* 解码不一致：{unquote(encoded)!r} != {name!r}"
print("  ✅ 下载头 ASCII 回退 v2.pdf + filename* 精确还原")
PY

# ---------- M1 seven-hop traceability chain ----------

step "可追溯链 1/7：file 行（sha256 + 下载字节一致性）"
M1=$(json "$TMP/file_ids.json" "d['M1']")
req GET "/files/$M1"
[ "$(json - "d['status']" <<<"$BODY")" = "COMPLETED" ] || fail "M1 应 COMPLETED：$BODY"
M1_SHA=$(json - "d['sha256']" <<<"$BODY")
[ "$M1_SHA" = "$(json "$TMP/mat/manifest.json" "[m['sha256'] for m in d if m['id']=='M1'][0]")" ] \
  || fail "M1 sha256 与 manifest 不符"
curl -fsS "$API/files/$M1/content" -H "$AUTH" -o "$TMP/m1_dl.pdf"
DL_SHA=$(sha256sum "$TMP/m1_dl.pdf" | cut -d' ' -f1)
[ "$DL_SHA" = "$M1_SHA" ] || fail "下载字节 sha256 不一致：$DL_SHA != $M1_SHA"
echo "  ✅ DB sha256 == manifest sha256 == 下载字节 sha256"

step "可追溯链 2/7：analysis 行（provider/prompt_version/结构化字段）"
req GET "/files/$M1/analysis"
[ "$CODE" = "200" ] || fail "M1 分析应存在：$CODE $BODY"
[ "$(json - "d['provider']" <<<"$BODY")" = "mock" ] || fail "provider 应为 mock"
[ "$(json - "d['prompt_version']" <<<"$BODY")" = "evidence-extraction-v1" ] || fail "prompt_version 不符"
[ "$(json - "d['classification']" <<<"$BODY")" = "labor_contract" ] || fail "classification 不符"
json - "'2022-10-01' in d['dates']" <<<"$BODY" | grep -q True || fail "dates 缺 2022-10-01"
json - "'7500元' in d['amounts']" <<<"$BODY" | grep -q True || fail "amounts 缺 7500元"
echo "  ✅ provider=mock prompt_version=evidence-extraction-v1 classification=labor_contract"

step "可追溯链 3/7：evidence 行（自动创建 PENDING，编号/证明目的）"
CASE_ID="$CASE"
EV=$(curl -fsS "$API/cases/$CASE_ID/evidence" -H "$AUTH")
M1_EV=$(json - "next(e['id'] for e in d['evidence'] if e['source_file_id']=='$M1')" <<<"$EV")
M1_NUM=$(json - "next(e['evidence_number'] for e in d['evidence'] if e['source_file_id']=='$M1')" <<<"$EV")
M1_STATUS=$(json - "next(e['review_status'] for e in d['evidence'] if e['source_file_id']=='$M1')" <<<"$EV")
[ "$M1_STATUS" = "PENDING" ] || fail "M1 证据应初始 PENDING：$M1_STATUS"
M1_EVDATE=$(json - "next(str(e['event_date']) for e in d['evidence'] if e['source_file_id']=='$M1')" <<<"$EV")
[ "$M1_EVDATE" = "2022-10-01" ] || fail "M1 event_date 应 2022-10-01：$M1_EVDATE"
echo "  ✅ evidence=$M1_EV 编号=证据$M1_NUM PENDING event_date=$M1_EVDATE"

step "可追溯链 4/7：人工修订 → reanalyze 保护 → 确认 CONFIRMED"
req PATCH "/evidence/$M1_EV" '{"summary":"用户核对：入职2022-10-01，月工资7500元。","proof_purpose":"用于证明双方自2022年10月1日起存在劳动关系及约定工资标准。"}'
[ "$CODE" = "200" ] || fail "修订失败：$CODE $BODY"
EDITED=$(json - "','.join(d['user_edited_fields'])" <<<"$BODY")
echo "$EDITED" | grep -q summary || fail "user_edited_fields 未记录 summary：$EDITED"
req POST "/evidence/$M1_EV/reanalyze"
[ "$CODE" = "200" ] || fail "reanalyze 失败：$CODE $BODY"
SUM=$(json - "d['summary']" <<<"$BODY")
[ "$SUM" = "用户核对：入职2022-10-01，月工资7500元。" ] || fail "reanalyze 覆盖了人工 summary：$SUM"
req POST "/evidence/$M1_EV/confirm"
[ "$CODE" = "200" ] || fail "确认失败：$CODE"
[ "$(json - "d['review_status']" <<<"$BODY")" = "CONFIRMED" ] || fail "确认后应 CONFIRMED"
echo "  ✅ 修订已记录、reanalyze 未覆盖、已 CONFIRMED"

step "可追溯链 5/7：时间轴事件关联该证据"
req POST "/cases/$CASE_ID/events/build"
[ "$CODE" = "200" ] || fail "时间轴构建失败：$CODE"
TLN=$(json - "d['total']" <<<"$BODY")
[ "$TLN" -ge 1 ] || fail "时间轴为空"
HAS=$(json - "any(e['event_date']=='2022-10-01' for e in d['events'])" <<<"$BODY")
[ "$HAS" = "True" ] || fail "时间轴缺 2022-10-01 事件：$BODY"
echo "  ✅ 时间轴含 2022-10-01 事件（共 $TLN 个）"

step "可追溯链 6/7：材料包条目 + 快照 content"
req POST "/cases/$CASE_ID/material-packages" '{"name":"9-D 验证卷"}'
[ "$CODE" = "201" ] || fail "创建材料包失败：$CODE $BODY"
PKG=$(json - "d['id']" <<<"$BODY")
ITEMS_BODY=$(printf '{"expected_draft_version":1,"items":[{"evidence_id":"%s","display_name":"劳动合同（证明劳动关系）","proof_purpose":"用于证明双方自2022年10月1日起存在劳动关系及约定工资标准。"}]}' "$M1_EV")
req PUT "/material-packages/$PKG/items" "$ITEMS_BODY"
[ "$CODE" = "200" ] || fail "保存条目失败：$CODE $BODY"
[ "$(json - "d['items'][0]['display_number']" <<<"$BODY")" = "1" ] || fail "display_number 应为 1"
[ "$(json - "d['items'][0]['evidence_number']" <<<"$BODY")" = "$M1_NUM" ] || fail "evidence_number 不符"
[ "$(json - "d['items'][0]['source_file_id']" <<<"$BODY")" = "$M1" ] || fail "source_file_id 不符"
req POST "/material-packages/$PKG/snapshots" '{"expected_draft_version":2}'
[ "$CODE" = "201" ] || fail "创建快照失败：$CODE $BODY"
SNAP_V=$(json - "d['version']" <<<"$BODY")
req GET "/material-packages/$PKG/snapshots/$SNAP_V"
[ "$CODE" = "200" ] || fail "读取快照失败"
"$PY" - "$BODY" "$M1" "$M1_EV" "$M1_NUM" <<'PY'
import json, sys
snap, fid, evid, num = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
item = snap["content"]["items"][0]
assert item["display_number"] == 1
assert item["evidence_id"] == evid
assert item["source_file_id"] == fid
assert item["evidence_number"] == num
assert item["display_name"] == "劳动合同（证明劳动关系）"
assert "2022年10月1日" in item["proof_purpose"]
print("  ✅ 快照 content 逐字段比对通过")
PY

step "可追溯链 7/7：导出 DOCX/PDF 文本含编号/名称/拟证明事项/原文片段"
for FMT in docx pdf; do
  req POST "/material-packages/$PKG/exports" "{\"format\":\"$FMT\"}"
  [ "$CODE" = "201" ] || fail "$FMT 导出创建失败：$CODE $BODY"
  JID=$(json - "d['id']" <<<"$BODY")
  [ "$(json - "d['status']" <<<"$BODY")" = "COMPLETED" ] || fail "$FMT 导出未完成：$BODY"
  curl -fsS "$API/exports/$JID/download" -H "$AUTH" -o "$TMP/pkg_out.$FMT"
done
"$PY" - "$TMP" <<'PY'
import io, sys, docx, pymupdf
tmp = sys.argv[1]
d = docx.Document(io.BytesIO(open(f"{tmp}/pkg_out.docx", "rb").read()))
text = "\n".join(p.text for p in d.paragraphs)
for t in d.tables:
    for r in t.rows:
        text += "\n" + " ".join(c.text for c in r.cells)
for needle in ("材料1", "劳动合同（证明劳动关系）", "拟证明事项", "2022年10月1日", "7500元"):
    assert needle in text, f"DOCX 缺 {needle!r}"
with pymupdf.open(f"{tmp}/pkg_out.pdf") as pdf:
    body = "".join(p.get_text("text") for p in pdf)
for needle in ("材料1", "劳动合同（证明劳动关系）", "拟证明事项"):
    assert needle in body, f"PDF 缺 {needle!r}"
print("  ✅ DOCX/PDF 均含材料编号、名称、拟证明事项与原文片段")
PY

step "案件级导出回归（证据目录 + 时间轴来源证据）"
req POST "/cases/$CASE_ID/exports" '{"format":"docx"}'
[ "$CODE" = "201" ] || fail "案件导出失败：$CODE"
JID=$(json - "d['id']" <<<"$BODY")
curl -fsS "$API/exports/$JID/download" -H "$AUTH" -o "$TMP/case_out.docx"
"$PY" - "$TMP" "$M1_NUM" <<'PY'
import io, sys, docx
tmp, num = sys.argv[1], sys.argv[2]
d = docx.Document(io.BytesIO(open(f"{tmp}/case_out.docx", "rb").read()))
text = "\n".join(p.text for p in d.paragraphs)
for t in d.tables:
    for r in t.rows:
        text += "\n" + " ".join(c.text for c in r.cells)
assert "证据目录" in text
assert f"证据{num}" in text, f"缺 证据{num}"
assert "案件时间轴" in text
assert f"证据{num}" in text  # 来源证据列
print(f"  ✅ 案件导出含 证据{num} 与时间轴")
PY

step "M3 聊天记录分类为 chat_record（高置信结构检测）"
M3=$(json "$TMP/file_ids.json" "d['M3']")
req GET "/files/$M3/analysis"
[ "$(json - "d['classification']" <<<"$BODY")" = "chat_record" ] || fail "M3 classification 不符：$BODY"
json - "d['confidence'] >= 0.9" <<<"$BODY" | grep -q True || fail "M3 置信度应 >=0.9：$BODY"
echo "  ✅ chat_record 置信度 $(json - "d['confidence']" <<<"$BODY")"

echo
echo "🎉 全部通过：M1-M12 材料矩阵 + M1 七跳可追溯链 + mock OCR 空文本固化"
