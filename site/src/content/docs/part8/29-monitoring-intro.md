---
title: "Chapter 29: What the Monitoring Stack Changes"
---

🔵 **Strategic**

Before automation, ACME's network monitoring was reactive. An engineer noticed a problem because a user called, or because they happened to run `show bgp summary` on the right device at the right time. There was no consolidated view of session state across sites. Interface utilisation was checked manually when someone suspected a problem. Drift — running config diverging from the intended config — was invisible unless someone went looking.

The monitoring stack changes this from reactive to observable. The difference is not just about catching problems faster. It is about what the data enables.

When BGP session state and interface utilisation are in Grafana with a 60-second resolution, two things become possible that weren't before:

**Correlation.** A BGP session drop at 14:32 can be correlated with a config push annotation at 14:31. Without the time-series data, you would be guessing. With it, you know that the push caused the session reset and that it recovered within 45 seconds — which is acceptable for planned maintenance but not for an unplanned event.

**Trend analysis.** Interface utilisation at 73% today, 78% last week, 82% in the previous cycle. Without the monitoring stack, capacity planning is a manual exercise. With it, the trend is visible before the threshold is crossed.

The third thing the monitoring stack enables is harder to quantify but arguably more valuable: it creates an objective record of network behaviour. In a regulated environment — MiFID II, FCA, GDPR — the ability to produce a timestamped record of "was the TRADING zone available at 09:23 on 14 March" is not just operationally useful; it is a compliance obligation.

## What Is Being Monitored

This section builds a monitoring stack that covers four domains:

| Domain | Metrics | Source | Dashboard |
|--------|---------|--------|-----------|
| BGP session state | Established/down per peer, per VRF | `write_bgp_metrics.yml` | Network Overview, TRADING Zone |
| Interface utilisation | Tx/Rx % per interface | `interface_utilisation.yml` | Network Overview |
| Config drift | Nodes with running/SoT divergence | `drift_detection.yml` | Network Overview |
| NTP compliance | Sync state per node | `write_bgp_metrics.yml` | Network Overview |

All four write Prometheus text-format metrics to `monitoring/prometheus/`. Prometheus scrapes these via `node_exporter`'s textfile collector. Grafana queries Prometheus and renders the dashboards.

## The Textfile Collector Pattern

The monitoring stack uses a pattern that is worth understanding explicitly, because it differs from how most monitoring guides describe metric collection.

Most monitoring documentation assumes that a Prometheus exporter runs as a long-lived process and responds to HTTP scrapes in real time: `go to device, collect data now, return it`. This works well for systems that expose a metrics endpoint (databases, web servers, Kubernetes pods).

Network devices in the lab — cEOS and FRR — do not expose Prometheus-compatible metrics endpoints. They speak SNMP or vendor-specific APIs. The production approach for this would be an SNMP exporter (covered in the Deep Dive section). In the lab, the simpler and more instructive approach is the **textfile collector**:

1. Ansible playbooks collect data from devices using the same Ansible modules used everywhere else in the lab
2. Playbooks write the data in Prometheus text format to `.prom` files in `monitoring/prometheus/`
3. `node_exporter` (running as a Docker container) reads these files and serves them as a standard Prometheus metrics endpoint
4. Prometheus scrapes `node_exporter` and stores the time series
5. Grafana queries Prometheus

The key insight: **Ansible is the exporter**. The monitoring stack does not require any new protocols or additional device configuration. Everything it knows about the network it learned through the same Ansible modules used for pushing configs, running health checks, and detecting drift.

This has a tradeoff worth understanding: the metrics are only as fresh as the last Ansible run. If the cron job fails, Grafana shows stale data. There is a `MetricsStale` alert in `prometheus/alerts.yml` that fires if a node's metrics have not been updated in more than 10 minutes. The alert is a safety net: if the collection pipeline breaks, you know immediately.

---

## Exercise 29.1 — Deploy the Monitoring Stack {#ex291}

🟡 **Practitioner**

### Scenario

ACME's Network Operations team has been asked to provide a live dashboard for the Trading floor management ahead of a MiFID II compliance review. The reviewers want to see BGP session state for the TRADING VRF and confirmation that the Frankfurt region has no TRADING zone connectivity — both in real time, both with a timestamped audit trail. You are deploying the monitoring stack and populating it with the first metrics.

### Prerequisites

The lab must be running. If you have not already done so:

```bash
cd topology && containerlab deploy -t containerlab.yml
cd ..
ansible-playbook scenarios/common/reset_lab.yml
ansible-playbook scenarios/common/verify_lab_healthy.yml
```

### Step 1 — Start the monitoring stack

```bash
cd monitoring && docker compose up -d
```

Verify all four services are running:

```bash
docker compose ps
```

Expected output:

```
NAME                  IMAGE                         STATUS
acme-prometheus       prom/prometheus:v2.51.0       Up
acme-grafana          grafana/grafana:10.4.0         Up
acme-node-exporter    prom/node-exporter:v1.7.0     Up
acme-alertmanager     prom/alertmanager:v0.27.0     Up
```

If any service fails to start, check the logs:

```bash
docker compose logs prometheus
docker compose logs grafana
```

The most common failure at this point is that the `acme-mgmt` Docker network does not exist. This network is created by containerlab when the lab topology is deployed. If you see `network acme-mgmt not found`, run `cd topology && containerlab deploy -t containerlab.yml` first, then return here.

### Step 2 — Write the first metrics

Return to the lab root directory:

```bash
cd ..
```

Run the two metric-writing playbooks:

```bash
ansible-playbook playbooks/write_bgp_metrics.yml
ansible-playbook playbooks/interface_utilisation.yml
```

The first playbook writes `monitoring/prometheus/bgp_state.prom` and `monitoring/prometheus/health_state.prom`. The second writes `monitoring/prometheus/network_utilisation.prom`. These files are already in Prometheus text format.

Inspect what was written:

```bash
head -30 monitoring/prometheus/bgp_state.prom
```

You will see lines like:

```
# HELP acme_bgp_session_established BGP session state: 1=Established, 0=not Established
# TYPE acme_bgp_session_established gauge
acme_bgp_session_established{node="border-lon-01",peer="10.1.100.17",peer_asn="65001",peer_description="spine-lon-01",vrf="default",region="emea-lon"} 1
acme_bgp_session_established{node="border-lon-01",peer="10.0.1.1",peer_asn="65010",peer_description="border-nyc-01",vrf="default",region="emea-lon"} 1
...
```

Each line is one BGP session: the labels identify the context, the value (1 or 0) is the state. This is the raw data that Prometheus will store and Grafana will visualise.

### Step 3 — Verify Prometheus is scraping

Open Prometheus in your browser: **http://localhost:9090**

Navigate to **Status → Targets**. You should see:

| Job | Target | State |
|-----|--------|-------|
| `acme_network_textfile` | `node_exporter:9100` | UP |
| `prometheus` | `localhost:9090` | UP |
| `alertmanager` | `alertmanager:9093` | UP |

If `acme_network_textfile` shows as DOWN, check the node_exporter container:

```bash
docker logs acme-node-exporter
```

Navigate to **Graph** and run the following query to confirm the BGP metrics are visible:

```
acme_bgp_session_established
```

You should see a series per BGP peer with value `1` (Established). If you see no results, wait 30 seconds for Prometheus to complete its first scrape, then try again.

### Step 4 — Open the dashboards

Open Grafana: **http://localhost:3000**

Log in with:
- Username: `admin`
- Password: `acme-lab`

Navigate to **Dashboards → ACME Network**. You should see two dashboards:

- **ACME Network Overview** — BGP session state table, interface utilisation, drift and NTP summary
- **ACME TRADING Zone** — TRADING VRF session state, TRADING-zone interface utilisation, compliance annotations

Open **ACME Network Overview**. The BGP Session State table at the top shows every active BGP session across the lab. All values should be `UP` (green) with a healthy lab.

Open **ACME TRADING Zone**. The TRADING VRF BGP Sessions panel shows sessions in the `TRADING` VRF. The Compliance Status panel on the right filters to `fra-dc1` — it should be empty, because Frankfurt has no TRADING sessions. This emptiness is the assertion: if a row appeared here, it would mean the Frankfurt isolation constraint (INTENT-003) had been violated.

### Step 5 — Set up metric refresh

For the dashboards to stay current, the metric-writing playbooks need to run on a schedule. The simplest approach is a cron job on your local machine:

```bash
# Edit your crontab
crontab -e
```

Add the following entries (adjust the path):

```cron
# ACME lab metrics — refresh every 2 minutes
*/2 * * * * cd /path/to/network_automation_lab && ansible-playbook playbooks/write_bgp_metrics.yml >> /tmp/acme_metrics.log 2>&1
*/5 * * * * cd /path/to/network_automation_lab && ansible-playbook playbooks/interface_utilisation.yml >> /tmp/acme_metrics.log 2>&1
```

BGP state changes quickly (sessions can go up or down in seconds), so a 2-minute interval for `write_bgp_metrics.yml` is appropriate. Interface utilisation changes slowly, so 5 minutes is sufficient.

After setting up the cron job, verify it fires:

```bash
tail -f /tmp/acme_metrics.log
```

### What to Notice

- The `.prom` files in `monitoring/prometheus/` have a modification timestamp. When the cron job fires, these files are rewritten. `node_exporter` detects the change on the next scrape and serves the updated metrics to Prometheus.
- Prometheus stores each scrape as a data point in its time-series database. The retention period is set to 30 days in `docker-compose.yml`. After running the lab for a few hours, you can see historical trends in Grafana.
- The Prometheus console at http://localhost:9090/graph supports the full PromQL query language. The queries in the Grafana dashboards are valid PromQL — you can run them directly in Prometheus to debug or explore.

### Verify

```bash
ansible-playbook scenarios/ch09/ex91_verify.yml
```

The verify checks:
- All four Docker services are running
- `bgp_state.prom` exists and is non-empty
- Prometheus target `acme_network_textfile` is healthy
- Grafana API returns the two expected dashboards

---

**Next:** Chapter 30 walks through the dashboards in detail and introduces the TRADING Zone view as a compliance monitoring tool.
