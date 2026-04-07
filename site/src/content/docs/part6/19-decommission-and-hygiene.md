---
title: "Chapter 19: Decommission and SoT Hygiene"
---

# Chapter 19: Decommission and SoT Hygiene

## Decommission Is the Hardest Operation

In most networks, provisioning gets the automation investment and decommissioning gets none.

The reasoning is understandable: provisioning happens frequently, has clear deliverables, and delivers visible value. Decommissioning happens rarely, involves removing things rather than adding them, and the consequences of getting it wrong are less visible. A device that is half-decommissioned — removed from the rack but still in BGP tables, still in the IPAM, still in the spreadsheet — rarely causes an immediate outage. It just quietly consumes resources and creates confusion.

But in a financial services network, a half-decommissioned device is a liability. Every device in a compliance record that doesn't physically exist needs explaining. Every BGP peer entry that points to a decommissioned device is a potential instability. Every IP address in an IPAM for a device that no longer exists is an IP that cannot be assigned to something new.

`playbooks/decommission.yml` treats decommission as a first-class operation with the same rigour as provisioning.

---

## The Six Phases of Decommission

The playbook runs six plays in sequence. They cannot be skipped individually — each phase gates the next.

### Phase 1: Pre-Checks

```
- Assert --limit is specified (no accidental full-estate decommission)
- Assert reason= is provided (required for audit trail)
- Assert target is not a spine/route-reflector (these need replacement first)
- Load and validate the SoT record
- Check device reachability
```

The spine check is critical. Decommissioning a route reflector without first designating a replacement would partition the network. The playbook refuses to proceed.

### Phase 2: BGP Drain

```
- Apply graceful-shutdown (EOS: graceful-restart-helper, FRR: bgp graceful-shutdown)
- Wait 30 seconds for peers to update path selection
- FRR: remove network statements to stop prefix advertisements
```

The 30-second wait is conservative. In production, you would tune this based on the BGP timer configuration. The default hold-time is 90 seconds, but graceful-shutdown typically drains traffic within a few seconds on a well-tuned network.

### Phase 3: Confirmation Gate

```
ansible.builtin.pause:
  prompt: |
    !! WARNING: About to decommission {{ inventory_hostname }} !!
    This will zero all interfaces and update the SoT.
    This action is irreversible without restoring from the git history.
    Press ENTER to confirm or Ctrl+C to abort.
```

This is the deliberate human checkpoint. In lab exercises, you skip it with `confirmed=yes`. In production, you would leave it in and require an engineer to confirm before the playbook proceeds to the destructive phases.

🔵 **Strategic: When to gate and when to automate**

Every automation decision involves a judgment about where human judgment adds value. BGP drain is safe to automate — the algorithm is deterministic and the risk of the automation making a wrong decision is very low. Interface shutdown is safe to automate once you have confirmed the device is the right target.

The confirmation gate is not because the automation is unreliable. It is because the consequences of decommissioning the wrong device are severe and the cost of a human pause is low. The gate exists to catch the scenario where the engineer ran the playbook with `--limit branch-lon-01` and then immediately doubted themselves.

### Phase 4: Interface Shutdown

```
- Shutdown all interfaces except Management0 and Loopback0 (EOS)
- Shutdown all interfaces except lo and eth0 (FRR)
```

Zeroing interfaces ensures no data traffic passes through the device during the final steps. The management interface stays up so Ansible can complete the remaining phases.

### Phase 5: SoT Update

```yaml
# Changes lab_state from 'active' to 'decommissioned'
# Adds decommission metadata:
decommission_date: "{{ ansible_date_time.iso8601 }}"
decommission_reason: "{{ reason }}"
decommission_engineer: "{{ ansible_user }}"
```

The SoT is updated in-place using `ansible.builtin.replace`. After this, `generate_inventory.py` will exclude the device from the active inventory because `lab_state != 'active'`.

### Phase 6: Archive

```
- Copy SoT record to state/decommissioned/<hostname>_<timestamp>.yml
- Copy last rendered config to state/decommissioned/<hostname>_config_<timestamp>.txt
- Print summary with git commit instructions
```

The archive preserves the full device record and its last known configuration. If the device is ever repurposed or the decommission needs to be reversed, the historical state is available.

---

## Exercise 1.2.1 — Decommission a Branch Office {#ex121}

🟡 **Practitioner**

### Scenario

ACME's Leeds branch office (`branch-lon-01`) is being closed. The building lease expires at end of month. All staff have been relocated to the London HQ. The physical router has been removed from the rack. Your task is to cleanly remove it from the network.

This is not a fault-injection exercise — there is no pre-existing problem to fix. This is a complete, realistic operational task.

### Set Up the Scenario

```bash
ansible-playbook scenarios/ch07/ex121_inject.yml
```

This writes a breadcrumb explaining the context (the inject here is purely informational — the device is already in its pre-decommission state in the lab).

### Your Task

**Step 1 — Confirm the current state.**

```bash
ansible-playbook playbooks/daily_health_check.yml --limit branch-lon-01
```

Confirm `branch-lon-01` is currently active and BGP is established.

**Step 2 — Run the decommission playbook.**

```bash
ansible-playbook playbooks/decommission.yml \
  --limit branch-lon-01 \
  --extra-vars "reason='Leeds branch closure — lease ended' confirmed=yes"
```

Watch the six phases run. Note where the BGP drain happens, where the confirmation gate would pause (bypassed by `confirmed=yes`), and where the SoT is updated.

**Step 3 — Commit the SoT change.**

```bash
git add sot/devices/branches/uk_branches.yml
git add state/decommissioned/
git commit -m "Decommission branch-lon-01 — Leeds branch closure"
```

This is an explicit step because the decommission playbook updates files but does not commit them. The git commit is the final, immutable record.

**Step 4 — Regenerate the inventory.**

```bash
python3 scripts/generate_inventory.py
```

**Step 5 — Verify.**

```bash
ansible-playbook scenarios/ch07/ex121_verify.yml
```

The verify checks three things:
1. `branch-lon-01` SoT record has `lab_state: decommissioned`
2. An archive file exists in `state/decommissioned/`
3. `branch-lon-01` is absent from the active inventory

### What to Notice

- The full decommission — including BGP drain, SoT update, archive, and inventory regeneration — takes under two minutes. Manually, this would require logging into `border-lon-01` to remove the BGP neighbor, updating a spreadsheet, filing a closure ticket, and notifying the IP team. The audit trail would be scattered across several systems.
- The git commit is the single source of truth. `git log --follow sot/devices/branches/uk_branches.yml` shows the entire lifecycle of the device: initial provisioning, any config changes, and the decommission.
- After the exercise, restore the lab: `ansible-playbook scenarios/common/reset_lab.yml` — this will push all configs including branch-lon-01 back to active state.

---

## SoT Hygiene

As the network grows and devices are added by different engineers, the SoT accumulates errors. These are almost always copy-paste mistakes: a new branch device gets added by duplicating an existing record, but the ASN field is not updated. An interface description is left as the template placeholder. A device hostname doesn't follow the naming convention.

None of these cause immediate failures. But they create confusion, make automation less reliable, and fail compliance audits.

`scripts/sot_hygiene.py` performs seven cross-file checks that Ansible alone cannot do elegantly:

| Code | Check | What it catches |
|---|---|---|
| HYG-001 | Hostname convention | Names not matching `[a-z][a-z0-9-]+-[a-z]{2,5}-\d{2}` |
| HYG-002 | Interface descriptions | Blank, `TBD`, `TODO`, `UNKNOWN`, `N/A` |
| HYG-003 | Duplicate ASNs | Two devices with the same ASN |
| HYG-004 | CHANGEME credentials | Vault references still containing placeholder values |
| HYG-005 | Stale sot_only devices | Devices with `sot_only: true` that have been sot_only for > 90 days |
| HYG-006 | Duplicate compliance tags | Same tag on two different devices |
| HYG-007 | Missing mandatory fields | hostname, platform, management_ip, asn, lab_state absent |

HYG-003 (duplicate ASNs) and HYG-007 (missing fields) are CRITICAL — they will cause BGP or provisioning failures. HYG-002 (missing descriptions) and HYG-004 (CHANGEME credentials) are WARNING. HYG-005 and HYG-006 are INFORMATIONAL.

### Running the Hygiene Check

```bash
# Human-readable output
python3 scripts/sot_hygiene.py

# JSON output (used by sot_hygiene.yml playbook)
python3 scripts/sot_hygiene.py --json

# Strict mode — treat warnings as errors
python3 scripts/sot_hygiene.py --strict

# Via Ansible (writes reports/)
ansible-playbook playbooks/sot_hygiene.yml
```

### Clean Output

```
ACME SoT Hygiene Report
=======================
Checked 12 device files across 3 sites

CRITICAL issues: 0
WARNING issues:  0
INFO issues:     0

✓ SoT is clean
```

### Output with Issues

```
ACME SoT Hygiene Report
=======================
Checked 12 device files across 3 sites

CRITICAL issues: 1
  [HYG-003] branch-lon-02: ASN 65100 is a duplicate of branch-lon-01
             Fix: Change asn in sot/devices/branches/uk_branches.yml

WARNING issues: 2
  [HYG-002] leaf-lon-04/Ethernet1: Interface has no description
             Fix: Add description field to interface entry
  [HYG-002] leaf-lon-04/Ethernet2: Interface has no description
             Fix: Add description field to interface entry

Exit code: 1 (CRITICAL issues present)
```

---

## Exercise 8.8 — SoT Hygiene Issues {#ex88}

🟡 **Practitioner**

### Scenario

A new branch device (`branch-lon-02`) was added by duplicating the `branch-lon-01` SoT record. The engineer updated the hostname and management IP but forgot to change the ASN. Separately, an interface description was removed from `leaf-lon-04` during a hurried incident response where the engineer was editing the SoT file and accidentally deleted two lines.

Neither issue caused an immediate failure. But the duplicate ASN will cause BGP to fail if `branch-lon-02` is ever provisioned, and the missing descriptions will fail the next compliance audit.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex88_inject.yml
```

This modifies the SoT YAML files directly:
- Changes `branch-lon-02` ASN from `65101` to `65100` (duplicate of `branch-lon-01`)
- Removes descriptions from `leaf-lon-04` Ethernet1 and Ethernet2

No device configs are changed — this is a SoT-only injection.

### Your Task

**Step 1 — Run the hygiene check.**

```bash
python3 scripts/sot_hygiene.py
```

You should see:
- 1 CRITICAL: duplicate ASN
- 2 WARNING: missing descriptions

**Step 2 — Fix the issues** by editing the SoT files directly:

Fix the ASN:
```bash
# Edit sot/devices/branches/uk_branches.yml
# Change branch-lon-02 asn: 65100 → asn: 65101
```

Restore the descriptions:
```bash
# Edit sot/devices/lon-dc1/leaf-lon-04.yml
# Add description back to Ethernet1 and Ethernet2
```

**Step 3 — Re-run the hygiene check** to confirm it is clean:

```bash
python3 scripts/sot_hygiene.py
```

**Step 4 — Verify.**

```bash
ansible-playbook scenarios/ch07/ex88_verify.yml
```

### What to Notice

- The hygiene check catches issues in SoT files that would not be visible in device configs. The duplicate ASN exists only in YAML — the device hasn't been provisioned yet. If the check wasn't run, the error would only surface when `branch-lon-02` was provisioned and BGP failed to establish.
- The fix is pure YAML editing — no device interaction required. This is one of the advantages of a SoT-driven approach: many classes of error can be caught and fixed without touching a live device.

> **CI gate:** Add `python3 scripts/sot_hygiene.py --strict` to your `.gitlab-ci.yml` validate stage. Any PR that introduces a CRITICAL or WARNING hygiene issue will fail the pipeline before it can be merged.

---

## SoT Hygiene as a CI Gate

Add to `.gitlab-ci.yml`:

```yaml
sot-hygiene:
  stage: validate
  script:
    - python3 scripts/sot_hygiene.py --strict --json > reports/hygiene_${CI_PIPELINE_ID}.json
  artifacts:
    paths:
      - reports/hygiene_*.json
    expire_in: 90 days
  rules:
    - changes:
        - sot/**/*.yml
```

This runs the hygiene check only when SoT files change, and stores the report as a CI artefact. The 90-day retention gives you a history of hygiene state over time.

---

## Part 6 Summary

You have now built and exercised the full Day-2 operations suite:

| Exercise | Skill Demonstrated |
|---|---|
| 8.1 BGP auth mismatch | Drift detection catches OOB BGP changes |
| 8.2 OOB NTP/description | Drift severity classification |
| 4.3 Telnet violation | Compliance reporting as a CI gate |
| 4.4 Regulatory artefact | SHA256-signed audit trail for MiFID II |
| 8.4 Route-map prefix suppression | Prefix monitoring catches what health checks miss |
| 8.6 Stuck maintenance mode | State-tracked maintenance windows |
| 1.2.1 Branch decommission | Six-phase safe decommission with full audit trail |
| 8.8 SoT hygiene | Cross-file consistency checks as a CI gate |

Each of these exercises models a real incident or operational task drawn from financial services network operations. The playbooks are not toy examples — they are the patterns you would adapt directly for a production estate.

Before moving to Part 7 (monitoring stack), reset your lab to known-good state:

```bash
ansible-playbook scenarios/common/reset_lab.yml
```

---

**Next:** Part 7 — Building the Monitoring Stack. You will connect the Prometheus output files from the Day-2 playbooks to a Grafana dashboard and build alerting rules that automatically open maintenance tickets.
