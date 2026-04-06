# Chapter 15: Health Checks and Drift Detection

## The Problem with Steady State

After a change freeze or a busy provisioning sprint, the network enters a period of "steady state." No changes are scheduled. BGP is green. Monitoring shows no alerts. Everything looks fine.

This is when silent problems accumulate.

A technician connects to a branch router to troubleshoot a circuit issue and runs `debug bgp`. They forget to turn it off. A junior engineer adds an NTP server to a leaf switch while chasing a log timestamp discrepancy. A vendor engineer applies a route-map change for a carrier Ethernet test and doesn't revert it. None of these trigger monitoring alerts. None break BGP. None appear in any ticket.

Six weeks later, the first of them causes a BGP session reset during peak trading hours because the debug output fills the router's memory. The second causes a compliance audit failure because the NTP server isn't in the approved list. The third causes branch traffic to black-hole silently during a failover.

All three were detectable the day they happened, if you had been running drift detection.

## Daily Health Check

`playbooks/daily_health_check.yml` collects a structured snapshot of every device's operational state and produces a HEALTHY / WARNING / CRITICAL summary.

### What It Collects

For EOS devices, the playbook runs four show commands in a single connection:

```
show bgp summary vrf all | json
show interfaces | json
show ntp status | json
show version | json
```

For FRR nodes, it collects equivalent data via inline Python over SSH:

```python
vtysh -c 'show bgp summary json'
cat /etc/frr/frr.conf | grep ntp
```

### The Health Fact

Each device produces a `device_health` fact with a consistent structure regardless of platform:

```yaml
device_health:
  hostname: leaf-lon-03
  platform: arista_eos
  bgp:
    sessions_total: 3
    sessions_established: 3
    sessions_not_established: 0
  interfaces:
    error_ports: []
    down_ports: ["Ethernet3"]
  ntp:
    synced: true
  version: "EOS 4.32.2F"
```

The aggregation play on localhost computes a `health_summary` across all devices:

- **HEALTHY** — all BGP established, no error ports, NTP synced
- **WARNING** — unexpected down ports, NTP unsynced, version mismatch
- **CRITICAL** — any BGP session not established

The play exits with `rc=1` on CRITICAL, making it suitable as a CI gate.

### Running the Health Check

```bash
# Full estate
ansible-playbook playbooks/daily_health_check.yml

# Single device
ansible-playbook playbooks/daily_health_check.yml --limit leaf-lon-03

# With verbose BGP detail
ansible-playbook playbooks/daily_health_check.yml -e show_bgp_detail=true
```

Output is written to `reports/health_<timestamp>.txt` and `state/health_<timestamp>.json`. The JSON file can be loaded by scripts or Grafana for trend analysis.

### Reading the Report

A healthy run looks like:

```
ACME Network Health Check — 2026-04-03T08:00:00Z
================================================
Status: HEALTHY

BGP Summary:
  Total sessions:       24
  Established:          24
  Not established:       0

Interface Summary:
  Error ports:           0
  Unexpected down:       1  [leaf-lon-04: Ethernet3 — planned dark]

NTP:
  Synchronised:         12/12

Devices checked:        12
```

A CRITICAL run fails the play immediately and outputs which device triggered it, which peer is affected, and what the peer state is. This is designed to be actionable: you can copy the device name and peer IP directly into a troubleshooting session.

---

## Exercise 8.1 — BGP Auth Mismatch {#ex81}

🟡 **Practitioner**

### Scenario

It's 02:30. The on-call engineer receives a PagerDuty alert: BGP session down on branch-lon-01. The session has been unstable for 20 minutes. Looking at the timeline, the outage started shortly after a scheduled carrier maintenance window on the branch circuit. The carrier engineer had SSH access to the branch router to test the circuit and "may have made some changes."

The BGP session to border-lon-01 is bouncing. Every few minutes it comes up briefly, then drops. This pattern is characteristic of MD5 authentication mismatch — the session can establish a TCP connection but the BGP OPEN is rejected because the passwords don't match.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex81_inject.yml
```

This changes the BGP MD5 password on branch-lon-01 to a value that doesn't match what border-lon-01 expects. The BGP session will go down.

### Your Task

1. **Run the health check.** The BGP session should appear as not-established.

   ```bash
   ansible-playbook playbooks/daily_health_check.yml --limit branch-lon-01
   ```

2. **Run drift detection** to see the configuration difference:

   ```bash
   ansible-playbook playbooks/drift_detection.yml --limit branch-lon-01
   ```

   Look for the CRITICAL drift line — it will show the `neighbor` password line differs from SoT.

3. **Remediate** by pushing the SoT config:

   ```bash
   ansible-playbook playbooks/push_config.yml --limit branch-lon-01
   ```

4. **Verify** the session recovers:

   ```bash
   ansible-playbook scenarios/ch07/ex81_verify.yml
   ```

### What to Notice

- The health check gives you `CRITICAL` status immediately.
- The drift report classifies the BGP password change as `CRITICAL` severity — it matches the pattern `r'^\s*(neighbor|router bgp|remote-as)'`.
- `push_config.yml` restores the SoT-defined password without you needing to know what the correct value is. The SoT is the authority.

> **Key insight:** The engineer who changed the password may not have known the correct value, or may have set it to a temporary test value and intended to revert it. Either way, drift detection catches it. The remediation is `push_config.yml`, not a manual CLI change — which would just add another untracked difference.

---

## Drift Detection

`playbooks/drift_detection.yml` compares what is running on each device against what the SoT says should be running.

### How It Works

The playbook runs in three stages:

**Stage 1 — Render SoT intent:**
```yaml
- import_playbook: render_configs.yml
```
This regenerates all templates from the current SoT, ensuring the comparison is against the latest intent.

**Stage 2 — Collect running config:**
- EOS: `show running-config`
- FRR: `vtysh -c 'show running-config'`

**Stage 3 — Compare and classify:**

An inline Python script uses `difflib.unified_diff` to produce the diff, then applies regex patterns to classify each changed line:

```python
CRITICAL_PATTERNS = [
    r'^\s*(neighbor|router bgp|remote-as|route-map|prefix-list)',
    r'^\s*(ip address|vrf|vlan)',
    r'^\s*(permit|deny)',
    r'^\s*(no ip telnet|ip telnet)',
]
WARNING_PATTERNS = [
    r'^\s*(timers|keepalive|hold-time)',
    r'^\s*(logging|snmp)',
    r'^\s*(ntp)',
]
# Everything else → INFORMATIONAL
```

Lines present in running config but absent from SoT are `+` lines (OOB additions). Lines present in SoT but absent from running config are `-` lines (missing intent).

Both directions matter. A `-` line means someone removed something that should be there (e.g., removed a BGP community filter). A `+` line means someone added something that isn't in the SoT (e.g., added a debug NTP server).

### Severity Philosophy

| Severity | Meaning | Action |
|---|---|---|
| CRITICAL | Could affect routing, security, or compliance | Fix immediately; block CI |
| WARNING | Operationally suboptimal but not immediately harmful | Fix within 24h; alert |
| INFORMATIONAL | Cosmetic or comment differences | Fix at next maintenance window |

The playbook exits with `rc=2` on any CRITICAL drift, making it suitable as a CI gate. In ACME's pipeline, drift detection runs as a scheduled job nightly and also before any new change is applied.

### Auto-Remediation Mode

```bash
ansible-playbook playbooks/drift_detection.yml -e auto_remediate=true
```

In auto-remediate mode, the playbook calls `push_config.yml` for any device with CRITICAL drift. Use with caution: this is appropriate for a nightly batch job on a well-understood network, but you would not run it manually during business hours without reviewing the drift report first.

---

## Exercise 8.2 — OOB Configuration Changes {#ex82}

🟡 **Practitioner**

### Scenario

The overnight monitoring report flags leaf-lon-03 as having `WARNING` drift. You need to identify what changed, classify the severity, and remediate.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex82_inject.yml
```

Two changes are injected:
1. Interface description changed to a debug session marker (`TEMP_DEBUG_SESSION...`)
2. A non-approved NTP server (`8.8.8.8`) added

### Your Task

1. **Run drift detection:**

   ```bash
   ansible-playbook playbooks/drift_detection.yml --limit leaf-lon-03
   ```

2. **Read the drift report** in `reports/drift_<timestamp>.txt`. Identify which change is INFORMATIONAL and which is WARNING.

3. **Without looking at the inject playbook**, determine from the drift report alone what was changed.

4. **Remediate** and verify:

   ```bash
   ansible-playbook playbooks/push_config.yml --limit leaf-lon-03
   ansible-playbook scenarios/ch07/ex82_verify.yml
   ```

### What to Notice

- The description change is classified `INFORMATIONAL` — it matches no CRITICAL or WARNING pattern.
- The NTP server addition is classified `WARNING` — it matches `r'^\s*(ntp)'`.
- Both are `+` lines in the diff: additions that don't exist in the SoT. This means someone added them out-of-band, not that the SoT is missing something.

> **Open exercise:** In a production environment, would you auto-remediate a `WARNING` drift? What about `INFORMATIONAL`? Consider: if you auto-remediate a description change, you silently remove evidence that someone was debugging. Sometimes the right action is to file a ticket, not push a config.

---

## Troubleshooting Bundle: Packaging State for Incident Response

### [🔵 Strategic] Why This Matters

Health checks tell you something is wrong. Drift detection tells you what changed. But at 02:47 on a Sunday morning, the on-call engineer — who may have started three weeks ago — does not have time to run three separate playbooks, interpret three separate reports, and compose a coherent incident summary from memory. They need to capture state, attach it to the ticket, and escalate. The troubleshooting bundle is that single command.

The bundle is not a diagnostic tool. It is a *handoff artefact*. It captures the network's state at the moment of an alert and packages it so that someone who was not present when the alert fired — possibly in a different timezone, possibly with no context beyond the ticket — can open one file (`MANIFEST.md`) and immediately understand what is happening.

This is the difference between an incident that takes 45 minutes to triage and one that takes 5 minutes. The senior engineer who receives the escalation reads the MANIFEST, opens the relevant device state files, and knows exactly which BGP session is down, whether there is config drift, and which devices are healthy. No SSH needed. No "can you send me the output of show bgp summary on border-lon-01."

### [🟡 Practitioner] The Bundle Playbook

`playbooks/troubleshooting_bundle.yml` orchestrates four collection phases into a single `.tar.gz`:

1. **State collection** — per-device BGP summary, interface status, route table, running config, and recent logs
2. **Health check** — aggregate BGP/NTP/interface health with HEALTHY/WARNING/CRITICAL classification
3. **Drift detection** — running config compared against SoT-rendered config, with severity classification
4. **Packaging** — everything compressed into a timestamped tarball with a human-readable MANIFEST

### Bundle Structure

```
bundle_20260406_143022/
  MANIFEST.md                  ← start here
  manifest.json                ← machine-readable metadata
  health/
    health_summary.json
    health_summary.txt
  state/
    border-lon-01/
      bgp_summary.json
      interfaces.json
      routes.json
      running_config.txt
      logs.txt
      version.json
    leaf-lon-02/
      ...
  drift/
    drift_summary.json
    drift_summary.txt
```

Each device gets its own subdirectory under `state/`. Each data type is a separate file. This matters: when the senior engineer opens the bundle, they go straight to `state/border-lon-01/bgp_summary.json` — they do not parse a 500-line monolithic JSON looking for the relevant device.

### Running It

```bash
# Full network bundle
ansible-playbook playbooks/troubleshooting_bundle.yml

# With incident reference (appears in MANIFEST)
ansible-playbook playbooks/troubleshooting_bundle.yml \
  -e "incident_id=INC-2026-04-0042"

# Single device (targeted investigation)
ansible-playbook playbooks/troubleshooting_bundle.yml --limit border-lon-01

# Triggered by Alertmanager (for automation)
ansible-playbook playbooks/troubleshooting_bundle.yml \
  -e "triggered_by=alertmanager" -e "incident_id=ALERT-1712420422"
```

Output is written to `bundles/bundle_<timestamp>.tar.gz`. The final play prints the file path, size, and SHA256 checksum.

### Reading the MANIFEST

The MANIFEST is designed to answer four questions in under 30 seconds:

1. **What is the overall health?** — HEALTHY / WARNING / CRITICAL
2. **Which devices have issues?** — BGP issues, interface errors, NTP drift
3. **Is there config drift?** — and on which devices
4. **What should I look at first?** — ordered list of files to open

A real MANIFEST looks like this:

```markdown
## Quick Summary

**Overall Health: CRITICAL**

- BGP issues on: border-lon-01
- Interfaces: no error counters
- NTP: all nodes synchronised
- Drift detected on: leaf-lon-02

## What to Look At First

1. health/health_summary.txt -- overall network health
2. state/border-lon-01/ -- device with BGP issues
3. drift/drift_summary.txt -- configuration drift details
```

The on-call engineer reads this, attaches the tarball to the incident, and writes: "BGP session loss on border-lon-01, config drift on leaf-lon-02. Bundle attached. Escalating to network team." That escalation takes 2 minutes, not 20.

### Design Decisions

**Why not call the existing playbooks?** The troubleshooting bundle inlines the health check and drift detection logic rather than calling `daily_health_check.yml` and `drift_detection.yml` directly. Those playbooks fail on CRITICAL status (by design — they are CI gates). The bundle must complete even when the network is broken. That is the whole point: you are capturing the broken state.

**Why separate files per device?** Because incident responders need to navigate directly to the relevant device. `state/border-lon-01/bgp_summary.json` is immediately useful. A single `all_state.json` requires tooling to extract the relevant section.

**Why no Batfish?** The bundle captures *live state*, not *model analysis*. Batfish takes 30-60 seconds to upload a snapshot and run assertions. At 02:47, that delay matters. If you want Batfish analysis, run it separately after the immediate triage.

---

## Exercise 8.9 — Troubleshooting Bundle for On-Call Handoff {#ex89}

🟡 **Practitioner**

### Scenario

It is 02:47 on a Sunday morning. Alertmanager pages the on-call engineer for ACME Investments: `BGPSessionLoss` on border-lon-01 to border-nyc-01. The on-call engineer is a junior member of the team who started three weeks ago. They have not worked on the border routers before.

Earlier that week, a senior engineer had SSH'd into leaf-lon-02 to chase an NTP discrepancy during business hours. They added a test NTP server (`8.8.8.8`) and forgot to revert it. Nobody noticed.

The on-call engineer needs to capture the current state, package it, and escalate — not diagnose and fix at 03:00 on a Sunday.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex89_inject.yml
```

Two faults are injected:
1. BGP session loss on border-lon-01 (Ethernet3 to border-nyc-01 shut down)
2. OOB config drift on leaf-lon-02 (NTP server 8.8.8.8 added)

### Your Task

1. **Generate the troubleshooting bundle:**

   ```bash
   ansible-playbook playbooks/troubleshooting_bundle.yml \
     -e "incident_id=INC-2026-04-0042"
   ```

2. **Extract and read the MANIFEST:**

   ```bash
   ls bundles/bundle_*.tar.gz
   tar -xzf bundles/bundle_*.tar.gz -C /tmp
   cat /tmp/bundle_*/MANIFEST.md
   ```

3. **Answer these questions from the MANIFEST alone** (without logging into any device):
   - What is the overall health status?
   - Which device has a BGP issue?
   - Is there configuration drift? On which device?
   - What file would you open first to investigate the BGP issue?

4. **Verify:**

   ```bash
   ansible-playbook scenarios/ch07/ex89_verify.yml
   ```

### What to Notice

- The bundle captured two unrelated issues in a single artefact: a BGP session loss and stale config drift. The on-call engineer did not need to know about the NTP issue in advance — the bundle surfaced it automatically.
- The MANIFEST told you exactly where to look first. No guesswork.
- The entire bundle generation was a single command. No show commands, no SSH sessions, no remembering which device to check.

> **Open exercise:** In production, you would configure Alertmanager to trigger the bundle automatically via webhook when a critical alert fires. The bundle would be generated within seconds of the alert and attached to the incident before the on-call engineer even opens their laptop. How would you implement that webhook? (Hint: a small Python Flask app that receives the Alertmanager JSON payload and runs `ansible-playbook` with the alert labels as extra vars.)

---

**Next:** Chapter 16 covers compliance reporting and the audit artefact playbooks — the tools you reach for when a regulator asks you to prove something.
