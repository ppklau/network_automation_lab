---
title: "Chapter 20: Introducing Rundeck"
---

## The Friday That Nobody Remembered

On a Friday afternoon in October, the ACME network operations team ran out the door at 17:30. The daily health check was a manual step — someone would SSH to the jump host, run `ansible-playbook playbooks/daily_health_check.yml`, scan the output for anything red, and move on. Most days this happened. On this particular Friday, it didn't.

By Monday morning, trading operations had already called. Branch office `branch-lon-01` had been showing intermittent connectivity to the CORPORATE zone since sometime over the weekend. The NOC investigated. The root cause: a BGP authentication mismatch on `branch-lon-01` that caused the session to `spine-lon-01` to reset under load. The session had been in a flap state — repeatedly establishing and then dropping — since Friday afternoon. The health check would have caught it immediately. Nobody ran the health check.

The incident lasted 63 hours. The trading desk noticed before the ops team did. That is not an acceptable monitoring posture for a regulated financial institution.

The deeper problem was not the forgotten health check. The deeper problem was that the health check's execution depended on a human being present, motivated, and not distracted. Three conditions that will eventually fail simultaneously, as they did here.

This module introduces the orchestration layer that eliminates that dependency.

---

🔵 **Strategic**

## What Orchestration Adds Above the Pipeline

The automation stack built in earlier parts of this lab has two primary execution surfaces:

1. **GitLab CI/CD** — executes config changes when code is pushed to the repository. A pipeline runs: lint, validate, push, verify. The pipeline is triggered by a commit.

2. **Ansible playbooks** — called by the pipeline, and also available for direct execution on the command line.

These two surfaces handle *what* changes and *how* it is validated. They do not handle *when* an operational workflow runs, *who* is permitted to trigger it, or *what approval was recorded* before it executed.

That gap is the orchestration layer.

Rundeck is an orchestration platform. It sits above both GitLab and Ansible in the stack. Its job is not to execute config changes directly — GitLab does that — but to manage the operational workflows that surround those changes: scheduled checks, human-triggered maintenance procedures, approval-gated changes, and emergency operations.

The architecture looks like this:

```
Network Ops Team
      │
      ▼
  Rundeck (port 4440)        ← orchestration layer: scheduling, approval, audit
      │
      ├─→ Ansible playbooks  ← direct execution (health check, maintenance, RMA)
      │
      └─→ GitLab API         ← pipeline trigger (for changes that go through CI/CD)
                │
                ▼
         Containerlab topology (cEOS + FRR nodes)
```

Note the position: Rundeck is the *front door*. An operations engineer does not run `ansible-playbook` from a terminal session. They submit a job in Rundeck. Rundeck records who submitted it, when, what options were specified, and what the outcome was. Then it executes the playbook. The terminal session is gone; the audit record is permanent.

### Three Change Paths

The ACME job library implements three distinct change paths:

**Scheduled changes** run automatically on a calendar — no human is involved in triggering them. The daily health check runs at 07:00 Monday through Friday whether or not anyone remembers. The compliance report runs every Sunday at 06:00. These jobs have no approval fields because there is no human to approve them; the *schedule itself* is the operational policy.

**Standard changes** are human-triggered and require documented approval before execution. A maintenance window on `border-lon-01` requires an `approved_by` name and a `change_ticket` reference. These fields are mandatory — the job will not run without them. The values are captured in the Rundeck execution log, which becomes the approval record for an auditor.

**Emergency changes** bypass the standard approval process but require a `bypass_reason` and `incident_reference`. The bypass reason is the compliance record. In a regulated environment, the post-incident question is not just "what happened" but "why was the standard process bypassed?" A mandatory bypass reason field, written to a persistent log before the playbook runs, answers that question definitively even if everything else fails.

Understanding which path a given operation falls into is an architectural decision, not an operational one. Part 8 works through each path in detail.

---

🟡 **Practitioner**

## Exercise 20.1 — Deploy Rundeck and Import the Job Library {#ex201}

### Deploy Rundeck

Rundeck runs as a Docker service alongside the monitoring stack. Start it from the `monitoring` directory:

```bash
cd monitoring && docker compose up -d rundeck
```

Rundeck takes 60–90 seconds to initialise. Follow the startup log to know when it is ready:

```bash
docker compose logs -f rundeck
```

Wait for this line before proceeding:

```
rundeck_1  | Grails application running at http://localhost:4440 in environment: production
```

Once you see it, press `Ctrl+C` to stop following the logs. Rundeck is up.

### Import the Job Library

Return to the lab root directory and run the job import script:

```bash
cd ..
./rundeck/import_jobs.sh
```

The script reads every `.yaml` file in `rundeck/jobs/` and imports it into the ACME project via the Rundeck API. You will see one line per job as they are created:

```
Importing daily_health_check.yaml... OK
Importing compliance_report.yaml... OK
Importing maintenance_window.yaml... OK
Importing emergency_change.yaml... OK
Importing leaf_rma.yaml... OK
Importing border_rma.yaml... OK
Importing os_upgrade.yaml... OK
```

If any import fails with a 401 error, Rundeck is still starting. Wait 15 seconds and retry.

### Explore the Job Library

Open **http://localhost:4440** in your browser.

Log in with:
- Username: `admin`
- Password: `acme-lab`

Navigate to **ACME → Jobs**. You will see three job groups:

| Group | Jobs |
|-------|------|
| `ACME/Scheduled` | Daily Health Check, Compliance Report |
| `ACME/Operations` | Maintenance Window, Emergency Change |
| `ACME/Lifecycle/Restricted` | Leaf RMA, Border RMA, OS Upgrade |

Expand each group and click through to each job. For each one, note:

**Daily Health Check** (`ACME/Scheduled`):
- Schedule: Mon–Fri at 07:00
- No user-facing options — this job runs with no human input
- Execution command calls `ansible-playbook playbooks/daily_health_check.yml`
- The Friday failure scenario from the chapter opening is now resolved by design

**Compliance Report** (`ACME/Scheduled`):
- Schedule: Sunday at 06:00
- No user-facing options
- Calls `ansible-playbook playbooks/compliance_report.yml`
- Output is written to `reports/` by the playbook; the Rundeck log captures who triggered it and when

**Maintenance Window** (`ACME/Operations`):
- No schedule — manual trigger only
- Six options: `target_node`, `action`, `window_reason`, `window_end`, `approved_by`, `change_ticket`
- `approved_by` and `change_ticket` are mandatory
- Calls `ansible-playbook playbooks/maintenance_window.yml --limit {{ target_node }} --extra-vars "action={{ action }} window_reason={{ window_reason }} approved_by={{ approved_by }} window_end={{ window_end }}"`

**Emergency Change** (`ACME/Operations`):
- No schedule — manual trigger only
- Options: `target_node`, `change_type`, `bypass_reason`, `incident_reference`
- `bypass_reason` and `incident_reference` are mandatory
- Appends a log entry to `state/emergency_changes.log` before executing the playbook

**Leaf RMA** (`ACME/Lifecycle/Restricted`):
- Calls `ansible-playbook playbooks/rma_leaf.yml --limit {{ target_node }} --extra-vars "new_serial={{ new_serial }} rma_reason={{ rma_reason }} confirmed=yes"`

**Border RMA** (`ACME/Lifecycle/Restricted`):
- Requires two approver fields — both captured in the execution log
- Calls `ansible-playbook playbooks/rma_border.yml`

**OS Upgrade** (`ACME/Lifecycle/Restricted`):
- No pre-configured schedule; uses Rundeck's per-execution scheduling to commit a future maintenance window
- Calls `ansible-playbook playbooks/os_upgrade.yml`

### Map Jobs to Playbooks

The relationship is direct and intentional. Each job in Rundeck is a wrapper around an Ansible playbook. The wrapper adds four things the playbook alone cannot provide:

1. **User identity** — who submitted the job (Rundeck username, captured automatically)
2. **Input validation** — mandatory fields that the playbook's `--extra-vars` cannot enforce
3. **Execution record** — timestamp, duration, all option values, full stdout, stored in Rundeck's database
4. **Access control** — the `ACME/Lifecycle/Restricted` group is only visible to `acme-senior-group`

The playbooks themselves are unchanged. The orchestration layer wraps them without modifying them.

---

### Exercise: Structured Tier

Log out of the admin account and log in as `acme-ops / acme-ops`. Navigate to **ACME → Jobs**.

Note which job groups are visible and which are not. The `ACME/Lifecycle/Restricted` group — containing Leaf RMA, Border RMA, and OS Upgrade — will not appear. This is enforced by a Rundeck ACL policy (`rundeck/acl/acme-ops.aclpolicy`) that grants `read` and `run` access to `ACME/Scheduled` and `ACME/Operations`, but not to `ACME/Lifecycle/Restricted`.

Now log out and log in as `acme-senior / acme-senior`. The `ACME/Lifecycle/Restricted` group is now visible. Senior engineers can run RMA and OS upgrade jobs that the operations team cannot.

Write down your observations: what access does each user have, and why is that the right boundary? Consider: should an operations engineer be able to run an OS upgrade on a border switch during a P1 incident? What are the risks if they can? What are the risks if they can't?

### Exercise: Open Tier

A new operational playbook — `playbooks/sot_hygiene.yml` — needs to be added to the job library. This playbook validates ACME's Source of Truth for common inconsistencies: duplicate IP allocations, missing required fields, VLANs defined in SoT but not deployed, and loopback addresses that don't match the IPAM allocation.

Define a job YAML for it in `rundeck/jobs/sot_hygiene.yaml`. Consider:

- Which job group should it be in? (`ACME/Scheduled`, `ACME/Operations`, or a new group?)
- Does it need approval fields?
- Should it run on a schedule? If so, when? (Hint: after trading close on Fridays is the standard ACME practice for hygiene jobs.)
- Should all users be able to trigger it manually, or only senior engineers?

Import it with `./rundeck/import_jobs.sh` (the script re-imports all jobs, including new ones). Verify it appears in the Rundeck UI in the correct group.

---

## Debrief

The Friday health check failure had nothing to do with Ansible. The playbook existed. It was correct. It would have caught the BGP auth mismatch immediately. The failure was operational: the execution depended on a person, and the person wasn't there.

The job library solves this in the most direct way possible: the health check now runs whether or not anyone is present. The schedule is a configuration artefact in `rundeck/jobs/daily_health_check.yaml`. It is version-controlled, visible in the UI, and produces an execution record for every run. When the auditor asks "was the health check running consistently throughout Q3?", the answer is no longer "I think so" — it is a list of 65 execution records with timestamps.

The second thing the job library achieves is that it removes the terminal session from the operational record. When an engineer ran `ansible-playbook` from their laptop, there was no persistent record of that execution. If the playbook failed silently, no one knew. If two engineers ran the same playbook simultaneously on the same device, there was no conflict detection. The Rundeck execution log captures every run, every user, every option value, and every line of output. The terminal sessions are gone; the audit trail is not.

That is the difference between a set of well-written playbooks and an orchestration layer. The playbooks are necessary. The orchestration layer is what makes them auditable.

---

**Next:** Chapter 21 covers the approval workflow in detail — how a Maintenance Window job moves from submission to execution, what the approval record looks like, and how emergency changes produce a compliance record without an approval gate.
