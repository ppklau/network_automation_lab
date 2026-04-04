#!/usr/bin/env bash
# capstone/inject_fault.sh
#
# ACME Investments — Capstone Random Fault Injector
# Implements: Exercise 12.2
#
# Selects a scenario randomly (or by number if $1 is provided) and injects it.
# Scenarios are independent — only one is active at a time.
#
# Usage:
#   bash capstone/inject_fault.sh          # random scenario
#   bash capstone/inject_fault.sh 1        # scenario-a (BGP auth mismatch)
#   bash capstone/inject_fault.sh 2        # scenario-b (route loop)
#   bash capstone/inject_fault.sh 3        # scenario-c (Frankfurt VLAN)
#   bash capstone/inject_fault.sh 4        # scenario-d (multi-device drift)
#
# The scenario number is written to /tmp/capstone_scenario.txt (hidden from reader).
# The verify playbook reveals which scenario was active after remediation.

set -euo pipefail

SCENARIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scenarios"
BREADCRUMB_FILE="/tmp/scenario_active.txt"
SCENARIO_RECORD="/tmp/capstone_scenario.txt"

# ── Check for already-active scenario ────────────────────────────────────────
if [[ -f "${BREADCRUMB_FILE}" ]]; then
    echo "[WARN] A scenario may already be active (${BREADCRUMB_FILE} exists)."
    echo "[WARN] Injecting a new scenario anyway."
fi

# ── Select scenario ───────────────────────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
    SCENARIO="${1}"
    if ! [[ "${SCENARIO}" =~ ^[1-4]$ ]]; then
        echo "[ERROR] Invalid scenario number '${SCENARIO}'. Must be 1–4." >&2
        exit 1
    fi
else
    SCENARIO=$(( (RANDOM % 4) + 1 ))
fi

# ── Map scenario number to playbook ──────────────────────────────────────────
case "${SCENARIO}" in
    1) PLAYBOOK="scenario-a.yml" ;;
    2) PLAYBOOK="scenario-b.yml" ;;
    3) PLAYBOOK="scenario-c.yml" ;;
    4) PLAYBOOK="scenario-d.yml" ;;
esac

# ── Record scenario number (restricted permissions to discourage peeking) ─────
echo "${SCENARIO}" > "${SCENARIO_RECORD}"
chmod 600 "${SCENARIO_RECORD}"

# ── Run the scenario playbook ─────────────────────────────────────────────────
echo "[INFO] Running fault injection playbook..."
ansible-playbook "${SCENARIO_DIR}/${PLAYBOOK}"

# ── Notify — intentionally vague ─────────────────────────────────────────────
echo ""
echo "========================================================================"
echo "  Scenario injected."
echo "  You have 90 minutes."
echo "  Diagnose and remediate all faults using available tooling."
echo "========================================================================"
echo ""
