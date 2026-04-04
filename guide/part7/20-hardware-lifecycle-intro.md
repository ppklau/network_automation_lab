# Part 7: Hardware Lifecycle

# Chapter 20: What Hardware Lifecycle Automation Actually Changes

🔵 **Strategic**

When ACME's London DC went through its last hardware refresh cycle, the network team spent six weeks on it. Not because the work was technically complex — a leaf switch replacement is mostly copy-pasting a config — but because of the coordination overhead. Schedule the maintenance window. Order the hardware. Wait for delivery. Escalate the service desk ticket. Find the correct config for the specific device. Confirm which VLANs it carries. Get a senior engineer to do the push. Verify the BGP sessions came up. Write the change record.

Most of those steps have nothing to do with the network.

The SoT-driven pipeline changes the shape of an RMA from "find a senior engineer and block out two hours" to "update one field in a YAML file and run a playbook." The junior engineer on the overnight shift can do it. The on-call engineer who gets paged at 03:00 can do it from their laptop without needing to know the device's full configuration from memory.

This is not an incremental improvement. It is a structural change in what skills are required to operate the network.

## The Hardware Lifecycle Events

Module 10 covers four lifecycle events that every network eventually faces:

| Event | Playbook | Typical trigger |
|---|---|---|
| Leaf switch failure | `rma_leaf.yml` | Hardware fault; EOL replacement |
| Border router failure | `rma_border.yml` | Hardware fault; higher impact than leaf |
| New branch deployment | `ztp_branch.yml` | Office opening; branch expansion |
| OS upgrade | `os_upgrade.yml` | Vendor advisory; compliance; planned refresh |

Each of these existed before automation. The difference is what happens when you run the automation versus what happens when you do it manually.

### Before: Manual Leaf RMA

1. An engineer SSHs to the failed switch and captures the running config (if the device is still up)
2. A different engineer cross-references the config against the design documentation (if documentation exists)
3. The replacement arrives. The engineer re-enters the config manually or pastes from notes
4. BGP is verified by watching `show bgp summary` for several minutes
5. The VLAN config is verified by checking a few test hosts
6. The change record is written retrospectively from memory

Total time: 2–4 hours. Error rate: non-trivial. Requires a senior engineer with knowledge of that specific device's config.

### After: Automated Leaf RMA

```bash
ansible-playbook playbooks/rma_leaf.yml \
  --limit leaf-lon-02 \
  --extra-vars "new_serial=ACE2501099X rma_reason='PSU failure' confirmed=yes"
```

The pipeline:
1. Reads the full configuration from the SoT (which already knows the VLANs, BGP config, VRFs, VRRP priorities)
2. Updates the serial number
3. Renders a config identical to the failed device
4. Pushes it to the replacement
5. Waits for BGP sessions to recover
6. Verifies sessions and writes an artefact record

Total time: under 10 minutes. Requires: the serial number of the replacement device. Executable by a junior engineer.

The senior engineer's knowledge is now encoded in the SoT, the templates, and the playbook — not locked in a person's head.

---

## 🔵 Exercise 10.6 — The Compounding Argument {#ex106}

🔵 **Strategic**

This exercise has no inject and no verify playbook. It is a discussion exercise.

Consider the following two scenarios from ACME's network history:

**Scenario A — The midnight leaf failure (before automation):**
A leaf switch in London DC1 failed at 23:40. The on-call engineer, who had been at ACME for three months, had never replaced a leaf before. The runbook said to call a senior engineer. The senior engineer lived 45 minutes away. By the time the correct config was rebuilt and pushed, 2h 20m had elapsed. Some TRADING VMs were silently running on a single uplink (ECMP broken) for the entire duration.

**Scenario B — The same failure (after automation):**
Same failure, same on-call engineer, but now the SoT pipeline exists. The engineer ran `daily_health_check.yml`, identified the failing device, ran `rma_leaf.yml` with the replacement serial from the delivery note taped to the hardware, and verified BGP in 8 minutes. The senior engineer was not called.

**Questions to consider:**

1. What is the actual cost of Scenario A? (Time to restore is 2h 20m, but what are the downstream costs — VRRP failover, TRADING latency, MiFID II incident reporting, post-incident review?)

2. In Scenario B, what knowledge did the junior engineer need that they would not have needed in Scenario A? (Answer: essentially none — they ran a command and read the output.)

3. What is the risk in Scenario B that didn't exist in Scenario A? (The SoT must be correct. If the SoT has wrong VLAN data, the replacement device will also have wrong VLAN data. What is the control that prevents this? See: Chapter 7 schema validation and Batfish intent checks.)

4. ACME has 30 branches across four regions. If each branch requires a router replacement every five years, that's six replacements per year. At 2h 20m each (manual), that's 14 engineer-hours per year on branch RMAs alone — all requiring senior engineering skill. At 8 minutes automated, that's under an hour. What could those 13 recovered hours be spent on?

> **Key insight:** Automation's ROI is not just in the reduction of individual task duration. It is in the reduction of the skill threshold required to execute the task safely. This changes who can be on call, who can be trusted to execute a change, and what your senior engineers' time is actually spent on.

---

## The Lab Setup for Part 7

The four hardware lifecycle playbooks require the same lab state as Part 6:

```bash
ansible-playbook scenarios/common/reset_lab.yml
ansible-playbook scenarios/common/verify_lab_healthy.yml
```

A healthy lab has:
- All BGP sessions Established
- All loopbacks reachable
- No active maintenance windows
- No stale scenario breadcrumbs in `/tmp/`

The RMA and ZTP scenarios involve temporarily degrading device state (shutting interfaces, clearing configs). Each scenario's inject playbook is designed so that running the target playbook is the remediation — you are not expected to diagnose and manually reverse the injection.

### Output Artefacts

The hardware lifecycle playbooks write to three new directories under `state/`:

```
state/
  rma/
    leaf-lon-02_<timestamp>.yml     # RMA completion record
    border-lon-01_<timestamp>.yml
  provisioned/
    branch-nyc-02_<timestamp>.yml   # ZTP provisioning record
  upgrades/
    leaf-lon-02_<timestamp>.yml     # OS upgrade record
```

These artefacts form the audit trail for hardware changes. In a production environment, they would be committed to git alongside the SoT change that triggered them, giving you a complete change history: device X was replaced on date Y, with serial Z, by engineer W, because of reason V.

---

**Next:** Chapter 21 walks through the leaf switch RMA workflow — from fault detection to BGP reconvergence.
