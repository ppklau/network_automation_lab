---
title: "Chapter 17: BGP Prefix Monitoring"
---

## What Health Checks Miss

A BGP session status check answers a binary question: is the session established? The answer is either yes or no.

But the most dangerous BGP problems are not session failures. They are prefix problems — situations where the session is fully established and both peers report it as healthy, but the routing table is wrong.

Consider what happens when a route-map on `border-lon-01` is modified out-of-band to suppress a `permit` statement. The BGP session to `border-nyc-01` stays up. Both peers show `Established`. The daily health check shows green. But `branch-lon-01`'s prefix (`10.100.0.0/29`) is no longer being advertised to New York. Any transatlantic traffic destined for the London branch is now black-holing silently.

This is exactly Exercise 8.4 — and it would not be detected by session monitoring alone.

Prefix monitoring adds a second dimension: not just "is the session up?" but "is the right number of routes being exchanged?"

---

## Prefix Baselines

`sot/bgp/prefix_baselines.yml` defines expected prefix counts for every BGP peer relationship in the network:

```yaml
# sot/bgp/prefix_baselines.yml
prefix_baselines:

  - node: border-lon-01
    peer_ip: 10.0.1.1
    peer_asn: 65200
    peer_description: "border-nyc-01 InterDC"
    expected_prefixes: 3
    tolerance: 1

  - node: border-lon-01
    peer_ip: 10.100.0.1
    peer_asn: 65100
    peer_description: "branch-lon-01"
    expected_prefixes: 1
    tolerance: 0

  - node: border-fra-01
    peer_ip: 10.0.2.1
    peer_asn: 65300
    peer_description: "border-lon-01 InterDC"
    expected_prefixes: 2
    tolerance: 0
    compliance_note: >
      INTENT-003: Frankfurt must not receive TRADING zone prefixes.
      Expected count of 2 reflects CORPORATE-only prefix advertisement.
      Any value > 2 is an INTENT-003 violation — alert immediately.
```

The `tolerance` field handles natural variation. A peer that normally advertises 3 prefixes but occasionally advertises 2 (e.g., during a route withdrawal and re-advertisement cycle) should not generate a false alert. A tolerance of 1 means: alert if the count is outside the range `[expected - tolerance, expected + tolerance]`.

A tolerance of 0 means: alert on any deviation. This is appropriate for peers where the prefix count is invariant — a branch peer that always advertises exactly one prefix.

### The Frankfurt Compliance Note

The `border-fra-01` baseline has a `compliance_note`. This is not enforced by the playbook; it is documentation for the human reading the alert.

If Frankfurt starts receiving 3 prefixes instead of 2, the compliance note explains the regulatory significance: it means a TRADING zone prefix has leaked into Frankfurt, violating INTENT-003 (zone isolation). This should trigger an immediate investigation, not a routine ticket.

🔵 **Strategic: Baselines are intent, not thresholds**

Traditional network monitoring uses thresholds: alert if BGP peer count drops below 90% of normal. This is statistical — it tells you something is different from usual but not whether that difference is acceptable.

Baselines in a SoT-driven network are intent: "this peer should receive exactly this many prefixes, because that is what the routing policy is designed to produce." A deviation is not "below threshold" — it is a violation of design intent. The distinction matters for regulatory reporting: you are not saying "traffic patterns changed," you are saying "the network is not behaving as designed."

---

## BGP Prefix Monitor

`playbooks/bgp_prefix_monitor.yml` checks every peer in `sot/bgp/prefix_baselines.yml` and compares the live prefix count against the baseline.

### Running the Monitor

```bash
# Check all baselines
ansible-playbook playbooks/bgp_prefix_monitor.yml

# Check a specific node
ansible-playbook playbooks/bgp_prefix_monitor.yml --limit border-lon-01

# Output Prometheus metrics
ansible-playbook playbooks/bgp_prefix_monitor.yml -e output_prometheus=true
```

### Reading the Output

A clean run:

```
ACME BGP Prefix Monitor — 2026-04-03T08:05:00Z
===============================================
Status: OK — all baselines within tolerance

border-lon-01:
  10.0.1.1  (border-nyc-01 InterDC)   expected=3 actual=3  OK
  10.100.0.1 (branch-lon-01)           expected=1 actual=1  OK
  10.200.0.1 (border-fra-01 InterDC)   expected=2 actual=2  OK

border-nyc-01:
  10.0.1.0  (border-lon-01 InterDC)   expected=3 actual=3  OK
  [...]
```

An alert run fails the play:

```
ACME BGP Prefix Monitor — 2026-04-03T08:05:00Z
===============================================
Status: ALERT — 1 baseline violation

border-lon-01:
  10.100.0.1 (branch-lon-01)
    ALERT: expected=1 actual=0 (outside tolerance=0)
    Action: Check route-map RM_INTERDC_OUT on border-lon-01
            Verify branch-lon-01 is advertising 10.100.0.0/29
```

---

## Exercise 8.4 — Route-Map Suppressing Branch Prefix {#ex84}

🟡 **Practitioner**

### Scenario

A vendor engineer was given temporary access to `border-lon-01` to test a new carrier Ethernet service. During testing, they added a route-map entry to suppress the branch prefix temporarily. They forgot to remove it. BGP sessions are all Established. Health check shows green. But transatlantic traffic to the London branch is black-holing.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex84_inject.yml
```

This adds a route-map `RM_INTERDC_SUMMARISE deny 5` entry on `border-lon-01` with a prefix-list that blocks `10.100.0.0/29` from being advertised to the WAN peers.

### Your Task

1. **Run the health check first** — confirm it shows green (session Established):

   ```bash
   ansible-playbook playbooks/daily_health_check.yml --limit border-lon-01
   ```

2. **Run the prefix monitor** — this should detect the violation:

   ```bash
   ansible-playbook playbooks/bgp_prefix_monitor.yml --limit border-lon-01
   ```

   The `branch-lon-01` peer entry should show `actual=0` against `expected=1`.

3. **Verify from the receiving end** — on `border-nyc-01` (FRR), check the BGP table:

   ```bash
   ansible -i inventory/hosts.yml border-nyc-01 \
     -m ansible.builtin.raw \
     -a "vtysh -c 'show bgp ipv4 unicast 10.100.0.0/29'"
   ```

   The prefix should be absent from the routing table.

4. **Run drift detection** on border-lon-01 to see the OOB route-map change:

   ```bash
   ansible-playbook playbooks/drift_detection.yml --limit border-lon-01
   ```

   The route-map deny entry will appear as a CRITICAL drift line.

5. **Remediate** with push_config:

   ```bash
   ansible-playbook playbooks/push_config.yml --limit border-lon-01
   ```

6. **Verify:**

   ```bash
   ansible-playbook scenarios/ch07/ex84_verify.yml
   ```

### What to Notice

- The health check (session state) and the prefix monitor (prefix count) tell different stories. Always run both.
- The drift report and the prefix alert both point to the same root cause, but from different angles: drift says "route-map was changed," the prefix alert says "branch prefix is gone." In a real incident, you might discover the prefix alert first and then use drift detection to find the cause.
- `border-nyc-01` is the FRR node checking the routes. The `ex84_verify.yml` runs a Python script on `border-nyc-01` to verify the prefix has returned — this is cross-platform verification.

> **Extension exercise:** Modify `sot/bgp/prefix_baselines.yml` to add a tolerance of 1 for the `branch-lon-01` peer. Run the inject again. Does the monitor still alert? Why or why not?

---

## Prometheus Integration

When run with `-e output_prometheus=true`, the prefix monitor writes metrics to `monitoring/prometheus/network_bgp.prom`:

```
# HELP acme_bgp_prefix_count Current BGP prefix count per peer
# TYPE acme_bgp_prefix_count gauge
acme_bgp_prefix_count{node="border-lon-01",peer="10.0.1.1",peer_desc="border-nyc-01 InterDC"} 3
acme_bgp_prefix_count{node="border-lon-01",peer="10.100.0.1",peer_desc="branch-lon-01"} 1

# HELP acme_bgp_prefix_baseline Expected BGP prefix count per peer
# TYPE acme_bgp_prefix_baseline gauge
acme_bgp_prefix_baseline{node="border-lon-01",peer="10.0.1.1"} 3
acme_bgp_prefix_baseline{node="border-lon-01",peer="10.100.0.1"} 1

# HELP acme_bgp_baseline_ok Whether prefix count is within tolerance (1=OK, 0=ALERT)
# TYPE acme_bgp_baseline_ok gauge
acme_bgp_baseline_ok{node="border-lon-01",peer="10.0.1.1"} 1
acme_bgp_baseline_ok{node="border-lon-01",peer="10.100.0.1"} 1
```

The `acme_bgp_baseline_ok` metric is designed for Grafana alerting: a value of 0 means alert, 1 means OK. You will connect this to a Grafana dashboard in Part 7.

---

## Interface Utilisation

`playbooks/interface_utilisation.yml` collects bandwidth utilisation and error rates from all interfaces and produces both a human-readable report and Prometheus metrics.

The playbook takes two samples 60 seconds apart and computes bit rate from the delta in octet counters. The threshold for alerting defaults to 80%:

```bash
# Use default 80% threshold
ansible-playbook playbooks/interface_utilisation.yml

# Use custom threshold
ansible-playbook playbooks/interface_utilisation.yml -e utilisation_threshold=70

# Single node
ansible-playbook playbooks/interface_utilisation.yml --limit spine-lon-01
```

The Prometheus output at `monitoring/prometheus/network_utilisation.prom` uses the `acme_interface_utilisation_percent` and `acme_interface_errors_total` metrics that you will visualise in Part 7.

> **Note on FRR:** EOS provides native JSON output for interface statistics. FRR would require SNMP or a Prometheus `node_exporter` on the container for equivalent data. In the lab, utilisation monitoring is EOS-only; the FRR nodes are noted in the playbook as `# FRR: requires node_exporter`.

---

**Next:** Chapter 18 covers maintenance windows — how to take a device out of service safely, track the maintenance state, and exit cleanly.
