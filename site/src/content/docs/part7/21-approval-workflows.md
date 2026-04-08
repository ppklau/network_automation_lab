---
title: "Chapter 21: Approval Workflows"
---

## The Optic That Wasn't Faulty

At 02:30 on a Wednesday morning, a junior engineer put `border-lon-01` into maintenance mode. The optic on Ethernet3 had been showing intermittent errors throughout the previous day. The engineer's diagnosis: failing optic. The fix: swap it during the overnight window when traffic was lowest.

There was no maintenance ticket. No notification to the NOC. No record of the action beyond a few lines in the engineer's personal notes.

BGP graceful-shutdown was applied to `border-lon-01`. Traffic shifted to `border-lon-02`. At 02:31, `border-lon-02` was carrying 100% of ACME's inter-region traffic.

The optic was fine. The errors had been caused by a loose fibre connector, which reseated itself when the engineer touched the cable during inspection. The maintenance window was never explicitly closed. The graceful-shutdown advertisement remained active.

By 06:00, four hours later, `border-lon-02` was still absorbing the full inter-region load. When trading opened at 08:30, the latency increase triggered an alert. Four hours of investigation followed before anyone thought to check whether `border-lon-01` was still in maintenance mode.

The root cause was not technical. BGP graceful-shutdown worked exactly as designed. The optic was fine. The fault was the absence of any governance around the decision to put a production border router into maintenance mode at 02:30 without telling anyone.

---

🔵 **Strategic**

## What Approval Gates Actually Achieve

It is important to be precise about what an approval gate does and does not do.

An approval gate would not have prevented this specific incident. The engineer had the access to run the maintenance window playbook. If the Rundeck job had required an approved_by field, the engineer could have typed any name. In Rundeck Community edition, the approved_by value is self-reported — it is not verified against an IdP or validated against a change management system.

So why have it?

**Accountability changes behaviour.** When an engineer knows that their name, the approver's name, and the change ticket reference will be permanently recorded against a timestamped execution, they behave differently than when they are running an anonymous terminal command at 02:30. The barrier is not technical; it is procedural. The form asks "who approved this?" and that question — which must be answered before the job runs — is the entire point.

**Post-incident reconstruction.** After the border-lon-01 incident, the question "who authorised this and when?" had no answer. The engineer's personal notes are not an audit record. With Rundeck in the picture, the execution log contains the approver name, the change ticket, the timestamp, and the user who submitted the job. The post-incident timeline can be reconstructed from the log rather than from fallible human memory.

**The compliance question is specific.** Under MiFID II, ACME's network operations must demonstrate that changes affecting systems involved in trade processing are subject to a documented authorisation process. The question an auditor asks is not "did you have a change process?" It is "show me the authorisation record for this specific change on this specific date." The Rundeck execution log is that record.

### Community vs Enterprise: Be Honest About the Distinction

Rundeck Community edition — which this lab uses — does not have a native approval queue. There is no state where a job sits in "pending" waiting for an approver to act.

What the lab implements instead is an **approval simulation** using two mechanisms:

1. **ACL restriction:** The `ACME/Lifecycle/Restricted` jobs are only accessible to `acme-senior-group`. The operational team cannot run RMA or OS upgrade jobs directly. This is real access control, not simulation.

2. **Mandatory fields:** The Maintenance Window and standard Lifecycle jobs require `approved_by` and `change_ticket` before execution. These are self-reported — the submitter types a name. The value is captured in the execution log and becomes the approval record. It is not cryptographically verified.

**Rundeck Enterprise** has a native approval queue. When a job is submitted, it enters a pending state. A designated approver — who must authenticate and act explicitly — is notified. The job does not execute until the approver takes action. The approval record in Enterprise is tied to the approver's authenticated session, not a typed string. This distinction matters in high-assurance environments.

For many financial institutions, the mandatory-field approach is sufficient for operational changes. For changes that require two-person integrity (4-eyes principle), or where the submitter and approver must be demonstrably different individuals, Enterprise's native queue is the correct answer. Name this trade-off explicitly when presenting this architecture to your security or compliance team.

---

🟡 **Practitioner**

## Exercise 13.2 — The Approval Simulation Walkthrough {#ex132}

### Step 1 — Submit the Maintenance Window as acme-ops

Open **http://localhost:4440** and log in as `acme-ops / acme-ops`.

Navigate to **ACME → Operations → Maintenance Window**. Click **Run Job Now**.

The options form appears. Fill it in:

| Field | Value |
|-------|-------|
| `target_node` | `border-lon-01` |
| `action` | `enter` |
| `window_reason` | `Optic replacement on Ethernet3` |
| `window_end` | `2026-04-12T22:00:00Z` |
| `approved_by` | `Jane Smith` |
| `change_ticket` | `CHG-2026-0042` |

Click **Run Job Now**.

The job starts immediately. This is the Community edition behaviour: there is no approval queue, so the job executes as soon as the options are submitted. The `approved_by` and `change_ticket` values are not a gate — they are a record.

Watch the execution output stream in the browser. You will see Ansible connecting to `border-lon-01`, applying BGP graceful-shutdown, and writing the maintenance state file. The output is identical to running the playbook from the command line. The difference is that it is captured.

### Step 2 — Read the Execution Log

When the job completes, navigate to **Activity** in the left sidebar. Find the execution that just ran.

Click on it. The execution detail page shows:

- **Submitted by:** `acme-ops`
- **Duration:** Xs
- **Status:** Succeeded
- **Job options:** all six fields, including `approved_by: Jane Smith` and `change_ticket: CHG-2026-0042`
- **Full output:** every line of Ansible output, stored permanently

This is the approval record. If an auditor asks "show me the authorisation for the maintenance window on border-lon-01 on 12 April 2026", this page is the answer. It shows who submitted the request, what they said was approved, what the change ticket was, and that the job succeeded.

The approved_by value is self-reported. Jane Smith did not authenticate to Rundeck. She is not a Rundeck user. Her name appears because the acme-ops engineer typed it. In a production environment, you would verify this against the ITSM ticket — CHG-2026-0042 would have Jane Smith's digital signature as the change approver.

In Community edition, you cannot enforce that programmatically. What you can enforce is that the field must be filled. An empty approval field produces no execution record.

### Step 3 — Observe the ACL Restriction

Stay logged in as acme-ops and navigate to **ACME → Jobs**. Expand the job groups. You will not see `ACME/Lifecycle/Restricted`. The group is absent — not greyed out, not present with a lock icon. It simply does not exist from the perspective of this user account.

This is enforced by `rundeck/acl/acme-ops.aclpolicy`. The policy grants `read` access to job groups matching `ACME/Scheduled` and `ACME/Operations`, and denies access to everything else by omission.

Log out. Log in as `acme-senior / acme-senior`.

Navigate to **ACME → Jobs**. The `ACME/Lifecycle/Restricted` group is now present. Leaf RMA, Border RMA, and OS Upgrade are all accessible. These jobs require approved_by and change_ticket fields, but they can now be triggered.

This is the two-tier access model: operations engineers can run operational workflows; senior engineers can additionally run lifecycle-impacting jobs. Neither group can run the other's restricted jobs. The admin account is not used for day-to-day operations.

---

## Exercise 13.4 — Emergency Change {#ex134}

### The P1 Scenario

At 14:17 on a Tuesday, the NOC dashboard shows `border-lon-01`'s BGP session to `border-nyc-01` has been down for eight minutes. The TRADING VRF is affected. Trading operations has already called. The standard maintenance change process takes 30 minutes. You do not have 30 minutes.

The emergency change path bypasses approval. It does not bypass the compliance record.

### Step 1 — Submit the Emergency Change

Log in as `acme-ops / acme-ops` (or acme-senior — both can run Emergency Change).

Navigate to **ACME → Operations → Emergency Change**.

Fill in the options:

| Field | Value |
|-------|-------|
| `target_node` | `border-lon-01` |
| `change_type` | `rollback` |
| `bypass_reason` | `P1 BGP session loss on border-lon-01 inter-region link. Standard approval bypassed — trading impact. See INC-2026-0891.` |
| `incident_reference` | `INC-2026-0891` |

Click **Run Job Now**.

### Step 2 — Read the Emergency Change Log

The job appends a structured log entry to `state/emergency_changes.log` *before* the playbook runs. This ordering is intentional: even if the playbook fails, the bypass record exists.

On the host, read the log:

```bash
cat state/emergency_changes.log
```

You will see an entry like:

```
---
timestamp: "2026-04-08T14:17:43Z"
submitted_by: "acme-ops"
target_node: "border-lon-01"
change_type: "rollback"
incident_reference: "INC-2026-0891"
bypass_reason: "P1 BGP session loss on border-lon-01 inter-region link. Standard approval bypassed — trading impact. See INC-2026-0891."
rundeck_execution_id: "42"
```

Every field is here. The timestamp is the exact moment the job was submitted. The submitted_by is the authenticated Rundeck user — not a typed name, not a claim. The bypass_reason is a written statement, attributed to a named individual, timestamped, and stored independently of whether the fix worked.

This is what distinguishes the emergency change path from an engineer running `ansible-playbook` from a terminal. The terminal session leaves no record. The emergency change leaves a compliance record that a regulator can read.

### The Compliance Point

The bypass reason IS the compliance record for an emergency change. Under MiFID II and FCA operational resilience requirements, the question after an emergency action is not "did you have approval?" — the emergency path explicitly acknowledges that you did not. The question is "why was normal authorisation bypassed, and was that decision documented at the time?"

A bypass reason written three days later, when the incident report is being drafted, is not adequate. A bypass reason written to `state/emergency_changes.log` fourteen seconds after the job was submitted is. The timestamp is not self-reported; it comes from the Rundeck server.

---

### Exercise: Structured Tier

Log in as `acme-senior / acme-senior`. Navigate to **ACME → Lifecycle/Restricted → Border RMA**.

Click **Run Job Now**. Observe the options form. There are two approver fields — `approved_by_1` and `approved_by_2`. Fill both with different names (for example, "Alice Wong" and "James Okafor"). Fill the remaining required fields with plausible values. Submit the job.

Navigate to the execution record in Activity. Confirm that both approver names are captured in the log alongside the submitter identity.

Now consider: this implements a two-person requirement (4-eyes principle) at the data-capture level. Both names are recorded. But neither person authenticated — neither typed a password in Rundeck to confirm their approval. What would need to change in the architecture to make this a genuine 4-eyes control rather than a documented convention? What would Rundeck Enterprise's approval queue add? What would an IdP integration add on top of that?

---

## Debrief

Return to the 02:30 maintenance window incident. Walk through it again with the approval workflow in place.

The engineer wants to put `border-lon-01` into maintenance mode. They open Rundeck. The form asks for `approved_by` and `change_ticket`. At 02:30, with no ticket, with no one to call for approval, that form is a pause. It does not technically prevent the action — the engineer could type anything. But it asks a question that deserves a real answer before 100% of inter-region traffic shifts to a single router.

The maintenance window was never closed because there was no record that it was opened. With Rundeck, the execution log shows `action=enter` at 02:31. At the next shift handover, the incoming engineer would see an open maintenance window in the activity log. The close action would be the obvious missing step.

The governance failure that caused four hours of incident response becomes a 10-minute checklist item: scan activity for open maintenance windows at the start of each shift. That scan is only possible because the record exists.

---

**Next:** Chapter 35 covers the scheduling layer in detail — how Rundeck's scheduled jobs work, how schedule configuration is version-controlled, and why declarative scheduling is audit evidence in a way that cron jobs are not.
