---
title: "Chapter 28: Advanced Automation Patterns"
---

# Chapter 28: Advanced Automation Patterns

The automation you've built across the first eight modules is largely reactive. You detect a problem, you run a playbook, you fix it. That is a significant step forward from manual operations, but it still depends on a human deciding to act.

This module covers three patterns that close the loop further: automated remediation, staged rollout, and bulk operations at scale. None of these require exotic infrastructure. They are direct extensions of the pipeline you've already built.

## The Automation Maturity Curve

Most organisations move through a recognisable sequence:

1. **Scripts** — individual engineers write ad-hoc scripts. Output is not standardised. Runbooks are in someone's head.
2. **Pipeline** — changes flow through a defined process. The SoT is authoritative. Configs are generated, not edited by hand.
3. **Proactive** — the pipeline detects problems and acts on them within defined constraints. Drift is self-healing. Rollouts are staged.
4. **Measured** — every operation produces a metric. MTTR is tracked. The automation system itself is observable.

After completing Modules 1–9, ACME is solidly at Level 2 and moving into Level 3. This module covers the Level 3 patterns. The maturity assessment worksheet in Module 12.4 will help you map your own organisation's current position.

## Three Patterns

**Auto-remediation.** The drift detection playbook already identifies when a device's running config diverges from its SoT-rendered config. Auto-remediation adds a decision layer: if the conditions are right (outside business hours, single device, no change freeze), push the fix automatically. If any condition fails, alert a human. The playbook does not guess — it applies a defined policy.

**Staged rollout.** Pushing a config change to 20 devices simultaneously is technically possible. It is also operationally reckless. Staged rollout applies the change to one device first (the canary), validates it, and only proceeds to the group if the canary passes. If the canary fails, the pipeline rolls it back and halts. The remaining 19 devices are untouched.

**Bulk import.** The SoT is a structured database. When ACME opens 20 new branches in a quarter, the SoT should accept a spreadsheet and validate it — not require an engineer to hand-craft 20 YAML files. The bulk import script is a thin conversion layer with a schema validation gate.

## What This Module Does Not Cover

These patterns are not AIOps. They do not use machine learning, anomaly detection, or predictive analytics. Those capabilities require streaming telemetry infrastructure that is beyond the scope of this lab.

What this module covers is practical and implementable at most financial institutions today, with the tooling already in place. The goal is not to impress — it is to remove human toil from well-understood, repetitive decisions.

## Prerequisites

Before starting Module 11, verify:

- All previous modules complete (lab healthy from Phase 1–9)
- `ansible-playbook scenarios/common/verify_lab_healthy.yml` passes cleanly
- `bash batfish/run_checks.sh` exits 0
- `ansible-playbook playbooks/drift_detection.yml` shows zero drift
