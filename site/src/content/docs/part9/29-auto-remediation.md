---
title: "Chapter 29: Self-Healing — Auto-Remediation of Detected Drift"
---

## Scenario

ACME's NOC receives 12–15 drift alerts per week. Most are low-risk: a BGP timer tweaked by an engineer during an incident investigation, a description field changed to annotate a maintenance window, the occasional NTP server swap. None of them require a change management ticket. All of them require a human to run `push_configs.yml`.

At 02:30 on a Sunday.

The NOC engineer who gets paged is not happy. The fix is trivial — push the SoT config and drift is gone. But someone has to authorise and execute it.

Auto-remediation removes this category of toil entirely. When drift is detected outside business hours, affects a single device, and is not blocked by a change freeze, the pipeline remediates it automatically. The engineer wakes up to a green dashboard and an audit entry showing what was fixed and when.

## 🔵 [Strategic] Why This Matters

The business case is straightforward: a financial institution's network cannot tolerate configuration drift for three reasons.

**Compliance.** Any device that diverges from its SoT-defined state is, by definition, in an unknown compliance state. INTENT-001 through INTENT-010 are only guaranteed if configs match the SoT. Drift breaks the chain.

**MTTR.** When an incident occurs on a device that has drifted, diagnosing it is harder because the actual config no longer matches the expected config. The drift is noise during a crisis.

**Audit.** MiFID II requires that change records accurately reflect the state of the network. A device that was changed out-of-band has an audit gap. Auto-remediation closes that gap and creates a timestamped record of the correction.

The guardrails matter as much as the capability. Auto-remediation does not act indiscriminately. All four conditions must be true:

1. Drift detected (CRITICAL or WARNING severity)
2. Outside business hours (before 07:00 or after 19:00 UTC)
3. Single device affected
4. No change freeze active

If any gate fails, the system alerts but does not act. A human decides. The automation is a complement to operational judgment, not a replacement for it.

## 🟡 [Practitioner] Guided Walkthrough — auto_remediate.yml

The playbook has four plays.

**Play 1 — Run drift detection.** Imports `drift_detection.yml` with `ignore_errors: true`. The drift report is generated regardless of whether drift exists. Results are available to subsequent plays via `hostvars`.

**Play 2 — Evaluate the auto-remediation gate.** Runs on localhost. Checks:
- Current UTC hour (via `date -u +%H`) against the business-hours window
- Count of drifted nodes from the drift report
- Presence of `/tmp/change_freeze_active` (written by `maintenance_window.yml`)
- Whether drift was detected at CRITICAL or WARNING severity

Sets `remediation_approved: true` or `false` and records the block reason if any gate failed.

**Play 3 — Auto-remediate.** Runs only when `remediation_approved` is true. Calls `push_configs.yml` limited to the single drifted device. Then runs `batfish/run_checks.sh` to confirm the remediation did not introduce a new violation.

**Play 4 — Report block reason.** Runs only when `remediation_approved` is false. Writes the block reason to the Ansible output and exits non-zero (which triggers an alert in the CI/monitoring pipeline).

## Exercise 11.2 — Auto-Remediation {#ex112}

🟡 **Practitioner**

### Scenario

leaf-lon-03 has accumulated drift from the previous incident response window. The BGP keepalive timers were adjusted during troubleshooting and never reverted. A description field was annotated. Neither change is critical on its own, but together they represent a device that is not in its SoT-defined state.

Your task: verify the drift, confirm the gate conditions, and observe auto-remediation correct the device.

### Inject the fault

```bash
ansible-playbook scenarios/ch11/ex112_inject.yml
```

This applies two changes to leaf-lon-03: a BGP timer adjustment (`timers bgp 5 15`) and a description change on Ethernet1. The BGP timer change is classified as CRITICAL drift — fast keepalive timers affect convergence behaviour.

### Step 1 — Confirm drift exists

```bash
ansible-playbook playbooks/drift_detection.yml --limit leaf-lon-03
```

The output will show one device with CRITICAL drift, the specific changed lines, and the severity classification. This is the input the gate evaluation uses.

### Step 2 — Run auto-remediation

For the lab exercise, use `force=true` to bypass the business-hours check (unless you are running this after 19:00 UTC):

```bash
ansible-playbook playbooks/auto_remediate.yml --extra-vars "force=true"
```

Watch play 2 evaluate the gate. You will see the condition checks logged. Play 3 fires: `push_configs.yml` runs for leaf-lon-03 only, and `run_checks.sh` confirms no new violations.

### Step 3 — Verify

```bash
ansible-playbook scenarios/ch11/ex112_verify.yml
```

### Your turn — Structured

Without using `force=true`: configure a cron entry that triggers `auto_remediate.yml` every 15 minutes. Inject the fault again and wait for it to self-heal. Record the time from injection to remediation. This is your MTTR for low-risk drift in ACME's configuration.

### Debrief

**What was injected:** BGP keepalive timers set to 5/15 (SoT default: 30/90) and interface description changed.

**Why it matters:** Fast BGP timers increase control-plane chatter and can cause session flaps under load. A description change is trivial but indicates the device was touched out-of-band. Both together suggest a troubleshooting session that was not fully cleaned up.

**In production:** This is a P3 incident in most financial NOCs — important enough to fix, not urgent enough to wake someone up. Auto-remediation compresses response from hours (overnight wait for business hours + NOC queue) to minutes.
