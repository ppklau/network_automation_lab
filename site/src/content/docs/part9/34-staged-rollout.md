---
title: "Chapter 34: Staged Rollout — Canary Push and Automated Rollback"
---

## Scenario

The network team needs to roll out a new BGP route-map policy to all 8 leaf devices in lon-dc1. The change is syntactically valid and passes Batfish checks against the snapshot. But the team is cautious — route-map changes affect prefix filtering, and a mistake on all 8 leaves simultaneously would impact every workload in the data centre.

The traditional approach: push to one device manually, watch it for 20 minutes, then push the rest. The automation approach: codify that process so it is consistent, observable, and capable of rolling back automatically if the validation fails.

## 🔵 [Strategic] Why This Matters

Staged rollout addresses the blast radius problem. A misconfiguration applied to 8 devices at once is 8 times harder to remediate than the same misconfiguration on 1 device. More importantly, if the mistake affects traffic, the impact is 8× larger.

The canary pattern is standard practice in software deployment. Network teams have been slower to adopt it, partly because the tooling has historically been manual and partly because rollback in networks is not as clean as deploying a previous container image. This module demonstrates that network rollback is reliable when backed by pre-push state capture and a validated rollback playbook.

For a financial institution, staged rollout also provides a natural audit checkpoint. The playbook halts after the canary phase. An operator can review the canary outcome before the broader push proceeds. This maps directly to the ITIL change management model: implementation step 1 (canary) + review + implementation step 2 (remaining devices).

## 🟡 [Practitioner] Guided Walkthrough — staged_rollout.yml

The playbook has six plays.

**Play 1 — Render configs.** Imports `render_configs.yml` scoped to `target_group`. Ensures configs in `configs/` are current before any push begins.

**Play 2 — Push canary.** Pushes to the canary device (default: first device in `target_group`, overrideable via `canary_device`). Uses `push_configs.yml` with the canary as the limit.

**Play 3 — Verify canary.** Runs `verify_state.yml` (BGP sessions, interface state) and `batfish/run_checks.sh`. Records `canary_pass: true/false`.

**Play 4 — Rollback canary on failure.** Runs only when `canary_pass` is false and `auto_rollback` is true (default). Calls `rollback.yml` limited to the canary. Fails with a clear message: remaining devices were NOT changed.

**Play 5 — Push remaining devices.** Runs only when `canary_pass` is true. Targets all devices in `target_group` except the canary, using `serial: "25%"` to push in batches.

**Play 6 — Verify remaining devices.** Runs `verify_state.yml` across the full group.

## Exercise 34.1 — Canary Push {#ex341}

🟡 **Practitioner**

### Scenario

A route-map update has been prepared for lon-dc1 leaves. You need to stage the rollout through leaf-lon-01 before proceeding to the group.

### Inject the fault

```bash
ansible-playbook scenarios/ch11/ex113_inject.yml
```

This removes the inbound route-map (`RM_LEAF_IN`) from leaf-lon-01's BGP configuration — simulating a config that would fail Batfish's routing policy checks.

### Run staged rollout

```bash
ansible-playbook playbooks/staged_rollout.yml \
  --extra-vars "target_group=site_lon_dc1 canary_device=leaf-lon-01"
```

### Expected outcome

Play 3 runs `batfish/run_checks.sh`. The route-map absence causes `test_routing_policy.py` to fail. Play 4 fires: `rollback.yml` restores leaf-lon-01 to its pre-push state. The playbook exits with a clear message that the canary failed and the group was not changed.

### Verify

```bash
ansible-playbook scenarios/ch11/ex113_verify.yml
```

Confirms: leaf-lon-01 rolled back (RM_LEAF_IN restored), leaf-lon-02 and leaf-lon-03 unchanged (confirming the halt worked).

### Your turn — Structured

Fix the injected fault: run `ansible-playbook playbooks/render_configs.yml --limit leaf-lon-01` to restore the correct config to `configs/`, then re-run `staged_rollout.yml`. Observe the canary pass and the group push proceed. Verify all 8 leaves match their SoT-rendered configs.

## Exercise 34.2 — Automated Rollback Trigger {#ex342}

🟡 **Practitioner**

### Scenario

The same scenario as 11.3, but this time the focus is on the automated rollback mechanism. The pipeline gate (Batfish post-canary check) is the decision point. No human is watching.

### Inject

```bash
ansible-playbook scenarios/ch11/ex115_inject.yml
```

### Run and observe

```bash
ansible-playbook playbooks/staged_rollout.yml \
  --extra-vars "target_group=site_lon_dc1 canary_device=leaf-lon-01 auto_rollback=true"
```

Pay attention to the output of play 4. You will see the rollback execute and the fail message explain exactly why the push halted.

### Verify

```bash
ansible-playbook scenarios/ch11/ex115_verify.yml
```

### Your turn — Open

Modify `staged_rollout.yml` to add a second tier: after the group push completes (play 5), run a final Batfish check across all devices. If this final check fails, trigger a group rollback. Validate your change by injecting a fault that passes the canary check but would be caught by a group-wide assertion.

## Debrief

**What the canary protects against:** Not just syntax errors. A syntactically valid config can still be semantically wrong — a route-map that filters too aggressively, a prefix-list that blocks legitimate advertisements. Batfish catches this class of error even before traffic is affected.

**Why network teams resist canary deployments:** The fear is that the canary device will behave differently from the rest of the group, making the canary result non-representative. In a SoT-driven environment, this is much less of a risk — every leaf gets the same template rendered with its specific values. If the canary fails, it is almost always a real error.

**The rollback guarantee:** Rollback works because `push_configs.yml` captures a pre-push state snapshot before making any changes. The snapshot is the rollback target. This guarantee breaks down if the snapshot is stale or if the device was modified between the snapshot and the rollback — which is why the playbook checks for the snapshot's existence and age.
