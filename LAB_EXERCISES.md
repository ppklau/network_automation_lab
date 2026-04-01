# ACME Investments — Lab Exercise Catalogue

Each exercise is tagged with the content track it primarily serves:

- **[S]** Strategic — narrative, no CLI. For architects and managers.
- **[P]** Practitioner — hands-on lab. For engineers.
- **[D]** Deep Dive — optional extension for advanced engineers.

Exercises are grouped by operational theme, not difficulty. Most Practitioner exercises build on a working base environment — complete Module 0 first.

---

## Module 0 — Lab Foundations

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 0.1 | Lab environment setup | P | Clone the repo, install prerequisites (Docker, containerlab), bring up the full topology. Verify all nodes are reachable and BGP has converged. |
| 0.2 | Exploring the SoT | S/P | Walk through the full YAML SoT structure — regions, devices, interfaces, BGP peers, security zones. Understand what each key represents and why it exists. |
| 0.3 | Understanding the pipeline | S/P | Trace a config change from SoT edit → Jinja2 render → diff review → GitLab CI → Ansible push. No changes made — observation only. |
| 0.4 | Your first config push | P | Make a trivial, safe change in the SoT (add a description to an interface). Push through the full pipeline end to end. Verify on device. |

---

## Module 1 — Site and Device Lifecycle

### 1.1 Adding Sites

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 1.1.1 | Add a new UK branch office | P | Add `branch-lon-05` to the SoT. Allocate an ASN from the UK branch pool, assign a /29 from the branch supernet, set CORPORATE zone only. Run the pipeline. Verify BGP peering to London DC1. |
| 1.1.2 | Add a new US branch office | P | Repeat the branch exercise for the Americas region. Note the differences in IPAM allocation and BGP policy. |
| 1.1.3 | Add a second leaf pair to London DC1 | P | Extend the London DC1 SoT with `leaf-lon-05` and `leaf-lon-06`. Generate configs, push, verify ECMP paths update. |
| 1.1.4 | Onboard a new data centre (Frankfurt DC2) | D | Add a full DC stub to the Frankfurt region in the SoT — 2 spine, 2 leaf. Generate configs for all devices. Verify Frankfurt's regulatory constraints are automatically enforced (no TRADING zone). |
| 1.1.5 | The business case for SoT-driven provisioning | S | Analysis of what the above exercises would look like manually (CLI, tickets, spreadsheets) versus pipeline-driven. Time, error rate, audit trail comparison. |

### 1.2 Removing and Decommissioning Sites

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 1.2.1 | Decommission a branch office | P | Remove `branch-lon-03` from the SoT. Pipeline generates a decommission playbook: withdraw BGP routes, remove firewall rules, zero out interface configs, archive device record. Verify no orphaned config remains. |
| 1.2.2 | Retire a leaf switch | P | Remove a leaf from the SoT. Verify that the pipeline correctly updates spine BGP neighbours, removes VLAN definitions, and flags any downstream devices that referenced the retired leaf. |
| 1.2.3 | Graceful vs emergency decommission | S | The two decommission paths — planned (pipeline-driven, zero impact) versus emergency (device already dead, clean up the SoT after the fact). What the audit trail looks like for each. |

---

## Module 2 — Port and Interface Operations

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 2.1 | Auto-provision an access port | P | A new workstation needs connectivity at `branch-lon-01`. Add a port record to the SoT (device, interface, VLAN, description). Pipeline renders config and pushes. No CLI on the device. |
| 2.2 | Change a port VLAN | P | Move an access port from CORPORATE to TRADING zone. The pipeline validates the change against zone policy (is TRADING permitted at this site?) before applying. |
| 2.3 | Bulk port description update | P | A naming convention change requires updating descriptions on all branch uplinks. Write a SoT update script, validate the diff, push in a single pipeline run. |
| 2.4 | Provision a SPAN/mirror port | P | A security team needs traffic mirroring on a TRADING zone interface. Add the SPAN session to the SoT, generate the config, push, verify session is active. Document the approval gate in the pipeline. |
| 2.5 | Port speed and duplex change | P | Upgrade a branch uplink from 1G to 10G. SoT change, config render, maintenance window flag in the pipeline, push with pre/post checks. |
| 2.6 | Trunk port provisioning | P | Add a new VLAN to an existing trunk between leaf and border router. Show how adding one line in the SoT propagates correctly to both ends of the link. |
| 2.7 | The port audit | P/D | Generate a full report of all ports across the lab: unused ports, non-compliant descriptions, ports not in SoT. Foundation for automated hygiene checks. |

---

## Module 3 — Routing and BGP Operations

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 3.1 | Add a new prefix to BGP | P | Add a new network to a branch's BGP advertisements. SoT update, pipeline, verify propagation to London DC1 and remote stubs. |
| 3.2 | Withdraw a prefix | P | Remove a prefix from BGP. Verify clean withdrawal — no route remains in the table. Useful as a prerequisite for decommission exercises. |
| 3.3 | BGP policy change — prefer a regional path | P | Adjust local-preference on border-lon-01 to prefer the NYC path over the SIN path for a specific prefix. Verify in the route table. |
| 3.4 | BGP policy change — prepend to influence inbound traffic | D | Add AS-path prepending on the Frankfurt border to discourage direct APAC-FRA routing. Verify the intended path is taken. |
| 3.5 | Route reflector failover | D | Simulate the London route reflector going offline. Verify iBGP reconverges correctly via the backup. |
| 3.6 | Route leak detection | D | Introduce a misconfiguration that leaks TRADING zone prefixes into the CORPORATE VRF. Use Batfish to detect it pre-push. Understand why this is a compliance event, not just a routing error. |
| 3.7 | VRF route table audit | P | Generate a report of all routes per VRF per device. Identify any routes not consistent with SoT intent. Foundation for drift detection. |

---

## Module 4 — Compliance and Audit

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 4.1 | Frankfurt zone violation (caught pre-push) | P | Attempt to add a TRADING VLAN to a Frankfurt leaf. Batfish catches it in the pipeline. Walk through the error, understand the policy assertion, fix the SoT. No change reaches a device. |
| 4.2 | Generate an audit trail for a change | S/P | After any config push, generate the audit artefact: who changed what, when, which pipeline run, which Ansible task, what the before/after diff was. This is MiFID II change traceability in practice. |
| 4.3 | Automated compliance report | P | Run the compliance playbook across all live nodes. Output: per-device pass/fail against a defined policy set (zone enforcement, BGP MD5 auth, description standards, NTP, logging). |
| 4.4 | Cross-border data flow assertion | S/P | Write a Batfish assertion that APAC-origin traffic cannot traverse the Frankfurt region. This is a topological encoding of a regulatory requirement — understand how automation enforces what a policy document only describes. |
| 4.5 | Emergency firewall rule push | P | Simulate a security incident: a TRADING zone IP needs to be immediately isolated. Push an ACL addition through the pipeline on an expedited path. Compare the emergency path (manual override) versus the standard path. |
| 4.6 | Pre-change and post-change diff for audit | P | For a planned maintenance, capture the full device state before and after the change window. Generate a signed diff artefact. Store it in the pipeline as a release artefact. |
| 4.7 | Licence and EOL compliance | D | Build a playbook that checks device hardware against a SoT field for end-of-life date. Flag devices approaching EOL. Generate a report for procurement. |

---

## Module 5 — Disaster Recovery and Resilience

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 5.1 | London DC1 spine failure (ECMP failover) | P | Shut down `spine-lon-01`. Verify traffic reconverges via `spine-lon-02`. Measure convergence time. Restore spine, verify reconvergence. |
| 5.2 | London DC1 border router failure | P | Shut down `border-lon-01`. Verify inter-region BGP sessions fail over to a backup path. Restore and verify clean recovery. |
| 5.3 | Full DC failover exercise | S/P | Simulate a London DC1 outage. Walk through the DR runbook: BGP withdrawal, traffic rerouting to DC2, updated DNS/load balancer records (simulated). This is the full DR exercise narrative for managers to understand; engineers execute the automation. |
| 5.4 | Regional failover — Americas | D | Simulate a NYC DC1 outage. Verify APAC and EMEA traffic reroutes. Validate that Frankfurt isolation constraints hold during the failover (no APAC-FRA direct path established). |
| 5.5 | Emergency rollback of a bad config push | P | Introduce a deliberate BGP misconfiguration via the pipeline. Detect the failure (BGP down, Batfish post-check alert). Execute the automated rollback. Verify recovery. Time the full detect-and-rollback cycle. |
| 5.6 | Out-of-band management during outage | P | Simulate data-plane failure on a leaf. Verify the management network (OOB) remains accessible. Push a remediation config via OOB path. |
| 5.7 | Backup and restore of SoT | P | Corrupt a SoT file. Restore from Git history. Validate that the restored SoT renders correctly and matches the running device state. |
| 5.8 | What DR automation actually buys you | S | Comparison of manual DR (runbook, CLI, phone calls) versus pipeline-driven DR. MTTR, error rate, audit trail quality. The business case for automating recovery, not just provisioning. |

---

## Module 6 — Isolation and Security Tests

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 6.1 | Zone isolation verification | P | Prove that TRADING zone traffic cannot reach CORPORATE zone across the topology. Use Batfish reachability assertions and a live ping test from the lab nodes. |
| 6.2 | Inter-VRF leak test | P | Attempt to route between TRADING and CORPORATE VRFs. Verify the firewall policy blocks it. Confirm Batfish would have caught the misconfiguration before it reached production. |
| 6.3 | Frankfurt regulatory isolation | P/D | Verify that no direct BGP path exists between Frankfurt and APAC. Verify TRADING zone is absent from all FRA devices. Generate the compliance assertion as a reusable Batfish check. |
| 6.4 | VLAN isolation on access ports | P | Verify that two access ports in different VLANs cannot communicate directly. Confirm VLAN assignment is consistent with the SoT. |
| 6.5 | Management plane isolation | P | Verify that the MGMT network is not reachable from TRADING or CORPORATE zones. Confirm the OOB management path is only accessible via the dedicated management interface. |
| 6.6 | Simulate a misconfigured firewall rule | D | Introduce a firewall rule that accidentally permits traffic between zones. Use Batfish to detect it pre-push. Walk through the remediation pipeline. |

---

## Module 7 — Troubleshooting Scenarios

Each scenario presents a broken lab state. The reader must diagnose and fix using automation tooling, not direct CLI.

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 7.1 | BGP session down — misconfigured peer ASN | P | A branch BGP session is down. Root cause: wrong remote-AS in the SoT. Diagnose via pipeline logs and Batfish, fix in SoT, push. |
| 7.2 | BGP session down — MD5 authentication mismatch | P | BGP is configured on both peers but won't establish. Root cause: password mismatch between SoT fields. Diagnose, correct, push. |
| 7.3 | Missing route — prefix not advertised | P | A branch prefix is unreachable from London. Root cause: network statement missing from BGP config. Identify via route table audit, fix in SoT. |
| 7.4 | Routing loop | D | A misconfigured redistribution creates a routing loop. Packets are not reaching their destination. Use Batfish loop detection. Fix and validate. |
| 7.5 | MTU black hole | D | Large packets are dropped between spine and border. Small pings succeed. Root cause: MTU mismatch on an inter-region link. Diagnose, fix in SoT, push. |
| 7.6 | VLAN mismatch on a trunk | P | A new leaf is not passing traffic. Root cause: VLAN missing from the trunk config on the upstream interface. Diagnose via SoT diff, fix, push. |
| 7.7 | Duplicate IP address | P | Two devices share an IP, causing intermittent reachability. Diagnose via ARP table output and SoT IPAM. Identify the conflict, correct the SoT, push. |
| 7.8 | Config drift — device not matching SoT | P | A device was changed out-of-band (simulated). The running config no longer matches what the SoT would generate. Detect with the drift detection playbook. Remediate via pipeline. |
| 7.9 | NTP desync causing authentication failure | D | An MD5-authenticated BGP session fails intermittently due to clock skew. Diagnose, identify NTP misconfiguration in the SoT, fix, push. |
| 7.10 | Asymmetric routing causing stateful firewall drops | D | Traffic flows in via one path and returns via another. The stateful firewall drops the return traffic. Diagnose with Batfish, fix routing policy. |
| 7.11 | Pipeline failure — Ansible unreachable | P | A pipeline run fails mid-push. One device is unreachable. Identify whether the failure left the network in a half-changed state. Assess and remediate safely. |
| 7.12 | Batfish false positive triage | D | A Batfish assertion fires but the network is actually correct. Diagnose why the assertion is wrong (e.g., stale snapshot), fix the check, re-run. |

---

## Module 8 — Day-2 BAU Operations

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 8.1 | Daily health check playbook | P | Run the automated daily health check: BGP neighbour status, interface error counters, reachability to all management IPs, NTP sync. Output a structured report. |
| 8.2 | Drift detection sweep | P | Run the drift detection playbook across all live nodes. Compare running config to SoT-rendered config. Categorise drift: informational, warning, critical. |
| 8.3 | Interface utilisation report | P | Collect interface counters from all nodes. Identify interfaces above 80% utilisation threshold. Output as a report and (optionally) a Grafana dashboard. |
| 8.4 | BGP prefix count monitoring | P | Compare current BGP prefix counts per peer against a baseline stored in the SoT. Alert if prefix count drops significantly (indicates route withdrawal or peer issue). |
| 8.5 | Change freeze enforcement | S/P | Simulate a change freeze period (e.g., before a trading system release). Configure the pipeline to reject all non-emergency pushes during the window. Show how the freeze is enforced technically, not just procedurally. |
| 8.6 | Scheduled maintenance window | P | Set a device to maintenance mode in the SoT. Pipeline applies a reduced-functionality config (admin-down non-critical interfaces, suppress BGP advertisements). Restore after the window. |
| 8.7 | Automated capacity reporting | D | Build a report that compares current prefix counts, link utilisations, and device CPU against defined thresholds. Flag devices approaching capacity limits. |
| 8.8 | SoT hygiene check | P | Run a linting pass over the full SoT: unused ASNs, IPs allocated but not assigned, devices with missing mandatory fields, descriptions that don't match naming convention. |

---

## Module 9 — Traffic Visibility and Monitoring

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 9.1 | Grafana dashboard — network overview | S/P | Deploy the pre-built Grafana dashboard (via Docker). Understand the panels: BGP state per region, interface utilisation heatmap, drift alert count, pipeline run history. |
| 9.2 | Custom dashboard — TRADING zone traffic | P | Build a Grafana panel showing traffic volume on TRADING zone interfaces. Annotate with pipeline push events. Show correlation between config changes and traffic patterns. |
| 9.3 | Alerting on BGP session loss | P | Configure a Grafana alert that fires when a BGP session goes down. Trigger it by shutting a border interface. Verify the alert fires and resolves on recovery. |
| 9.4 | Traffic baselining | D | Collect interface counter data over a period and establish a baseline. Use the baseline for anomaly detection in later exercises. |
| 9.5 | End-to-end path trace | P | Trace the path for a specific source/destination pair using Batfish. Verify it matches the expected route. Use this as a pre-change and post-change verification step. |
| 9.6 | SPAN port for packet capture | P | Provision a SPAN port on a TRADING zone interface (from Module 2.4). Attach tcpdump to the mirror destination. Capture and inspect traffic. Deprovision cleanly. |

---

## Module 10 — Hardware Replacement Workflows

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 10.1 | Leaf switch RMA (like-for-like) | P | Simulate a failed leaf. Update the SoT with the replacement device's serial number and MAC. Run the provisioning pipeline — the replacement receives its full config automatically. Verify BGP and VLANs are restored. |
| 10.2 | Leaf switch replacement (different model) | D | Replacement is a different hardware revision with a slightly different interface naming convention. Update the SoT device model and interface map. Verify the Jinja2 template handles the model difference correctly. |
| 10.3 | Border router RMA | P | Higher-impact than a leaf — the border router carries inter-region BGP. Walk through the replacement: pre-stage config, maintenance mode, physical swap (simulated), zero-touch push, verify sessions restore. |
| 10.4 | Branch router replacement | P | Simulate a branch router failure. The replacement is shipped pre-staged. Walk through the zero-touch provisioning path: DHCP, initial boot, pipeline push, BGP up. |
| 10.5 | Firmware/OS upgrade workflow | P | Upgrade the OS version on a leaf switch. SoT records the target version. Pipeline validates current version, stages the image, schedules the upgrade, verifies post-upgrade BGP reconvergence. |
| 10.6 | The hardware replacement playbook | S | What the automation changes about the RMA process: from a multi-hour CLI task requiring a senior engineer onsite, to a pipeline-driven workflow executable by a junior team member remotely. |

---

## Module 11 — Advanced Automation Patterns

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 11.1 | Intent-based networking — encoding business intent | S/P | Define a business intent in the SoT ("TRADING zone must not be routable from CORPORATE zone") as a machine-readable assertion. Show how Batfish enforces the intent without specifying the implementation. |
| 11.2 | Self-healing: auto-remediation of detected drift | D | Extend the drift detection playbook to automatically push a remediation when drift is detected and meets defined criteria (non-business-hours, single device, low-risk change category). |
| 11.3 | Canary/staged rollout | D | Push a config change to one leaf first, validate BGP and reachability, then proceed to remaining leaves. Pipeline stages the rollout and halts if the canary step fails. |
| 11.4 | Multi-vendor config generation | P | The SoT has both Arista EOS and FRRouting devices. Walk through how the same SoT data drives different Jinja2 templates for each vendor. Highlight the separation of data (SoT) from presentation (template). |
| 11.5 | Automated rollback trigger | D | Configure the post-push Batfish check to trigger an automatic rollback if a critical assertion fails. Demonstrate the full loop: push → validate → detect failure → rollback → alert. |
| 11.6 | Pipeline as a change management system | S | Map the GitLab CI pipeline stages to a traditional ITIL change management process: RFC → approval → implementation → verification → closure. Show how automation compresses the cycle time without bypassing governance. |
| 11.7 | Scaling the SoT — bulk import from a spreadsheet | D | Import a CSV of 20 new branch devices into the SoT via a conversion script. Validate the resulting YAML, run the pipeline. Demonstrate how bulk onboarding becomes a data problem, not an engineering problem. |

---

## Module 12 — Capstone Exercises

These exercises combine skills from multiple modules and are designed to be completed without step-by-step guidance.

| # | Title | Track | Description |
|---|-------|-------|-------------|
| 12.1 | New office opening — end to end | P | ACME opens a new Frankfurt office. You receive: site name, address, user count, and a note that Frankfurt has restricted zone access. Everything else is derived from SoT conventions. Provision from scratch. |
| 12.2 | Incident simulation — production-like pressure | P | A simulated incident is introduced (one of several pre-built scenarios — chosen randomly at runtime). Diagnose using the available tooling, remediate via pipeline, produce a post-incident report. |
| 12.3 | Quarterly DR test | S/P | Run the full DR exercise (Module 5.3) with no guidance — just the DR runbook. Document the results: failover time, issues encountered, actions taken. This is what ACME would present to regulators. |
| 12.4 | Maturity self-assessment | S | Use the maturity assessment worksheet to score your own organisation (or ACME post-lab) against the automation maturity dimensions. Identify the next two or three initiatives that would move the needle. |

---

## Appendix — Exercise Quick Reference

### By Skill Area

| Skill | Exercises |
|-------|-----------|
| SoT design and editing | 0.2, 1.1.1–1.1.4, 1.2.1–1.2.2, 2.1–2.6, 3.1–3.2, 11.7 |
| Ansible / config push | 0.4, 1.1.1, 2.1–2.5, 3.1–3.3, 8.6, 10.1–10.5 |
| Jinja2 templating | 0.3, 0.4, 11.4 |
| Batfish validation | 4.1, 4.4, 6.1–6.3, 7.4, 7.12, 9.5, 11.1 |
| GitLab CI pipeline | 0.3, 4.2, 8.5, 11.3, 11.5 |
| BGP operations | 3.1–3.7, 5.1–5.2, 7.1–7.2, 7.3, 8.4 |
| Compliance and audit | 4.1–4.7, 6.1–6.6 |
| Troubleshooting | 7.1–7.12 |
| DR and resilience | 5.1–5.8, 12.2–12.3 |
| Monitoring | 9.1–9.6 |
| Hardware lifecycle | 10.1–10.6 |

### By Audience

| Audience | Recommended path |
|----------|-----------------|
| Manager / executive | 0.2, 1.1.5, 1.2.3, 4.2–4.3, 5.8, 8.5, 10.6, 11.6, 12.4 |
| Architect | 0.2–0.3, 1.1.1–1.1.5, 4.1–4.4, 6.1–6.3, 11.1–11.2, 12.4 |
| Network engineer (new to automation) | 0.1–0.4, 1.1.1–1.1.2, 2.1–2.2, 3.1, 7.1–7.3, 8.1–8.2 |
| Network engineer (experienced) | All practitioner exercises, focus on Modules 5–7, 11 |
| Advanced / senior engineer | All exercises including Deep Dive, Modules 11–12 |

---

*Total: 80 exercises across 12 modules. Modules 0–3 form the recommended beta release.*
