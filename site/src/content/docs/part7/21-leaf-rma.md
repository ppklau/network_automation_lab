---
title: "Chapter 21: Leaf Switch RMA"
---

## The First Call at 03:00

A leaf switch replacement at ACME typically follows the same arc. The monitoring system alerts on BGP session loss. The on-call engineer runs the health check. Two BGP sessions — both to the same device — are down. The problem is not a peering issue or a routing misconfiguration; both sessions dropped simultaneously, which points to the device itself. Either the device has lost power, lost management connectivity, or failed catastrophically.

The on-call engineer calls the DC hands team. The answer comes back: `leaf-lon-02` is showing amber fault LEDs. Power supply failure. A replacement unit is in the spares cabinet. It can be installed tonight.

At this point, the manual process begins a multi-hour clock. The automated process takes under 10 minutes.

## What `rma_leaf.yml` Does

The playbook has seven phases:

| Phase | What happens |
|---|---|
| 1 — Pre-checks | Verify target is a leaf, SoT file exists, reason documented |
| 2 — Confirmation gate | Human confirmation before any change (bypassed with `confirmed=yes`) |
| 3 — SoT update | Serial number updated in `sot/devices/<site>/<hostname>.yml` |
| 4 — Config generation | `render_configs.yml` runs against updated SoT |
| 5 — Config push | Full config pushed to replacement via NAPALM replace |
| 6 — Verification | BGP sessions checked (retries for 60s); serial verified against device |
| 7 — Artefact record | RMA record written to `state/rma/<hostname>_<timestamp>.yml` |

The replacement device needs to be:
- Physically installed with identical cabling
- Running the correct cEOS image
- Accessible on its management IP (assigned from the OOB network)

That's it. The playbook handles the rest.

### The Serial Number Is the Only Input

This is worth stating explicitly. The only thing you need to know about the replacement device is its serial number — which is printed on the box and on a label on the device itself. You do not need to know:

- Which VLANs the device carries (the SoT knows)
- What BGP peers it has (the SoT knows)
- What VRRP priority it holds (the SoT knows)
- What VRFs are configured (the SoT knows)

The full config is derived from the SoT. The serial number is the only fact about the *physical* device that isn't already in the SoT.

---

## Exercise 10.1 — Leaf RMA (Like-for-Like) {#ex101}

🟡 **Practitioner**

### Scenario

ACME's trading floor in London DC1 reported intermittent connectivity to CORPORATE servers at 07:42. NOC identified `leaf-lon-02` as the source — both fabric uplinks are down. A replacement unit (same model, new serial `ACE2501099X`) has been installed in the rack with identical cabling. It is accessible on management. Your task is to drive the replacement through the pipeline.

### Inject the Fault

```bash
ansible-playbook scenarios/ch08/ex101_inject.yml
```

This shuts down `leaf-lon-02`'s fabric uplinks (Ethernet1 and Ethernet2) to simulate a powered-off device, and overwrites the serial number in the SoT with `FAIL000000` to simulate a stale record.

You will not be told which BGP sessions are affected.

### Your Task

**Step 1 — Identify the fault.**

```bash
ansible-playbook playbooks/daily_health_check.yml
```

Look at the CRITICAL section. Which device is affected? Which sessions are down? What does the peer state tell you about whether this is a reachability issue or a hardware failure?

**Step 2 — Confirm the scope.**

A leaf switch has two fabric uplinks — one to each spine. If both sessions are down simultaneously, the device is offline, not misconfigured. If only one session is down, the uplink to a single spine has failed.

In this case, both sessions to `leaf-lon-02` will be down. That tells you: the device, not the peering.

**Step 3 — Update the SoT serial.**

Open `sot/devices/lon-dc1/leaf-lon-02.yml`. Find the `serial:` field. Change it to `ACE2501099X` (the new unit's serial).

This is the one human decision in the process. You are declaring: "I have confirmed that `ACE2501099X` is the physically installed replacement."

**Step 4 — Run the RMA playbook.**

```bash
ansible-playbook playbooks/rma_leaf.yml \
  --limit leaf-lon-02 \
  --extra-vars "new_serial=ACE2501099X rma_reason='PSU failure' confirmed=yes"
```

Watch the output. The playbook will:
1. Verify the target and reason
2. Read and update the SoT
3. Regenerate the inventory
4. Render the config from SoT
5. Push to the replacement device
6. Wait for BGP to re-establish (with retries)
7. Verify the serial number matches `ACE2501099X`
8. Write the artefact record

**Step 5 — Verify.**

```bash
ansible-playbook scenarios/ch08/ex101_verify.yml
```

The verify checks:
- SoT serial is not `FAIL000000`
- BGP sessions to both spines are Established
- Fabric interfaces Ethernet1 and Ethernet2 are up

**Step 6 — Commit the SoT change.**

```bash
git add sot/devices/lon-dc1/leaf-lon-02.yml
git commit -m "RMA leaf-lon-02: PSU failure, replacement serial ACE2501099X"
```

This is the change record. The commit message, the SoT diff, and the `state/rma/leaf-lon-02_<timestamp>.yml` artefact together constitute the full audit trail.

### What to Notice

- The playbook verifies the serial number against the device at the end. If you put the wrong serial in the SoT, the verify step fails — immediately surfacing the discrepancy before it becomes a silent mismatch.
- VRRP for CORPORATE VLAN 200 will have failed over to `leaf-lon-01` during the outage. After the RMA, VRRP will fail back (preempt delay is 60 seconds). You can observe this by watching `show vrrp` on `leaf-lon-01` and `leaf-lon-02` after the RMA completes.
- The `rma_reason` is mandatory. This enforces documentation at the point of action — you cannot run the playbook without providing a reason. This feeds the `state/rma/` artefact and, in production, would populate the ITSM ticket automatically.

---

## Exercise 10.2 — Leaf Replacement with Different Model {#ex102}

🟡 **Practitioner** / 🔴 **Deep Dive**

### Scenario

The preferred replacement unit (DCS-7050TX3-48C8) is out of stock. The vendor has offered a DCS-7050CX3-32S as a temporary substitute. The interface naming convention is identical in this case, but the supported speeds differ: the replacement supports 100G on all 32 ports, whereas the failed unit had 10G server access ports (Ethernet3–6).

Your task is to update the SoT to reflect the model change, verify that the Jinja2 templates handle the model difference gracefully, and complete the RMA.

### Your Task

**Step 1 — Identify the field difference.**

In `sot/devices/lon-dc1/leaf-lon-02.yml`, the `hardware_model` is currently `DCS-7050TX3-48C8`. The replacement is `DCS-7050CX3-32S`.

Run `rma_leaf.yml` with both `new_serial` and `new_model`:

```bash
ansible-playbook playbooks/rma_leaf.yml \
  --limit leaf-lon-02 \
  --extra-vars "new_serial=ACE2501099X new_model=DCS-7050CX3-32S rma_reason='Model substitution — DCS-7050TX3 OOS' confirmed=yes"
```

**Step 2 — Inspect the rendered config.**

Before the push, look at what the template generated for the server access ports:

```bash
cat configs/leaf-lon-02/running.conf | grep -A 5 'Ethernet3'
```

Does the 10G speed flag appear? What does your Jinja2 template do with the `speed` field from the SoT? If the template simply passes through the SoT value, the rendered config will try to set `speed 10G` on a port that only supports 100G — and the push will fail or silently ignore the command.

**Step 3 — Consider the template handling.**

Open `templates/arista_eos/interfaces.j2`. How does the template handle the `speed` field? Is there a guard for speed mismatches? If not, what would you add?

This is the key teaching point of Exercise 10.2: the automation is only as good as the SoT. A model substitution requires a conscious decision about which SoT fields need updating alongside the serial number, and it requires the templates to handle edge cases gracefully.

> **Design question:** Should the Jinja2 template silently omit the speed command if the model in the SoT doesn't match the hardware? Or should it fail loudly? The argument for failing loudly: you would rather discover the mismatch during the lab push than after deploying to production. A silent omission might mean 10G SFPs inserted into 100G ports — which would also fail, but with a less informative error.

---

## The Impact on VRRP

During a leaf failure and replacement, VRRP behaviour is worth understanding precisely.

`leaf-lon-02` is configured as:
- **Active** gateway for CORPORATE VLAN 200 (priority 110)
- **Standby** gateway for TRADING VLAN 100 (priority 90)

When `leaf-lon-02` goes offline, VRRP transitions for CORPORATE to `leaf-lon-01` (which is standby, priority 90 for CORPORATE). Traffic continues to flow — VRRP provides sub-second failover for the servers.

When `leaf-lon-02` comes back up after the RMA, its VRRP priority for CORPORATE is again 110 (higher than `leaf-lon-01`'s 90). With `preempt: true` and `preempt_delay_seconds: 60` in the SoT, `leaf-lon-02` will wait 60 seconds after its uplinks come up before reclaiming the active role. This delay is deliberate — it allows BGP to fully reconverge before VRRP traffic shifts, preventing a brief black-hole during the transition.

You can observe this in the lab:

```bash
# Watch VRRP state on leaf-lon-01 (while leaf-lon-02 is being restored)
ansible -i inventory/hosts.yml leaf-lon-01 \
  -m arista.eos.eos_command \
  -a "commands=['show vrrp brief']"
```

After the RMA push, wait 60 seconds and run it again. The VRRP role for VLAN 200 will have moved back to `leaf-lon-02`.

---

**Next:** Chapter 22 covers border router RMA — the same pattern with higher stakes.
