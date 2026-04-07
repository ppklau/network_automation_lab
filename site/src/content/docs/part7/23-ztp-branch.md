---
title: "Chapter 23: Zero-Touch Provisioning for Branch Routers"
---

## The Branch Deployment Problem

ACME has 30 branches across four regions. Opening a new branch, or replacing a failed branch router, used to require either sending an engineer on-site or shipping a pre-configured device. Both options are expensive. An engineer visit to a regional branch costs a day of travel time plus the configuration work. A pre-configured device requires someone to configure it in advance, label it correctly, and hope that the configuration is still correct by the time the device ships and arrives.

Zero-touch provisioning (ZTP) eliminates both. The branch router ships with nothing but a minimal bootstrap configuration — enough to get management access. The pipeline detects the new device, pulls the full configuration from the SoT, and pushes it. The on-site contact (which might be a facilities manager with no networking knowledge) only needs to plug in the cables and power.

## How ACME's ZTP Works

The ZTP path in this lab models the most common real-world pattern:

1. **Device shipped pre-imaged** — The branch router leaves the warehouse running FRR with a minimal bootstrap config: management interface gets DHCP (or a pre-assigned static IP from IPAM), SSH is enabled for the `ansible` user.

2. **SoT record exists** — The branch is already in `sot/devices/branches/` before the device ships. All the configuration data — ASN, WAN IPs, BGP peers, LAN prefix — is defined at the time the branch is created in the SoT, not at the time of deployment.

3. **Pipeline push** — `ztp_branch.yml` renders the full SoT config for the target branch and pushes it. BGP sessions to the border router establish automatically.

4. **Verification** — The playbook confirms BGP is Established and writes a provisioning artefact.

This is the model described in INTENT-007 (`provisioning_standards.yml`): branch routers are provisioned from the SoT pipeline with no manual CLI configuration required.

### The Bootstrap Config

The minimal bootstrap config that FRR branch routers ship with looks like this:

```
frr version 9.1.0
frr defaults traditional
hostname branch-nyc-02
!
interface eth0
 description OOB management
 ip address 10.200.0.17/29
!
ip route 0.0.0.0/0 10.200.0.22
!
line vty
!
```

That's it. No BGP. No WAN IP. The router can reach the Ansible controller via the management network, and that's all it needs. The pipeline handles the rest.

---

## Exercise 10.4 — Branch Router ZTP {#ex104}

🟡 **Practitioner**

### Scenario

ACME is opening a new branch office in Newark, NJ. The branch router (`branch-nyc-02`) has been shipped with a minimal bootstrap config and installed by the local facilities team. The device is accessible on management. Your task is to use the ZTP pipeline to provision the full configuration and bring the branch online.

### Inject the Fault

```bash
ansible-playbook scenarios/ch08/ex104_inject.yml
```

This clears the FRR configuration on `branch-nyc-02` to simulate a factory-fresh device — removing the BGP configuration and WAN interface IPs. Only management access (eth0) remains.

### Your Task

**Step 1 — Confirm the SoT record exists.**

Before running ZTP, confirm that `branch-nyc-02` is defined in the SoT:

```bash
grep -A 20 'branch-nyc-02' sot/devices/branches/us-branches.yml
```

What ASN is assigned? What WAN IP? What is the uplink peer IP for the BGP session to `border-nyc-01`?

This is the data the pipeline will use. You are confirming that the SoT reflects the physical reality before trusting the pipeline to push it.

**Step 2 — Run the ZTP playbook.**

```bash
ansible-playbook playbooks/ztp_branch.yml \
  --limit branch-nyc-02 \
  --extra-vars "provisioned_by='Operations team'"
```

Watch the phases:
1. Pre-check: confirms the target is a branch, verifies management reachability
2. Render: calls `render_configs.yml` to generate the FRR config from SoT
3. Push: writes the rendered config to `/etc/frr/frr.conf` and reloads FRR
4. Verify: checks that at least one BGP session is Established
5. Artefact: writes a provisioning record to `state/provisioned/`

**Step 3 — Verify.**

```bash
ansible-playbook scenarios/ch08/ex104_verify.yml
```

Checks:
- BGP session to `border-nyc-01` is Established
- `eth1` has the correct WAN IP from the SoT

**Step 4 — Update lab_state in SoT (if applicable).**

If `branch-nyc-02` was `sot_only` before this exercise, update its `lab_state` to `active` now that it is provisioned:

```bash
# In sot/devices/branches/us-branches.yml, find branch-nyc-02 and change:
#   lab_state: sot_only
# to:
#   lab_state: active
git add sot/devices/branches/us-branches.yml
git commit -m "ZTP: branch-nyc-02 provisioned and active"
```

### What to Notice

**The SoT was complete before the device existed.** `branch-nyc-02` was defined in the SoT when the office was approved — not when the hardware arrived. This decoupling is intentional: network engineering work (assigning ASNs, IPs, BGP policy) happens at design time, not at installation time. The installation is a mechanical step that a non-engineer can execute.

**The playbook handles FRR reload safely.** FRR does not have a "replace config" mode like NAPALM does for EOS. The playbook writes the full rendered config to `/etc/frr/frr.conf` and calls `service frr reload`, which applies the configuration without dropping existing connections. On a factory-fresh device this distinction doesn't matter — but on a replacement device that still has a partial configuration, a reload is safer than a restart.

**Management reachability is the only pre-condition.** The inject playbook cleared the BGP configuration, but the device is still reachable on `eth0`. This models the real-world ZTP scenario precisely: a new device from the warehouse has management access but nothing else. The ZTP playbook asks: "Can I reach this device on SSH?" If yes, it proceeds. If no, it warns and exits.

---

## ZTP vs. Pre-Staging

There is a simpler alternative to ZTP: pre-stage the full config before shipping the device. An engineer configures the device in the office, labels it, ships it, and the on-site contact plugs in the cables.

This works, but it has three failure modes that ZTP eliminates:

**Stale config:** If the SoT changes between pre-staging and installation (an IP address reassignment, an ASN change, a BGP policy update), the pre-staged config is wrong. ZTP always pulls from the current SoT.

**Human error in pre-staging:** Copying configuration manually introduces typos. Applying the wrong template to a device introduces wrong VLANs or wrong BGP configuration. ZTP uses the same template pipeline as every other device push — it cannot introduce a typo that was not already in the SoT.

**Audit gap:** A manually pre-staged device has no provenance — there is no record of exactly which configuration was pushed, by whom, and at what time. ZTP produces a `state/provisioned/` artefact that records the SoT state at the time of provisioning, the template that was used, and the engineer who ran the playbook.

---

## 🔵 What ZTP Changes About Branch Operations {#ztp-strategic}

🔵 **Strategic**

At ACME's current scale — 30 branches — the ZTP improvement is measurable but not transformative. The real benefit appears at scale and in resilience scenarios.

**Rapid deployment:** ACME's strategy team is considering expanding into Southeast Asia. Twelve new branches in Singapore, Kuala Lumpur, Jakarta, Bangkok, and six other cities. Without ZTP, this requires either twelve on-site engineering visits or twelve pre-staged devices that could become stale during shipping. With ZTP, the network team creates twelve SoT records, ships twelve devices with minimal bootstrap configs, and provisions all twelve via the pipeline when the devices come online.

**Branch failure recovery:** A branch router failure in Birmingham at 02:00 would require a courier run or an on-site visit in the manual model. With ZTP, the replacement ships next-day, the facilities manager plugs it in, and the on-call engineer runs `ztp_branch.yml` remotely. The branch is back online before business hours.

**Consistency at scale:** With manual provisioning, each branch configuration diverges over time — a change made here, a tweak made there, an NTP server added during a troubleshooting session. With SoT-driven ZTP, every branch config is derived from the same SoT. `drift_detection.yml` catches deviations. The compliance posture for all 30 branches is auditable from a single YAML file.

> **For managers in the room:** ZTP is not primarily a time-saving tool at ACME's current scale. It is a consistency and auditability tool. The compliance value — being able to prove that all 30 branches received an identical BGP policy, derived from the SoT that was approved by the network architect — is the business case. The time saving is a bonus.

---

**Next:** Chapter 24 covers OS upgrades — using the SoT's `target_version` field to drive a structured upgrade workflow with pre-checks and post-verification.
