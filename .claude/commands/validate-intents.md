# Validate Design Intents (Layer 2)

You are a network automation validation agent. Your task is to validate the Layer 2 design intents for technical feasibility, internal consistency, and correct alignment with Layer 1 business requirements.

## Inputs

Read ALL of these files thoroughly before performing any checks:

**Layer 1 (for traceability):**
1. `requirements/business_requirements.yml`

**Layer 2 (primary validation targets):**
2. `design_intents/zone_isolation.yml` — INTENT-001, INTENT-002
3. `design_intents/routing_policy.yml` — INTENT-003, INTENT-004
4. `design_intents/bgp_standards.yml` — INTENT-005, INTENT-006, INTENT-007
5. `design_intents/resilience.yml` — INTENT-008
6. `design_intents/compliance_controls.yml` — INTENT-009 (or INTENT-011)
7. `design_intents/provisioning_standards.yml` — INTENT-010

## Validation Checks

### CHECK 1: INTENT-ID Uniqueness and Completeness

- All INTENT IDs must be unique across all design intent files
- Check for gaps in the numbering sequence
- Flag any duplicate IDs
- Verify each INTENT has: `id`, `title`, `description`, `requirements_refs`, `scope`, `enforcement_mechanism`, and either `batfish_assertions` or `sot_checks`

### CHECK 2: Requirement Traceability (Upward)

For every INTENT:
- Verify its `requirements_refs` list only valid REQ-IDs that exist in `business_requirements.yml`
- Flag any INTENT referencing a non-existent REQ

For every REQ in `business_requirements.yml`:
- Check if at least one INTENT covers it (via `design_intent_refs` in the REQ or `requirements_refs` in the INTENT)
- Flag any REQ with zero INTENT coverage — this is a gap in the design

### CHECK 3: Batfish Assertion ID Uniqueness

Collect all BA-xxx IDs across all intent files:
- Verify global uniqueness (no two intents share a BA-xxx ID)
- Check for numbering gaps within each intent's BA range
- Flag any duplicates

### CHECK 4: SoT Check ID Uniqueness

Collect all SC-xxx IDs across all intent files:
- Verify global uniqueness
- Check for numbering gaps within each intent's SC range
- Flag any duplicates

### CHECK 5: Technical Feasibility — Zone Isolation

Review INTENT-001 and INTENT-002 (zone isolation):
- Is VRF separation technically sufficient to prevent inter-zone reachability?
- Does the firewall enforcement layer add genuine defence-in-depth or create a contradiction?
- Are the Batfish assertions testable? (Can Batfish actually verify VRF isolation and firewall policy?)
- Is the scope correct? (Which sites/devices should this apply to?)
- Does "no reachability" mean no L3 routing, no L2 bridging, or both?

### CHECK 6: Technical Feasibility — Frankfurt Isolation

Review INTENT-003 and INTENT-004:
- INTENT-003 says Frankfurt peers only with London. Is this consistent with INTENT-008 (WAN redundancy, dual paths)?
  - If border-fra-01 has only one BGP peer (border-lon-01), it has a single WAN path — does INTENT-008 exempt Frankfurt, or is there a contradiction?
- INTENT-004 says TRADING prefixes and community must be stripped on LON-FRA sessions. Is dual filtering (prefix-list + community) technically achievable in a single route-map?
- Are the route-map sequence numbers (seq 5, 7, 10, 30) logically ordered and non-conflicting?

### CHECK 7: Technical Feasibility — BGP Standards

Review INTENT-005, INTENT-006, INTENT-007:
- INTENT-005 (MD5 on all sessions): Is the key naming convention consistent? Are there edge cases (e.g., RR-to-RR peering, firewall OSPF adjacency)?
- INTENT-006 (route-maps on all eBGP): Does "all eBGP" include branch sessions? Are the specific route-map names (RM_BRANCH_IN, RM_INTERDC_*) consistent with what the SoT and templates expect?
- INTENT-007 (branch /29 only): Are the regional supernet allocations correct? Does the ASN-to-region mapping match the ASN pools?
- Do the three intents create any circular dependencies?

### CHECK 8: Technical Feasibility — Resilience

Review INTENT-008:
- Dual-spine with ECMP: Is maximum-paths >= 2 sufficient, or should it match the actual spine count?
- VRRP tracking: Do the priority decrements (20 per interface) create correct failover behaviour? (e.g., if both uplinks fail, does priority drop below standby?)
- BFD timers: Are fabric (300ms/900ms) and WAN (1s/3s) timers reasonable for the stated reconvergence targets?
- Does the 30-second RTO claim hold given the stated mechanisms?
- Frankfurt exemption: If FRA has single WAN path (per INTENT-003), is INTENT-008's "dual WAN" requirement scoped correctly?

### CHECK 9: Technical Feasibility — Compliance Controls

Review INTENT-009/011:
- Are the five controls (logging, NTP, SSH, no-Telnet, SNMP v3) independently achievable on both platforms (EOS and FRR)?
- Are the specified servers (10.1.0.50, 10.1.0.53, etc.) in the correct management subnets?
- Is Loopback0 as source interface correct for all device roles? (Spines have Loopback0, but do branches/firewalls?)

### CHECK 10: Technical Feasibility — Provisioning and Routing Policy

Review INTENT-010, INTENT-003, INTENT-004:
- Branch provisioning constraints: Are the 6 constraint groups internally consistent?
- ASN pool boundaries: Do they match the pools defined in `sot/global/asn_pools.yml`? (Read and verify)
- Summarization (SUMM-001): Is summary_only: true on borders compatible with the branch /29 advertisements needing to reach other regions?
- No default route (SUMM-002): Does this conflict with branch connectivity requirements?

### CHECK 11: Cross-Intent Consistency

Look for contradictions or gaps between intents:
- Does zone isolation (INTENT-001/002) conflict with resilience (INTENT-008) in any scenario?
- Does Frankfurt isolation (INTENT-003) conflict with WAN redundancy (INTENT-008)?
- Does branch /29 restriction (INTENT-007) work with route summarization (SUMM-001)?
- Are compliance controls (INTENT-009/011) achievable within zone isolation constraints (INTENT-001/002)?
- Can management traffic (SNMP, syslog, NTP) reach its servers if zones are strictly isolated?

## Output Format

```
## Layer 2 — Design Intent Validation Report

### CHECK 1: INTENT-ID Uniqueness and Completeness
**Result: PASS/FAIL**
[Details...]

[... repeat for all checks ...]

## Cross-Reference Matrix

| REQ-ID | Covered by INTENT(s) | Status |
|--------|----------------------|--------|
| REQ-001 | INTENT-xxx | OK / GAP |
| ... | ... | ... |

## Summary
- Total checks: 11
- Passed: X
- Failed: Y
- Contradictions found:
  1. [Description with INTENT-IDs]
- Coverage gaps:
  1. [REQ-IDs without INTENT coverage]
- Technical concerns:
  1. [Feasibility issue with explanation]
```

Be precise and technically rigorous. Reference specific INTENT-IDs, BA-xxx, SC-xxx, and REQ-IDs. Do not invent issues — only report genuine problems. When flagging a technical feasibility concern, explain the specific mechanism that would fail and why.
