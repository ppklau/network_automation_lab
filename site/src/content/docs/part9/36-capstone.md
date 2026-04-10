---
title: "Chapter 36: Capstone"
---

This module has no guided walkthroughs. The scenarios are realistic. The tooling is everything you have built across the lab. The DR runbook is the only structured reference.

This is what operational readiness looks like: the tools are there, the knowledge is there, the process is what you build under pressure.

---

## Exercise 36.1 — New Office Opening (End to End) {#ex361}

🟡 **Practitioner**

### Scenario

ACME's Frankfurt operations team has submitted a provisioning request for a new branch office. You receive the specification file. Nothing else.

```bash
ansible-playbook scenarios/part9/ex361_inject.yml
cat /tmp/new_office_spec.txt
```

Provision the new Frankfurt branch using only SoT edits, the pipeline, and the available validation tools. The spec file tells you everything you need to know. Do not guess at the compliance requirements — read the spec.

```bash
ansible-playbook scenarios/part9/ex361_verify.yml
```

> **Stuck?** The required steps, in order: (1) add the branch to `sot/devices/branches/eu-branches.yml` following the existing entry format, (2) ensure `trading_zone_prohibited: true` is set at the file level, (3) run `python3 scripts/validate_sot.py`, (4) run `ansible-playbook playbooks/render_configs.yml --limit fra-branch-05`, (5) run `pytest batfish/tests/test_frankfurt_isolation.py -v`. The schema will tell you if you've missed a required field.

---

## Exercise 36.2 — Incident Simulation {#ex362}

🟡 **Practitioner**

### Scenario

A fault has been injected into the lab environment. You do not know which one. You have the full tooling suite: daily health checks, drift detection, compliance reporting, Batfish intent verification, BGP monitoring, and the Grafana dashboards.

```bash
ansible-playbook scenarios/part9/ex362_inject.yml
```

Begin your investigation. Treat this as a real incident. As you work, document:

1. **First indicator** — what was the first sign of a problem, and how did you find it?
2. **Diagnosis steps** — which tools did you use, in what order, and what did each tell you?
3. **Root cause** — what was the actual fault?
4. **Remediation** — what did you do to fix it?
5. **Verification** — how did you confirm the fix was complete?

When you are confident the lab is healthy:

```bash
ansible-playbook scenarios/part9/ex362_verify.yml
```

This runs the full health, compliance, and Batfish suite and reveals which scenario was active.

## Debrief

The four capstone scenarios test four failure categories that occur repeatedly in real financial network incidents:

**Scenario A (BGP auth mismatch):** A credential management failure. The BGP MD5 key on one side of a session was changed out-of-band — a common side effect of a security rotation that was not fully coordinated. Detected by: health check (BGP session down), confirmed by: Batfish path trace failures. Remediated by: push_configs.yml.

**Scenario B (route loop):** A troubleshooting artefact not cleaned up. A static route added during an incident was never removed and is now black-holing traffic to a broad prefix. Detected by: Batfish path trace failures, confirmed by: traceroute. Remediated by: push_configs.yml.

**Scenario C (Frankfurt VLAN violation):** A compliance failure. VLAN 100 (TRADING) was added to a Frankfurt device — a direct MiFID II violation. Detected by: compliance_report.yml (ZONE-001), confirmed by: Batfish Frankfurt isolation tests. Remediated by: push_configs.yml.

**Scenario D (drift):** Accumulated change control failure across three devices. None of the individual changes are critical in isolation. Together they represent a network that has diverged from its documented state. Detected by: drift_detection.yml. Remediated by: push_configs.yml across all three devices.

In each case the remediation is the same: push the SoT config. The difference is in the detection — which tool, in what time, with what confidence.

---

## Exercise 36.3 — Quarterly DR Test {#ex363}

🔵 **Strategic** + 🟡 **Practitioner**

### Scenario

ACME's information security team requires a quarterly DR test of the network automation platform. The test simulates the failure of the primary automation infrastructure (GitLab CI runner unavailable, monitoring stack down) while the network devices remain reachable.

The DR runbook is the only guidance. Read it before starting. Execute each phase in order. Complete the documentation table.

```bash
cat capstone/dr_runbook.md
```

### What to document

Regulators — FCA and BaFin in ACME's case — do not require that DR tests are perfect. They require that tests are conducted, documented, and that issues found are tracked to resolution. A post-DR report that identifies two issues and shows they were remediated is more credible than one that claims flawless execution.

Your DR test documentation should include:
- The time each phase started and completed
- Whether each gate passed on first attempt
- Any issues encountered and the actions taken
- Total RTO achieved (time from T+0 to final gate passing)
- Engineer and manager sign-off

This document is a MiFID II-relevant operational artefact. In a real institution, it would be retained for 7 years.

---

## Exercise 36.4 — Maturity Self-Assessment {#ex364}

🔵 **Strategic**

### Scenario

You have completed the ACME Investments lab. You have built and operated a SoT-driven network automation pipeline with intent verification, Day-2 operations, hardware lifecycle management, monitoring, and advanced self-healing patterns.

Now use the maturity assessment worksheet to score either ACME (as it stands after this lab) or your own organisation.

```bash
cat worksheets/maturity_assessment.md
```

Score each of the eight dimensions. Be honest about the gaps. The score is not the point — the gap analysis is.

### How to use the results

Identify your two or three lowest-scoring dimensions. For each one, write a one-sentence initiative that would move it up by one level. These are your next automation priorities.

If you scored ACME after completing this lab, you should find it sitting at Level 3 on most dimensions and Level 2 on a few (the ones that require infrastructure beyond the containerlab scope — streaming telemetry, production IPAM integration). That is the honest assessment of what a well-executed lab delivers.

### Looking ahead

The patterns in this lab are a foundation, not a ceiling. The next frontier for financial network automation involves event-driven architectures (network events trigger pipeline runs rather than scheduled checks), streaming telemetry (gNMI replaces textfile-based metrics), and GitOps convergence (the git repository is the complete and sole source of operational truth, with no manual overrides possible).

Those capabilities require the foundation you have built here. A team that cannot reliably detect drift cannot benefit from event-driven remediation. A team that has not validated its rollback process cannot safely automate it.

Network automation is not a project with a completion date. It is an operational practice. The lab ends here. The practice does not.
