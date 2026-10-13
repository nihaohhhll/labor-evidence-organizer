#!/usr/bin/env bash
# End-to-end smoke test against a *running* backend.
#
# Exercises the full MVP loop named in docs/README.md §6 完成标准:
#   创建案件 → 批量上传 → 自动解析 → 查看/修改解析结果 → 生成时间轴
#   → 生成证据目录 → 生成 DOCX/PDF/ZIP → 下载证据包 → 材料缺口分析（A3）
#
# Exits non-zero on the first failed assertion so CI cannot pass on a
# partially working system.
set -euo pipefail

API=${API:-http://127.0.0.1:8000/api/v1}
# Use the project venv so pymupdf/docx are importable when generating fixtures.
PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY=${PY:-"$PROJ/backend/.venv/bin/python"}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() { echo "❌ $*" >&2; exit 1; }
step() { echo; echo "▶ $*"; }

STEP=0
check() {  # check <description> <command...>
  STEP=$((STEP + 1))
  if ! "$@" >/dev/null 2>&1; then
    fail "第 $STEP 步失败：$1"
  fi
  echo "  ✅ $1"
}

step "注册并登录"
EMAIL="e2e-$(date +%s)@example.com"
curl -fsS -X POST "$API/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery\"}" >"$TMP/reg.json"
TOKEN=$("$PY" -c "import json;print(json.load(open('$TMP/reg.json'))['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
echo "  ✅ token 已获取"

step "创建案件"
CASE=$(curl -fsS -X POST "$API/cases" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"E2E 劳动争议案件","description":"端到端冒烟"}' | "$PY" -c "import json,sys;print(json.load(sys.stdin)['id'])")
echo "  ✅ case=$CASE"

step "准备多种格式的测试材料"
"$PY" - "$TMP" <<'PY'
import io, os, sys, zipfile
import pymupdf, docx

tmp = sys.argv[1]
text = ("劳动合同\n甲方：某某科技有限公司\n乙方：张三\n"
        "入职日期：2022年10月1日\n月工资7500元\n")

open(os.path.join(tmp, "劳动合同.txt"), "w", encoding="utf-8").write(text)

d = pymupdf.open(); p = d.new_page()
p.insert_font(fontname="F0", fontfile="/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
p.insert_text((50, 72), text, fontsize=9, fontname="F0")
open(os.path.join(tmp, "工资通知.pdf"), "wb").write(d.tobytes()); d.close()

doc = docx.Document(); doc.add_paragraph(text.strip())
buf = io.BytesIO(); doc.save(buf)
open(os.path.join(tmp, "考勤记录.docx"), "wb").write(buf.getvalue())
print("fixtures ready")
PY

step "批量上传 3 个文件（含多格式）"
UP=$(curl -fsS -X POST "$API/cases/$CASE/files" -H "$AUTH" \
  -F "files=@$TMP/劳动合同.txt" \
  -F "files=@$TMP/工资通知.pdf" \
  -F "files=@$TMP/考勤记录.docx")
COUNT=$("$PY" -c "import json,sys;print(len(json.load(sys.stdin)['files']))" <<<"$UP")
[ "$COUNT" = "3" ] || fail "应上传 3 个文件，实际 $COUNT"
echo "  ✅ 上传成功 $COUNT 个"

step "全部解析"
AN=$(curl -fsS -X POST "$API/cases/$CASE/analyze" -H "$AUTH")
ANALYZED=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['analyzed'])" <<<"$AN")
[ "$ANALYZED" = "3" ] || fail "应解析 3 个文件，实际 $ANALYZED"
echo "  ✅ 解析 $ANALYZED 个"

step "查看解析结果（证据目录已自动生成）"
EV=$(curl -fsS "$API/cases/$CASE/evidence" -H "$AUTH")
EVN=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['total'])" <<<"$EV")
[ "$EVN" = "3" ] || fail "应生成 3 条证据，实际 $EVN"
NUMS=$("$PY" -c "import json,sys;print(sorted(e['evidence_number'] for e in json.load(sys.stdin)['evidence']))" <<<"$EV")
echo "  ✅ 证据 $EVN 条，编号 $NUMS"

step "修改 AI 结果（人工核对）"
EID=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['evidence'][0]['id'])" <<<"$EV")
curl -fsS -X PATCH "$API/evidence/$EID" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"summary":"用户人工核对后的摘要","proof_purpose":"用于证明劳动关系存在的事实。"}' \
  -o "$TMP/edited.json"
EDITED=$("$PY" -c "import json,sys;d=json.load(open('$TMP/edited.json'));print(','.join(d['user_edited_fields']))" )
echo "$EDITED" | grep -q "summary" || fail "用户修改未被记录"
echo "  ✅ 已记录人工修改：$EDITED"

step "重新解析，验证用户修改未被 AI 覆盖"
curl -fsS -X POST "$API/evidence/$EID/reanalyze" -H "$AUTH" -o "$TMP/re.json"
SUM=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['summary'])" <<<"$(cat "$TMP/re.json")")
[ "$SUM" = "用户人工核对后的摘要" ] || fail "用户修改被 AI 覆盖了：$SUM"
echo "  ✅ 用户修改得到保护"

step "确认全部证据"
for ID in $("$PY" -c "import json,sys;print(' '.join(e['id'] for e in json.load(sys.stdin)['evidence']))" <<<"$EV"); do
  curl -fsS -X POST "$API/evidence/$ID/confirm" -H "$AUTH" -o /dev/null
done
echo "  ✅ 全部已确认"

step "生成时间轴"
TL=$(curl -fsS -X POST "$API/cases/$CASE/events/build" -H "$AUTH")
TLN=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['total'])" <<<"$TL")
[ "$TLN" -ge 1 ] || fail "时间轴为空"
echo "  ✅ 时间轴事件 $TLN 个"

step "导出 DOCX / PDF / ZIP"
for FMT in docx pdf zip; do
  JOB=$(curl -fsS -X POST "$API/cases/$CASE/exports" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"format\":\"$FMT\"}")
  JID=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['id'])" <<<"$JOB")
  ST=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['status'])" <<<"$JOB")
  [ "$ST" = "COMPLETED" ] || fail "$FMT 导出状态为 $ST"
  curl -fsS "$API/exports/$JID/download" -H "$AUTH" -o "$TMP/out.$FMT"
  SIZE=$(stat -c%s "$TMP/out.$FMT")
  [ "$SIZE" -gt 500 ] || fail "$FMT 导出文件过小（$SIZE 字节）"
  echo "  ✅ $FMT 导出完成（$SIZE 字节）"
done

step "验证导出内容"
"$PY" - "$TMP" <<'PY'
import io, sys, zipfile, docx, pymupdf
tmp = sys.argv[1]

d = docx.Document(io.BytesIO(open(f"{tmp}/out.docx", "rb").read()))
text = "\n".join(p.text for p in d.paragraphs)
for t in d.tables:
    for r in t.rows:
        text += "\n" + " ".join(c.text for c in r.cells)
assert "证据目录" in text, "DOCX 缺少证据目录"
assert "证据1" in text, "DOCX 缺少证据编号"
assert "案件时间轴" in text, "DOCX 缺少时间轴"
print("  ✅ DOCX 含编号与时间轴")

with pymupdf.open(stream=open(f"{tmp}/out.pdf", "rb").read(), filetype="pdf") as pdf:
    body = "".join(p.get_text("text") for p in pdf)
assert "第 1 页 / 共" in body, "PDF 缺少页码"
print("  ✅ PDF 含「第 X 页 / 共 Y 页」")

with zipfile.ZipFile(f"{tmp}/out.zip") as z:
    names = z.namelist()
    assert "证据目录.docx" in names and "证据目录.pdf" in names, "ZIP 缺少文档"
    assert "证据索引.csv" in names, "ZIP 缺少索引"
    originals = [n for n in names if n.startswith("原始文件/")]
    assert len(originals) >= 3, f"ZIP 原始文件数 {len(originals)} < 3"
print("  ✅ ZIP 含文档、索引与 3 份原始文件")
PY

step "材料缺口分析（A3）"
# 主案件：结构契约 —— SUCCESS、版本、missing_items 键存在。
G1=$(curl -fsS -X POST "$API/cases/$CASE/evidence-gaps" -H "$AUTH")
"$PY" -c "
import json, sys
g = json.loads(sys.argv[1])
assert g['status'] == 'SUCCESS', g['status']
assert g['version'] == 1, g['version']
assert isinstance(g['gap_json']['missing_items'], list), g['gap_json']
print('  ✅ 主案件缺口分析 SUCCESS（缺失项 %d）' % len(g['gap_json']['missing_items']))
" "$G1"
GLATEST=$(curl -fsS "$API/cases/$CASE/evidence-gaps" -H "$AUTH")
GV=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['version'])" <<<"$GLATEST")
[ "$GV" = "1" ] || fail "GET latest 版本应为 1，实际 $GV"
GH=$(curl -fsS "$API/cases/$CASE/evidence-gaps/history" -H "$AUTH")
GT=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['total'])" <<<"$GH")
[ "$GT" = "1" ] || fail "历史总数应为 1，实际 $GT"
echo "  ✅ latest/history 契约正确"

# 专项案件：仅聊天记录 + 事实标签，必须触发 FACT_NO_EXPECTED_TYPE_SOURCE。
GCASE=$(curl -fsS -X POST "$API/cases" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"A3 缺口专项","description":"e2e"}' | "$PY" -c "import json,sys;print(json.load(sys.stdin)['id'])")
printf '微信聊天记录\n[图片]\n张三：公司说让我明天不用来上班了\n李四：收到\n' > "$TMP/聊天记录.txt"
GUP=$(curl -fsS -X POST "$API/cases/$GCASE/files" -H "$AUTH" -F "files=@$TMP/聊天记录.txt")
GF=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['files'][0]['id'])" <<<"$GUP")
curl -fsS -X POST "$API/files/$GF/analyze" -H "$AUTH" -o /dev/null
GE=$(curl -fsS "$API/cases/$GCASE/evidence" -H "$AUTH")
GEID=$("$PY" -c "import json,sys;print(json.load(sys.stdin)['evidence'][0]['id'])" <<<"$GE")
curl -fsS -X PATCH "$API/evidence/$GEID" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"summary":"入职时间：2022-10-01，双方在微信中确认入职安排。","category":"chat_record"}' \
  -o /dev/null
GR=$(curl -fsS -X POST "$API/cases/$GCASE/evidence-gaps" -H "$AUTH")
"$PY" -c "
import json, sys
g = json.loads(sys.argv[1])
items = g['gap_json']['missing_items']
codes = [i['code'] for i in items]
assert 'FACT_NO_EXPECTED_TYPE_SOURCE' in codes, codes
gap = next(i for i in items if i['code'] == 'FACT_NO_EXPECTED_TYPE_SOURCE')
assert gap['sources'], gap
assert set(gap['suggested_evidence_types']) <= {
    'labor_contract', 'company_notice', 'chat_record', 'bank_statement',
    'salary_statement', 'attendance_record', 'social_insurance',
    'identity_document', 'company_registration', 'work_record', 'other',
}, gap['suggested_evidence_types']
assert '必须' not in gap['title'] + gap['description']
print('  ✅ Rule-1 缺口触发且来源/类型词表/措辞闸门通过')
" "$GR"
echo "  ✅ A3 专项案件缺口触发"

step "验证跨用户隔离"
OTHER=$(curl -fsS -X POST "$API/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"other-$(date +%s)@example.com\",\"password\":\"another-good-pass\"}" \
  | "$PY" -c "import json,sys;print(json.load(sys.stdin)['access_token'])")
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$API/cases/$CASE" -H "Authorization: Bearer $OTHER")
[ "$CODE" = "404" ] || fail "他人应无法读取案件（得到 $CODE）"
echo "  ✅ 越权访问返回 404"
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/cases/$CASE/evidence-gaps" -H "Authorization: Bearer $OTHER")
[ "$CODE" = "404" ] || fail "他人 POST 缺口分析应 404（得到 $CODE）"
for GURL in "cases/$CASE/evidence-gaps" "cases/$CASE/evidence-gaps/history"; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "$API/$GURL" -H "Authorization: Bearer $OTHER")
  [ "$CODE" = "404" ] || fail "他人 GET $GURL 应 404（得到 $CODE）"
done
echo "  ✅ 缺口端点越权返回 404"

echo
echo "🎉 端到端全流程通过：上传 → 解析 → 人工核对 → 时间轴 → 导出 → 下载 → 材料缺口"
