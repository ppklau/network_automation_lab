---
title: "Chapter 26: Border Router RMA"
---

## Why Border Is Different

A leaf switch failure affects one segment of one DC. A border router failure affects everything.

`border-lon-01` carries:
- Three inter-region eBGP sessions — NYC, SIN, FRA
- Twelve UK branch eBGP sessions
- The LON aggregate route advertised to all WAN peers
- All inter-DC traffic between London and the rest of the ACME network

When `border-lon-01` fails, London DC1 loses connectivity to every other region. Branch offices in London, Birmingham, Manchester, and nine other UK cities lose connectivity to DC resources. The TRADING zone — which has the strictest latency requirements — is running on a single path (through whatever inter-region redundancy exists at the WAN level).

In ACME's lab topology, `border-lon-01` is the only active border router for the London site. In production, there would be a second border router (`border-lon-02`) providing redundancy. When ACME eventually build out the full topology, the RMA workflow would benefit from the redundancy — traffic would route via `border-lon-02` during the replacement window, making the outage invisible to applications.

In the lab, you are working without that redundancy. The exercise focuses on minimising the time-to-restore and ensuring the replacement is fully verified — not on traffic engineering around the outage.

## The Extra Phase: Graceful-Shutdown

`rma_border.yml` has one phase that `rma_leaf.yml` does not: Phase 3 applies BGP graceful-shutdown before the SoT update and config push.

This matters even without a redundant border. The graceful-shutdown community (`65535:0`) signals to all peers that `border-lon-01`'s routes should be deprioritised. In a dual-border topology, this causes traffic to shift cleanly to the peer border. In the lab single-border topology, it gives BGP a structured wind-down rather than an abrupt session drop — some peers handle an ordered session close more gracefully than a sudden TCP RST.

More importantly, applying graceful-shutdown before the SoT update establishes a clean operational boundary: first we drain the device, then we replace it. This sequencing is what makes the process safe to document as a formal change procedure. Regulators and change boards care about sequence.

The graceful-shutdown phase waits 90 seconds — longer than the 60 seconds in the leaf playbook — because the border has more sessions and more traffic to drain. The wait is configurable via `extra-vars` if your network requires a different window.

---

## Exercise 26.1 — Border Router RMA {#ex261}

🟡 **Practitioner**

### Scenario

At 03:15 UTC, ACME's NOC receives simultaneous alerts: LON-NYC, LON-SIN, and LON-FRA BGP sessions are all down. Three inter-region sessions dropping at exactly the same time points to `border-lon-01` — not to the WAN circuits (which would rarely fail simultaneously). The DC hands team confirms: `border-lon-01` has a hardware fault on its WAN NIC card (Ethernet3–5 affected). Power is still on — management is accessible — but the WAN interfaces are dead.

A replacement unit is racked and accessible on management. Your task is to execute the border RMA.

### Inject the Fault

```bash
ansible-playbook scenarios/part8/ex261_inject.yml
```

This shuts down `border-lon-01`'s WAN interfaces (Ethernet3, Ethernet4, Ethernet5), dropping the inter-region eBGP sessions. The SoT serial is also set to `FAIL000001` to simulate a stale record.

All twelve UK branch eBGP sessions will also drop — the branch sessions use Ethernet7 sub-interfaces, which remain up, but without the WAN sessions the branches have no path to other regions.

### Your Task

**Step 1 — Scope the outage.**

```bash
ansible-playbook playbooks/daily_health_check.yml
```

Read the CRITICAL section carefully. How many sessions are down? Which devices are affected? Can you determine from the health check output alone whether this is a WAN circuit failure or a device hardware failure?

> Hint: All three inter-region sessions dropping simultaneously points to the common factor — `border-lon-01`. Three independent WAN circuits failing at the same moment is statistically improbable. One device failing is routine.

**Step 2 — Confirm the failure type.**

A WAN circuit failure and a NIC card failure have different remediation paths. If the circuits were up but the BGP sessions were down, you would check BGP configuration (auth mismatch, timer mismatch). In this case, the interfaces themselves are down — which is hardware.

```bash
ansible -i inventory/hosts.yml border-lon-01 \
  -m arista.eos.eos_command \
  -a "commands=['show interfaces Ethernet3,Ethernet4,Ethernet5 status | json']"
```

All three will show `down`. This confirms hardware, not configuration.

**Step 3 — Update the SoT serial.**

Open `sot/devices/lon-dc1/border-lon-01.yml`. Change the `serial:` field to `ACE2501088B` (the replacement unit).

**Step 4 — Run the border RMA playbook.**

```bash
ansible-playbook playbooks/rma_border.yml \
  --limit border-lon-01 \
  --extra-vars "new_serial=ACE2501088B rma_reason='WAN NIC failure' confirmed=yes"
```

Watch the phases:
1. Pre-check confirms `border-lon-01` is a border router (not a leaf)
2. Confirmation gate (bypassed with `confirmed=yes`)
3. Graceful-shutdown applied and 90-second drain wait
4. SoT serial updated
5. Config regenerated and pushed
6. 120-second wait for BGP reconvergence (longer than leaf — more sessions)
7. Verification: all sessions Established, serial verified
8. Maintenance mode removed

**Step 5 — Verify.**

```bash
ansible-playbook scenarios/part8/ex261_verify.yml
```

Checks:
- SoT serial is not `FAIL000001`
- All BGP sessions on `border-lon-01` are Established
- WAN interfaces Ethernet3, Ethernet4, Ethernet5 are up

**Step 6 — Commit and notify.**

```bash
git add sot/devices/lon-dc1/border-lon-01.yml
git commit -m "RMA border-lon-01: WAN NIC failure, replacement serial ACE2501088B"
```

In production, you would also:
- Close the incident ticket with the restoration time
- File a post-incident review noting the failure mode
- Confirm with NYC, SIN, and FRA NOC teams that their sessions are restored

### What to Notice

**Reconvergence time is longer.** The border has 15 BGP sessions (2 iBGP to spines + 3 inter-region eBGP + 12 branch eBGP, though only 1 branch is active in the lab). The playbook waits up to 120 seconds with retries before declaring success. If you tried to verify immediately after the push, you would see sessions still in `OpenConfirm` or `Active` state.

**The graceful-shutdown community matters at scale.** In this lab, graceful-shutdown may appear to have no visible effect (because there is no redundant border to absorb the traffic). In production with `border-lon-02` present, all 15 sessions would smoothly drain before the RMA, and applications would see no interruption. This is the design justification for dual-border — it turns a hardware replacement from an outage into a maintenance event.

**Pre-checks prevent the wrong playbook.** If you accidentally ran `rma_leaf.yml` against `border-lon-01`, it would fail at Phase 1 with:
```
border-lon-01 has role 'border', not 'leaf'. Use rma_border.yml for border router replacements.
```
The role check is a safety gate against using the wrong playbook on the wrong device type.

---

## 🔵 The Dual-Border Design Argument {#dual-border}

🔵 **Strategic**

ACME's London DC currently has one active border router in the lab. In production, the design calls for two. This is not primarily about cost efficiency or throughput — it is about making hardware replacement a non-event rather than an outage.

The numbers:

- `border-lon-01` MTBF (mean time between failures) for a data-centre router: approximately 8–12 years
- Expected tenure of the London DC: 15+ years
- Probability of at least one border router hardware failure during the DC's lifetime: ~75%

That one hardware failure, without a redundant border, is a multi-hour outage affecting all inter-region traffic, all UK branches, and all TRADING and CORPORATE application connectivity. With a redundant border, it is a 10-minute planned maintenance event.

The cost of the second border router is amortised against the cost of a single MiFID II reportable outage — which includes regulatory notification overhead, potential fine risk, and reputational exposure with institutional clients.

The automation also changes the calculus for the redundant border. Without automation, operating a second border doubles the configuration management overhead. With SoT-driven deployment, the second border is derived from the same SoT as the first — configuration consistency is guaranteed by construction, not by discipline.

> **For managers in the room:** When someone asks why a second border router is in the budget, the answer is not "redundancy." The answer is: "It converts a 2-hour outage-causing RMA into a 10-minute non-event, and it reduces the senior engineering hours required for that RMA from 4 to 0."

---

## Debrief

**What was practised:** Replacing a border router — the same SoT-driven pattern as leaf RMA, but with higher blast radius because the border carries all inter-region and branch traffic.

**Why it matters:** A border router RMA without a redundant peer is a multi-hour outage. With a redundant peer, it is a 10-minute planned operation. The automation changes the ROI calculation for the second border: without it, a redundant border doubles config management overhead; with SoT-driven deployment, the second border is derived from the same SoT as the first.

**In production:** The business case for border redundancy is not "redundancy" in the abstract — it is the difference between an MiFID II reportable outage and a routine maintenance event. The automation makes the redundant border operationally free to maintain.

---

**Next:** Chapter 27 covers zero-touch provisioning for branch routers — deploying to a new office without touching the device manually.
