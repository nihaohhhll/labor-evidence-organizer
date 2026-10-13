#!/usr/bin/env bash
# End-to-end test of the Phase 9-B material package flow against a *running*
# backend (and the Next dev server, when reachable).
#
# Covers the §7 items that are verifiable over the real HTTP interface the
# UI calls:
#   列表/空状态 → 创建打开草稿 → 添加/移除 → 排序 → 名称与拟证明事项持久化
#   → 审核状态 → 快照 → 快照只读不变 → 跨案件拒绝 → 越权 404
#   → 版本冲突不静默覆盖 → 快照无草稿编辑通道 → 来源异常标注
# UI-only behaviour (dirty markers, confirm dialogs) is covered by vitest.
set -euo pipefail

API=${API:-http://127.0.0.1:8000/api/v1}
WEB=${WEB:-http://127.0.0.1:3000}
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

# json <file|-> <python-expr using d>
json() {
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

step "注册并登录"
EMAIL="e2e-pkg-$(date +%s)@example.com"
curl -fsS -X POST "$API/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery\"}" >"$TMP/reg.json"
TOKEN=$(json "$TMP/reg.json" "d['access_token']")
AUTH="Authorization: Bearer $TOKEN"
echo "  ✅ token 已获取"

step "创建案件并生成两条证据"
CASE=$(curl -fsS -X POST "$API/cases" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"E2E 材料包案件","description":"材料包端到端"}' | json - "d['id']")
printf '劳动合同\n甲方：某某科技有限公司\n入职日期：2022年10月1日\n' >"$TMP/劳动合同.txt"
printf '工资流水\n2023年5月工资 7500 元\n' >"$TMP/工资流水.txt"
curl -fsS -X POST "$API/cases/$CASE/files" -H "$AUTH" \
  -F "files=@$TMP/劳动合同.txt" -F "files=@$TMP/工资流水.txt" >/dev/null
curl -fsS -X POST "$API/cases/$CASE/analyze" -H "$AUTH" >/dev/null
curl -fsS "$API/cases/$CASE/evidence" -H "$AUTH" >"$TMP/ev.json"
EVN=$(json "$TMP/ev.json" "d['total']")
[ "$EVN" -ge 2 ] || fail "需要至少 2 条证据，实际 $EVN"
E1=$(json "$TMP/ev.json" "d['evidence'][0]['id']")
E2=$(json "$TMP/ev.json" "d['evidence'][1]['id']")
echo "  ✅ 证据 $EVN 条"

step "1. 材料包列表为空状态"
req GET "/cases/$CASE/material-packages"
[ "$CODE" = "200" ] || fail "列表应 200，实际 $CODE"
[ "$(json - "d['total']" <<<"$BODY")" = "0" ] || fail "新案件材料包应为空"
echo "  ✅ total=0（空状态）"

step "2. 创建草稿并重新打开"
req POST "/cases/$CASE/material-packages" '{"name":"仲裁材料包 E2E"}'
[ "$CODE" = "201" ] || fail "创建应 201，实际 $CODE：$BODY"
PKG=$(json - "d['id']" <<<"$BODY")
[ "$(json - "d['status']" <<<"$BODY")" = "DRAFT" ] || fail "新包应为 DRAFT"
[ "$(json - "d['draft_version']" <<<"$BODY")" = "1" ] || fail "初始 draft_version 应为 1"
req GET "/material-packages/$PKG"
[ "$CODE" = "200" ] || fail "重新打开草稿失败"
echo "  ✅ pkg=$PKG status=DRAFT v1"

step "3. 添加两条证据"
ITEMS=$(printf '{"evidence_id":"%s","display_name":"劳动合同","proof_purpose":"证明劳动关系存在","review_status":"PENDING"},{"evidence_id":"%s","display_name":"工资流水","proof_purpose":null,"review_status":"PENDING"}' "$E1" "$E2")
req PUT "/material-packages/$PKG/items" "{\"expected_draft_version\":1,\"items\":[$ITEMS]}"
[ "$CODE" = "200" ] || fail "保存条目应 200，实际 $CODE：$BODY"
[ "$(json - "d['item_count']" <<<"$BODY")" = "2" ] || fail "条目数应为 2"
[ "$(json - "d['draft_version']" <<<"$BODY")" = "2" ] || fail "保存后 draft_version 应为 2"
echo "  ✅ 2 条已保存，v2"

step "4. 移除条目只影响草稿，不删原始证据"
req PUT "/material-packages/$PKG/items" "{\"expected_draft_version\":2,\"items\":[{\"evidence_id\":\"$E1\",\"display_name\":\"劳动合同\"}]}"
[ "$CODE" = "200" ] || fail "移除条目失败"
[ "$(json - "d['item_count']" <<<"$BODY")" = "1" ] || fail "移除后应剩 1 条"
curl -fsS "$API/cases/$CASE/evidence" -H "$AUTH" | json - "d['total']" >"$TMP/evn2"
[ "$(cat "$TMP/evn2")" = "$EVN" ] || fail "移除条目后原始证据被改动了"
echo "  ✅ 草稿 1 条，原始证据仍 $EVN 条"

step "5. 调整顺序 + 名称/拟证明事项/审核状态（v3）"
ITEMS=$(printf '{"evidence_id":"%s","display_name":"工资流水（2023-05）","proof_purpose":"证明月工资标准","review_status":"APPROVED"},{"evidence_id":"%s","display_name":"劳动合同（首份）","proof_purpose":"证明劳动关系存续","review_status":"PENDING"}' "$E2" "$E1")
req PUT "/material-packages/$PKG/items" "{\"expected_draft_version\":3,\"items\":[$ITEMS]}"
[ "$CODE" = "200" ] || fail "排序保存失败：$BODY"
[ "$(json - "d['items'][0]['evidence_id']" <<<"$BODY")" = "$E2" ] || fail "顺序未生效（首条应为 E2）"
[ "$(json - "d['items'][0]['display_number']" <<<"$BODY")" = "1" ] || fail "首条编号应为 1"
[ "$(json - "d['items'][1]['display_number']" <<<"$BODY")" = "2" ] || fail "次条编号应为 2"
echo "  ✅ 顺序与编号生效"

step "6. 刷新后（重新 GET）名称/拟证明事项/审核状态保留"
req GET "/material-packages/$PKG"
[ "$(json - "d['items'][0]['display_name']" <<<"$BODY")" = "工资流水（2023-05）" ] || fail "展示名称未保留"
[ "$(json - "d['items'][0]['proof_purpose']" <<<"$BODY")" = "证明月工资标准" ] || fail "拟证明事项未保留"
[ "$(json - "d['items'][0]['review_status']" <<<"$BODY")" = "APPROVED" ] || fail "审核状态未保留"
[ "$(json - "d['items'][1]['review_status']" <<<"$BODY")" = "PENDING" ] || fail "PENDING 状态未保留"
echo "  ✅ 持久化验证通过"

step "7. 创建快照并读取只读历史"
req POST "/material-packages/$PKG/snapshots" '{"expected_draft_version":4}'
[ "$CODE" = "201" ] || fail "创建快照应 201，实际 $CODE：$BODY"
[ "$(json - "d['version']" <<<"$BODY")" = "1" ] || fail "快照版本应为 1"
req GET "/material-packages/$PKG/snapshots"
[ "$(json - "d['total']" <<<"$BODY")" = "1" ] || fail "快照列表应为 1"
req GET "/material-packages/$PKG/snapshots/1"
[ "$CODE" = "200" ] || fail "快照详情读取失败"
[ "$(json - "d['content']['items'][0]['display_name']" <<<"$BODY")" = "工资流水（2023-05）" ] || fail "快照内容缺失"
echo "  ✅ 快照 v1 已归档"

step "8. 快照不随草稿变化（改草稿后快照仍为旧内容）"
ITEMS=$(printf '{"evidence_id":"%s","display_name":"工资流水（已修改）","proof_purpose":"草稿新内容","review_status":"PENDING"},{"evidence_id":"%s","display_name":"劳动合同（首份）","proof_purpose":"证明劳动关系存续","review_status":"PENDING"}' "$E2" "$E1")
req PUT "/material-packages/$PKG/items" "{\"expected_draft_version\":4,\"items\":[$ITEMS]}"
[ "$CODE" = "200" ] || fail "草稿再保存失败"
req GET "/material-packages/$PKG/snapshots/1"
[ "$(json - "d['content']['items'][0]['display_name']" <<<"$BODY")" = "工资流水（2023-05）" ] || fail "快照被草稿改动污染了！"
[ "$(json - "d['content']['items'][0]['proof_purpose']" <<<"$BODY")" = "证明月工资标准" ] || fail "快照拟证明事项被污染！"
echo "  ✅ 快照内容保持归档时状态"

step "9. 并发版本冲突返回 409，不静默覆盖"
req PUT "/material-packages/$PKG/items" "{\"expected_draft_version\":3,\"items\":[{\"evidence_id\":\"$E1\"}]}"
[ "$CODE" = "409" ] || fail "过期版本应 409，实际 $CODE"
grep -q "VERSION_CONFLICT" <<<"$BODY" || fail "应返回 VERSION_CONFLICT：$BODY"
req GET "/material-packages/$PKG"
[ "$(json - "d['items'][0]['display_name']" <<<"$BODY")" = "工资流水（已修改）" ] || fail "冲突保存覆盖了现有草稿！"
echo "  ✅ 409 VERSION_CONFLICT，数据未被覆盖"

step "10. 跨案件证据被拒绝（与不存在同错，防探测）"
CASE2=$(curl -fsS -X POST "$API/cases" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"E2E 第二案件"}' | json - "d['id']")
printf '考勤\n迟到三次\n' >"$TMP/考勤.txt"
curl -fsS -X POST "$API/cases/$CASE2/files" -H "$AUTH" -F "files=@$TMP/考勤.txt" >/dev/null
curl -fsS -X POST "$API/cases/$CASE2/analyze" -H "$AUTH" >/dev/null
EX=$(curl -fsS "$API/cases/$CASE2/evidence" -H "$AUTH" | json - "d['evidence'][0]['id']")
req PUT "/material-packages/$PKG/items" "{\"expected_draft_version\":5,\"items\":[{\"evidence_id\":\"$EX\"}]}"
[ "$CODE" -ge 400 ] || fail "跨案件证据应被拒绝，实际 $CODE"
grep -q "EVIDENCE_NOT_FOUND" <<<"$BODY" || fail "应返回 EVIDENCE_NOT_FOUND：$BODY"
echo "  ✅ 跨案件证据被拒绝"

step "11. 越权访问返回 404"
OTHER=$(curl -fsS -X POST "$API/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"other-pkg-$(date +%s)@example.com\",\"password\":\"another-good-pass\"}" \
  | json - "d['access_token']")
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$API/material-packages/$PKG" \
  -H "Authorization: Bearer $OTHER")
[ "$CODE" = "404" ] || fail "他人应无法读取材料包（得到 $CODE）"
echo "  ✅ 越权 404"

step "12. 快照没有草稿编辑通道"
for M in PUT PATCH DELETE; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' -X "$M" "$API/material-packages/$PKG/snapshots/1" \
    -H "$AUTH" -H 'Content-Type: application/json' -d '{}')
  case "$CODE" in
    404|405) ;;
    *) fail "$M 快照应 404/405，实际 $CODE" ;;
  esac
done
echo "  ✅ 快照只读（无写方法路由）"

step "13. 来源证据异常标注（直接操作开发库）"
# 删除快照引用的证据行，模拟来源异常；随后快照必须显式标注 MISSING。
# 失败（外键/权限）则诚实标注跳过，不计为通过。
if "$PY" -c "
import sys
sys.path.insert(0, '$PROJ/backend')
from app.config import settings
from sqlalchemy import create_engine, text
eng = create_engine(settings.database_url)
with eng.begin() as c:
    c.execute(text('DELETE FROM material_package_items WHERE evidence_id = :e'), {'e': sys.argv[1]})
    c.execute(text('DELETE FROM evidence WHERE id = :e'), {'e': sys.argv[1]})
" "$E1"; then
  req GET "/material-packages/$PKG/snapshots/1"
  ST=$(json - "d['content']['items'][1]['source_status']" <<<"$BODY" 2>/dev/null || echo "?")
  [ "$ST" = "MISSING" ] || fail "来源证据删除后应标注 MISSING，实际 $ST"
  echo "  ✅ source_status=MISSING（显式异常，不静默替换）"
else
  echo "  ⚠️ 无法删除来源证据（外键/权限），跳过该步（未执行，不计为通过）"
fi

step "14. 前端材料包路由可达（dev server 运行时）"
if curl -s -o /dev/null -w '%{http_code}' "$WEB/cases" | grep -q 200; then
  for P in \
    "/cases/$CASE/material-packages" \
    "/cases/$CASE/material-packages/new" \
    "/cases/$CASE/material-packages/$PKG/edit" \
    "/cases/$CASE/material-packages/$PKG/history" \
    "/cases/$CASE/material-packages/$PKG/history/1"; do
    C=$(curl -s -o /dev/null -w '%{http_code}' "$WEB$P")
    [ "$C" = "200" ] || fail "页面 $P 返回 $C"
  done
  echo "  ✅ 5 个前端路由均返回 200"
else
  echo "  ⚠️ 前端未运行，跳过路由探活（未执行，不计为通过）"
fi

echo
echo "🎉 材料包端到端通过：创建 → 编辑 → 排序 → 保存 → 快照 → 只读历史 → 冲突防护 → 权限隔离"
