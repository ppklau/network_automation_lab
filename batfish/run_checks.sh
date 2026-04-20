#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ACME Investments — Batfish Intent Check Runner
# ─────────────────────────────────────────────────────────────────────────────
# Builds a Batfish snapshot from rendered configs, then runs the full pytest
# intent-check suite. Called from the GitLab CI intent-check stage.
#
# Usage:
#   ./batfish/run_checks.sh                   # full suite
#   ./batfish/run_checks.sh -k test_bgp       # filter by test name
#   BATFISH_HOST=192.168.1.10 ./batfish/run_checks.sh
#
# Requirements:
#   - Batfish container running (docker run batfish/batfish or CI service)
#   - pybatfish and pytest installed (pip install pybatfish pytest pytest-html)
#   - Rendered configs in configs/<hostname>/running.conf
#     (run: ansible-playbook playbooks/render_configs.yml first)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SNAPSHOT_DIR="${SCRIPT_DIR}/snapshots/acme_lab/configs"
REPORTS_DIR="${SCRIPT_DIR}/reports"
BATFISH_HOST="${BATFISH_HOST:-localhost}"

echo "=== ACME Investments — Batfish Intent Check ==="
echo "    Project:     ${PROJECT_ROOT}"
echo "    Snapshot:    ${SNAPSHOT_DIR}"
echo "    Batfish:     ${BATFISH_HOST}"
echo "    Timestamp:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# ── Step 1: Build snapshot from rendered configs ──────────────────────────
echo "[1/3] Building Batfish snapshot from rendered configs..."

mkdir -p "${SNAPSHOT_DIR}" "${REPORTS_DIR}"

config_count=0
for host_dir in "${PROJECT_ROOT}/configs"/*/; do
    hostname="$(basename "${host_dir}")"
    # FRR devices have a separate batfish.conf that includes IOS-style ACL config
    # for policy analysis. Use it in preference to running.conf (which is stripped
    # of ACL syntax that FRR vtysh cannot parse).
    if [[ -f "${host_dir}/batfish.conf" ]]; then
        cp "${host_dir}/batfish.conf" "${SNAPSHOT_DIR}/${hostname}.cfg"
        config_count=$((config_count + 1))
    elif [[ -f "${host_dir}/running.conf" ]]; then
        cp "${host_dir}/running.conf" "${SNAPSHOT_DIR}/${hostname}.cfg"
        config_count=$((config_count + 1))
    fi
done

if [[ "${config_count}" -eq 0 ]]; then
    echo "ERROR: No rendered configs found in ${PROJECT_ROOT}/configs/"
    echo "       Run: ansible-playbook playbooks/render_configs.yml"
    exit 1
fi

echo "    Copied ${config_count} device configs to snapshot directory."

# ── Step 2: Wait for Batfish to be ready ─────────────────────────────────
echo "[2/3] Waiting for Batfish service at ${BATFISH_HOST}:9996..."

max_wait=60
waited=0
until python3 -c "import socket; s=socket.create_connection(('${BATFISH_HOST}',9996),timeout=2); s.close()" 2>/dev/null; do
    if [[ "${waited}" -ge "${max_wait}" ]]; then
        echo "ERROR: Batfish not ready after ${max_wait}s. Is the container running?"
        echo "       docker run --name batfish -d -p 9996:9996 -p 9997:9997 batfish/batfish"
        exit 1
    fi
    sleep 2
    waited=$((waited + 2))
done
echo "    Batfish is ready."

# ── Step 3: Run pytest intent-check suite ────────────────────────────────
echo "[3/3] Running intent-check test suite..."

cd "${PROJECT_ROOT}"

pytest batfish/tests/ \
    --verbose \
    --tb=short \
    --junit-xml="${REPORTS_DIR}/junit.xml" \
    ${PYTEST_HTML:+--html="${REPORTS_DIR}/report.html" --self-contained-html} \
    -p no:cacheprovider \
    "$@"

exit_code=$?

echo ""
if [[ "${exit_code}" -eq 0 ]]; then
    echo "=== All intent checks PASSED ==="
else
    echo "=== Intent checks FAILED (exit ${exit_code}) ==="
    echo "    Review: ${REPORTS_DIR}/junit.xml"
fi

exit "${exit_code}"
