# Chapter 6: The Intent Layer — From Business Need to Machine Assertion

> 🔵 **Strategic** — sections marked
> 🟡 **Practitioner** — Modules 4.2, 11.1

---

## Scenario

> 🔵 **Strategic**

ACME's head of compliance has a question: "How do I know that the trading network is actually isolated from corporate users, right now, and not just in a document that someone wrote two years ago?"

This is the question that network automation either answers or does not. The traditional answer is: "We have a firewall policy. Here is the document." The problem is that a document is not a test. A document cannot fail. A document cannot tell you whether the config that was deployed last Tuesday matches the policy it describes.

The intent layer answers the question differently: "We have a machine-readable assertion. Here is the most recent test run. It passed 47 minutes ago, on the exact configs currently deployed on those devices."

That is a different kind of evidence. It is the kind that satisfies regulators.

---

## The three layers

```
Layer 1 — Business requirements
  requirements/business_requirements.yml
  "Trading systems must be isolated from corporate users (MiFID II Article 48)"

      ↓ translates to

Layer 2 — Design intents
  design_intents/zone_isolation.yml
  "No reachability between TRADING_VRF and CORPORATE_VRF"
  "fw-lon-01 must be on path for all inter-zone traffic"

      ↓ implemented in

Layer 3 — Operational values (the SoT)
  sot/sites/fra-dc1.yml: vlans_prohibited: [100]
  sot/devices/lon-dc1/leaf-lon-01.yml: vrf: TRADING_VRF
  sot/compliance/zone_policies.yml: ZONE-001

      ↓ rendered as

  configs/leaf-lon-01/running.conf: vrf TRADING_VRF, no cross-VRF routes

      ↓ verified by

  batfish/tests/test_zone_isolation.py
  batfish/tests/test_frankfurt_isolation.py
```

Each layer is traceable to the one above and below it. When a business requirement changes, you can find every design intent that implements it. When a Batfish test fails, you can trace it back to the requirement that mandates it.

---

## Layer 1 — Business requirements

```bash
cat requirements/business_requirements.yml
```

```yaml
requirements:
  - id: REQ-007
    title: "TRADING zone isolation"
    description: >
      Trading systems must be isolated from corporate users at all times.
      No IP reachability path must exist between the TRADING and CORPORATE zones,
      directly or via transit through any other zone.
    owner: CRO
    regulatory_refs:
      - MiFID_II: "Article 48 — algorithmic trading safeguards"
      - FCA: "SYSC 8.1 — systems and controls"
    criticality: critical
    last_reviewed: 2024-01-15
    implements: [INTENT-001, INTENT-002]
```

Each requirement has an owner (who in the business is accountable), regulatory references (which specific articles mandate it), and links to the design intents that implement it. The `last_reviewed` date is tracked here — if this date is more than 12 months old, the compliance report flags it.

> 🔵 **Strategic** — The discipline of writing requirements this way matters. Most organisations have network design documents. Few have machine-readable requirements linked to the specific regulatory articles that mandate each control. The difference matters during an audit: "Here is REQ-007. Here is the MiFID II article it satisfies. Here is the design intent that implements it. Here is the Batfish test that verifies it. Here is last Friday's test run showing it passed." That is an audit-ready evidence trail, not a conversation.

---

## Layer 2 — Design intents

```bash
cat design_intents/zone_isolation.yml
```

```yaml
intents:
  - id: INTENT-001
    name: "TRADING_CORPORATE_isolation"
    requirement_refs: [REQ-007, REQ-008]
    description: >
      No IP-level reachability path must exist between TRADING_VRF and
      CORPORATE_VRF, in either direction, via any transit zone.
    assertion_type: reachability
    batfish_check:
      test_file: "batfish/tests/test_zone_isolation.py"
      test_class: "TestTradingVrfIsolation"
    sot_check:
      field: "interfaces[*].vrf"
      constraint: "TRADING and CORPORATE VRF interfaces must not coexist on a device without fw-lon-01 on path"
    enforcement_layer: [vrf_separation, firewall_policy]

  - id: INTENT-003
    name: "Frankfurt_TRADING_ringfence"
    requirement_refs: [REQ-007, REQ-009]
    description: >
      Frankfurt (fra-dc1) must never have VLAN 100 or TRADING_VRF.
      Frankfurt BGP sessions must only import/export prefixes from the
      Frankfurt site prefix space (10.30.0.0/16). Frankfurt must not
      have a direct BGP path to APAC sites.
    assertion_type: topology + routing_policy
    batfish_check:
      test_file: "batfish/tests/test_frankfurt_isolation.py"
      test_class: "TestFrankfurtRingfence"
    sot_check:
      field: "site.vlans_prohibited"
      constraint: "VLAN 100 must appear in vlans_prohibited for all fra-dc1 devices"
```

Design intents are more specific than business requirements. They describe the network-level behaviour that implements the requirement — not "trading must be isolated" (business language) but "no reachability between TRADING_VRF and CORPORATE_VRF" (network language). That specificity is what makes them machine-testable.

---

## Layer 2 → Layer 3 traceability

> 🟡 **Practitioner**

Find where INTENT-001 is enforced in the SoT:

```bash
grep -r "INTENT-001" sot/
```

You should find references in:
- `sot/compliance/zone_policies.yml` — the zone policy that implements INTENT-001
- `sot/devices/lon-dc1/leaf-lon-01.yml` — the `intent_refs` annotation on the TRADING_VRF interface

Now find where INTENT-001 is tested:

```bash
grep -r "INTENT-001" batfish/
```

You should find references in `batfish/tests/test_zone_isolation.py` in the test docstrings.

This cross-referencing is what makes the chain auditable. You can start from any layer and navigate to any other layer.

---

## The resilience intent

```bash
cat design_intents/resilience.yml
```

```yaml
intents:
  - id: INTENT-008
    name: "Fabric_and_WAN_redundancy"
    requirement_refs: [REQ-020, REQ-021]
    description: >
      London DC1 must have exactly two spine nodes.
      Each spine must be a route-reflector for all leaves and the border.
      Each leaf must have two ECMP BGP paths to border-lon-01 (one via each spine).
      border-lon-01 must have at least three WAN eBGP sessions (NYC, SIN, FRA).
      The fabric must survive a single spine failure without losing reachability
      between any leaf and border-lon-01.
    assertion_type: topology + routing + failover
    batfish_check:
      test_file: "batfish/tests/test_resilience.py"
      test_classes:
        - TestSpineRedundancy
        - TestLeafEcmpPaths
        - TestBorderWanRedundancy
    batfish_failover_check:
      test_file: "batfish/tests/test_path_trace.py"
      test_class: "TestSpineFailureResilience"
      method: "forbiddenLocations"
      description: >
        Batfish pathConstraints.forbiddenLocations is used to simulate a spine
        failure without taking a device offline. The test verifies that with
        spine-lon-01 excluded from all paths, every leaf can still reach
        border-lon-01 via spine-lon-02.
```

> 🔵 **Strategic** — The failover simulation in this intent is worth understanding. To verify that the network survives a spine failure, you would normally shut down a spine and observe. In a lab this is acceptable; in production it is not. Batfish provides a model-based alternative: `forbiddenLocations` excludes a device from all paths and Batfish recomputes whether the traffic flow can still succeed. This gives you the same evidence without touching production hardware. The test runs on every pipeline push — you get continuous failover verification at zero operational cost.

---

## Exercise 11.1 — Write a new design intent

> 🟡 **Practitioner**

The ACME CISO has raised a new requirement: all management-plane traffic must be isolated from TRADING and CORPORATE zones. SSH to network devices must only be possible from the MGMT zone (10.1.0.0/25).

1. Add a new requirement to `requirements/business_requirements.yml` — give it the next sequential REQ-ID.
2. Write a new design intent in `design_intents/compliance_controls.yml` referencing that requirement.
3. Identify which existing Batfish test partially covers this (hint: look at `test_zone_isolation.py`).
4. Write a stub for a new test function in `test_zone_isolation.py` that would verify SSH from CORPORATE to MGMT is denied. You do not need it to pass — write the intent assertion only.

**Verify:** There is no automated verify script for this exercise. Review your entries with a colleague or compare against the debrief below.

**Debrief:** Management plane isolation is one of the most commonly violated security intents in financial services networks — not through malice, but because OOB management is treated as an afterthought. Codifying it as an intent (and testing it in Batfish) means a future config push that accidentally exposes SSH to CORPORATE zone fails before it reaches a device.

*Handbook reference: Chapter 11 (Intent-based networking), Chapter 4 (Compliance automation)*
