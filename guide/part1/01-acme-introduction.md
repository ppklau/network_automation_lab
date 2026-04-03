# Part 1 — Setting the Scene

# Chapter 1: ACME Investments

## The firm

ACME Investments is a mid-sized asset management firm headquartered in London, with data centres in New York, Singapore, and Frankfurt. They run their own network infrastructure: a spine-leaf fabric in London, inter-region BGP connecting the sites, and branch offices across the UK and US.

The trading division operates algorithmic and electronic trading platforms. These systems have strict latency requirements, strict isolation requirements, and strict regulatory requirements. MiFID II mandates that trading infrastructure cannot share a network path with corporate systems. The FCA requires auditable records of every change that touches the trading environment. GDPR and BaFin rules mean that data originating in Frankfurt cannot transit non-EU routing paths.

These are not hypothetical constraints. They are the kind of requirements that cause incidents when they are not met — regulatory investigations, fines, and trading halts.

## The network

```
EMEA — London (Primary HQ)            AMERICAS — New York
  DC1-LON: spine ×2, leaf ×4            DC1-NYC: border stub
  border-lon-01 (inter-region BGP)       border-nyc-01 [AS 65010]
  fw-lon-01 (zone enforcement)
  AS 65001

APAC — Singapore                      EU Regulatory — Frankfurt
  DC1-SIN: border stub                   DC1-FRA: border stub
  border-sin-01 [AS 65020]               border-fra-01 [AS 65030]
                                          ⚠ No TRADING zone — regulatory

Branch offices
  branch-lon-01 [AS 65100]  — UK office
  branch-nyc-01 [AS 65120]  — US office
  (30+ branches defined in SoT; 2 instantiated in the lab)
```

The London DC1 fabric is fully instantiated in the lab. The regional sites (NYC, SIN, FRA) are represented as FRR stub routers that participate in BGP, respond to pings, and accept Ansible pushes — but do not have a full DC behind them. The SoT knows they should. That gap is part of the learning: you will see how the automation pipeline handles a device defined in the SoT but not fully instantiated.

## The security zones

Every device and every interface belongs to a zone. Zone membership determines reachability policy.

| Zone | VLAN | Subnet (LON DC1) | Description |
|------|------|------------------|-------------|
| TRADING | 100 | 10.1.1.0/24 | Algorithmic trading systems — highest isolation |
| CORPORATE | 200–220 | 10.1.2.0/22 | General business users and services |
| DMZ | 300 | 10.1.6.0/24 | Public-facing services, market data feeds |
| MGMT | 900 | 10.1.0.0/25 | Network management plane — OOB access |

The firewall (`fw-lon-01`) enforces inter-zone policy. Batfish models the entire topology and verifies that zone policy holds — including catching misconfigurations before they reach a device.

Frankfurt has a special constraint: **VLAN 100 (TRADING) is prohibited**. An ACME trading platform in Frankfurt would mean EU client data touching a system that also sees UK trading flows, which violates GDPR's data minimisation principle and BaFin's operational resilience guidelines. This constraint is encoded in the SoT, enforced by the pipeline, and verified by Batfish. If someone tries to add a TRADING VLAN to a Frankfurt device, the pipeline blocks it before any config reaches the device.

## The problem ACME was solving

> 🔵 **Strategic**

Three years ago, ACME's network team managed the network by logging into devices. Changes were made with CLI commands, verified by pinging things, and documented in a spreadsheet that nobody kept up to date. The team was competent. The process was not.

When regulators requested audit evidence for a change that had affected the trading network, the team spent two weeks manually reviewing device logs, piecing together what had changed, when, and why. They could not prove that the change had been reviewed before implementation. They could not show who approved it. The audit finding cost the firm money and required the team to implement additional manual controls — more spreadsheets, more sign-off processes.

This is a common story. It is not a story about incompetent people. It is a story about a process that cannot produce the artefacts that modern compliance requires, regardless of how skilled the team is.

The target state ACME set was:

1. **Every change flows through the pipeline.** No direct CLI on production devices. If it did not go through the pipeline, it did not happen — and the pipeline records it.
2. **Config is generated from a source of truth.** If the SoT says a device should have VLAN 100, the device will have VLAN 100. If the SoT says Frankfurt devices must not have VLAN 100, no Frankfurt device will ever have it — even if someone tries.
3. **Design intent is tested automatically.** Batfish verifies zone isolation, routing policy, and resilience on every pipeline run. Compliance is not a quarterly review exercise. It is a status that is either passing or failing right now.
4. **Day-2 operations are automated.** Health checks, drift detection, compliance reports, and maintenance windows are playbooks, not procedures documented in a runbook that someone might follow.

By the end of this guide, ACME has achieved that target state, and you have operated every part of it.

## What you will build

> 🟡 **Practitioner**

The repository you cloned contains the complete ACME automation stack:

```
sot/                    The source of truth — all network intent in YAML
requirements/           Business requirements (REQ-001 to REQ-021)
design_intents/         Architectural intents (INTENT-001 to INTENT-010)
schema/                 JSONSchema validation for SoT files
scripts/                SoT validation and inventory generation
templates/              Jinja2 config templates (Arista EOS + FRR)
playbooks/              Ansible playbooks for push, verify, rollback, Day-2
batfish/                Intent verification test suite (pybatfish + pytest)
topology/               containerlab topology and startup configs
.gitlab-ci.yml          The CI/CD pipeline
monitoring/             Prometheus + Grafana stack
scenarios/              Fault injection and verify scripts for lab exercises
guide/                  This guide
```

You will not build this from scratch. You will operate it, extend it, break it, fix it, and — in the capstone exercises — use it to respond to simulated incidents under realistic pressure.

*Handbook reference: Chapter 1 (The automation imperative), Chapter 3 (The source of truth)*
