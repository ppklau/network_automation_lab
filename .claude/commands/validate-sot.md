# Validate SoT and Templates (Layer 3)

You are a network automation validation agent. Your task is to validate that the Layer 3 Source of Truth (SoT) data and Jinja2 templates correctly implement the Layer 2 design intents.

## Inputs

Read ALL of the following files before performing checks. This is a large file set — read systematically.

**Layer 2 (design intents — the "spec" you are validating against):**
1. `design_intents/zone_isolation.yml`
2. `design_intents/routing_policy.yml`
3. `design_intents/bgp_standards.yml`
4. `design_intents/resilience.yml`
5. `design_intents/compliance_controls.yml`
6. `design_intents/provisioning_standards.yml`

**Layer 3 — Global SoT:**
7. `sot/global/asn_pools.yml`
8. `sot/global/ipam.yml`
9. `sot/global/platform_defaults.yml`
10. `sot/compliance/zone_policies.yml`
11. `sot/bgp/route_policies.yml`
12. `sot/bgp/communities.yml`

**Layer 3 — Device SoT (read ALL files in each directory):**
13. `sot/devices/lon-dc1/` — all 8 device files
14. `sot/devices/lon-dc2/` — all device files
15. `sot/devices/nyc-dc1/` — all device files (border-nyc-01 is active)
16. `sot/devices/sin-dc1/` — all device files (border-sin-01 is active)
17. `sot/devices/fra-dc1/` — all device files (border-fra-01 is active)
18. `sot/devices/hkg-dc1/` — all device files
19. `sot/devices/branches/` — all branch files

**Layer 3 — Templates:**
20. `templates/arista_eos/` — all .j2 files
21. `templates/frr/` — all .j2 files

**Generated configs (spot-check):**
22. `configs/` — read running.conf for at least: border-lon-01, border-fra-01, spine-lon-01, leaf-lon-01, one branch device

## Validation Checks

### SECTION A: Zone Isolation (INTENT-001, INTENT-002)

**CHECK A1: Frankfurt TRADING Prohibition**
For ALL devices in `sot/devices/fra-dc1/`:
- VLAN 100 must NOT appear in any `vlans` list
- TRADING_VRF must NOT appear in any `vrfs` list
- No interface may reference VRF TRADING_VRF
- No BGP network may advertise a TRADING prefix (10.x.1.0/24)
- `security_zones` must NOT include TRADING

**CHECK A2: Branch TRADING Prohibition**
For ALL branches in `sot/devices/branches/`:
- No branch may have TRADING zone in `security_zones`
- No branch may have VLAN 100
- No branch may advertise TRADING prefixes

**CHECK A3: VRF Route Target Isolation**
Across all devices:
- TRADING_VRF route targets (import/export) must be disjoint from CORPORATE_VRF and DMZ_VRF
- No device should import TRADING_VRF routes into CORPORATE_VRF or vice versa

**CHECK A4: Template Zone Guards**
In `templates/arista_eos/vlans.j2` and `templates/arista_eos/vrfs.j2`:
- Verify Frankfurt conditional logic correctly skips VLAN 100 and TRADING_VRF
- Verify the condition matches actual site identifiers used in SoT

### SECTION B: Frankfurt and Routing Policy (INTENT-003, INTENT-004)

**CHECK B1: Frankfurt BGP Peering Scope**
For `border-fra-01`:
- Must have exactly ONE eBGP neighbor (border-lon-01)
- Must NOT have direct eBGP sessions to NYC, SIN, or HKG borders
- Verify the neighbor IP and remote AS match the IPAM and ASN pools

**CHECK B2: TRADING Route-Map Filtering**
In `sot/bgp/route_policies.yml`:
- RM_INTERDC_LON_FRA_OUT must have a deny sequence for PL_TRADING_PREFIXES
- RM_INTERDC_LON_FRA_OUT must have a deny sequence for ZONE_TRADING community
- RM_INTERDC_LON_FRA_IN must have a deny sequence for ZONE_TRADING community
- Verify sequence ordering is correct (deny before permit)

**CHECK B3: PL_TRADING_PREFIXES Completeness**
- The prefix list must include ALL TRADING subnet prefixes from ALL DC sites that have TRADING zones
- Cross-reference against IPAM allocations for TRADING VLANs (10.x.1.0/24 for each site)

**CHECK B4: FRR Frankfurt Template**
In `templates/frr/bgp.j2`:
- Verify Frankfurt-specific TRADING denial logic exists
- Verify it applies to inbound eBGP sessions

### SECTION C: BGP Standards (INTENT-005, INTENT-006, INTENT-007)

**CHECK C1: MD5 Authentication on All BGP Sessions**
For EVERY device with BGP neighbors:
- Every neighbor must have a non-null `md5_password_ref`
- The key naming must follow the convention: `bgp_md5_{site}_fabric` (iBGP), `bgp_md5_wan_{site1}_{site2}` (inter-DC), `bgp_md5_branch_{hostname}` (branch)
- No neighbor may have an inline plaintext password

**CHECK C2: Route-Maps on All eBGP Sessions**
For every eBGP neighbor (where remote_as != local_as):
- Must have `route_map_in` defined (non-null)
- Must have `route_map_out` defined (non-null)
- The referenced route-map names must exist in `sot/bgp/route_policies.yml`

**CHECK C3: Branch /29 Prefix Validation**
For every branch device:
- Must advertise exactly ONE prefix
- That prefix must be a /29
- The /29 must fall within the correct regional supernet:
  - UK branches: 10.100.0.0/16
  - US branches: 10.101.0.0/16
  - APAC branches: 10.102.0.0/16
  - EU branches: 10.103.0.0/16
- No two branches may share the same /29

**CHECK C4: Route-Map Name Consistency**
Cross-reference route-map names used in device SoT `bgp.neighbors[].route_map_in/out` against the route-map definitions in `sot/bgp/route_policies.yml`. Flag any:
- Device referencing a route-map that doesn't exist in route_policies.yml
- Route-map defined in route_policies.yml but never referenced by any device

### SECTION D: Resilience (INTENT-008)

**CHECK D1: Dual Spines**
For lon-dc1 (the active site):
- Exactly 2 spine devices must exist
- Both must have `role: spine` and BGP `role: route_reflector`
- Both must peer with all leaf devices as RR clients

**CHECK D2: Leaf Dual-Homing**
For every leaf in lon-dc1:
- Must have exactly 2 fabric uplinks (one to each spine)
- BGP neighbors must include both spine loopbacks
- Fabric interface IPs must be consistent (leaf Ethernet1 → spine-lon-01, leaf Ethernet2 → spine-lon-02)

**CHECK D3: Border WAN Redundancy**
For border-lon-01:
- Must have eBGP neighbors to at least NYC, SIN, and FRA borders
- Verify neighbor IPs match IPAM WAN link allocations
- Verify remote ASNs match ASN pool allocations

**CHECK D4: VRRP Configuration**
For leaves with VRRP:
- Virtual IPs must be consistent across VRRP group members
- Priority values must create a deterministic active/standby pairing
- Track interfaces must reference actual fabric uplinks

### SECTION E: Compliance Controls (INTENT-009/011)

**CHECK E1: Platform Defaults Coverage**
In `sot/global/platform_defaults.yml`:
- NTP servers defined with authentication
- Syslog servers defined with correct source interface
- SSH v2 enforced, Telnet disabled
- SNMP v3 users defined with SHA auth and AES privacy

**CHECK E2: Device Loopback Consistency**
For every active device:
- Must have a Loopback0 interface defined
- Loopback0 IP must be unique across all devices
- Loopback0 must be within the correct site's loopback range (10.x.255.0/24)

### SECTION F: Cross-Device Consistency

**CHECK F1: Fabric P2P IP Matching**
For every fabric point-to-point link:
- If spine-lon-01 Ethernet1 is 10.1.100.0/31, then leaf-lon-01 Ethernet1 must be 10.1.100.1/31
- Check ALL fabric links for IP pair consistency
- Verify /31 subnets don't overlap

**CHECK F2: ASN Consistency**
- Every device's `bgp.local_as` must match the ASN allocated in `sot/global/asn_pools.yml` for its site
- No two sites share an ASN (unless explicitly documented as same-AS design)

**CHECK F3: BGP Neighbor Symmetry**
For every BGP neighbor relationship:
- If device A lists device B as a neighbor, device B should list device A
- Verify remote_as on A matches local_as on B and vice versa
- Verify peer IPs are correct (A's neighbor IP = B's source IP)

**CHECK F4: IPAM Alignment**
Cross-reference device interface IPs against `sot/global/ipam.yml`:
- Management IPs within management subnet
- Loopbacks within loopback range
- VLAN SVIs within VLAN subnet allocations
- Fabric P2P within fabric range

### SECTION G: Template Validation

**CHECK G1: Template Variable References**
For each template in `templates/arista_eos/` and `templates/frr/`:
- List all Jinja2 variables referenced (e.g., `{{ device.hostname }}`, `{{ bgp.local_as }}`)
- Verify these variables exist in the SoT device files (check at least 2 device files per platform)
- Flag any variable referenced in a template but missing from the SoT structure

**CHECK G2: Template Conditional Logic**
- Frankfurt guards in vlans.j2, vrfs.j2, and frr/bgp.j2 — do the conditions match the actual site identifier format in SoT?
- Route-reflector logic in bgp.j2 — does it correctly key on `bgp.role == 'route_reflector'`?
- VRF iteration in bgp.j2 — does it handle the case where a device has no VRF-scoped networks?

**CHECK G3: Generated Config Spot-Check**
Read the running.conf for border-lon-01, border-fra-01, spine-lon-01, and leaf-lon-01:
- Does border-fra-01 config contain any TRADING references? (It should not)
- Does border-lon-01 have route-maps for all WAN peers?
- Does spine-lon-01 have route-reflector-client for all leaves?
- Does leaf-lon-01 have correct VRRP configuration?

## Output Format

```
## Layer 3 — SoT and Template Validation Report

### SECTION A: Zone Isolation
#### CHECK A1: Frankfurt TRADING Prohibition
**Result: PASS/FAIL**
[Details with file:line references...]

[... repeat for all checks ...]

### SECTION G: Template Validation
#### CHECK G3: Generated Config Spot-Check
**Result: PASS/FAIL**
[Details...]

## Summary
- Total checks: ~25
- Passed: X
- Failed: Y
- Critical issues (would cause Batfish failures):
  1. [Issue with file path and specific data]
- Non-critical issues (inconsistencies that should be fixed):
  1. [Issue with file path and specific data]
```

Be precise. Every finding must include the specific file path, the problematic value, and what the correct value should be based on the design intent. Do not invent issues — only report genuine problems found in the data.
