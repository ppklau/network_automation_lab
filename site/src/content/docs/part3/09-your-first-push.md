---
title: "Chapter 9: Your First Config Push"
---

> 🟡 **Practitioner** — Exercise 9.1

*Estimated time: 25 minutes*

---

## Scenario

It is your first week at ACME. Your manager has asked you to add a description to `Ethernet3` on `leaf-lon-01`. "Use the pipeline," they said. "No direct SSH."

This is the smallest possible change. That is deliberate. The goal is to experience the full loop — SoT edit → render → push → verify — on a change where nothing can go seriously wrong. Every subsequent exercise assumes you have done this.

---

## Before you start

Reset the lab to a known-good state:

```bash
ansible-playbook scenarios/common/reset_lab.yml
ansible-playbook scenarios/common/verify_lab_healthy.yml
```

Both playbooks should complete with no failures. If `verify_lab_healthy.yml` reports issues, check the lab setup (Chapter 2) before continuing.

---

## Step 1 — Make the SoT change

Open `sot/devices/lon-dc1/leaf-lon-01.yml` and find the `Ethernet3` interface. It currently has:

```yaml
  - name: Ethernet3
    ip: 10.1.100.5/31
    peer: spine-lon-02
    peer_interface: Ethernet3
```

Add a description:

```yaml
  - name: Ethernet3
    description: "P2P to spine-lon-02 Ethernet3 — iBGP underlay"
    ip: 10.1.100.5/31
    peer: spine-lon-02
    peer_interface: Ethernet3
```

Save the file.

---

## Step 2 — Validate the SoT

```bash
python3 scripts/validate_sot.py
yamllint sot/devices/lon-dc1/leaf-lon-01.yml
```

Both should pass. A description change cannot introduce a schema error — but running validation is a habit worth building.

---

## Step 3 — Render the config

```bash
ansible-playbook playbooks/render_configs.yml --limit leaf-lon-01
```

The playbook generates `configs/leaf-lon-01/running.conf`. Check what changed:

```bash
git diff configs/leaf-lon-01/running.conf
```

You should see something like:

```diff
-interface Ethernet3
-   no switchport
-   ip address 10.1.100.5/31
+interface Ethernet3
+   description P2P to spine-lon-02 Ethernet3 — iBGP underlay
+   no switchport
+   ip address 10.1.100.5/31
```

One line added. Everything else unchanged. This is the diff that would appear in the pipeline's `diff` stage for a reviewer to approve.

---

## Step 4 — Push the config

```bash
ansible-playbook playbooks/push_configs.yml --limit leaf-lon-01
```

**What happens during the push:**

1. `pre_tasks` — collects the current running config and BGP summary, stores in `state/`
2. Main task — `napalm_install_config` connects to leaf-lon-01, applies the rendered config atomically
3. A diff of the change is written to `state/diff_<timestamp>.txt`
4. `post_tasks` — collects the post-push BGP summary, stores alongside the pre-push snapshot

**Expected output:**

```
PLAY [Push rendered configs to active devices] ****

TASK [Collect pre-push state] ****
ok: [leaf-lon-01]

TASK [Push config via NAPALM (EOS)] ****
changed: [leaf-lon-01]

TASK [Collect post-push state] ****
ok: [leaf-lon-01]

PLAY RECAP ****
leaf-lon-01: ok=3  changed=1  unreachable=0  failed=0
```

---

## Step 5 — Verify the change

```bash
ansible-playbook playbooks/verify_state.yml --limit leaf-lon-01
```

This runs the post-push verification suite:
- BGP neighbors: all sessions should still be Established
- Interface status: Ethernet3 should still be up
- Management reachability: the node should still respond to pings

**Then verify on the device itself:**

```bash
ssh admin@172.20.20.21
leaf-lon-01# show interface Ethernet3
```

```
Ethernet3 is up, line protocol is up (connected)
  Description: P2P to spine-lon-02 Ethernet3 — iBGP underlay
  Hardware is Ethernet, address is ...
```

The description is there.

---

## Step 6 — Review the audit artefact

```bash
cat state/diff_*.txt | head -30
```

This file contains the exact diff that was applied to the device: the before state, the after state, and the changeset. In a production pipeline, this file is attached to the GitLab pipeline run as a release artefact. It is the audit trail for this change.

```bash
ls state/
```

You should see:
- `pre_push_leaf-lon-01_<timestamp>.json` — BGP summary before the push
- `post_push_leaf-lon-01_<timestamp>.json` — BGP summary after the push
- `diff_<timestamp>.txt` — the config diff
- `push_record_<timestamp>.yml` — who ran the push, when, against which snapshot

---

## What just happened

> 🔵 **Strategic**

You made a change that:
- Went through schema validation before anything was rendered
- Was rendered from a single source of truth, not hand-typed
- Produced a reviewable diff before being applied to any device
- Was applied atomically — the device either got the full new config or kept the old one
- Was verified programmatically after the push
- Produced an audit artefact that records exactly what changed

A description change is a trivial example. The same process applies when a BGP policy changes, when a new VLAN is added, or when a compliance-relevant interface configuration is modified. The pipeline does not distinguish between trivial and important. That consistency is the compliance guarantee.

---

## Exercise 9.1 — Your second push {#ex91}

> 🟡 **Practitioner**

Now do it without the step-by-step guidance. Make a slightly more complex change:

Add a new loopback interface to `leaf-lon-02`:

```yaml
  - name: Loopback1
    description: "Secondary loopback — SNMP source"
    ip: 10.1.255.112/32
```

Use the standard flow: validate → render → diff (inspect it) → push → verify.

**Verify:** Run `ansible-playbook playbooks/verify_state.yml --limit leaf-lon-02`. All tasks should pass.

**Additional check:** SSH to leaf-lon-02 and confirm the interface exists with the correct IP.

**Debrief:** A loopback addition is safe — it does not affect traffic flow and BGP sessions will not be disrupted. The risk surface of a change is a function of what it touches, not how many lines change. Your pipeline treats a loopback addition and a BGP policy change with the same validation rigour, because the pipeline does not know which changes matter and which do not. That is a feature.

*Handbook reference: Chapter 6 (The config push workflow), Chapter 5 (Atomic changes and rollback)*
