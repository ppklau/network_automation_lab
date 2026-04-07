---
title: "Appendix B — Quick Reference"
---

# Appendix B — Quick Reference

## Lab management commands

| Task | Command |
|------|---------|
| Start the lab | `sudo containerlab deploy --topo topology/containerlab.yml` |
| Stop the lab | `sudo containerlab destroy --topo topology/containerlab.yml` |
| Reset to known-good state | `ansible-playbook scenarios/common/reset_lab.yml` |
| Verify lab health | `ansible-playbook scenarios/common/verify_lab_healthy.yml` |
| SSH to a node | `ssh admin@172.20.20.<N>` (see IP table in Chapter 2) |
| View node logs | `docker logs clab-acme_lab-<hostname>` |

## Ansible playbook reference

| Playbook | Purpose | Common flags |
|----------|---------|-------------|
| `render_configs.yml` | Generate configs from SoT | `--limit <hostname>` |
| `push_configs.yml` | Push rendered configs to devices | `--limit <hostname>`, `--extra-vars "push_serial=1"` |
| `verify_state.yml` | Post-push verification | `--limit <hostname>` |
| `rollback.yml` | Restore previous config | `--limit <hostname>`, `--extra-vars "rollback_timestamp=<ts>"` |
| `collect_state.yml` | Collect BGP/interface/route state | `--limit <hostname>`, `--extra-vars "label=pre_change"` |
| `daily_health_check.yml` | BGP + interface + NTP health | — |
| `drift_detection.yml` | Compare running vs SoT-rendered | `--limit <hostname>` |
| `compliance_report.yml` | Per-device compliance pass/fail | — |

## SoT validation commands

| Task | Command |
|------|---------|
| Validate all SoT files | `python3 scripts/validate_sot.py` |
| Verbose validation | `python3 scripts/validate_sot.py --verbose` |
| Lint YAML | `yamllint sot/ design_intents/ requirements/` |
| Generate inventory | `python3 scripts/generate_inventory.py` |

## Batfish commands

| Task | Command |
|------|---------|
| Start Batfish | `docker run -d --name batfish -p 9997:9997 -p 9996:9996 batfish/batfish:latest` |
| Check Batfish health | `curl -s http://localhost:9996/` |
| Run all intent checks | `bash batfish/run_checks.sh` |
| Run a specific test file | `pytest batfish/tests/test_zone_isolation.py -v` |
| Run a specific test | `pytest batfish/tests/test_zone_isolation.py::TestTradingVrfIsolation::test_trading_to_corporate_denied -v` |
| Run by marker | `pytest batfish/tests/ -m zone_isolation -v` |
| Run slow tests | `pytest batfish/tests/ -m slow -v` |

## pytest markers

| Marker | Tests |
|--------|-------|
| `zone_isolation` | TRADING/CORPORATE/DMZ separation (INTENT-001, 002) |
| `frankfurt` | Frankfurt ring-fence (INTENT-003, 004) |
| `bgp_standards` | MD5, route-maps, branch prefix scope (INTENT-005) |
| `resilience` | Dual-spine, ECMP, WAN redundancy (INTENT-008) |
| `routing_policy` | Summarisation, no default (INTENT-006, 010) |
| `path_trace` | End-to-end path assertions |
| `compliance` | All compliance-critical checks (zone_isolation + frankfurt) |
| `slow` | Tests taking >10s (full reachability queries) |

## Network addressing reference

| Network | Purpose |
|---------|---------|
| 10.1.0.0/16 | London DC1 (all zones) |
| 10.1.1.0/24 | TRADING zone |
| 10.1.2.0/22 | CORPORATE zone |
| 10.1.6.0/24 | DMZ zone |
| 10.1.0.0/25 | MGMT zone |
| 10.1.100.0/22 | Fabric P2P links (spine↔leaf) |
| 10.1.255.0/24 | Loopbacks |
| 10.1.255.1 | spine-lon-01 loopback |
| 10.1.255.2 | spine-lon-02 loopback |
| 10.1.255.11–14 | leaf-lon-01 to leaf-lon-04 loopbacks |
| 10.1.255.20 | border-lon-01 loopback |
| 10.1.255.30 | fw-lon-01 loopback |
| 10.0.1.0/31 | WAN link: LON ↔ NYC |
| 10.0.2.0/31 | WAN link: LON ↔ SIN |
| 10.0.3.0/31 | WAN link: LON ↔ FRA |
| 10.10.0.0/16 | NYC DC1 |
| 10.20.0.0/16 | SIN DC1 |
| 10.30.0.0/16 | FRA DC1 |
| 10.100.0.0/14 | Branch pool (all regions) |
| 10.100.0.0/29 | branch-lon-01 |
| 10.101.0.0/29 | branch-nyc-01 |
| 172.20.20.0/24 | Lab management network |

## BGP ASN reference

| ASN | Entity |
|-----|--------|
| 65001 | London DC1 (all LON devices) |
| 65010 | New York DC1 (border-nyc-01) |
| 65020 | Singapore DC1 (border-sin-01) |
| 65030 | Frankfurt DC1 (border-fra-01) |
| 65100–65111 | UK branch offices |
| 65120–65127 | US branch offices |
| 65130–65135 | APAC branch offices |
| 65140–65143 | EU branch offices |

## SoT field reference

### Device file required fields

| Field | Type | Valid values |
|-------|------|-------------|
| `hostname` | string | `^[a-z][a-z0-9-]+$` |
| `platform` | enum | `arista_eos`, `frr`, `cisco_ios` |
| `role` | enum | `spine`, `leaf`, `border`, `firewall`, `branch` |
| `site` | string | Must match a site ID in `sot/sites/` |
| `lab_state` | enum | `active`, `sot_only`, `decommissioned` |

### BGP neighbor optional fields

| Field | Type | Notes |
|-------|------|-------|
| `md5_password_ref` | string | Must exist as a key in `vault.yml`. Required on all sessions. |
| `route_reflector_client` | bool | Only valid when device `bgp.role == 'route_reflector'` |
| `import_policy` | string | Route-map name from `sot/bgp/route_policies.yml`. Required on eBGP. |
| `export_policy` | string | Route-map name from `sot/bgp/route_policies.yml`. Required on eBGP. |

## Batfish assertion reference

| Question | Common parameters | Returns |
|----------|-------------------|---------|
| `bf.q.bgpSessionStatus()` | — | DataFrame: all BGP sessions with Established_Status |
| `bf.q.bgpPeerConfiguration()` | — | DataFrame: BGP peer config including MD5_Auth_Enabled, Import_Policy, Export_Policy |
| `bf.q.routes()` | — | DataFrame: all routes including Node, VRF, Network, Protocol, Next_Hop_IP |
| `bf.q.reachability()` | `pathConstraints`, `headers`, `actions` | DataFrame: flows that match the action |
| `bf.q.traceroute()` | `startLocation`, `headers` | DataFrame: per-hop path traces |
| `bf.q.bgpEdges()` | — | DataFrame: BGP session topology (Local_AS, Remote_AS, Session_Type) |

### PathConstraints parameters

| Parameter | Example | Notes |
|-----------|---------|-------|
| `startLocation` | `"@enter(leaf-lon-01[Vlan100])"` | Traffic enters at this interface |
| `forbiddenLocations` | `"spine-lon-01"` | Exclude this device from all paths (simulates failure) |
| `transitLocations` | `"fw-lon-01"` | Traffic must pass through this device |

### HeaderConstraints parameters

| Parameter | Example |
|-----------|---------|
| `srcIps` | `"10.1.1.100"` or `"10.1.1.0/24"` |
| `dstIps` | `"10.1.2.100"` |
| `ipProtocols` | `["TCP"]` |
| `dstPorts` | `["443", "8443"]` |

## Traceability matrix

| REQ-ID | Description | Design Intent | Batfish Test |
|--------|-------------|---------------|-------------|
| REQ-007 | Trading zone isolation (MiFID II) | INTENT-001, 002 | `test_zone_isolation.py` |
| REQ-008 | DMZ access restrictions | INTENT-002 | `test_zone_isolation.py::TestDmzIsolation` |
| REQ-009 | EU data residency routing | INTENT-003 | `test_frankfurt_isolation.py` |
| REQ-010 | Route summarisation at WAN boundary | INTENT-006 | `test_routing_policy.py::TestRouteSummarisation` |
| REQ-012 | BGP MD5 authentication | INTENT-005 | `test_bgp_standards.py::TestBgpAuthentication` |
| REQ-013 | eBGP route-map requirements | INTENT-005 | `test_bgp_standards.py::TestEbgpPolicy` |
| REQ-020 | Single spine failure survivability | INTENT-008 | `test_resilience.py`, `test_path_trace.py::TestSpineFailureResilience` |
| REQ-021 | WAN redundancy | INTENT-008 | `test_resilience.py::TestBorderWanRedundancy` |
