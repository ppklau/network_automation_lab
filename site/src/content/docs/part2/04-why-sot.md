---
title: "Chapter 4: Config Is an Output, Not an Input"
---

> 🔵 **Strategic** — no CLI in this chapter

---

## The insight that changes everything

In a traditional network operations model, the device is the source of truth. If you want to know what a device is doing, you log in and look. If you want to change what it is doing, you type commands and the change takes effect. The config file on the device is the record of intent.

This model has a problem that compounds over time: the device config accumulates changes from hundreds of sessions by dozens of engineers over years. Some changes were intentional. Some were exploratory and never cleaned up. Some were emergency fixes that bypassed the normal process. Some were made by engineers who have since left. The config is an accurate description of every change that was ever made — not of what the network was ever designed to do.

The source-of-truth model inverts this. The device config is an **output**, generated from an authoritative declaration of intent. The declaration lives in version-controlled YAML. The device holds a copy. The copy can drift — but the SoT can regenerate and re-apply the correct config at any time.

This is not a new idea. Infrastructure as Code communities have operated this way for years. What is newer is applying it rigorously to network infrastructure, where the stakes are higher, the devices are more varied, and the compliance requirements are more demanding.

---

## What a SoT actually is

A source of truth is not a database of device configs. It is a database of **intent**.

The distinction matters. A device config contains:

```
interface Vlan100
   description TRADING_ZONE
   ip address 10.1.1.1/24
   no shutdown
```

A SoT entry contains:

```yaml
- name: Vlan100
  description: "TRADING zone SVI"
  ip: 10.1.1.1/24
  vrf: TRADING_VRF
  zone: TRADING
  vrrp:
    - group: 10
      virtual_ip: 10.1.1.254
      priority: 110
  intent_refs: [INTENT-001, INTENT-002]
```

The SoT entry expresses what the interface is for (`zone: TRADING`), what compliance obligations it carries (`intent_refs`), and what redundancy it should provide (`vrrp`). The specific config syntax — whether it is Arista EOS, Cisco IOS, or Juniper JunOS — is a rendering concern, handled by the Jinja2 template layer. The SoT entry works for any platform.

When you add a new device vendor, you write a new template. You do not rewrite the SoT.

---

## The compliance argument

> 🔵 **Strategic**

Regulators do not care about your config files. They care about evidence of control. Specifically:

- **What is the intended state of the network?** (The SoT provides this)
- **How is that intent enforced?** (The pipeline and Batfish assertions provide this)
- **What changed, when, who approved it, and what was the impact?** (Git history and pipeline artefacts provide this)
- **Is the network currently consistent with its intended state?** (The drift detection playbook provides this)

A device config can answer none of these questions. It tells you what the device is doing right now. It cannot tell you why, who decided it, whether it was reviewed, or whether it matches the design.

The SoT answers all of them — but only if the discipline of SoT-first operations is maintained. That discipline is the hard part. The technical implementation is straightforward. The cultural change — "we do not touch devices directly; we change the SoT and run the pipeline" — requires consistent enforcement and visible tooling that makes it easier to do the right thing than the wrong thing.

The pipeline is that enforcement mechanism. It does not prevent direct device access. It makes the SoT-driven path so much faster and safer than the manual path that the manual path becomes unattractive by comparison.

---

## Why YAML, and why not a database?

YAML is not the only possible representation for a SoT. NetBox, Nautobot, Infrahub, and other platforms are purpose-built for this. They provide UIs, APIs, IPAM integration, and richer validation. For larger teams and larger networks, they are often the right answer.

YAML files in git are the right answer for this lab because:

1. **Zero infrastructure dependency.** No database to provision, no UI to deploy, no API to learn. The lab starts with `git clone`.
2. **Native version control.** Every change is a git commit. The diff is readable. The history is complete. No separate audit log.
3. **Transparent templating.** When you look at a Jinja2 template consuming a YAML file, the relationship between intent and config is explicit and readable. Learning the pattern on YAML transfers directly to learning it on NetBox or any other SoT.
4. **Handbook alignment.** Chapter 3 of the Handbook uses YAML-in-git as the canonical SoT example for exactly these reasons.

The ACME SoT contains 75 files and approximately 10,500 lines of YAML representing the full global network. That is manageable without a database. At 500 devices or 50 engineers, the calculus changes.

---

## The three-layer model

The Handbook describes a three-layer model for intent-based networking:

```
Layer 1: Business requirements
  "Trading systems must be isolated from corporate users"
  "EU data must not traverse non-EU routing paths"
  → documented in requirements/business_requirements.yml

Layer 2: Design intents
  "No reachability between TRADING_VRF and CORPORATE_VRF"
  "Frankfurt devices must not have VLAN 100"
  → documented in design_intents/zone_isolation.yml
  → tested by batfish/tests/test_zone_isolation.py

Layer 3: Operational values
  "leaf-lon-01, Vlan100, 10.1.1.1/24, TRADING_VRF"
  "fra-dc1, vlans_prohibited: [100]"
  → documented in sot/devices/ and sot/sites/
  → rendered by templates/arista_eos/vlans.j2
```

The traceability runs both ways. A specific IP address in a device file exists because of a design intent (which subnet this zone uses). That design intent exists because of a business requirement (MiFID II zone isolation). The chain is readable, auditable, and machine-verifiable.

Without this chain, automation is a productivity tool. With it, automation is a compliance control.

---

## What the SoT cannot do

> 🔵 **Strategic**

A SoT does not automatically become correct just because it exists. It is only as accurate as the discipline that maintains it. Three common failure modes:

**1. The SoT diverges from the network.** Engineers make emergency changes directly on devices and do not update the SoT. The pipeline then "fixes" their emergency change on the next run. This is the drift problem — addressed in Module 8.

**2. The SoT contains incorrect intent.** Someone adds a wrong IP address or a misconfigured BGP policy. The pipeline faithfully renders and pushes the incorrect config. This is why validation (schema checks, Batfish intent verification) must run before the push, not after.

**3. The SoT is incomplete.** Some devices are not managed via the pipeline because migrating them is too complex. Those devices are invisible to the SoT-driven tooling. Drift detection, compliance reporting, and rollback do not work for them. This is the adoption problem — the value of the SoT scales with coverage.

None of these are arguments against the SoT model. They are arguments for taking it seriously: building the validation and enforcement tooling, maintaining the cultural discipline, and expanding coverage deliberately.

*Handbook reference: Chapter 3 (The source of truth), Chapter 11 (Intent-based networking)*
