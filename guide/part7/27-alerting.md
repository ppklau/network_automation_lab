# Chapter 27: Alerting

## The Difference Between Dashboards and Alerts

A dashboard answers questions you already know to ask. You open Grafana, look at the BGP session table, and see that everything is healthy. A dashboard is a pull model: you go to it.

An alert answers a question you did not know you needed to ask. At 02:47 on a Sunday, `border-lon-01`'s session to `border-nyc-01` drops. Nobody was looking at the dashboard. The alert fires, the on-call engineer is paged, and the incident response clock starts. An alert is a push model: it comes to you.

Both are necessary. The monitoring stack has both. This chapter focuses on the alerting layer and how it connects to the incident response playbooks built in earlier modules.

## How the Alert Pipeline Works

```
Ansible (write_bgp_metrics.yml)
    │  writes .prom textfile
    ▼
node_exporter → Prometheus (evaluates alert rules every 60s)
    │  rule: acme_bgp_session_established == 0 for 60s
    ▼
Alertmanager (routes, deduplicates, inhibits)
    │  routes to notification channel
    ▼
On-call engineer / PagerDuty / Slack
```

The key component is **Alertmanager**, which sits between Prometheus and the notification channel. Alertmanager does three things that Prometheus alone cannot:

**Routing.** Different alerts go to different recipients. A BGP session loss in the TRADING VRF at 09:30 on a trading day might go to both the NOC and the trading operations desk. A config drift alert at 03:00 might only go to the NOC. Routing rules in `alertmanager/alertmanager.yml` define this.

**Deduplication.** If five BGP sessions drop simultaneously (e.g., border-lon-01 loses power), Alertmanager groups them into a single notification rather than sending five separate pages. This is controlled by `group_by` in the routing config.

**Inhibition.** If a BGP session is down, the BGP prefix count for that peer will also drop. Without inhibition, you get two alerts for one problem. The inhibition rule in `alertmanager.yml` suppresses the `BGPPrefixCountDrop` alert when `BGPSessionLoss` fires for the same node and peer.

---

## Exercise 9.3 — BGP Session Loss Alert {#ex93}

🟡 **Practitioner**

### Scenario

ACME's SLA for the inter-region BGP sessions requires that any session loss is detected and the on-call engineer is notified within 3 minutes. The current process depends on the engineer running a manual health check. Your task is to configure and verify the automated alert for BGP session loss, and validate that the inhibition rules work correctly.

### Inject the Fault

```bash
ansible-playbook scenarios/ch09/ex93_inject.yml
```

This shuts down the BGP session from `border-lon-01` to `border-nyc-01` by applying an inbound route-map that drops all received routes, simulating a session that is technically `Established` but not passing prefixes — and then brings the session fully down.

You will not be told which session is affected.

### Step 1 — Observe the Prometheus alert firing

Run the metrics playbook to write fresh data:

```bash
ansible-playbook playbooks/write_bgp_metrics.yml
```

Open Prometheus: http://localhost:9090/alerts

Within 60–90 seconds of the next metrics write, the `BGPSessionLoss` alert will appear in the `Firing` state. The alert shows:
- Which node and peer are affected
- The label values (region, VRF, peer description)
- The annotation text including the runbook reference

Observe the alert carefully before proceeding. The information in the alert should be sufficient for the on-call engineer to identify the affected device without needing to query any other system.

### Step 2 — Verify Alertmanager received the alert

Open Alertmanager: http://localhost:9093

Navigate to **Alerts**. The `BGPSessionLoss` alert should be visible. Notice:
- The grouping: alerts are grouped by `alertname`, `node`, and `region`
- The receiver: `lab-log` (in production, this would be PagerDuty or Slack)
- The silence option: you can silence the alert for a duration (this is the Alertmanager equivalent of an ACK in traditional monitoring)

### Step 3 — Verify Grafana alert

Open Grafana: http://localhost:3000/alerting/list

The `BGP Session Loss` alert rule (from `monitoring/grafana/alerts/bgp_session_loss.yml`) will show as `Firing`. Click on it to see the alert detail, including which series triggered it.

Navigate to the **ACME Network Overview** dashboard. The BGP Session State table will show `border-lon-01 → border-nyc-01` (or whichever session is affected) as `DOWN` (red). Grafana places an alert indicator on the panel.

### Step 4 — Verify inhibition

Because the BGP session is down, the prefix count for `border-nyc-01` will also drop to zero. This should trigger a `BGPPrefixCountDrop` alert — but the inhibition rule should prevent it from being routed to the on-call engineer.

In Alertmanager, check the **Inhibited** tab. You should see `BGPPrefixCountDrop` listed as inhibited, with the source alert (`BGPSessionLoss`) shown. This is the inhibition rule in action: one notification for one problem, even if multiple alert rules fire.

### Step 5 — Check the `MetricsStale` alert does NOT fire

The `MetricsStale` alert fires when a node's metrics have not been updated in more than 10 minutes. Because the metrics playbook ran in Step 1, `acme_last_metrics_update_timestamp` is fresh. The alert should not be firing.

This is worth verifying explicitly. A monitoring system that produces false-positive stale alerts will be ignored. The inhibition rule for `MetricsStale` (which suppresses BGP and NTP alerts when stale data might be causing false positives) only works correctly if `MetricsStale` is itself accurate.

### Step 6 — Remediate and verify recovery

Identify the failing session from the alert data, then remediate:

```bash
ansible-playbook scenarios/ch09/ex93_verify.yml
```

The verify playbook restores the BGP session and confirms it recovers to `Established`. After running it, write fresh metrics:

```bash
ansible-playbook playbooks/write_bgp_metrics.yml
```

Within the next Prometheus evaluation cycle (up to 60 seconds), the `BGPSessionLoss` alert will transition to `Resolved`. In Alertmanager, resolved alerts generate a resolution notification — in production, this closes the PagerDuty incident or sends a Slack message confirming the session is restored.

### What to Notice

- The `for: 60s` duration in the alert rule means the alert only fires after the session has been down for a full minute. This prevents spurious alerts from momentary BGP resets (common during config pushes). The tradeoff is a 60-second detection latency. For the ACME SLA, this is acceptable — but you could reduce it to 30 seconds if needed.
- The alert annotation includes a `runbook` URL. In production, this URL points to the remediation runbook. The engineer who gets paged at 02:47 does not need to remember the steps — the alert itself tells them where to look. The runbooks built in Chapters 21 and 22 (RMA workflows) are the target of these runbook URLs.
- The Alertmanager silence UI allows an engineer to suppress an alert during a planned maintenance window. This is the Alertmanager equivalent of the `maintenance_window.yml` playbook — one approaches it from the automation side, the other from the monitoring side. In production, you would use both: the playbook suppresses the change, and the Alertmanager silence ensures that if the suppression fails, the alert does not page the wrong person.

---

## 🔴 Deep Dive: SNMP Exporter {#snmp-deep-dive}

🔴 **Deep Dive**

The textfile collector approach has one limitation: metrics are only as fresh as the last Ansible run. For some use cases — detecting a BGP session drop within seconds, or capturing interface counter spikes that last less than a minute — polling every 2 minutes is too slow.

The production-grade solution is the **Prometheus SNMP exporter**, which scrapes SNMP data directly from devices on every Prometheus scrape interval (60 seconds by default, configurable to 30 or 15 seconds).

ACME's cEOS nodes support SNMPv3 (configured in `sot/global/snmp.yml`). The relevant MIBs are:

| MIB | What it provides |
|-----|-----------------|
| BGP4-MIB (RFC 4273) | BGP peer state, prefixes received/sent, uptime |
| IF-MIB (RFC 2863) | Interface counters, speed, operational state |
| Arista-specific OIDs | EOS-specific extensions (temperature, hardware status) |

The SNMP exporter is not deployed in the base monitoring stack (it requires additional SNMP module configuration that varies by device platform). To add it:

**1 — Add the service to docker-compose.yml:**

```yaml
snmp_exporter:
  image: prom/snmp-exporter:v0.25.0
  container_name: acme-snmp-exporter
  restart: unless-stopped
  volumes:
    - ./snmp_exporter/snmp.yml:/etc/snmp_exporter/snmp.yml:ro
  ports:
    - "9116:9116"
  networks:
    - monitoring
    - acme-mgmt
```

**2 — Add a scrape config to prometheus.yml:**

```yaml
- job_name: acme_snmp_bgp
  scrape_interval: 30s
  static_configs:
    - targets:
        - 172.20.20.11  # spine-lon-01
        - 172.20.20.31  # border-lon-01
        # ... etc
  metrics_path: /snmp
  params:
    module: [bgp4_mib]
    auth: [acme_snmpv3]
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: snmp_exporter:9116
```

**3 — Create the SNMP module config** (`monitoring/snmp_exporter/snmp.yml`):

The SNMP exporter uses a generator to produce module configs from MIB files. The BGP4-MIB module would walk `bgpPeerTable` (OID `1.3.6.1.2.1.15.3`) and translate the `bgpPeerState` value (1=idle, 3=active, 6=established) into a Prometheus gauge.

This is a significant configuration effort and requires the MIB files to be available locally. The lab's textfile approach gives equivalent data with less complexity — the SNMP route is appropriate when you need sub-minute refresh rates.

> **Design note:** In a real financial institution running this monitoring stack, you would use SNMP (or streaming telemetry via gNMI) for the operational layer and the textfile collector for compliance-oriented metrics that benefit from the Ansible context (drift detection, NTP sync from the same run that validates configs). The two approaches are complementary, not mutually exclusive.

---

## The Monitoring Stack as a Whole

At the end of Part 8, ACME's monitoring stack provides:

- **BGP session state** for all 13 active lab nodes, refreshed every 2 minutes
- **Interface utilisation** at 5-minute resolution
- **Config drift** as a binary flag per node, refreshed whenever drift_detection.yml runs
- **NTP compliance** as a binary flag per node
- **Automated alerts** for session loss (60s for trigger), prefix drops, and stale metrics
- **TRADING zone compliance** as a dedicated dashboard with historical data
- **Alertmanager** with deduplication, inhibition, and routing rules

What it does not yet provide:

- **Capacity trending** — the utilisation graphs show current state but trend analysis requires longer retention and a capacity planning workflow. This is Module 11.
- **Incident correlation** — the annotations on graphs require manual correlation. The advanced chapter (Module 11.2) covers automated drift detection with auto-remediation, which extends this toward closed-loop operation.

---

**Next:** Part 9 covers advanced automation patterns — staged rollouts, auto-remediation, and the capstone scenarios.
