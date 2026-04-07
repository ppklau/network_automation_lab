---
title: "Chapter 18: Maintenance Windows"
---

## The Forgotten Maintenance Window

Every network engineer has a version of this story.

A leaf switch needed an emergency optic replacement at 23:00. The engineer put the device into BGP graceful-shutdown — the correct thing to do, ensuring traffic drained before the device went dark. The optic was replaced, the cable reconnected, the device came back up. BGP sessions re-established. The engineer confirmed traffic was flowing and went to bed at 01:30.

The graceful-shutdown was never removed.

Three days later, the device is still running with BGP graceful-shutdown active. Its routes are deprioritised by every peer. ECMP is broken across the London DC — `leaf-lon-04` is carrying almost no traffic while `leaf-lon-03` carries double its intended share. No monitoring alert fired because the sessions are up and traffic is flowing, just not balanced.

The problem is discovered during a capacity review when someone notices `leaf-lon-03` is consistently running at 85% utilisation while `leaf-lon-04` shows 12%.

Two things went wrong. First, there was no automated exit step. Second, there was no mechanism to detect that a maintenance window had been open for three days.

`playbooks/maintenance_window.yml` solves both.

---

## How Maintenance Windows Work

The playbook uses a state file in `state/maintenance_<hostname>.yml` to track every open maintenance window. The enter step creates the state file; the exit step removes it.

This gives you three properties:

1. **Auditability** — `state/` is committed to git. Every maintenance window is recorded: who opened it, why, when, and when it was closed.
2. **Detectability** — A scheduled job that scans for state files older than 8 hours can alert the on-call engineer automatically. This is the basis for Module 11.2 (auto-remediation) later in the guide.
3. **Idempotency** — Running enter twice is safe. Running exit on a device that was never put into maintenance is safe (it will warn and skip, not error).

### Entering a Maintenance Window

```bash
ansible-playbook playbooks/maintenance_window.yml \
  --limit leaf-lon-04 \
  --extra-vars "action=enter window_reason='Optic replacement on Ethernet1'"
```

What happens:

1. BGP graceful-shutdown applied (EOS: `graceful-restart-helper` under `router bgp`; FRR: `bgp graceful-shutdown` via vtysh)
2. Maintenance banner set on the device
3. `state/maintenance_leaf-lon-04.yml` written with timestamp, reason, and approver

The state file looks like:

```yaml
hostname: leaf-lon-04
action: maintenance_active
reason: "Optic replacement on Ethernet1"
started: "2026-04-03T23:05:00Z"
scheduled_end: "2026-04-04T01:00:00Z"
approved_by: "{{ ansible_user }}"
status: active
```

### Exiting a Maintenance Window

```bash
ansible-playbook playbooks/maintenance_window.yml \
  --limit leaf-lon-04 \
  --extra-vars "action=exit"
```

What happens:

1. State file checked — playbook warns if no active maintenance found
2. Graceful-shutdown removed
3. Operational banner restored
4. State file deleted
5. BGP recovery wait — playbook waits up to 60 seconds for all sessions to re-establish

The exit step will not proceed if the state file shows the window was opened more than 24 hours ago without a `confirmed=yes` override. This prevents accidental exits from forgotten windows without review.

---

## Exercise 8.6 — Stuck Maintenance Mode {#ex86}

🟡 **Practitioner**

### Scenario

`leaf-lon-04` has been in maintenance mode for three days. BGP sessions are Established but routes are deprioritised. ECMP is broken across the London DC. The on-call engineer found the issue during a capacity review. Your task is to identify the state, understand the impact, and exit maintenance cleanly.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex86_inject.yml
```

This puts `leaf-lon-04` into BGP graceful-shutdown and writes a maintenance state file with a start timestamp three days in the past.

### Your Task

**Step 1 — Read the state file.**

```bash
cat state/maintenance_leaf-lon-04.yml
```

What does the state tell you? When was the window started? What was the reason?

**Step 2 — Run the health check.**

```bash
ansible-playbook playbooks/daily_health_check.yml --limit leaf-lon-04
```

The health check should show the BGP sessions as `Established` but you may see a WARNING about graceful-shutdown state depending on your health check version. This is the key teaching point: a session can be `Established` and still be in a degraded operational state.

**Step 3 — Confirm the BGP graceful-shutdown is active.**

Connect directly and check the BGP configuration:

```bash
ansible -i inventory/hosts.yml leaf-lon-04 \
  -m arista.eos.eos_command \
  -a "commands=['show bgp summary | json']"
```

Look for `gracefulRestart` or `graceful-restart-helper` in the running config:

```bash
ansible -i inventory/hosts.yml leaf-lon-04 \
  -m arista.eos.eos_command \
  -a "commands=['show running-config | section router bgp']"
```

**Step 4 — Exit maintenance.**

```bash
ansible-playbook playbooks/maintenance_window.yml \
  --limit leaf-lon-04 \
  --extra-vars "action=exit"
```

Watch the output — the playbook will wait for BGP sessions to recover before reporting success.

**Step 5 — Verify.**

```bash
ansible-playbook scenarios/ch07/ex86_verify.yml
```

The verify checks:
- `graceful-restart-helper` absent from BGP config
- Maintenance banner cleared
- `state/maintenance_leaf-lon-04.yml` does not exist
- BGP sessions Established

### What to Notice

- The state file is the diagnostic artifact. In a real incident, the state file tells you immediately who opened the window, why, and when — without logging into the device.
- The exit step waits for BGP recovery before succeeding. If you run the verify immediately after a manual config change, BGP may not have converged yet. The playbook's wait loop handles this.
- After the exercise, check `git log state/` — if you committed the state file earlier, you can see the full maintenance history in git.

> **Extension exercise:** Write a shell script that scans `state/maintenance_*.yml` and alerts if any window has been open more than 8 hours. What command would you add to crontab to run this check every hour?

---

## Maintenance Windows and ECMP

🔴 **Deep Dive**

BGP graceful-shutdown works by setting the `GRACEFUL_SHUTDOWN` community (65535:0) on all routes advertised by the device. Receiving routers that honour this community set the local preference for those routes very low — typically 0 — causing them to be deprioritised in the path selection process.

The result: traffic still flows to and from the device (sessions are up, routes are in the table), but the device carries almost no traffic because its routes lose every ECMP comparison. This is the intended behaviour for maintenance — drain the device before taking it offline.

The problem is that ECMP operates silently. There is no alert for "this device is carrying 5% of its expected share of traffic." Without a utilisation monitor comparing the two leaf switches, the imbalance could persist indefinitely.

This is why the Day-2 playbooks are designed to be run together. `interface_utilisation.yml` would have shown:

```
leaf-lon-03: Ethernet1  utilisation_pct=84%  [ALERT: >80%]
leaf-lon-04: Ethernet1  utilisation_pct=9%
```

The imbalance between the two leaf switches is the signal. Once you know `leaf-lon-04` is carrying almost no traffic, the next step is to check its BGP state — and that's where you find the forgotten graceful-shutdown.

In Part 7 (monitoring stack), you will build a Grafana dashboard that plots utilisation for both leaf switches on the same panel. The imbalance would be immediately visible as two diverging lines.

---

## Scheduling Maintenance Window Audits

In production, add a crontab entry on the Ansible controller to scan for stale maintenance windows:

```bash
# /etc/cron.d/acme-maintenance-audit
# Run every hour; alert if any window older than 8h
0 * * * * ansible /opt/acme-network/scripts/check_stale_maintenance.py \
  --max-age-hours 8 \
  --alert-webhook https://hooks.slack.com/services/XXXXX
```

The script reads all `state/maintenance_*.yml` files, parses the `started` timestamp, and sends a Slack alert for any window exceeding the threshold. This is the same logic Module 11.2 (auto-remediation) builds into an Ansible playbook that can automatically exit stale windows with a human-approval gate.

---

**Next:** Chapter 19 covers the final two Day-2 operations: device decommission and SoT hygiene — the playbooks you run infrequently but that matter the most when you do.
