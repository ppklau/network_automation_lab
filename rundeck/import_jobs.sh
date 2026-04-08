#!/usr/bin/env bash
# ACME Investments — Rundeck job import script
# ─────────────────────────────────────────────────────────────────────────────
# Imports all job definition YAML files from rundeck/jobs/ into the 'acme'
# Rundeck project via the Rundeck REST API.
#
# Usage:
#   ./rundeck/import_jobs.sh
#
# Prerequisites:
#   - Rundeck container must be running (docker compose up -d rundeck)
#   - curl must be available on the host
#   - Run from any directory; the script locates itself via $0
#
# Credentials used: admin / acme-lab (set via RUNDECK_ADMIN/RUNDECK_PASSWORD
# env vars to override).
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
RUNDECK_URL="${RUNDECK_URL:-http://localhost:4440}"
RUNDECK_USER="${RUNDECK_ADMIN:-admin}"
RUNDECK_PASS="${RUNDECK_PASSWORD:-acme-lab}"
RUNDECK_PROJECT="${RUNDECK_PROJECT:-acme}"
RUNDECK_API_VERSION="45"

# Resolve the script's own directory so we can find the jobs/ folder
# regardless of where the script is called from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOBS_DIR="${SCRIPT_DIR}/jobs"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

# ── Helper functions ──────────────────────────────────────────────────────────

log_info()    { echo -e "${CYAN}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }

# wait_for_rundeck: polls the Rundeck system info endpoint until a 200 response
# is returned or the timeout is exceeded.
wait_for_rundeck() {
    local max_wait=180      # seconds
    local poll_interval=5   # seconds
    local elapsed=0
    local api_url="${RUNDECK_URL}/api/${RUNDECK_API_VERSION}/system/info"

    log_info "Waiting for Rundeck to be ready at ${RUNDECK_URL} ..."

    while [ "${elapsed}" -lt "${max_wait}" ]; do
        http_code=$(curl --silent --output /dev/null \
            --write-out "%{http_code}" \
            --max-time 5 \
            --user "${RUNDECK_USER}:${RUNDECK_PASS}" \
            "${api_url}" 2>/dev/null || echo "000")

        if [ "${http_code}" = "200" ]; then
            log_success "Rundeck is ready (HTTP ${http_code})"
            return 0
        fi

        log_info "  Rundeck not ready yet (HTTP ${http_code}). Waiting ${poll_interval}s... (${elapsed}/${max_wait}s elapsed)"
        sleep "${poll_interval}"
        elapsed=$(( elapsed + poll_interval ))
    done

    log_error "Rundeck did not become ready within ${max_wait} seconds."
    log_error "Check: docker compose logs rundeck"
    return 1
}

# ensure_project: creates the 'acme' project if it does not already exist.
ensure_project() {
    local project_url="${RUNDECK_URL}/api/${RUNDECK_API_VERSION}/project/${RUNDECK_PROJECT}"

    log_info "Checking project '${RUNDECK_PROJECT}' exists..."

    http_code=$(curl --silent --output /dev/null \
        --write-out "%{http_code}" \
        --user "${RUNDECK_USER}:${RUNDECK_PASS}" \
        --header "Accept: application/json" \
        "${project_url}" 2>/dev/null || echo "000")

    if [ "${http_code}" = "200" ]; then
        log_success "Project '${RUNDECK_PROJECT}' already exists."
        return 0
    fi

    log_info "Project '${RUNDECK_PROJECT}' not found (HTTP ${http_code}). Creating..."

    response=$(curl --silent \
        --output /dev/null \
        --write-out "%{http_code}" \
        --user "${RUNDECK_USER}:${RUNDECK_PASS}" \
        --header "Content-Type: application/json" \
        --header "Accept: application/json" \
        --request POST \
        --data "{\"name\":\"${RUNDECK_PROJECT}\",\"config\":{\"project.label\":\"ACME Lab\",\"project.description\":\"ACME Investments Network Automation\"}}" \
        "${RUNDECK_URL}/api/${RUNDECK_API_VERSION}/projects" 2>/dev/null || echo "000")

    if [ "${response}" = "201" ] || [ "${response}" = "200" ]; then
        log_success "Project '${RUNDECK_PROJECT}' created (HTTP ${response})."
    else
        log_error "Failed to create project '${RUNDECK_PROJECT}' (HTTP ${response})."
        return 1
    fi
}

# import_project_acl: uploads acme.aclpolicy to the project ACL store via the API.
# This is the project-level ACL that controls which Rundeck groups can run which
# job groups. It must be imported after the project exists.
import_project_acl() {
    local acl_file="${SCRIPT_DIR}/acme.aclpolicy"
    local acl_url="${RUNDECK_URL}/api/${RUNDECK_API_VERSION}/project/${RUNDECK_PROJECT}/acl/acme.aclpolicy"

    if [ ! -f "${acl_file}" ]; then
        log_warn "acme.aclpolicy not found at ${acl_file} — skipping project ACL import."
        return 0
    fi

    log_info "Importing project-level ACL policy..."

    http_code=$(curl --silent \
        --output /dev/null \
        --write-out "%{http_code}" \
        --user "${RUNDECK_USER}:${RUNDECK_PASS}" \
        --request PUT \
        --header "Content-Type: application/yaml" \
        --header "Accept: application/json" \
        --data-binary "@${acl_file}" \
        "${acl_url}" 2>/dev/null || echo "000")

    if [ "${http_code}" = "200" ] || [ "${http_code}" = "201" ]; then
        log_success "Project ACL policy imported (HTTP ${http_code})."
    else
        log_warn "Project ACL import returned HTTP ${http_code} — check Rundeck UI under Project Settings > Access Control."
    fi
}

# import_job: imports a single YAML job file into the Rundeck project.
import_job() {
    local job_file="$1"
    local job_name
    job_name=$(basename "${job_file}" .yaml)

    local import_url="${RUNDECK_URL}/api/${RUNDECK_API_VERSION}/project/${RUNDECK_PROJECT}/jobs/import"

    log_info "Importing: ${job_name} ..."

    response=$(curl --silent \
        --user "${RUNDECK_USER}:${RUNDECK_PASS}" \
        --header "Accept: application/json" \
        --request POST \
        --form "xmlBatch=@${job_file};type=application/yaml" \
        --form "fileformat=yaml" \
        --form "dupeOption=update" \
        "${import_url}" 2>/dev/null)

    # The API returns JSON with 'succeeded' and 'failed' arrays.
    succeeded=$(echo "${response}" | grep -o '"succeeded":\[[^]]*\]' | grep -o '"name":"[^"]*"' | wc -l || echo "0")
    failed=$(echo "${response}" | grep -o '"failed":\[[^]]*\]' | grep -c '"name"' || echo "0")

    if echo "${response}" | grep -q '"failed":\[\]'; then
        log_success "${job_name} imported successfully."
    elif echo "${response}" | grep -q '"succeeded":\[{'; then
        log_success "${job_name} imported successfully."
    else
        log_warn "${job_name}: unexpected response — check below:"
        echo "${response}" | python3 -m json.tool 2>/dev/null || echo "${response}"
        log_warn "If the job definition is valid, this may be a transient error. Try re-running."
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ACME Investments — Rundeck Job Import"
echo "  Rundeck: ${RUNDECK_URL}"
echo "  Project: ${RUNDECK_PROJECT}"
echo "  Jobs dir: ${JOBS_DIR}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Validate jobs directory
if [ ! -d "${JOBS_DIR}" ]; then
    log_error "Jobs directory not found: ${JOBS_DIR}"
    exit 1
fi

job_files=("${JOBS_DIR}"/*.yaml)
if [ ${#job_files[@]} -eq 0 ] || [ ! -f "${job_files[0]}" ]; then
    log_error "No .yaml job files found in ${JOBS_DIR}"
    exit 1
fi

log_info "Found ${#job_files[@]} job file(s)."
echo ""

# Step 1: Wait for Rundeck
wait_for_rundeck
echo ""

# Step 2: Ensure the project exists
ensure_project
echo ""

# Step 3: Import project-level ACL policy
import_project_acl
echo ""

# Step 4: Import each job
log_info "Importing jobs..."
echo ""

import_errors=0
for job_file in "${job_files[@]}"; do
    if [ -f "${job_file}" ]; then
        import_job "${job_file}" || (( import_errors++ )) || true
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "${import_errors}" -eq 0 ]; then
    log_success "All jobs imported. Open ${RUNDECK_URL} to verify."
else
    log_warn "${import_errors} job(s) had warnings. Review output above."
fi
echo ""
echo "  Next steps:"
echo "  1. Open ${RUNDECK_URL} and log in as admin / acme-lab"
echo "  2. Create users via Admin > User Manager:"
echo "       acme-ops    / acme-ops    (group: acme-ops-group)"
echo "       acme-senior / acme-senior (group: acme-senior-group)"
echo "  3. Navigate to ACME > Jobs to verify all jobs are imported"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
