---
title: "Chapter 22: Scheduling"
---

## Four Times in Thirteen Weeks

ACME's compliance team received the audit request six weeks before the external review. The auditor wanted evidence that compliance checks had been run consistently throughout the quarter — specifically, that `compliance_report.yml` had executed weekly and that the output had been reviewed.

The network team checked the GitLab pipeline history. The compliance report playbook had been run four times in thirteen weeks.

The distribution was telling: twice in the week before a previous audit, once ad hoc after a routing incident when someone wanted a baseline snapshot, and once when a new engineer was onboarding and testing playbooks they had not used before. None of the four runs were part of a regular cadence. The first two were audit panic. The last one was an accident.

The compliance team was not pleased. The auditor's question — "was this control operating continuously throughout the period?" — had an obvious and uncomfortable answer.

The problem was not that the playbook was unreliable or that anyone was negligent. The problem was that running the compliance report depended on someone remembering to do it. In a team handling P1 incidents, deployments, vendor escalations, and capacity planning simultaneously, a weekly compliance report is not memorable enough to survive every competing priority for thirteen consecutive weeks.

This is the scheduling problem. It is not a technical problem. It is an organisational reliability problem, and the solution is to remove the human memory dependency from the execution path entirely.

---

🔵 **Strategic**

## "We Can Run This" vs "We Do Run This"

There is a meaningful difference between a playbook existing in a repository and that playbook executing on a known, auditable schedule.

A team that has `compliance_report.yml` can truthfully say "we have a compliance report capability." They cannot say "our compliance checks ran every Sunday throughout Q3" unless they have evidence of each execution. Evidence requires execution records. Execution records require a system that ran the job and logged the result.

Cron jobs are the traditional answer to this problem. A cron entry on the jump host or a shared server will run the playbook on schedule. But cron jobs have several properties that make them inadequate as audit evidence:

- They live on a single machine. When that machine is rebuilt, or when the engineer who owns it leaves, the cron job disappears without any record that it existed.
- They do not appear in any central log unless you explicitly redirect output to a persistent location — which most engineers do not consistently maintain.
- There is no access control on who can create or delete a cron job on a shared server.
- There is no execution history UI. "Did the cron job run on 15 March?" requires either log archaeology or hoping the engineer remembers.

Rundeck's scheduled jobs address all of these properties:

**The schedule is a configuration artefact.** It lives in `rundeck/jobs/daily_health_check.yaml`, is version-controlled in the lab repository, and is imported into Rundeck's database. If the schedule changes, the change is in git history. If someone asks "what was the health check schedule in February?", `git log` has the answer.

**Every scheduled execution is a Rundeck execution.** It appears in the Activity log with a timestamp, a `system` or `scheduler` user attribution (distinguishing automated runs from manual ones), and full output. Six weeks of Sunday compliance reports produces six execution records. Those records are the audit evidence.

**The schedule is visible.** Anyone with Rundeck access can see the current schedule for any job. There are no hidden cron jobs. The operational posture is inspectable.

This is what it means to make compliance a property of the system rather than a property of individual discipline.

---

🟡 **Practitioner**

## Exercise 13.3 — Working with Scheduled Jobs {#ex133}

### Part 1 — Observe the Daily Health Check Schedule

Log into Rundeck at **http://localhost:4440** as `admin / acme-lab`.

Navigate to **ACME → Scheduled → Daily Health Check**. Click the job name (not the Run button) to open the job definition view.

Scroll to the **Schedule** section. You will see:

```
Cron: 0 0 7 ? * MON,TUE,WED,THU,FRI *
Timezone: UTC
Next scheduled execution: [date/time]
```

This schedule did not originate in the Rundeck UI — it came from `rundeck/jobs/daily_health_check.yaml` when you ran the import script. Open that file in the repository:

```bash
cat rundeck/jobs/daily_health_check.yaml
```

Find the `schedule` block. The cron expression there matches exactly what Rundeck displays. The job definition file is the source of truth for the schedule, just as the SoT YAML files are the source of truth for device configuration. Both are version-controlled. Both can be reviewed in a PR. Both can be rolled back with `git revert`.

### Trigger a Manual Health Check Run

If you have not reached 07:00 UTC today, the execution history will be empty. Generate an execution record manually by clicking **Run Job Now** from the job page.

The output streams in the Rundeck UI. You will see the same BGP summary, interface error counts, and NTP sync status per device that you would see running the playbook from the command line — but this execution is now in the Rundeck activity log, attributed to your user account, with a permanent timestamp.

Navigate to **Activity** after the job completes. Your manual run will appear with:
- Your username
- Execution duration
- Status: Succeeded (or Failed with an error message if the lab topology is not running)

Scroll down if prior executions exist. Scheduled runs show `rundeck-scheduler` as the user rather than a named account. This is how you distinguish "someone clicked Run" from "the schedule fired."

### Part 2 — Manually Trigger the Compliance Report

Navigate to **ACME → Scheduled → Compliance Report**.

Note the schedule: Sunday at 06:00. You are not going to wait for Sunday.

Click **Run Job Now**. No options form appears — this job has no user-supplied options. Click **Run Job Now** again to confirm.

Watch the output stream. The compliance report playbook checks BGP session state, interface error counts, config drift status, and NTP compliance across all lab nodes, then writes a structured report to `reports/`.

When the execution completes, check the reports directory on the host:

```bash
ls -la reports/
```

The playbook will have written a file like `compliance_report_2026-04-08.yml` (or `.json`, depending on the playbook version). This file is the compliance report artefact — it is what the auditor reviews.

Now look at the Rundeck execution record. The Activity entry shows:
- Who triggered it (your username, since this was a manual run)
- When it ran
- That it succeeded
- The full output

The file in `reports/` is the *content* of the compliance check. The Rundeck execution record is the *evidence that the check ran*. You need both. A compliance report file with no execution record could have been written by hand. An execution record that points to a missing report file means the playbook failed silently. Together, they are unambiguous.

### Part 3 — The OS Upgrade Scheduling Pattern

Log in as `acme-senior / acme-senior` (OS Upgrade is in `ACME/Lifecycle/Restricted`).

Navigate to **ACME → Lifecycle/Restricted → OS Upgrade**.

This job does not have a standing schedule like the health check. Instead, it uses Rundeck's per-execution scheduling feature — which allows a human to commit a specific future execution time when they submit the job, rather than relying on a recurring calendar entry.

Click **Run Job Now**. The options form appears with several fields:

| Field | Description |
|-------|-------------|
| `target_node` | Which node to upgrade |
| `image_path` | Path to the OS image file |
| `target_version` | Expected version string post-upgrade |
| `approved_by` | Change approver name (mandatory) |
| `change_ticket` | Change management reference (mandatory) |

At the bottom of the options form, observe the **Schedule** toggle. Expand it. You can specify a future date and time for this execution.

This is the maintenance window scheduling pattern: the engineer fills in all the required fields (including approval evidence), sets the execution time to 02:00 Saturday, and submits. Rundeck commits the scheduled execution. At 02:00 Saturday, Rundeck triggers the playbook automatically — no engineer needs to be awake and logged in.

The approval record (approved_by and change_ticket) is captured at submission time, not at execution time. This is important: the change was authorised on Thursday when the engineer submitted the form. The execution happens Saturday. The approval record predates the execution, which is the correct temporal relationship for a pre-authorised change.

Close the form without running (or cancel if you opened a run dialog). You do not need to actually run an OS upgrade for this exercise.

---

### Exercise: Structured Tier

ACME's trading hours start at 07:30 UTC. The operations team wants the daily health check to complete before trading opens, not at the same time. They want to push it 15 minutes earlier, to 06:45.

Update the schedule in the job definition file:

```bash
# Open the job definition
nano rundeck/jobs/daily_health_check.yaml
```

Find the cron expression. The current value is:

```yaml
schedule:
  crontab: "0 0 7 ? * MON,TUE,WED,THU,FRI *"
  timezone: UTC
```

Change it to:

```yaml
schedule:
  crontab: "0 45 6 ? * MON,TUE,WED,THU,FRI *"
  timezone: UTC
```

Save the file. Re-import:

```bash
./rundeck/import_jobs.sh
```

Navigate to **ACME → Scheduled → Daily Health Check** in the Rundeck UI. The schedule section should now show `6:45 AM` as the next scheduled time.

Now verify that the change is in git history:

```bash
git diff rundeck/jobs/daily_health_check.yaml
```

The diff shows the cron expression change. This is the value of keeping job definitions in version control: the schedule is auditable in the same way that a config template change is auditable.

### Exercise: Open Tier

ACME wants a weekly SoT hygiene check every Friday at 18:00 UTC — after London trading closes and before any weekend change windows begin. The playbook `playbooks/sot_hygiene.yml` exists.

If you completed the Open Tier exercise in Chapter 33, you already have a job YAML started. Build on it, or start fresh.

Your job definition needs:

1. The correct job group (the compliance team considers SoT hygiene a scheduled operational control — where does that sit in the ACME hierarchy?)
2. A cron schedule for Friday at 18:00 UTC
3. Appropriate user access (should all users be able to trigger this manually between scheduled runs, or should it be restricted?)
4. A description field that explains what the job does and why it runs after trading close

Import the job:

```bash
./rundeck/import_jobs.sh
```

Verify in the Rundeck UI:
- The job appears in the correct group
- The schedule shows Friday 18:00
- The next scheduled execution time is correct

Trigger a manual run and confirm the execution record appears in Activity.

---

## Debrief

Return to the audit scenario. Thirteen weeks, four executions.

With Rundeck's scheduled Compliance Report job in place, that scenario resolves differently. The job runs every Sunday at 06:00. It does not depend on anyone remembering. It does not depend on the jump host having a correctly configured cron entry. It does not disappear when an engineer leaves the team.

Six weeks of Sunday compliance reports produces six execution records in Rundeck Activity. Each record has a timestamp, a status, and a link to the report artefact written to `reports/`. When the auditor asks "was this control operating continuously?", the answer is a list of execution timestamps.

There is one failure mode worth acknowledging: if the Rundeck service goes down — if the Docker container crashes or the host runs out of disk — the scheduled jobs do not fire. This is a monitoring gap that the Rundeck deployment should cover: the monitoring stack's container health alerting should include Rundeck. If Rundeck is down, the compliance report does not run, and the ops team should know about that before it becomes an audit finding.

Scheduled jobs shift the reliability requirement from human memory to system availability. The second is easier to monitor and alert on than the first.

---

**Next:** Chapter 36 brings together the Rundeck execution log and the GitLab pipeline artefact into a unified compliance record — and explains why a regulated environment needs both.
