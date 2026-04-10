---
title: "Chapter 23: Orchestration as a Compliance Layer"
---

## The Auditor's Four Questions

Three months after ACME's network automation programme went live, an external auditor from the FCA arrived. She was reviewing a BGP policy modification on `border-lon-01` made on 14 February — applied during a scheduled maintenance window that coincided with trading hours due to a regulatory deadline.

Her four questions were direct:

1. Who authorised this change?
2. What exactly changed?
3. Was it tested before deployment?
4. What was the rollback plan?

The team had good tooling. They spent 20 minutes pulling records.

The GitLab pipeline answered questions 2, 3, and 4. The pipeline for that date showed a diff of the BGP policy config, Batfish intent check output confirming no new paths violated INTENT-002, and a rollback artefact stored in the pipeline artefacts. The evidence was clear and timestamped.

Question 1 had no answer in the pipeline. The pipeline execution was triggered by the service account `acme-service-account`. That is not a person. The git commit showed `acme-ops-engineer` as the author, but commit author is trivially self-reported in git config. Neither record established authorisation by a named individual with documented approval from a change manager.

The Rundeck execution log answered question 1. It showed that `jsmith` submitted the Maintenance Window job at 14:23 on 14 February, with `approved_by: "Sarah Chen, Change Manager"` and `change_ticket: "CHG-2026-0089"`. That is a named individual, a named approver, a change management reference, and a timestamp.

But the Rundeck log did not contain the diff, the Batfish output, or any details of what the BGP policy actually changed to. Rundeck knew a maintenance window was opened. It did not know what happened inside it.

Neither record alone answered all four questions. Together, they did.

---

🔵 **Strategic**

## The Two-Layer Compliance Model

This is the key insight of Part 8. A complete compliance record for a network change in a regulated environment has two distinct layers, and they come from different systems.

### Layer 1 — Authorisation (Rundeck execution log)

| Field | Where it comes from |
|-------|---------------------|
| Who requested the change | Rundeck authenticated username — not self-reported |
| Who approved it | `approved_by` job option — self-reported, per change ticket |
| Change management reference | `change_ticket` job option |
| When the request was submitted | Rundeck server timestamp |
| Target device and action | Job option values, captured automatically |
| Emergency bypass reason | `bypass_reason` field, written to `state/emergency_changes.log` |

### Layer 2 — Implementation (GitLab pipeline artefact)

| Field | Where it comes from |
|-------|---------------------|
| Before-state | Pre-push config snapshot, stored as pipeline artefact |
| What changed | Config diff, stored as pipeline artefact |
| Validation result | Batfish intent check output, stored as pipeline artefact |
| Post-change verification | Post-push health check output |
| Rollback availability | Rollback config generated and stored at pipeline time |

A MiFID II-compliant change record for a network modification requires both layers. The audit question is not one question — it is four, and the answers come from two different systems.

### Why This Pattern Is Not Optional

An organisation with only GitLab has Layer 2 but cannot answer "who authorised this." The pipeline execution record shows what the service account did. It does not show who decided it should happen.

An organisation with only an ITSM tool has Layer 1 in a different form — a change ticket with approver records — but if the ITSM record was created after the fact, or if the ticket number was typed into a terminal command that left no execution log, the link between the authorisation and the implementation cannot be verified.

An organisation with only Rundeck and no GitLab pipeline has Layer 1 but a limited Layer 2 — Rundeck captures what playbook ran with what options, but not what the config state was before and after.

The two-layer model works because each layer captures what the other cannot. GitLab captures technical implementation detail with cryptographic integrity (git hashes don't lie). Rundeck captures the human authorisation context with temporal precision.

### The Link Between Layers

The change ticket number is the bridge. `CHG-2026-0089` appears in the Rundeck job option as `change_ticket`. The same number appears in the ITSM system's change record, which references both the Rundeck execution URL and the GitLab pipeline URL. An auditor who starts at the ITSM ticket can reach both evidence sources. An auditor who starts at the Rundeck log can find the change ticket and from it reach the pipeline.

In the lab, this link is manual — you would copy both URLs into the change ticket. In a mature production implementation, the Rundeck job would automatically update the ITSM ticket with the execution URL after completion. Rundeck Enterprise supports this natively via ServiceNow, Jira Service Management, and other ITSM integrations.

### What Community Edition Doesn't Verify

In Rundeck Community, the `approved_by` field is a text string. The submitter types a name. Rundeck does not verify that person's identity, check that they have authority to approve changes, or require them to authenticate.

This is adequate for many organisations operating with a functioning change management process alongside the tooling. The approved_by value is a pointer to the ITSM record, not a substitute for it. The auditor's question "who approved this?" gets answered by reading the change ticket, not by reading the Rundeck log alone.

For organisations that require cryptographic proof of approval — where "I typed Jane Smith's name" is not acceptable and "Jane Smith authenticated and clicked Approve" is required — Rundeck Enterprise's native approval queue provides that. The approver authenticates to Rundeck, sees the pending job, and explicitly approves or rejects it. The approval action is tied to the approver's authenticated session. That record is part of the Rundeck execution, not a separate ITSM entry.

Neither approach is universally correct. The right choice depends on your organisation's specific compliance requirements, your existing ITSM tooling, and how your change management process is actually supervised. Be explicit about this when presenting the architecture.

---

🟡 **Practitioner**

## Exercise 23.1 — Constructing a Complete Change Record {#ex231}

You will work with the execution records from Exercise 21.1 (Maintenance Window) and reference a GitLab pipeline from earlier lab work to understand how the two layers fit together.

### Step 1 — Read the Rundeck Execution Log

Open **http://localhost:4440**. Log in as `admin / acme-lab`.

Navigate to **Activity** in the left sidebar. Find the Maintenance Window execution from Exercise 21.1 (the one where you submitted `border-lon-01`, `action=enter`, `approved_by=Jane Smith`, `change_ticket=CHG-2026-0042`).

Click on the execution. Read through the execution detail page carefully:

**Execution summary (top section):**
- **Submitted by:** `acme-ops`
- **Started:** [timestamp — exact to the second]
- **Duration:** [Xs]
- **Status:** Succeeded

**Job options (middle section):**
- `target_node: border-lon-01`
- `action: enter`
- `window_reason: Optic replacement on Ethernet3`
- `window_end: 2026-04-12T22:00:00Z`
- `approved_by: Jane Smith`
- `change_ticket: CHG-2026-0042`

**Execution output (bottom section):**
- Every line of Ansible output, with timestamps

This is Layer 1. It answers "who requested it, who approved it, what ticket covers it, and when did it execute."

Note what is missing: there is no config diff here. You can see that `maintenance_window.yml` ran against `border-lon-01`. You cannot see what the BGP graceful-shutdown configuration looks like in detail, or what it looked like before.

### Step 2 — Find the GitLab Pipeline Layer

The `maintenance_window.yml` playbook applies BGP graceful-shutdown directly via Ansible, without triggering a GitLab pipeline. This means the maintenance window action itself does not produce a GitLab Layer 2 record — which is an accurate reflection of how operational workflows and config-change pipelines are divided.

For Layer 2 evidence, use a config push pipeline from Part 4 or Part 6 of the lab. Navigate to **http://localhost:8888** (GitLab) and open the ACME network repository. Navigate to **CI/CD → Pipelines** and find a recent pipeline run for a config change.

Open the pipeline run. Navigate to the pipeline stages:

- **validate stage:** Find the Batfish job. Open the job log. The intent check output shows which intents were evaluated and whether they passed.
- **push stage:** Find the config push job. In the artefacts, look for the diff output (the before and after state of the device configs).
- **verify stage:** Find the post-push health check output.

This is Layer 2. It answers "what changed, was it validated, and did the post-change state match expectations."

Note what is missing from the pipeline: who triggered it. The pipeline was triggered by `acme-service-account`. The commit author shows the engineer's git identity — but that is not an authenticated business record. It does not show who approved the change before it was merged.

### Step 3 — Connect the Two Layers

The link is the change ticket number. In a complete change management workflow:

1. Engineer raises `CHG-2026-0089` in the ITSM system, describing the intended BGP policy modification
2. Change Manager Sarah Chen reviews and approves — her approval is recorded in the ITSM ticket
3. Engineer submits the Maintenance Window job in Rundeck, referencing `CHG-2026-0089` as the `change_ticket` field
4. Rundeck execution URL is copied into the `CHG-2026-0089` ticket
5. Engineer merges the config change to the main branch
6. GitLab pipeline runs — pipeline URL is copied into `CHG-2026-0089` ticket
7. Change ticket is closed with references to both URLs

At any later date, the auditor opens `CHG-2026-0089` and finds:
- Sarah Chen's approval (Layer 1 authorisation, in ITSM)
- Rundeck execution URL showing `acme-ops` submitted the job with `approved_by: Sarah Chen` (Layer 1 execution record)
- GitLab pipeline URL showing the diff, the Batfish output, and the post-change verification (Layer 2 implementation record)

The four questions are answered. The chain of evidence is complete.

### Step 4 — Read the Emergency Change Record

Return to the emergency change log from Exercise 21.2:

```bash
cat state/emergency_changes.log
```

Read through the log entry. This is a different compliance scenario. There was no approval. The bypass reason is the record.

For a regulatory review, the question here is not "who authorised this?" but "why was the standard process bypassed, was that decision documented, and was it attributed to a named individual at the time it was made?"

The log entry answers all three:
- The bypass reason is present (documented)
- The timestamp is the Rundeck server time, recorded before the playbook ran (at the time it was made)
- The `submitted_by` field is the authenticated Rundeck user (attributed to a named individual)

The emergency change path and the standard change path produce different compliance records because they serve different post-incident questions. Design the records to answer the questions that will actually be asked.

---

### Exercise: Guided Tier 13.5

Construct a complete MiFID II-style change record for the Maintenance Window exercise. You need two sources:

**From Rundeck:** The execution summary from Exercise 21.1. Copy out:
- Submitted by
- Timestamp
- All job option values (target_node, action, window_reason, approved_by, change_ticket)

**From the lab state file:** The maintenance state written by the playbook:

```bash
cat state/maintenance_border-lon-01.yml
```

This file contains the BGP graceful-shutdown configuration that was applied, the timestamp, and the action type.

Now write a one-paragraph change record in plain English that answers all four of the auditor's questions:

1. **Who authorised it?** (Rundeck execution log + approved_by field)
2. **What exactly changed?** (state file + playbook behaviour description)
3. **Was it tested before deployment?** (honest answer: this is an operational action, not a config deployment — the maintenance_window playbook applies a standard procedure that has been tested in this lab environment)
4. **What was the rollback plan?** (the Maintenance Window job's `action=exit` option closes the window; the state file records the current action=enter, making the rollback step explicit)

The goal of this exercise is to experience the gap-filling exercise that your future self — or your compliance team — will have to do after a real change. If you cannot answer one of the four questions from the available records, that gap is a gap in your change management architecture.

---

## Debrief

This chapter is the conceptual endpoint of the lab's change management thread. Recall the earlier chapter where you mapped an Ansible config push to the ITIL change management lifecycle. That mapping was incomplete at the time — there was no authorisation layer.

With Rundeck in the picture, the ITIL mapping is now complete:

| ITIL Stage | Lab Mechanism |
|------------|--------------|
| RFC raised | Rundeck job submitted by engineer (creates execution record) |
| CAB approval recorded | `approved_by` and `change_ticket` fields in Rundeck job options |
| Implementation | Rundeck triggers Ansible playbook or GitLab pipeline |
| Post-implementation review | Batfish post-check output (in pipeline), or health check run after operational change |
| Change record closure | Rundeck execution log + GitLab pipeline artefact, linked by change ticket number |

None of this requires a specific ITSM product. It requires that each component of the chain produces a persistent, timestamped record, and that the records reference each other via the change ticket number.

The specific tools will vary between organisations. The FCA does not mandate Rundeck, GitLab, or Batfish. What it mandates is that changes to systems involved in regulated activities are authorised, documented, and auditable. The two-layer model — Rundeck for authorisation context, GitLab for implementation detail — is one implementation of that requirement. It is not the only implementation. It is, however, a concrete and workable one that you have now seen end-to-end.

### A Note for Strategic Track Readers

If you are following the Strategic track and have not worked through the practitioner exercises in this module, this chapter is worth reading in full regardless. The two-layer compliance model is the conceptual keystone of Part 8. Understanding what each layer captures — and specifically what each layer cannot capture on its own — is the foundation for evaluating any network automation toolchain against a compliance requirement.

The practitioner exercises in Chapters 33, 34, and 35 show how this works in the lab. The pattern they demonstrate is the same pattern you would apply when evaluating a production deployment. The tools are different; the questions are not.

---

**Next:** Part 9 covers advanced automation patterns — staged rollouts, auto-remediation, and the capstone scenarios that bring together everything built across the lab.
