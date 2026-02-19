#!/usr/bin/env bash
# =============================================================================
# Digestor Unified - Post-Deployment Smoke Test
# Usage: ./scripts/smoke-test.sh <base-url>
#   e.g. ./scripts/smoke-test.sh https://digestor-dev-123456.us-east-1.elb.amazonaws.com
# =============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
PASS=0
FAIL=0

check() {
    local name="$1"
    local method="$2"
    local path="$3"
    local expected_status="$4"

    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$BASE_URL$path" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "$expected_status" ]; then
        echo "  ✓ $name (HTTP $HTTP_CODE)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name — expected $expected_status, got $HTTP_CODE"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo " Smoke Tests: $BASE_URL"
echo "============================================"
echo ""

echo "--- Public Endpoints ---"
check "Health check"          GET  "/api/health"    200
check "SPA root serves HTML"  GET  "/"              200

echo ""
echo "--- Auth Required (expect 403 without token) ---"
check "Projects (no auth)"    GET  "/api/projects"  403
check "Tickets (no auth)"     GET  "/api/tickets"   403
check "Analytics (no auth)"   GET  "/api/analytics/overview" 403
check "Auth me (no auth)"     GET  "/api/auth/me"   403

echo ""
echo "--- Validation (expect 422 bad request body) ---"
check "Login (empty body)"    POST "/api/auth/login" 422

echo ""
echo "============================================"
echo " Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
