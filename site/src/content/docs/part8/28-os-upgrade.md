---
title: "Chapter 28: OS Upgrade Workflow"
---

## The Version Drift Problem

ACME's network team had a problem they didn't know about.

After a vendor advisory was issued about a BGP timer regression in EOS 4.32.2F, the team upgraded most devices during a planned maintenance window. Most — not all. Three leaf switches were missed because the maintenance window ran over and the engineer deferred them. The deferred devices were noted in a spreadsheet, but the spreadsheet was never acted on.

Six months later, during a BGP instability incident under heavy trading load, the engineer investigating the issue discovered that `leaf-lon-02`, `leaf-lon-03`, and `leaf-nyc-04` were still running 4.32.2F. Two of the three were in the affected site. The regression was the likely cause.

The problem was not that the upgrades were not done. The problem was that there was no authoritative record of which devices should be running which version, and no automated check to detect when a device had drifted from its intended version.

The SoT's `target_version` field solves this.

## The `target_version` Pattern

The SoT is the authority for what a device should look like. This extends to software version. When the change board approves an upgrade, the SoT is updated:

```yaml
# In sot/devices/lon-dc1/leaf-lon-02.yml
image: ceos:4.32.2F
target_version: "4.32.3F"   # CAB-approved upgrade: CAB-2026-0041
```

This declaration has immediate effects:
- `os_upgrade.yml` will detect the mismatch in its pre-check phase
- `daily_health_check.yml` can optionally flag version mismatches (see WARNING conditions)
- The GitLab CI pipeline can include a version compliance check gate

Until the upgrade is complete, the device is in a documented non-compliant state — not an undocumented one. The difference matters for audits.

## What `os_upgrade.yml` Does

The playbook has seven phases:

| Phase | What happens |
|---|---|
| 1 — Pre-check | Collect current version; compare to `target_version` from SoT |
| 2 — Skip if current | Exit cleanly if already at target (idempotent) |
| 3 — Maintenance mode | BGP graceful-shutdown to drain traffic before reload |
| 4 — Image stage | Copy EOS .swi file to device flash |
| 5 — Upgrade | Set boot image, save config, reload; wait for device to return |
| 6 — Post-verify | Assert version matches target; assert BGP reconverged |
| 7 — SoT and artefact | Update `image:` field in SoT; write upgrade record |

The idempotency is important: you can run `os_upgrade.yml` against your entire estate on a schedule, and it will only perform upgrades on devices that are not already at their target version. Devices already at target are skipped with a clean exit.

### The Pre-Check Output

Running `os_upgrade.yml` before the upgrade window gives you a version inventory:

```
OS UPGRADE PRE-CHECK: leaf-lon-02
===================================
Current version : 4.32.2F
Target version  : 4.32.3F
Pre-upgrade BGP : 2/2 Established
Reason          : Routine OS upgrade per SoT target_version

upgrade_needed: true
```

Run against all active devices, this becomes a pre-upgrade audit: which devices need upgrading, which are already at target, and what their current BGP state is. You run the upgrade against the devices that need it; the pre-check for the others passes cleanly and exits.

---

## Exercise 28.1 — Firmware Upgrade {#ex281}

🟡 **Practitioner**

### Scenario

ACME's change board has approved upgrading `leaf-lon-02` from EOS 4.32.2F to 4.32.3F. The CAB reference is CAB-2026-0041. The upgrade should use the SoT's `target_version` field as the authority. Your task is to set the target version, detect the mismatch, and execute the upgrade workflow.

### Inject the Fault

```bash
ansible-playbook scenarios/ch08/ex105_inject.yml
```

This adds `target_version: "4.32.3F"` to `leaf-lon-02`'s SoT entry with the CAB reference in a comment. The device is still running 4.32.2F — the SoT now declares a mismatch.

### Your Task

**Step 1 — Inspect the SoT entry.**

```bash
grep -A 3 'image:' sot/devices/lon-dc1/leaf-lon-02.yml
```

You should see:
```yaml
image: ceos:4.32.2F
target_version: "4.32.3F"  # INJECTED: upgrade approved via CAB-2026-0041
```

This is the SoT state after the change board approves the upgrade but before the upgrade is executed. The `image:` field reflects what is currently running. The `target_version:` field declares what should be running.

**Step 2 — Run the upgrade pre-check.**

```bash
ansible-playbook playbooks/os_upgrade.yml \
  --limit leaf-lon-02 \
  --extra-vars "image_path=/images/EOS-4.32.3F.swi confirmed=yes" \
  --tags precheck
```

The pre-check phase will:
- Read the current running version from the device
- Compare it to `target_version` from the SoT
- Report `upgrade_needed: true` and the pre-upgrade BGP state

In the lab without a real EOS image, stop here. The pre-check demonstrates the detection pattern. Move directly to the verify step to confirm detection.

**Step 2b — Full upgrade (if image available).**

If you have an EOS image available at the path:

```bash
ansible-playbook playbooks/os_upgrade.yml \
  --limit leaf-lon-02 \
  --extra-vars "image_path=/path/to/EOS-4.32.3F.swi confirmed=yes \
                upgrade_reason='CAB-2026-0041: BGP timer regression fix'"
```

Watch the maintenance phase — BGP graceful-shutdown is applied and you can observe traffic draining on `leaf-lon-01` (which absorbs the load). Then watch the reload wait: the playbook polls until the device returns on SSH, then runs a second poll until BGP reconverges.

**Step 3 — Verify.**

```bash
# Detection-only mode (default — no real image needed)
ansible-playbook scenarios/ch08/ex105_verify.yml

# Full upgrade mode (if you completed the actual upgrade)
ansible-playbook scenarios/ch08/ex105_verify.yml \
  --extra-vars "verify_mode=full_upgrade"
```

Detection-only checks: `target_version` is present in the SoT and correctly set to `4.32.3F`.

Full upgrade checks: running version matches target, all BGP sessions Established.

### What to Notice

**The SoT update happens after the upgrade.** After a successful upgrade, the playbook updates the `image:` field in the SoT to reflect the new running version, and removes the `target_version:` field (or leaves it — both approaches are valid). The important thing is that the SoT remains an accurate reflection of reality, not a stale record.

**Idempotency matters.** Run the playbook again after a successful upgrade:

```bash
ansible-playbook playbooks/os_upgrade.yml --limit leaf-lon-02 \
  --extra-vars "image_path=/images/EOS-4.32.3F.swi confirmed=yes"
```

It will detect that the current version matches the target and exit cleanly:
```
leaf-lon-02 is already running 4.32.3F (= target). No upgrade needed. Exiting cleanly.
```

This is the correct behaviour for a scheduled upgrade run: devices already at target are skipped without error.

**The maintenance phase protects BGP convergence.** The graceful-shutdown before reload gives peer devices (the two spines) 60 seconds to prefer alternative paths. When `leaf-lon-02` reloads, the spines have already deprioritised its routes. When it comes back, the routes are re-advertised at full preference. The BGP convergence after the reload is fast because the spines never fully removed the routes from their tables — they just deprioritised them.

---

## Running Upgrades at Scale

For a planned upgrade window covering multiple devices, the pattern is:

```bash
# 1. Run pre-check across all active devices — identify who needs upgrading
ansible-playbook playbooks/os_upgrade.yml \
  --extra-vars "target_version=4.32.3F image_path=/images/EOS-4.32.3F.swi" \
  --tags precheck

# 2. Review the output — confirm which devices need upgrading and their BGP state

# 3. Upgrade leaf switches (one at a time to preserve ECMP)
for leaf in leaf-lon-01 leaf-lon-02 leaf-lon-03 leaf-lon-04; do
  ansible-playbook playbooks/os_upgrade.yml \
    --limit "$leaf" \
    --extra-vars "image_path=/images/EOS-4.32.3F.swi confirmed=yes \
                  upgrade_reason='CAB-2026-0041'"
done

# 4. Upgrade spines last (they carry the most critical BGP sessions)
for spine in spine-lon-01 spine-lon-02; do
  ansible-playbook playbooks/os_upgrade.yml \
    --limit "$spine" \
    --extra-vars "image_path=/images/EOS-4.32.3F.swi confirmed=yes \
                  upgrade_reason='CAB-2026-0041'"
done
```

The ordering matters. Leaf switches first: each one upgrades independently while the other leaf carries VRRP and ECMP traffic. Spines last: the spines are route reflectors, and upgrading them last means the leaf switches are already on the new version and have stable BGP sessions before the RR is reloaded.

Never upgrade both spines simultaneously. A spine reload drops all iBGP sessions for all RR clients in the DC until the spine comes back. If both spines reload simultaneously, London DC1 loses all inter-device iBGP for the duration.

---

## The Audit Trail

After the upgrade window, the `state/upgrades/` directory contains one record per device:

```yaml
upgrade_record:
  device: leaf-lon-02
  role: leaf
  site: lon-dc1
  from_version: "4.32.2F"
  to_version: "4.32.3F"
  reason: "CAB-2026-0041: BGP timer regression fix"
  completed_at: "2026-04-04T02:47:11Z"
  engineer: "jsmith"
```

Combined with the git commit updating `image:` in the SoT, this gives you:
- What version the device was running before
- What version it is running now
- When the change happened
- Who authorised and executed it
- The CAB reference linking it to the change board approval

This is the operational traceability required by REQ-016 and the MiFID II article on change management.

---

## 🔵 The Version Governance Model {#version-governance}

🔵 **Strategic**

The `target_version` pattern in the SoT implements a simple but effective governance model:

1. **Change board approves upgrade** → engineer adds `target_version:` to affected SoT entries with CAB reference
2. **SoT is the truth** → any device without `target_version:` is assumed to be at its correct version (no upgrade needed)
3. **Pipeline enforces compliance** → `os_upgrade.yml` detects mismatches and remediates them; a CI check can alert if `target_version` has been set for more than X days without being actioned
4. **SoT reflects reality** → after upgrade, `image:` is updated and `target_version:` is removed

This model ensures that version drift is always visible (it's in the SoT as a mismatch), always attributed (the CAB reference is in the YAML comment), and always actionable (the playbook remediation is a single command).

Without this model, version state is implicit — what the device reports is what you get. With this model, version state is explicit — what the SoT declares is the authority, and the device either conforms or is in a documented remediation state.

The same governance model applies to every other SoT field. This is what makes the SoT-first approach more than a configuration management tool — it is an operational governance framework.

---

## Debrief

**What was practised:** Running a firmware upgrade driven by the SoT's `target_version` field — with pre-checks that verify readiness, post-checks that confirm success, and a governance model that tracks the upgrade from change-board approval to completion.

**Why it matters:** The `target_version` pattern makes version drift visible and actionable. A device without `target_version` is at its correct version. A device with `target_version` is in a documented remediation state — the SoT records what version it should be, and the playbook enforces it. This eliminates the implicit version management where "whatever the device reports" is the only truth.

**In production:** OS upgrades in financial services networks are among the most risk-sensitive operations. The pre-check/post-check pattern ensures that an upgrade does not proceed if prerequisites are not met (wrong image, insufficient disk, active maintenance window) and that success is verified programmatically, not assumed.

---

**Next:** Chapter 29 introduces the monitoring stack — Prometheus, Grafana, and the observability layer that connects the Day-2 operational data to real-time dashboards and alerting.
