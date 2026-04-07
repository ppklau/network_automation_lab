---
title: "Chapter 14: What Day-2 Actually Means"
---

# Part 6: Day-2 Operations

# Chapter 14: What Day-2 Actually Means

🔵 **Strategic**

Everyone talks about automating network provisioning. Day-1 automation — deploying a new branch, provisioning a leaf switch — is visible, dramatic, and easy to justify. A configuration rendered from a template and pushed in 90 seconds versus three hours of CLI work is a compelling before-and-after story.

Day-2 is less visible but far more consequential.

Day-2 is everything that happens after the device is running: health checks, drift detection, compliance audits, BGP prefix monitoring, maintenance windows, decommissions, SoT hygiene. In a 50-device network, Day-2 operations consume far more engineering hours than initial provisioning. In a 500-device network, they consume almost all of them.

ACME's network team discovered this the hard way. After automating initial provisioning (the work you completed in Parts 1–5), they found that:

- A technician's OOB change to a branch router put BGP auth into a state the SoT didn't reflect. The session stayed up. Nobody noticed for six weeks.
- A leaf switch was put into maintenance mode for an emergency optic swap. The maintenance window was never formally closed. Three days later, the device was still in BGP graceful-shutdown and carrying none of its traffic share.
- A compliance audit required producing evidence that Telnet had never been enabled on any device in the trading segment. This took two engineers a full day of SSH sessions and manual inspection.

Each of these is a Day-2 problem. Each has an automated solution. This part of the guide walks through building all of them.

## The Day-2 Playbook Suite

By the end of this part, you will have built and exercised:

| Playbook | Purpose | Trigger |
|---|---|---|
| `daily_health_check.yml` | BGP, interfaces, NTP, version per device | Daily cron / on-demand |
| `drift_detection.yml` | SoT intent vs. running config comparison | Per change / nightly |
| `compliance_report.yml` | REQ checks (Telnet, SSH, MD5, NTP, SNMP) | Weekly / pre-audit |
| `bgp_prefix_monitor.yml` | Prefix count against baselines | Every 5 minutes |
| `interface_utilisation.yml` | Bandwidth utilisation + error rates | Every 15 minutes |
| `maintenance_window.yml` | Structured enter/exit with state tracking | On-demand |
| `decommission.yml` | 6-phase safe decommission with SoT update | On-demand |
| `sot_hygiene.yml` | Cross-file SoT consistency checks | Per PR / nightly |

These are not toy examples. They are production patterns adapted to the lab scale. The same playbook structure you build here would run unchanged on a 500-device estate.

## The Scenario-First Learning Model

Each chapter in Part 6 follows the same structure:

1. **Scenario** — a realistic incident or operational task drawn from financial services network operations
2. **Diagnosis** — what you would check manually, and why that doesn't scale
3. **The playbook** — walk-through of how the automation solves it
4. **Lab exercise** — fault-inject, detect, remediate, verify

The fault-inject approach means your lab always has a specific, realistic problem to solve rather than a clean state with nothing to find. When the verify playbook passes, you have demonstrated the skill end-to-end.

## Lab Reset

Before starting any chapter in Part 6, if your lab is in an unknown state, run:

```bash
ansible-playbook scenarios/common/reset_lab.yml
```

This restores known-good configuration on all devices, clears any stale scenario breadcrumbs, and waits for BGP to converge. The full reset takes about 90 seconds.

You can also verify the lab is healthy without resetting:

```bash
ansible-playbook scenarios/common/verify_lab_healthy.yml
```

If it passes, you are ready to start. If it fails, run the reset.

## Output Artefacts

The Day-2 playbooks generate structured output you can inspect:

```
state/
  health_<timestamp>.json       # daily health check snapshots
  maintenance_<hostname>.yml    # open maintenance window records
  decommissioned/               # archived device SoT records
  audit/<change_id>/            # pre/post state for audit trail

reports/
  health_<timestamp>.txt        # human-readable health summary
  drift_<timestamp>.json        # drift report with severity classification
  compliance_<timestamp>.txt    # compliance check results
  hygiene_<timestamp>.json      # SoT hygiene check output

monitoring/
  prometheus/
    network_utilisation.prom    # OpenMetrics format for Grafana
```

These artefacts form the audit trail that regulators ask for. The `audit/` directory output from `audit_artefact.yml` includes a SHA256-signed manifest.json referencing the specific MiFID II articles being satisfied.

## A Note on Scheduling

In production, most of these playbooks run on a schedule — Ansible AWX/Tower, GitLab CI cron triggers, or a simple crontab on the Ansible controller. In the lab, you run them manually. The commands are identical; the trigger mechanism is the only difference.

When you reach Part 7 (monitoring stack), you will connect the Prometheus output files to Grafana and see the data visualised. For now, focus on the data generation and the operational patterns.

---

**Next:** Chapter 15 walks through `daily_health_check.yml` and `drift_detection.yml` — the two playbooks you will run most often.
