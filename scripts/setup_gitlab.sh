#!/usr/bin/env bash
# setup_gitlab.sh — One-shot bootstrap for GitLab CE + Runner
# Run once after: docker compose -f docker-compose.gitlab.yml -p acme-gitlab up -d
# Safe to re-run if interrupted (idempotent).

set -euo pipefail

# ─── Colour helpers ────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${GREEN}[setup]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error() { echo -e "${RED}[error]${RESET} $*" >&2; }
die()   { error "$*"; exit 1; }

GITLAB_URL="http://localhost:8929"
COMPOSE_FILE="docker-compose.gitlab.yml"
PROJECT_NAME="acme-gitlab"
ROOT_PASS="ACMElab2024!"
PAT_NAME="lab-setup-token"

# Repo root is the directory that contains this script's parent
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ─── Step 1: Check dependencies ───────────────────────────────────────────────
info "Checking required tools..."

if ! command -v jq &>/dev/null; then
  die "jq is not installed. Install it with: brew install jq  (macOS) or apt-get install jq (Linux)"
fi

if ! command -v curl &>/dev/null; then
  die "curl is not installed. Install it with: brew install curl (macOS) or apt-get install curl (Linux)"
fi

info "jq and curl are available."

# ─── Step 2: Check docker compose is running ──────────────────────────────────
info "Checking acme-gitlab compose project is running..."

if ! docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" -p "${PROJECT_NAME}" ps --services --filter status=running 2>/dev/null | grep -q "gitlab"; then
  die "GitLab container is not running. Start it first with:\n  docker compose -f ${COMPOSE_FILE} -p ${PROJECT_NAME} up -d"
fi

info "acme-gitlab project is running."

# ─── Step 3: Wait for GitLab healthcheck ──────────────────────────────────────
info "Waiting for GitLab to become healthy at ${GITLAB_URL}/-/health ..."
info "(This can take 3–8 minutes on first boot. Grab a coffee.)"

TIMEOUT=600   # 10 minutes
ELAPSED=0
INTERVAL=10

until curl -sf "${GITLAB_URL}/-/health" &>/dev/null; do
  if [[ ${ELAPSED} -ge ${TIMEOUT} ]]; then
    die "GitLab did not become healthy within ${TIMEOUT}s. Check: docker compose -f ${COMPOSE_FILE} -p ${PROJECT_NAME} logs gitlab"
  fi
  printf "."
  sleep ${INTERVAL}
  ELAPSED=$(( ELAPSED + INTERVAL ))
done
echo ""
info "GitLab is healthy."

# ─── Step 4: Create root PAT ──────────────────────────────────────────────────
info "Creating root Personal Access Token '${PAT_NAME}'..."

RUBY_SCRIPT=$(cat <<'RUBY'
user = User.find_by_username('root')
existing = PersonalAccessToken.find_by(user: user, name: ENV['PAT_NAME'])
if existing && existing.active?
  puts existing.token
else
  pat = PersonalAccessToken.create!(
    user:       user,
    name:       ENV['PAT_NAME'],
    scopes:     %w[api read_api read_user create_runner],
    expires_at: Date.today + 90
  )
  puts pat.token
end
RUBY
)

RAW_PAT_OUTPUT=$(
  PAT_NAME="${PAT_NAME}" \
  docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" -p "${PROJECT_NAME}" \
    exec -T \
    -e PAT_NAME="${PAT_NAME}" \
    gitlab \
    gitlab-rails runner - <<< "${RUBY_SCRIPT}" 2>&1
)

GITLAB_PAT=$(echo "${RAW_PAT_OUTPUT}" | tail -1 | tr -d '[:space:]')

if [[ -z "${GITLAB_PAT}" || "${GITLAB_PAT}" == "null" ]]; then
  error "Failed to retrieve PAT. Raw output:"
  echo "${RAW_PAT_OUTPUT}" >&2
  die "Could not create or retrieve root PAT."
fi

info "Root PAT obtained (${#GITLAB_PAT} chars)."

# Convenience alias for API calls
api() {
  curl -sf \
    --header "PRIVATE-TOKEN: ${GITLAB_PAT}" \
    --header "Content-Type: application/json" \
    "$@"
}

# ─── Step 5: Create acme group ────────────────────────────────────────────────
info "Creating GitLab group 'acme'..."

GROUP_RESPONSE=$(
  curl -sf \
    --header "PRIVATE-TOKEN: ${GITLAB_PAT}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data '{"name":"acme","path":"acme","visibility":"private"}' \
    "${GITLAB_URL}/api/v4/groups" || true
)

if [[ -z "${GROUP_RESPONSE}" ]]; then
  warn "Group creation returned empty response (may already exist — continuing)."
else
  GROUP_ERROR=$(echo "${GROUP_RESPONSE}" | jq -r '.message // empty' 2>/dev/null || true)
  if echo "${GROUP_ERROR}" | grep -qi "taken\|already\|exist"; then
    warn "Group 'acme' already exists — skipping."
  elif [[ -n "${GROUP_ERROR}" ]]; then
    die "Unexpected error creating group: ${GROUP_ERROR}"
  else
    info "Group 'acme' created."
  fi
fi

# Fetch group ID (needed for project creation)
GROUP_ID=$(api "${GITLAB_URL}/api/v4/groups/acme" | jq -r '.id')
if [[ -z "${GROUP_ID}" || "${GROUP_ID}" == "null" ]]; then
  die "Could not retrieve group ID for 'acme'."
fi
info "Group ID: ${GROUP_ID}"

# ─── Step 6: Create project ───────────────────────────────────────────────────
info "Creating project 'network-automation-lab' under acme group..."

PROJECT_RESPONSE=$(
  curl -sf \
    --header "PRIVATE-TOKEN: ${GITLAB_PAT}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data "{
      \"name\": \"network-automation-lab\",
      \"path\": \"network-automation-lab\",
      \"namespace_id\": ${GROUP_ID},
      \"initialize_with_readme\": false,
      \"visibility\": \"private\"
    }" \
    "${GITLAB_URL}/api/v4/projects" || true
)

if [[ -z "${PROJECT_RESPONSE}" ]]; then
  warn "Project creation returned empty response (may already exist — continuing)."
else
  PROJECT_ERROR=$(echo "${PROJECT_RESPONSE}" | jq -r '.message // empty' 2>/dev/null || true)
  if echo "${PROJECT_ERROR}" | grep -qi "taken\|already\|exist"; then
    warn "Project 'network-automation-lab' already exists — skipping."
  elif [[ -n "${PROJECT_ERROR}" ]]; then
    die "Unexpected error creating project: ${PROJECT_ERROR}"
  else
    info "Project 'network-automation-lab' created."
  fi
fi

# Fetch project ID
PROJECT_ID=$(api "${GITLAB_URL}/api/v4/projects/acme%2Fnetwork-automation-lab" | jq -r '.id')
if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "null" ]]; then
  die "Could not retrieve project ID for acme/network-automation-lab."
fi
info "Project ID: ${PROJECT_ID}"

# ─── Step 7: MR merge settings ────────────────────────────────────────────────
info "Configuring merge request settings..."

# Block merge if pipeline is failing; allow merge even if discussions are open
api \
  --request PUT \
  --data '{
    "only_allow_merge_if_pipeline_succeeds": true,
    "only_allow_merge_if_all_discussions_are_resolved": false,
    "merge_requests_author_approval": true
  }' \
  "${GITLAB_URL}/api/v4/projects/${PROJECT_ID}" \
  > /dev/null

info "Merge settings applied: pipeline must pass before merge is allowed."
info "Note: enforced required approvals require GitLab EE — approval is advisory in this CE lab."

# ─── Step 8: Create GitLab Runner via API ─────────────────────────────────────
info "Checking for existing instance runners..."

EXISTING_RUNNERS=$(api "${GITLAB_URL}/api/v4/runners?type=instance_type" | jq -r '.[].description // empty')

RUNNER_TOKEN=""
if echo "${EXISTING_RUNNERS}" | grep -q "acme-lab-runner"; then
  warn "Runner 'acme-lab-runner' already registered via API — reusing existing token from config.toml."
  SKIP_RUNNER_REGISTER=true
else
  info "Creating runner via API..."
  RUNNER_CREATE_RESPONSE=$(
    api \
      --request POST \
      --data '{
        "runner_type": "instance_type",
        "description": "acme-lab-runner",
        "run_untagged": true
      }' \
      "${GITLAB_URL}/api/v4/user/runners"
  )

  RUNNER_TOKEN=$(echo "${RUNNER_CREATE_RESPONSE}" | jq -r '.token // empty')
  if [[ -z "${RUNNER_TOKEN}" || "${RUNNER_TOKEN}" == "null" ]]; then
    error "Runner creation response: ${RUNNER_CREATE_RESPONSE}"
    die "Could not retrieve runner authentication token."
  fi
  info "Runner created. Auth token obtained."
  SKIP_RUNNER_REGISTER=false
fi

# ─── Step 9: Register runner inside the runner container ──────────────────────
TOML_PATH="/etc/gitlab-runner/config.toml"

# Check if runner is already configured in config.toml
TOML_HAS_RUNNER=$(
  docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" -p "${PROJECT_NAME}" \
    exec -T gitlab-runner \
    sh -c "grep -c '\[\[runners\]\]' ${TOML_PATH} 2>/dev/null || echo 0"
)

if [[ "${TOML_HAS_RUNNER}" -gt 0 ]] || [[ "${SKIP_RUNNER_REGISTER}" == "true" ]]; then
  warn "Runner already present in config.toml — skipping registration."
else
  info "Registering runner inside gitlab-runner container..."
  docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" -p "${PROJECT_NAME}" \
    exec -T gitlab-runner \
    gitlab-runner register \
      --non-interactive \
      --url "http://localhost:8929" \
      --token "${RUNNER_TOKEN}" \
      --executor "docker" \
      --docker-image "python:3.12-slim" \
      --docker-network-mode "host" \
      --description "acme-lab-runner"

  info "Runner registered successfully."
fi

# ─── Step 10: Set CI/CD project variables ─────────────────────────────────────
info "Setting CI/CD project variables..."

set_variable() {
  local key="$1"
  local value="$2"
  local masked="$3"
  local protected="$4"

  # Try to create; ignore 400 (already exists)
  local http_code
  http_code=$(
    curl -s -o /dev/null -w "%{http_code}" \
      --header "PRIVATE-TOKEN: ${GITLAB_PAT}" \
      --header "Content-Type: application/json" \
      --request POST \
      --data "{
        \"key\": \"${key}\",
        \"value\": \"${value}\",
        \"masked\": ${masked},
        \"protected\": ${protected}
      }" \
      "${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/variables"
  )

  if [[ "${http_code}" == "201" ]]; then
    info "  Variable '${key}' created."
  elif [[ "${http_code}" == "400" ]]; then
    warn "  Variable '${key}' already exists — skipping."
  else
    warn "  Variable '${key}' returned HTTP ${http_code} — check manually."
  fi
}

set_variable "VAULT_PASS"                 "CHANGEME" "true"  "false"
set_variable "BATFISH_HOST"               "localhost" "false" "false"
set_variable "ANSIBLE_HOST_KEY_CHECKING"  "False"    "false" "false"
set_variable "CI_SSH_PRIVATE_KEY"         ""         "true"  "false"

# ─── Step 11: Ensure git identity is configured ───────────────────────────────
info "Checking git identity..."

GIT_NAME=$(git config --get user.name 2>/dev/null || true)
GIT_EMAIL=$(git config --get user.email 2>/dev/null || true)

if [[ -z "${GIT_NAME}" || -z "${GIT_EMAIL}" ]]; then
  warn "No git identity found — setting local defaults for this repo."
  git config --local user.name  "${GIT_NAME:-ACME Lab User}"
  git config --local user.email "${GIT_EMAIL:-lab-user@acme-investments.internal}"
  info "Git identity set (repo-local only). Change anytime with: git config user.name / user.email"
else
  info "Git identity already configured: ${GIT_NAME} <${GIT_EMAIL}>"
fi

# ─── Step 12: Add git remote ──────────────────────────────────────────────────
info "Configuring git remote 'lab'..."

cd "${REPO_ROOT}"

REMOTE_URL="http://root:${GITLAB_PAT}@localhost:8929/acme/network-automation-lab.git"

if git remote get-url lab &>/dev/null; then
  warn "Remote 'lab' already exists — updating URL."
  git remote set-url lab "${REMOTE_URL}"
else
  git remote add lab "${REMOTE_URL}"
  info "Remote 'lab' added."
fi

# ─── Step 13: Push main branch ────────────────────────────────────────────────
info "Pushing main branch to lab remote..."

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push lab "${CURRENT_BRANCH}:main" --force 2>&1 | sed "s/${GITLAB_PAT}/***PAT***/g"

info "Branch '${CURRENT_BRANCH}' pushed to lab remote as 'main'."

# ─── Step 14: Success summary ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║              GitLab Lab Setup Complete!                  ║${RESET}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${GREEN}GitLab URL:${RESET}    ${GITLAB_URL}"
echo -e "  ${GREEN}Credentials:${RESET}   root / ${ROOT_PASS}"
echo -e "  ${GREEN}Project:${RESET}       ${GITLAB_URL}/acme/network-automation-lab"
echo -e "  ${GREEN}Runner:${RESET}        registered as acme-lab-runner (instance, Docker executor)"
echo ""
echo -e "  ${YELLOW}Next step:${RESET} Open an MR to trigger your first pipeline (Chapter 9)"
echo ""
echo -e "  ${YELLOW}Note:${RESET} Update CI_SSH_PRIVATE_KEY in GitLab CI/CD settings"
echo -e "        before running push/verify pipeline stages."
echo ""
