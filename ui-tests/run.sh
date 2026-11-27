#!/usr/bin/env bash
# End-to-end UI tests: loads the real front-end modules in jsdom and drives them against a LIVE server.
# Prerequisites (in the project root):  python manage.py migrate && python manage.py seed_demo --with-requests
#                                       python manage.py runserver        (or set BASE=http://host:port)
# Use a throw-away database: these tests create, approve, reject and cancel real records.
# Start the server with the file email backend so the tests can read the 6-digit codes:
#   THROTTLE_LOGIN=1000/min THROTTLE_CODE=1000/min THROTTLE_REGISTER=1000/min \
#   EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend EMAIL_FILE_PATH=sent_emails python manage.py runserver
# (the raised limits are only so a test run is not rate-limited; keep the defaults in production)
set -u
cd "$(dirname "$0")"
BASE="${BASE:-http://127.0.0.1:8000}"; export BASE
HRTOK=$(curl -s -X POST "$BASE/api/auth/login/" -H 'Content-Type: application/json' -d '{"username":"hr","password":"Passw0rd!123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])") || { echo "Cannot reach $BASE"; exit 1; }
export TMP_PW=$(curl -s -X POST "$BASE/api/users/" -H "Authorization: Token $HRTOK" -H 'Content-Type: application/json' -d '{"username":"t.force","email":"tf@example.com","first_name":"Force","last_name":"Change"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('temporary_password',''))")
ALL="/dashboard,/apply,/leave,/calendar,/approvals,/delegation,/account,/hr/requests,/hr/reports,/hr/people,/hr/policies,/hr/audit"
fail=0
for pair in "staff1:staff" "staff1:nav" "staff2:account" "sup.eng:approver" "hr:hr" "anon:anon" "anon:force"; do
  u=${pair%%:*}; f=${pair##*:}; echo "=== $u / $f"
  out=$(timeout 150 node run.mjs "$u" "" "$f" 2>&1 | grep -v "Not implemented" | grep -vE "^--- |^$"); echo "$out"
  echo "$out" | grep -qE "^FAIL|Error|ERRORS" && fail=1
done
for u in staff1 sup.eng hr admin; do timeout 90 node run.mjs "$u" "$ALL" 2>&1 | grep -E "^FAIL" | grep -v "access to this page" && fail=1; done
[ $fail = 0 ] && echo "ALL UI CHECKS PASSED" || { echo "SOME UI CHECKS FAILED"; exit 1; }
