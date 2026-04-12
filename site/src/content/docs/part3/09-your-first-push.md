---
title: "Chapter 9: Your First Config Push"
---

> 🟡 **Practitioner** — Exercise 9.1

*Estimated time: 35 minutes (pipeline runs add a few minutes to each step)*

---

## Scenario

It is your first week at ACME. Your manager has asked you to add a description to `Ethernet3` on `leaf-lon-01`. "Use the pipeline," they said. "No direct SSH."

This is the smallest possible change. That is deliberate. The goal is to experience the full loop — SoT edit → MR pipeline (validate, render, diff) → peer review → merge → main pipeline (push, verify) — on a change where nothing can go seriously wrong. Every subsequent exercise assumes you have done this.

---

## Before you start

Check that GitLab and the lab are healthy:

```bash
curl -sf http://localhost:8929/-/health && echo "GitLab is up" || echo "Start GitLab: docker compose -f docker-compose.gitlab.yml -p acme-gitlab up -d"
ansible-playbook scenarios/common/reset_lab.yml
ansible-playbook scenarios/common/verify_lab_healthy.yml
```

Both playbooks should complete with no failures. If `verify_lab_healthy.yml` reports issues, check the lab setup (Chapter 2, Step 9) before continuing. GitLab CE must be reachable at `http://localhost:8929` throughout this chapter.

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

## Step 2 — Validate locally

Before committing, run a quick local sanity check:

```bash
python3 scripts/validate_sot.py
yamllint sot/devices/lon-dc1/leaf-lon-01.yml
```

Both should pass cleanly. A description addition cannot introduce a schema error, but the habit matters: catching a YAML syntax mistake locally is far cheaper than waiting for a CI pipeline to tell you the same thing two minutes later.

> 🟡 **Practitioner**
>
> Local validation is not a substitute for the pipeline — it is a fast pre-check. The pipeline runs the same validators plus Batfish intent checks and a full config render that your local environment cannot replicate. Think of local validation as catching your typos before you push, not as gatekeeping your change.

---

## Step 3 — Commit and push to a feature branch

```bash
git checkout -b feat/leaf-lon-01-eth3-description
git add sot/devices/lon-dc1/leaf-lon-01.yml
git commit -m "Add description to leaf-lon-01 Ethernet3"
git push lab feat/leaf-lon-01-eth3-description
```

The remote is named `lab` and points to `http://localhost:8929/acme/network-automation-lab`. After the push, GitLab knows about the branch but has not yet run anything — that happens when you open a Merge Request.

---

## Step 4 — Open a Merge Request

1. Open your browser and go to `http://localhost:8929/acme/network-automation-lab`
2. GitLab will show a yellow banner at the top of the page: **"You pushed to `feat/leaf-lon-01-eth3-description` — Create merge request"**. Click it.
3. Fill in the form:
   - **Title:** `Add description to leaf-lon-01 Ethernet3`
   - **Description:** briefly explain what changed and why — for example: *"Adds a human-readable description to the Ethernet3 P2P link on leaf-lon-01 to improve operator visibility in `show interface` output. No IP or routing change."*
4. Click **"Create merge request"**.

The pipeline starts automatically. Stay on the MR page and watch the status badges appear beneath the MR title. The MR pipeline runs these stages in order:

| Stage | Jobs |
|---|---|
| validate | `yamllint`, `schema-validate`, `change-freeze-check` |
| intent-check | `generate-inventory`, `batfish-intent-check` |
| render | `render-configs` |
| diff | `config-diff` |

> 🔵 **Strategic**
>
> The MR pipeline stops at `config-diff`. No config is pushed to any device while the MR is open. This is intentional: the MR pipeline exists to produce a reviewable artefact and give automated systems a chance to object. A human reviewer looks at the diff and decides whether to merge. The push happens only after merge, and only after a manual gate on the main pipeline.

---

## Step 5 — Review the pipeline and diff

Once the `config-diff` job passes (the badge turns green):

1. Click the pipeline status badge (or go to the **Pipelines** tab on the MR page) to open the pipeline view.
2. Click the `config-diff` job tile to open the job log.
3. Scroll to the bottom of the log or click **"Browse"** in the **Artifacts** panel on the right to download the diff artefact.

You should see a line like this in the diff:

```diff
+   description P2P to spine-lon-02 Ethernet3 — iBGP underlay
```

That single added line is the entire change. Everything else in the rendered config — IP address, routing configuration, BGP stanzas — is unchanged.

This diff is what a peer reviewer approves. They can see exactly what will land on the device, without needing SSH access to the device or knowledge of Jinja2 templates.

> 🔴 **Deep Dive**
>
> The `config-diff` job uses NAPALM's `compare_config()` method to produce a unified diff between the rendered candidate config and the current running config retrieved from the device over NETCONF or SSH. The diff is exact: it reflects what the device will apply, not what changed in the template. If the device already had that description (for example, from a previous push), the diff would be empty and the job would still pass — it would simply report no changes pending.

---

## Step 6 — Merge to main

Once you (or a peer reviewer) are satisfied with the diff:

1. Return to the MR page.
2. Click **"Merge"**.

GitLab merges the feature branch into `main` and immediately triggers a new pipeline on `main`. This pipeline runs all the same stages as the MR pipeline, and then continues further:

| Stage | Jobs | Notes |
|---|---|---|
| validate | `yamllint`, `schema-validate`, `change-freeze-check` | Same as MR |
| intent-check | `generate-inventory`, `batfish-intent-check` | Same as MR |
| render | `render-configs` | Same as MR |
| diff | `config-diff` | Same as MR |
| approve | `approve-push` | **Manual gate — pipeline pauses here** |
| push | `push-configs` | Runs after approval |
| verify | `verify-state` | Runs automatically after push |

The pipeline pauses at the `approve-push` job. To proceed:

1. Go to **CI/CD → Pipelines** in the GitLab sidebar.
2. Click the running pipeline for the `main` branch.
3. Find the `approve-push` job — it shows a **▶ play** button (outlined triangle) indicating it is waiting for manual trigger.
4. Click the play button.
5. Confirm the action in the dialog that appears.

GitLab records your username and a timestamp in the job log at the moment you click play. This is the approval record for audit purposes.

> 🔵 **Strategic**
>
> The manual gate exists because `diff` alone is not sufficient assurance for a production push. The approval step enforces that a named individual, with appropriate access, has looked at the pipeline state and decided it is safe to proceed. In a team environment you would configure GitLab protected environments so that only senior engineers or a network change manager can trigger `approve-push`. The mechanism is GitLab's environment protection rules, not a separate change management tool.

---

## Step 7 — Watch push and verify

After you click play on `approve-push`, the remaining jobs run automatically:

- **`push-configs`** — NAPALM connects to `leaf-lon-01` and applies the rendered config atomically. If the connection fails or the device returns an error, the job fails and GitLab marks the pipeline red. No partial config is left on the device.
- **`verify-state`** — runs the post-push verification suite: BGP neighbor state, interface reachability, and management connectivity.

Watch the `verify-state` job badge turn green in the pipeline view.

Then confirm the change directly on the device:

```bash
ssh netadmin@172.20.20.21       # password: CHANGEME
leaf-lon-01# show interface Ethernet3
```

```
Ethernet3 is up, line protocol is up (connected)
  Description: P2P to spine-lon-02 Ethernet3 — iBGP underlay
  Hardware is Ethernet, address is ...
```

The description is there. The pipeline put it there, not you.

---

## What just happened

> 🔵 **Strategic**

You made a change that travelled through a GitLab-mediated loop with hard boundaries at each stage:

1. **SoT edit** — you changed one field in one YAML file. No config was touched.
2. **Local validation** — fast syntax and schema check before consuming CI resources.
3. **Feature branch + MR** — the change was isolated from `main` until it was reviewed.
4. **MR pipeline (validate → intent-check → render → diff)** — automated systems checked the change for schema validity, intent conformance (Batfish), and produced a rendered diff. The pipeline stopped here. Nothing was pushed.
5. **Peer review** — a human read the diff and decided it was correct.
6. **Merge** — the branch joined `main`.
7. **Main pipeline (validate → intent-check → render → diff → approve → push → verify)** — the same automated checks ran again against `main`, then paused for a named human to approve the push.
8. **Approval** — a named individual triggered the push. GitLab recorded who and when.
9. **Push and verify** — NAPALM applied the config atomically; automated verification confirmed the device state matched intent.

**Audit artefacts produced and where to find them:**

- **Pipeline job logs** — GitLab CI/CD → Pipelines → click any job. Logs show who triggered each job, when, and the full output. Retained indefinitely by default.
- **`config-diff` artefact** — the exact unified diff applied to the device. Downloadable from the `config-diff` job's Artifacts panel. Retained for 12 weeks.
- **`push-configs` artefact** — the NAPALM push record, including pre- and post-push device state snapshots. Retained for 12 weeks.
- **MR thread** — the merge request itself is a permanent record of who reviewed the diff, any comments left, and who approved the merge.

A description change is a trivial example. The same process applies when a BGP policy changes, when a new VLAN is added, or when a compliance-relevant interface configuration is modified. The pipeline does not distinguish between trivial and important. That consistency is the compliance guarantee.

---

## Exercise 9.1 — Your second push {#ex91}

> 🟡 **Practitioner**

Now do it without the step-by-step guidance, following the same MR → pipeline → merge → approve → push flow you just completed.

Make a slightly more complex change:

Add a new loopback interface to `leaf-lon-02`:

```yaml
  - name: Loopback1
    description: "Secondary loopback — SNMP source"
    ip: 10.1.255.112/32
```

Work through the full process: create a feature branch, validate locally, commit, push, open an MR, let the MR pipeline run to `config-diff`, review the diff, merge, trigger the `approve-push` manual gate on the main pipeline, and confirm the interface exists on the device after `verify-state` passes.

**Final check:** SSH to `leaf-lon-02` and confirm the interface exists with the correct IP and description.

**Debrief:** A loopback addition is safe — it does not affect traffic flow and BGP sessions will not be disrupted. The risk surface of a change is a function of what it touches, not how many lines change. Your pipeline treats a loopback addition and a BGP policy change with the same validation rigour, because the pipeline does not know which changes matter and which do not. That is a feature. The audit trail — the MR, the diff artefact, the approval record — is identical in both cases.

*Handbook reference: Chapter 6 (The config push workflow), Chapter 5 (Atomic changes and rollback)*
