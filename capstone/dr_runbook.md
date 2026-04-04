# ACME Investments — Quarterly DR Runbook
# Module 12.3

This document is the authorised DR runbook for the ACME Investments network automation platform.
It is structured for execution. Use it as-is; do not improvise.

## Scope

This runbook covers a full recovery of the London DC1 automation pipeline following a catastrophic failure scenario where:
- The primary pipeline runner (GitLab CI) is unavailable
- The SoT repository is intact (remote backup verified)
- Network devices are reachable but running last-known configs
- Monitoring stack may be unavailable

## Pre-Conditions (Verify Before Proceeding)

- [ ] SoT repository accessible: `git clone <repo_url>`
- [ ] Vault password available (refer to: secrets management procedure)
- [ ] Ansible control node reachable (`ping <ansible_controller>`)
- [ ] At least one BGP border session is Established
- [ ] Containerlab (or equivalent) is running or can be started

## Phase 1 — Establish Control Plane Baseline (T+0 to T+15)

1. Clone SoT and verify integrity: `git log --oneline -5`
2. Generate Ansible inventory: `python3 scripts/generate_inventory.py`
3. Run lab health check: `ansible-playbook scenarios/common/verify_lab_healthy.yml`
4. **Gate:** All critical devices (border-*) must show BGP Established. If not, proceed to Phase 2.

## Phase 2 — Emergency Config Push (T+15 to T+45)

1. Render all configs from SoT: `ansible-playbook playbooks/render_configs.yml`
2. Push to border devices first (--limit border): `ansible-playbook playbooks/push_configs.yml --limit border`
3. Verify inter-region sessions: `ansible-playbook playbooks/verify_state.yml --limit border`
4. Push to spine devices: `ansible-playbook playbooks/push_configs.yml --limit spine`
5. Push to leaf devices: `ansible-playbook playbooks/push_configs.yml --limit leaf`
6. **Gate:** `ansible-playbook scenarios/common/verify_lab_healthy.yml` must pass.

## Phase 3 — Compliance Verification (T+45 to T+60)

1. Run compliance report: `ansible-playbook playbooks/compliance_report.yml`
2. Run Batfish intent checks: `bash batfish/run_checks.sh`
3. Run Frankfurt isolation checks: `pytest batfish/tests/test_frankfurt_isolation.py -v`
4. **Gate:** Zero CRITICAL compliance failures. Frankfurt VLAN 100 must be absent.

## Phase 4 — Pipeline Recovery (T+60 to T+90)

1. Start GitLab CI runner (refer to: infrastructure runbook)
2. Push a no-op commit to verify pipeline: `git commit --allow-empty -m "DR test: pipeline verify"`
3. Confirm all 7 stages complete successfully
4. **Gate:** Pipeline green end-to-end.

## Phase 5 — Monitoring Restore (T+90 to T+120)

1. Start monitoring stack: `cd monitoring && docker-compose up -d`
2. Verify Prometheus targets: `curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool`
3. Write initial metrics: `ansible-playbook playbooks/write_bgp_metrics.yml`
4. Verify Grafana dashboards accessible: `curl -s http://localhost:3000/api/health`
5. **Gate:** All active BGP sessions visible in Grafana Network Overview dashboard.

## DR Test Documentation (Record and Retain)

Complete the following table during the DR test and retain for regulatory submission:

| Phase | Target Time | Actual Start | Actual End | Gate Passed | Issues |
|-------|-------------|--------------|------------|-------------|--------|
| 1 — Baseline | T+15 | | | | |
| 2 — Config push | T+45 | | | | |
| 3 — Compliance | T+60 | | | | |
| 4 — Pipeline | T+90 | | | | |
| 5 — Monitoring | T+120 | | | | |

**Total RTO achieved:** _____ minutes

**Issues encountered:**

**Sign-off:**
- Engineer: _____________________ Date: __________
- Manager: _____________________ Date: __________

This DR record is a MiFID II-relevant operational artefact. Retain for 7 years.
