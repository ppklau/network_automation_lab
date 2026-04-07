---
title: "Chapter 26: Dashboards"
---

# Chapter 26: Dashboards

## Two Audiences, Two Dashboards

ACME has two Grafana dashboards. The distinction between them is not aesthetic — it maps to two different reasons for looking at the monitoring system.

**Network Overview** is an operational tool. The NOC engineer uses it to check network health at a glance. The BGP session table at the top tells them, in one view, whether any session is down anywhere in the lab. The interface utilisation panels tell them whether any link is approaching capacity. The drift counter tells them whether any device has diverged from its expected config. An engineer on a 07:00 shift can do their morning check in under a minute.

**TRADING Zone** is a compliance tool. A compliance officer, or a MiFID II reviewer, uses it to answer a specific question: is the TRADING zone operating as designed? This means: are TRADING VRF sessions up on the devices that should have them, and absent on Frankfurt (which must not)? Are the TRADING-facing interfaces showing utilisation patterns consistent with normal operation? Is there any drift on the devices that enforce zone separation?

The two dashboards answer different questions. They are both built from the same underlying metrics — the same `acme_bgp_session_established` gauge, the same `acme_interface_utilisation_percent` gauge. The difference is filtering and framing.

---

## Exercise 9.2 — The TRADING Zone as a Compliance Artefact {#ex92}

🟡 **Practitioner** / 🔵 **Strategic**

### Scenario

The MiFID II compliance review is next Tuesday. The compliance team has asked for evidence that the TRADING zone isolation controls are operating. Specifically, they want:

1. Confirmation that Frankfurt (`fra-dc1`) has no TRADING zone BGP sessions — now and historically
2. Confirmation that TRADING VRF sessions on London DC1 are continuously established
3. A record of any BGP state changes in the TRADING VRF in the last 30 days, with timestamps

Your task is to use the TRADING Zone dashboard to produce this evidence, then simulate a compliance breach and observe how the monitoring stack surfaces it.

### Part A — The Baseline View

Open **ACME TRADING Zone** in Grafana. Set the time range to `Last 7 days`.

**Panel: TRADING VRF BGP Sessions**

This shows the current state of every BGP session in the `TRADING` VRF. In a healthy lab, all sessions will show `UP` (green).

Look at the label values. The `node` label identifies which device holds the session; `peer_description` describes the other end. In a functioning ACME network, TRADING VRF sessions exist on the London leaf switches (`leaf-lon-03`, `leaf-lon-04`) that connect to the firewall (`fw-lon-01`) which enforces zone separation.

**Panel: TRADING Zone — Compliance Status**

This panel filters the BGP session data to show only rows where `region = fra-dc1`. In a correctly configured lab, this panel is empty. This is the assertion: Frankfurt has no TRADING zone BGP sessions.

This emptiness is meaningful. It is not a missing panel or a data collection problem — `acme_bgp_session_established` data exists for Frankfurt devices, but none of it has `vrf="TRADING"`. The filter returns zero rows because the data says zero.

If this panel showed a row, you would have a compliance event: the Frankfurt isolation constraint (INTENT-003) has been violated. The monitoring stack would have caught it before the manual compliance review did.

**Panel: TRADING Zone Interface Utilisation**

This shows interface utilisation on the leaf and firewall devices that carry TRADING traffic. In a lab without active traffic generation, utilisation will be near zero. In production, you would see the signature of trading system activity — typically spiky patterns correlated with market open/close times.

The annotations on this panel are important. When the `write_bgp_metrics.yml` playbook detects a BGP state change, it writes an annotation to Prometheus which Grafana renders as a vertical marker on time-series panels. Orange markers are drift events; red markers are BGP state changes.

A BGP state change annotation that appears without a preceding pipeline push annotation is an unplanned event. A state change that follows a pipeline push by a few seconds is expected behaviour — the config push caused a BGP session reset, and recovery happened as designed.

### Part B — Inject the Compliance Breach

This exercise has no inject playbook. You will make the change directly.

Open `sot/devices/fra-dc1/border-fra-01.yml` and add the following to the BGP stanza:

```yaml
bgp:
  # ... existing config ...
  vrfs:
    TRADING:
      description: "TRADING VRF — added in error"
      rd: "65030:100"
      neighbors: []
```

This adds a TRADING VRF definition to the Frankfurt border router SoT. Run the metrics playbook:

```bash
ansible-playbook playbooks/write_bgp_metrics.yml
```

Now open the **TRADING Zone — Compliance Status** panel. The Frankfurt TRADING VRF will not show a live session (no BGP peer is configured), but the SoT now contains the prohibited zone. This is the gap the monitoring stack does not cover on its own — it monitors device state, not SoT state.

**What catches this gap?**

Run the Batfish compliance check:

```bash
cd batfish && pytest tests/test_frankfurt_isolation.py -v
```

The test `test_no_fra_trading_vrf` will fail, because the SoT now contains a TRADING VRF for Frankfurt. This is the correct behaviour — the pipeline blocks the config push before it reaches the device. The monitoring stack sees live device state; Batfish sees SoT intent. Together, they provide defence in depth.

Revert the change:

```bash
git checkout sot/devices/fra-dc1/border-fra-01.yml
```

### Part C — The Historical View as an Audit Artefact

Set the Grafana time range to cover the last hour. Observe the **BGP Session History** panel at the bottom of the TRADING Zone dashboard.

This time-series graph shows session state (UP/DOWN) over time for all TRADING VRF peers. In a healthy lab with metric refresh running, this graph should show a flat green line since the monitoring stack started.

**Exporting for compliance review:**

Grafana dashboards can be exported as PNG reports using the `grafana-image-renderer` plugin or the built-in panel download. For the lab, use the browser:

1. Navigate to the BGP Session History panel
2. Click the panel title → **Inspect → Data**
3. Download as CSV

The CSV contains timestamps and session state values that can be included in a compliance artefact. In production, Grafana Enterprise provides scheduled PDF report generation — the same dashboards can be emailed to compliance teams weekly without manual intervention.

### 🔵 What This Proves

The TRADING Zone dashboard produces three artefacts that a compliance reviewer needs:

1. **Current state** — TRADING VRF sessions are established; Frankfurt has none (panel screenshot)
2. **Historical record** — no unplanned BGP state changes in the review period (session history CSV)
3. **Drift status** — no config drift on zone-enforcing devices (drift counter = 0)

These are not retrospective claims assembled after the fact. They are the output of a monitoring system that runs continuously and retains 30 days of history. The compliance evidence is a by-product of the operations tooling — not a separate exercise.

This is the financial services angle that makes this more than a technical monitoring story. MiFID II Article 17 requires firms to have in place "effective systems and risk controls" for their trading systems. A monitoring stack that provides timestamped, continuous evidence of zone isolation is a stronger compliance artefact than a quarterly manual review.

> **Key question for strategic readers:** Your firm almost certainly has some form of network monitoring today. The question is whether the monitoring system produces evidence that maps directly to your regulatory obligations — or whether compliance evidence is assembled separately, from multiple systems, after the fact. The ACME monitoring stack shows that these two things can be the same system.

---

## Exercise 9.2b — Correlating a BGP Drop to a Config Push {#ex92b}

🟡 **Practitioner**

This short exercise demonstrates the value of annotations — the markers on time-series graphs that show when pipeline pushes occurred.

Make a deliberate, trivial config change to a device that affects a BGP session:

```bash
# Inject a brief BGP session disruption by toggling maintenance mode on border-lon-01
ansible-playbook playbooks/maintenance_window.yml \
  --limit border-lon-01 \
  --extra-vars "duration_minutes=1 reason='Exercise 9.2b - correlation test'"
```

While maintenance mode is active, run the metrics playbook:

```bash
ansible-playbook playbooks/write_bgp_metrics.yml
```

Open the **Network Overview** dashboard. Look at the BGP session table. The border-lon-01 sessions will show DOWN. On the TRADING Zone dashboard, look at the session history panel — you will see a state change annotation at the time the maintenance mode was applied.

Exit maintenance mode:

```bash
ansible-playbook playbooks/maintenance_window.yml \
  --limit border-lon-01 \
  --extra-vars "duration_minutes=0 exit_maintenance=true"
```

Run the metrics playbook again. The sessions will recover. On the session history graph, you now have a complete picture: DOWN at T₁ (maintenance entered), UP again at T₂ (maintenance exited), with the duration (T₂ - T₁) visible.

**Why this matters:** If this event had been unplanned, the monitoring graph would look identical — a session drop at T₁, recovery at T₂. The difference is whether there is a pipeline annotation (planned) or not (unplanned). In a production environment, the pipeline annotation comes from the GitLab CI commit message. An unplanned event with no annotation is the signal that something unexpected happened, and it warrants investigation.

---

**Next:** Chapter 27 builds the alerting layer — turning these dashboard observations into automated notifications.
