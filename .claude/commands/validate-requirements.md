# Validate Business Requirements (Layer 1)

You are a network automation validation agent. Your task is to validate the Layer 1 business requirements for internal consistency, logical soundness, and regulatory alignment.

## Inputs

Read these files thoroughly before performing any checks:

1. `requirements/business_requirements.yml` — The business requirements register (REQ-001 through REQ-021)
2. `requirements/regulatory_mappings.yml` — Regulatory obligation to REQ-ID traceability

## Validation Checks

Perform each check below. For each check, report PASS or FAIL with specific details.

### CHECK 1: Requirement Completeness

For every REQ in `business_requirements.yml`, verify it has:
- `id` (REQ-xxx format)
- `title` / `description`
- `category`
- `owner` (a team or role)
- `regulatory_refs` (at least one regulatory reference)
- `design_intent_refs` (at least one INTENT-xxx reference)
- `enforcement` or `sot_enforcement` (how it is implemented)
- `priority` or `severity`

List any REQ missing required fields.

### CHECK 2: REQ-ID Uniqueness and Sequencing

- All REQ IDs must be unique
- Check for gaps in the numbering sequence (e.g., REQ-001 to REQ-021 — are any missing?)
- Flag any duplicate IDs

### CHECK 3: Regulatory Cross-Reference Integrity

For every REQ-ID referenced in `regulatory_mappings.yml`:
- Verify it exists in `business_requirements.yml`

For every REQ in `business_requirements.yml`:
- Verify its `regulatory_refs` correspond to actual frameworks in `regulatory_mappings.yml`

List any orphaned references in either direction.

### CHECK 4: Regulatory Coverage

For every obligation in `regulatory_mappings.yml`:
- Verify it maps to at least one REQ-ID
- Flag any regulatory obligation with zero REQ coverage (a compliance gap)

### CHECK 5: Contradiction Detection — Zone Isolation

Analyse the zone-related requirements together:
- REQ-007 (TRADING isolation from CORPORATE)
- REQ-008 (TRADING isolation from DMZ)
- REQ-009 (EU/UK data residency)
- REQ-010 (Frankfurt no TRADING)
- REQ-011 (Branches no TRADING)

Check for:
- Any requirement that demands connectivity between zones that another requirement forbids
- Any requirement that permits TRADING traffic where another explicitly denies it
- Whether Frankfurt restrictions (REQ-010) and branch restrictions (REQ-011) are consistent subsets of the broader zone isolation (REQ-007, REQ-008)

### CHECK 6: Contradiction Detection — BGP and Connectivity

Analyse BGP-related requirements together:
- REQ-012 (MD5 on all BGP sessions)
- REQ-013 (route-maps on all eBGP)
- REQ-014 (branch /29 only)
- REQ-020 (spine failure resilience)
- REQ-021 (dual WAN paths)

Check for:
- Whether resilience requirements (REQ-020, REQ-021) conflict with isolation requirements
- Whether "all BGP sessions" in REQ-012 is feasible given branch and Frankfurt constraints
- Whether branch advertisement restrictions (REQ-014) are achievable alongside WAN redundancy (REQ-021)

### CHECK 7: Contradiction Detection — Compliance Controls

Analyse compliance control requirements:
- REQ-015 (audit logging)
- REQ-016 (NTP)
- REQ-017 (no Telnet)
- REQ-018 (SSH v2)
- REQ-019 (SNMP v3)

Check for:
- Any mutual exclusions between these controls
- Whether "all devices" scope is consistently defined across all five
- Whether management zone access controls could prevent compliance mechanisms from functioning (e.g., if SNMP is required but management access is too restrictive)

### CHECK 8: Design Intent Coverage

For every REQ, verify that its `design_intent_refs` list references INTENT IDs that are plausible for that requirement's domain:
- Zone isolation REQs should map to zone isolation INTENTs
- BGP REQs should map to BGP INTENTs
- Compliance REQs should map to compliance INTENTs

Flag any suspicious mappings (e.g., a zone isolation REQ pointing to a resilience INTENT with no obvious connection).

## Output Format

Present findings as:

```
## Layer 1 — Business Requirements Validation Report

### CHECK 1: Requirement Completeness
**Result: PASS/FAIL**
[Details...]

### CHECK 2: REQ-ID Uniqueness and Sequencing
**Result: PASS/FAIL**
[Details...]

[... repeat for all checks ...]

## Summary
- Total checks: 8
- Passed: X
- Failed: Y
- Issues requiring attention:
  1. [Issue description with specific REQ-IDs and file references]
  2. [...]
```

Be precise. Reference specific REQ-IDs, field names, and line numbers where issues are found. Do not invent issues — only report genuine problems found in the data.
