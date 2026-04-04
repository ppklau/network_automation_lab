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

**Next:** Chapter 16 covers compliance reporting and the audit artefact playbooks — the tools you reach for when a regulator asks you to prove something.
