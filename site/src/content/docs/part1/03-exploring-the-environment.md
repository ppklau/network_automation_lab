---
title: "Chapter 3: A First Look at the Environment"
---

> 🟡 **Practitioner** — Modules 0.2 and 0.3
> 🔵 **Strategic** — sections marked

*Estimated time: 30 minutes — no changes made, observation only*

---

## Scenario

You have joined the ACME network automation team. Before your first change, your manager asks you to spend an afternoon understanding how the environment is structured. "Read the SoT, trace a change through the pipeline on paper, then we will talk through it."

This chapter is that afternoon.

---

## The source of truth

The SoT lives in `sot/`. Everything that should be true about the network lives here. No spreadsheets, no tickets, no device CLIs.

```bash
find sot/ -name "*.yml" | head -20
```

```
sot/global/asn_pools.yml
sot/global/ipam.yml
sot/global/platform_defaults.yml
sot/global/ntp.yml
sot/global/dns.yml
sot/global/snmp.yml
sot/regions/emea.yml
sot/regions/americas.yml
sot/regions/apac.yml
sot/regions/eu_regulatory.yml
sot/sites/lon-dc1.yml
sot/sites/fra-dc1.yml
...
sot/devices/lon-dc1/spine-lon-01.yml
sot/devices/lon-dc1/leaf-lon-01.yml
...
```

### Global configuration

The global files define values that apply everywhere:

```bash
cat sot/global/asn_pools.yml
```

```yaml
bgp_asn_pools:
  emea_lon:    65001
  americas_nyc: 65010
  apac_sin:    65020
  eu_fra:      65030
  branches:
    uk:   { start: 65100, end: 65111 }
    us:   { start: 65120, end: 65127 }
    apac: { start: 65130, end: 65135 }
    eu:   { start: 65140, end: 65143 }
```

Every BGP ASN in the network comes from this pool. No ASN is allocated by hand — you pick the next available from the correct regional pool and record it here. The schema validation script checks for duplicates.

### Site configuration

```bash
cat sot/sites/fra-dc1.yml
```

```yaml
name: fra-dc1
region: eu_regulatory
timezone: Europe/Berlin
zone_permissions:
  - CORPORATE
  - DMZ
  - MGMT
vlans_prohibited:
  - 100   # TRADING — prohibited by BaFin/GDPR regulatory constraints
compliance_tags:
  - gdpr_data_residency
  - bafin_operational_resilience
```

The `vlans_prohibited` list is enforced at multiple layers:

1. The Jinja2 template for VLANs skips any VLAN in this list
2. `validate_sot.py` checks that Frankfurt devices do not reference VLAN 100
3. `test_frankfurt_isolation.py` verifies in Batfish that VLAN 100 is absent from all FRA interfaces

This is the three-layer model in practice: a business requirement (GDPR/BaFin ring-fencing) becomes a site-level constraint in the SoT, which becomes a template skip, which becomes a Batfish assertion.

### Device configuration

```bash
cat sot/devices/lon-dc1/leaf-lon-01.yml
```

The device file is the single authoritative record for everything about that device. Scroll through it:

```yaml
hostname: leaf-lon-01
platform: arista_eos
role: leaf
site: lon-dc1
lab_state: active
compliance_tags:
  - mifid_ii_trading_zone
  - fca_sysc_8

interfaces:
  - name: Ethernet1
    description: "P2P to spine-lon-01 Ethernet3"
    ip: 10.1.100.1/31
    peer: spine-lon-01
    peer_interface: Ethernet3

  - name: Vlan100
    description: "TRADING zone SVI"
    ip: 10.1.1.1/24
    vrf: TRADING_VRF
    vrrp:
      - group: 10
        virtual_ip: 10.1.1.254
        priority: 110

vrfs:
  - name: TRADING_VRF
    rd: "65001:100"
    route_targets:
      import: ["65001:100"]
      export: ["65001:100"]

bgp:
  local_as: 65001
  router_id: 10.1.255.11
  role: rr_client
  neighbors:
    - peer: 10.1.255.1
      remote_as: 65001
      description: "iBGP to spine-lon-01 (RR)"
      md5_password_ref: ibgp_lon_leaf01_spine01
    - peer: 10.1.255.2
      remote_as: 65001
      description: "iBGP to spine-lon-02 (RR)"
      md5_password_ref: ibgp_lon_leaf01_spine02
```

Notice what is not here: no BGP timer values, no session hold-time, no logging format. Those come from `sot/global/platform_defaults.yml`. Device files contain only what is specific to that device. Everything else is inherited.

> 🔵 **Strategic** — This separation is fundamental. When you want to change the BGP hold-time globally, you change one line in `platform_defaults.yml` and re-render all configs. When that change was made by hand on 60 devices, some would have the new value, some would not, and you would not know which until something broke. The SoT makes "change one thing everywhere" trivially correct.

---

## Tracing a config change on paper

> 🟡 **Practitioner**

Before running anything, trace this change mentally: *Add a description to Ethernet3 on leaf-lon-01.*

**Where does the change happen?** In `sot/devices/lon-dc1/leaf-lon-01.yml`. Not on the device.

**What happens next?**

```
SoT edit (leaf-lon-01.yml)
  ↓
git commit → GitLab CI triggered
  ↓
Stage 1: validate
  yamllint checks all YAML files
  validate_sot.py checks schemas + cross-references
  ↓
Stage 2: intent-check
  Batfish loads rendered configs, runs pytest assertions
  Checks: zone isolation, routing policy, BGP standards, resilience
  ↓
Stage 3: render
  Jinja2 templates + SoT → configs/leaf-lon-01/running.conf
  ↓
Stage 4: diff
  New running.conf vs last deployed config
  Shows exactly what will change on the device
  ↓
Stage 5: approve (manual gate)
  Engineer reviews the diff and clicks Approve in GitLab
  ↓
Stage 6: push
  Ansible connects to leaf-lon-01, pushes config atomically
  Captures before/after state
  ↓
Stage 7: verify
  Checks BGP neighbors up, interfaces up, management reachable
  Stores artefact in GitLab pipeline
```

A description change on one interface goes through seven stages. That might seem like a lot. The point is that the same pipeline that handles a description change also handles a VLAN addition, a BGP policy change, or a Frankfurt device modification. The pipeline does not know whether the change is trivial or dangerous — it applies the same rigour either way. That consistency is what makes the audit evidence credible.

---

## Exploring the pipeline without running it

Open `.gitlab-ci.yml` and read the stage definitions:

```bash
grep "^stages:" .gitlab-ci.yml -A 10
```

```yaml
stages:
  - validate
  - intent-check
  - render
  - diff
  - approve
  - push
  - verify
```

Find the Batfish intent-check job:

```bash
grep -A 20 "batfish-intent-check:" .gitlab-ci.yml
```

```yaml
batfish-intent-check:
  stage: intent-check
  services:
    - batfish/batfish:latest
  script:
    - bash batfish/run_checks.sh
  artifacts:
    reports:
      junit: batfish/reports/junit.xml
    expire_in: 4 weeks
```

The `services:` key starts a Batfish container as a sidecar to the job. The `run_checks.sh` script builds a snapshot from the rendered configs and runs the full pytest suite. JUnit output is captured as a GitLab test report — you can browse it in the MR view.

---

## What the pipeline does NOT do

> 🔵 **Strategic**

The pipeline does not prevent someone from SSHing directly to a device and making a change. It cannot. What it does is make out-of-band changes immediately visible: the next pipeline run will generate a diff between what the SoT says the device should look like and what it actually looks like. That diff is the starting point for the drift detection exercises in Chapter 15.

The pipeline is not a lock. It is a record. Every change that goes through it is traceable: who proposed it (git commit), who approved it (GitLab approval record), what it changed (the diff artefact), and whether the network was healthy before and after (the verify stage output). That record is the compliance artefact.

---

## Exercise 3.1 — Explore the SoT {#ex31}

> 🟡 **Practitioner**

Answer these questions by reading the SoT files — do not log into any device.

1. How many branch offices does ACME have defined in the SoT? *(hint: `sot/devices/branches/`)*
2. What ASN is assigned to `branch-lon-01`?
3. What BGP ASN does the Singapore DC use?
4. Which site files include `TRADING` in their `zone_permissions` list?
5. What NTP key type is used globally? *(hint: `sot/global/ntp.yml`)*
6. What is the `md5_password_ref` for the iBGP session between `spine-lon-01` and `border-lon-01`?

**Answers:** Check your answers by reviewing the relevant SoT files. There is no verify script for this exercise — you are training your ability to navigate the SoT, which is a prerequisite for every subsequent exercise.

---

## Exercise 3.2 — Trace a change through the pipeline {#ex32}

> 🟡 **Practitioner**

Without running any commands, answer:

1. If you add a new VLAN to `leaf-lon-01.yml`, which Jinja2 template renders that section of config?
2. Which Batfish test would catch a VLAN 100 addition to a Frankfurt device?
3. If the Batfish intent-check fails, does the render stage still run?
4. What happens if the verify stage fails after a push? Is the push automatically rolled back?

**Check your answers:** Look at `.gitlab-ci.yml`, `templates/arista_eos/vlans.j2`, and `batfish/tests/test_frankfurt_isolation.py`.

---

## Debrief

**What was practised:** Navigating the SoT file hierarchy and tracing a change through the pipeline stages — without running any commands or touching any devices.

**Why it matters:** Every subsequent exercise starts with an SoT edit and ends with a pipeline verification. If you cannot find the right file, read the right YAML key, or predict which pipeline stage catches a given error, you will be debugging tooling instead of learning automation. SoT navigation is the prerequisite skill for everything that follows.

**In production:** Senior engineers who know a network inside-out often resist structured SoT navigation — they prefer CLI and show commands. The shift from "I know where the config is on the device" to "I know where the intent is in the SoT" is the hardest cultural change in network automation adoption.

*Handbook reference: Chapter 5 (Pipeline patterns), Chapter 6 (Intent verification)*
