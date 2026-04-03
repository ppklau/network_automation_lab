# Appendix A — Glossary

**ASN (Autonomous System Number)** — A unique identifier for a BGP routing domain. ACME uses private ASNs (65001–65143) for all internal and branch routing.

**Batfish** — An open-source network analysis tool that models the entire network from device configuration files. It can answer reachability, routing, and security questions without connecting to any device.

**BGP (Border Gateway Protocol)** — The routing protocol used between ACME's sites and branches. iBGP runs within London DC1 (route reflector topology); eBGP runs between sites and to branches.

**cEOS** — Arista's containerised EOS image. Used for spine, leaf, and border devices in the London DC1 lab.

**Change freeze** — A period during which non-emergency pipeline pushes are blocked. Enforced by the `change-freeze-check` CI job in the validate stage.

**CORPORATE zone** — General business users and services. VLAN 200–220, subnet 10.1.2.0/22. Isolated from TRADING zone by firewall policy and VRF separation.

**containerlab** — A Docker-based network topology lab tool. Manages the 18-node ACME lab topology defined in `topology/containerlab.yml`.

**Design intent** — A Layer 2 (architectural) statement of what the network must do, expressed in machine-verifiable terms. Defined in `design_intents/`. Tested by Batfish.

**DMZ zone** — Public-facing services and market data feeds. VLAN 300, subnet 10.1.6.0/24. TRADING can reach DMZ on TCP 443/8443/6000 only.

**drift** — A divergence between the SoT-rendered config (what the network should look like) and the running config (what it actually looks like). Detected by `playbooks/drift_detection.yml`.

**ECMP (Equal-Cost Multi-Path)** — Multiple BGP paths of equal cost, all used for forwarding. Each London leaf has two ECMP paths to border-lon-01 (one via each spine), providing redundancy.

**fault injection** — Deliberately introducing a misconfiguration to create a realistic exercise scenario. Implemented by `scenarios/*/inject.yml` playbooks.

**FRR (FRRouting)** — An open-source routing software suite. Used for the FRA/NYC/SIN border stubs, branch routers, and the London firewall (`fw-lon-01`) in the lab.

**intent-based networking (IBN)** — A network management paradigm in which intent (what the network should do) is declared separately from implementation (how it is configured). The Handbook Chapter 11 defines a three-layer model for IBN.

**intent_refs** — Annotation fields in SoT device files that link specific configuration values to the design intents that mandate them. Enables traceability from device config back to business requirements.

**IPAM (IP Address Management)** — The tracking and allocation of IP addresses. In ACME's SoT, IPAM is managed through `sot/global/ipam.yml` and validated by `validate_sot.py`.

**JSONSchema** — A vocabulary for describing the structure of JSON (and YAML) documents. Used in `schema/` to validate SoT file structure.

**lab_state** — A field in each device file that controls Ansible inclusion. `active`: running in the lab, receives pushes. `sot_only`: defined in SoT but not instantiated. `decommissioned`: archived.

**MGMT zone** — Out-of-band network management. VLAN 900, subnet 10.1.0.0/25. Reachable only from the management plane; not routable from TRADING or CORPORATE.

**MD5 authentication** — BGP session-level authentication using an MD5 hash of the message content. Required on all ACME BGP sessions (INTENT-005). Passwords stored in `vault.yml`.

**MiFID II** — Markets in Financial Instruments Directive II. EU regulation governing financial markets. Article 48 requires algorithmic trading systems to be operationally and logically separated from other systems. The primary driver for TRADING zone isolation.

**NAPALM** — Network Automation and Programmability Abstraction Layer with Multi-vendor support. Used by `playbooks/push_configs.yml` to push configs to Arista EOS devices.

**pybatfish** — The Python client library for Batfish. Used by all test files in `batfish/tests/`.

**route reflector (RR)** — A BGP router that reflects routes from its clients to all other clients, eliminating the need for a full iBGP mesh. The London DC1 spines are route reflectors; leaves and border are RR clients.

**route-map** — A Cisco/Arista construct for filtering and modifying BGP routes. Required on all eBGP sessions (INTENT-005). Defined in `sot/bgp/route_policies.yml` and rendered by `templates/arista_eos/bgp.j2`.

**serial** — In Ansible, the number (or percentage) of devices pushed to simultaneously. ACME uses `serial: "20%"` to limit blast radius: only 20% of targeted devices are pushed at once.

**snapshot (Batfish)** — A directory containing device config files that Batfish loads as a network model. Located at `batfish/snapshots/acme_lab/`. Built by `batfish/run_checks.sh` from the rendered configs.

**SoT (Source of Truth)** — The authoritative record of network intent. In ACME's lab, this is the `sot/` directory of YAML files, version-controlled in Git.

**TRADING zone** — ACME's algorithmic trading systems. VLAN 100, subnet 10.1.1.0/24. Most strictly isolated zone — no reachability to CORPORATE or DMZ except specific permitted ports.

**vault.yml** — `inventory/group_vars/vault.yml`. Contains all credentials (BGP passwords, NTP keys, SNMP keys, user passwords) as named references. Values are `CHANGEME` in the lab. In production, encrypted with Ansible Vault or replaced by a secrets manager lookup.

**VRF (Virtual Routing and Forwarding)** — A mechanism for maintaining multiple independent routing tables on a single device. ACME uses VRFs to enforce zone separation: `TRADING_VRF`, `CORPORATE_VRF`, `DMZ_VRF`, `MGMT_VRF`.

**VRRP (Virtual Router Redundancy Protocol)** — Provides gateway redundancy for hosts on a subnet. Leaf pairs run VRRP for each zone SVI, with one leaf as primary and one as backup.

**yamllint** — A linting tool for YAML files. Enforces syntax correctness, indentation, line length, and formatting consistency. Runs in the CI validate stage.
