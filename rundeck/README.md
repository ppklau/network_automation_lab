# Rundeck Orchestration — ACME Investments Lab

Phase 12 of the ACME Investments Network Automation Lab. Rundeck provides a
web UI and REST API for running, scheduling, and auditing Ansible playbooks
against the lab network without requiring direct CLI access to the control
node.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture](#architecture)
3. [Deploy](#deploy)
4. [First-Time Setup](#first-time-setup)
5. [User Accounts](#user-accounts)
6. [Job Library](#job-library)
7. [Approval Simulation](#approval-simulation)
8. [Approval Workflow Walkthrough](#approval-workflow-walkthrough)
9. [Access](#access)
10. [Lab Exercise Links](#lab-exercise-links)

---

## Prerequisites

Before starting the Rundeck service:

- **containerlab topology running** — the `acme-mgmt` Docker network must exist.
  It is created automatically when containerlab deploys the `acme-lab` topology:
  ```
  sudo containerlab deploy -t acme-lab.clab.yml
  ```
- **Docker monitoring stack running** — Prometheus, Grafana, Alertmanager:
  ```
  cd monitoring && docker compose up -d
  ```
- **SSH key for lab devices** — Ansible (running inside the Rundeck container)
  needs an SSH key to reach lab devices. The `~/.ssh` directory from the Docker
  host is mounted read-only into the container. Ensure the key used for lab
  device access is present:
  ```
  ls -la ~/.ssh/id_rsa      # must exist and be chmod 600
  ```
  If you use a different key name, update the `volumes:` entry in
  `monitoring/docker-compose.yml` and the `project.ssh.keypath` in
  `rundeck/projects/acme/project.properties`.

---

## Architecture

```
  Browser / CI
      │
      ▼ :4440
  ┌──────────────────────────────────────────────────────────────────┐
  │  Rundeck 5.8.0 container (acme-rundeck)                          │
  │                                                                  │
  │  ┌──────────────────────────────────────────┐                    │
  │  │  ansible-playbook (Python venv)          │                    │
  │  │  + NAPALM + Netmiko                      │                    │
  │  └──────────────────────────────────────────┘                    │
  │                                                                  │
  │  Volumes:                                                         │
  │    /opt/acme-lab  ←── ../  (entire lab directory, rw)            │
  │    ~/.ssh         ←── host ~/.ssh (ro)                           │
  └──────────────────────────────────────────────────────────────────┘
      │
      │  acme-mgmt Docker network (containerlab)
      ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Lab devices: spine-lon-01/02, leaf-lon-01..04,                  │
  │               border-lon-01/02, border-nyc-01,                   │
  │               border-sin-01, border-fra-01,                      │
  │               branch-lon-01, branch-nyc-01                       │
  └─────────────────────────────────────────────────────────────────┘

  Rundeck also shares the 'monitoring' bridge network with Prometheus,
  Grafana, and Alertmanager.
```

All job steps execute `ansible-playbook` locally inside the Rundeck container.
The lab directory (`/opt/acme-lab`) is bind-mounted, so playbooks, inventory,
the SoT, and output files (reports, state, logs) are all accessible.

---

## Deploy

Add Rundeck to an already-running monitoring stack:

```bash
cd monitoring && docker compose up -d rundeck
```

Or start the full stack (first time):

```bash
cd monitoring && docker compose up -d
```

Build the Rundeck image (Python + Ansible layer) on first run. This takes
approximately 2–4 minutes depending on network speed.

---

## First-Time Setup

### 1. Wait for Rundeck to become ready

The JVM startup takes ~60–90 seconds. Watch the logs:

```bash
docker compose -f monitoring/docker-compose.yml logs -f rundeck
```

Rundeck is ready when you see:
```
Grails application running at http://0.0.0.0:4440 in environment: production
```

Then open http://localhost:4440 in your browser.

### 2. Log in as admin

- URL: http://localhost:4440
- Username: `admin`
- Password: `acme-lab`

### 3. Create the `acme` project

If the project does not already exist (it may be auto-created from the
`project.properties` file on first start):

1. Click **New Project** on the Rundeck home page
2. Project name: `acme`
3. Label: `ACME Lab`
4. Leave node source as **Local** (the Rundeck container is the only node;
   Ansible handles SSH to lab devices internally)
5. Click **Create**

### 4. Import jobs

Run the import script from the lab root:

```bash
./rundeck/import_jobs.sh
```

The script will:
- Wait for Rundeck to be ready (polls the API)
- Create the `acme` project if it does not exist
- Import all YAML job definitions from `rundeck/jobs/`
- Print the result of each import

To re-run after editing a job definition, use the same script — it passes
`dupeOption=update` so existing jobs are updated in place.

### 5. Create user accounts

Rundeck Community stores users in a realm.properties file (or via the UI).

In the Rundeck UI:
1. Go to **Admin Menu** (top right) > **User Manager**
2. Create two users:

| Username    | Password    | Group(s)                          |
|-------------|-------------|-----------------------------------|
| acme-ops    | acme-ops    | acme-ops-group                    |
| acme-senior | acme-senior | acme-senior-group, acme-ops-group |

Alternatively, edit the Rundeck realm.properties file inside the container:

```bash
docker exec -it acme-rundeck bash
# Inside the container:
cat >> /home/rundeck/server/config/realm.properties <<'EOF'
acme-ops: MD5:acme-ops,acme-ops-group
acme-senior: MD5:acme-senior,acme-senior-group,acme-ops-group
EOF
```

Note: for a lab the plaintext password format is also acceptable:
```
acme-ops: acme-ops,acme-ops-group
acme-senior: acme-senior,acme-senior-group,acme-ops-group
```
Restart the container after editing: `docker compose -f monitoring/docker-compose.yml restart rundeck`

### 6. SSH key verification

The Rundeck container mounts `~/.ssh` from the Docker host. Verify Ansible
can reach a lab device from inside the container:

```bash
docker exec -it acme-rundeck bash
ansible -i /opt/acme-lab/inventory/hosts.yml spine-lon-01 -m ping
```

If this fails, check:
- `~/.ssh/id_rsa` exists on the host and has permissions `600`
- The public key is in the `authorized_keys` of lab devices
- Lab devices are reachable on the `acme-mgmt` network

---

## User Accounts

| Username    | Password    | Role                | Access                                         |
|-------------|-------------|---------------------|------------------------------------------------|
| admin       | acme-lab    | Administrator       | Full system and project access                 |
| acme-ops    | acme-ops    | Operations Engineer | ACME/Scheduled and ACME/Operations jobs only   |
| acme-senior | acme-senior | Senior Engineer     | All jobs including ACME/Lifecycle/Restricted   |

---

## Job Library

| Job Name               | Group                       | Schedule          | Approval Required | Playbook Called         |
|------------------------|-----------------------------|-------------------|-------------------|-------------------------|
| Daily Health Check     | ACME/Scheduled              | Mon–Fri 07:00     | No                | daily_health_check.yml  |
| Compliance Report      | ACME/Scheduled              | Sunday 06:00      | No                | compliance_report.yml   |
| Maintenance Window     | ACME/Operations             | Manual            | Yes (simulated)   | maintenance_window.yml  |
| Emergency Change       | ACME/Operations             | Manual            | No (bypass log)   | push_configs / rollback |
| Leaf Switch RMA        | ACME/Lifecycle/Restricted   | Manual            | Yes (simulated)   | rma_leaf.yml            |
| Border Router RMA      | ACME/Lifecycle/Restricted   | Manual            | Yes (simulated)   | rma_border.yml          |
| OS Upgrade             | ACME/Lifecycle/Restricted   | Manual / Deferred | Yes (simulated)   | os_upgrade.yml          |

**Deferred execution (OS Upgrade):** when running the OS Upgrade job, click the
clock icon ("Schedule this execution") on the Run Job page to schedule it for a
specific future time. This is available in Rundeck Community.

---

## Approval Simulation

Rundeck Community (the open-source edition) does **not** have a native approval
queue or approval-hold workflow. That feature is part of **Rundeck Enterprise**
(also known as PagerDuty Process Automation).

This lab simulates approvals through two complementary mechanisms:

### Mechanism 1 — ACL-based role restriction

Jobs in the group `ACME/Lifecycle/Restricted` can only be executed by users in
`acme-senior-group`. The ACL is defined in `rundeck/acme.aclpolicy`.

This means that in practice, a junior engineer (`acme-ops`) cannot physically
submit an RMA or OS Upgrade execution. They would need to ask a senior engineer
to run it, which mirrors a real-world approval gate.

### Mechanism 2 — Mandatory approval fields

Jobs that require approval have two mandatory option fields:

- **`approved_by`** — the name of the engineer who authorised the change
- **`change_ticket`** — the change management reference (e.g. CHG-2026-0042)

These values are stored in Rundeck's execution history and are visible in the
job run audit log. They form the compliance record.

For the Border Router RMA (which requires two CAB approvers), there are two
separate fields: `approver_1` and `approver_2`.

### What this does not do

- It does not prevent the same person entering their own name in `approved_by`
- It does not send an approval request to a second person
- It does not hold the execution in a "pending" state awaiting approval

These limitations are inherent to Rundeck Community. For a genuine approval
queue, evaluate:
- **Rundeck Enterprise** — native approval UI with email notifications
- **ServiceNow / Jira Service Management integration** — trigger Rundeck jobs
  from a ITSM change ticket workflow via the Rundeck API
- **GitLab pipeline with manual gates** — the lab's CI/CD pipeline (Phase 11)
  can enforce approval via GitLab's protected environments feature

---

## Approval Workflow Walkthrough

This walkthrough demonstrates Exercise 13.2 using the Maintenance Window job.

### As acme-ops — submit a maintenance window request

1. Log in as `acme-ops` / `acme-ops`
2. Navigate to **Jobs** > **ACME** > **Operations**
3. Click **Maintenance Window**
4. Fill in the options:
   - **Target Device**: `leaf-lon-01`
   - **Action**: `enter`
   - **Maintenance Reason**: `Optic replacement on Ethernet3`
   - **Expected End Time**: `2026-04-12T22:00:00Z`
   - **Approved By**: *(leave blank — acme-ops cannot self-approve in a real process)*
   - **Change Ticket**: `CHG-2026-0042`

   Notice that `approved_by` is a required field — the job cannot be submitted
   without it. In a real process, `acme-ops` would obtain approval from a senior
   engineer first, then enter that name.

5. Enter the approver name as provided out-of-band (e.g. via Teams/Slack):
   `approved_by`: `Jane Smith`
6. Click **Run Job Now**

The job runs immediately (Community has no hold queue). The execution record
captures `approved_by=Jane Smith` and `change_ticket=CHG-2026-0042`.

### As acme-ops — attempt a restricted job

1. Still logged in as `acme-ops`
2. Navigate to **Jobs** > **ACME** > **Lifecycle** > **Restricted**
3. You will see the Leaf Switch RMA job listed (read access) but the **Run**
   button will be absent or disabled

This is the ACL restriction in action: `acme-ops-group` has `deny: [run]` on
the `ACME/Lifecycle/Restricted` group.

### As acme-senior — run a restricted job

1. Log in as `acme-senior` / `acme-senior`
2. Navigate to **Jobs** > **ACME** > **Lifecycle** > **Restricted**
3. Click **Leaf Switch RMA**
4. Fill in all fields including `approved_by` (your own name, since as a senior
   engineer you ARE the authorised approver for this job) and `change_ticket`
5. Click **Run Job Now**

The execution runs and the full audit trail is in Rundeck's execution history.

---

## Access

| Service     | URL                   | Credentials          |
|-------------|-----------------------|----------------------|
| Rundeck     | http://localhost:4440 | admin / acme-lab     |
| Rundeck     | http://localhost:4440 | acme-ops / acme-ops  |
| Rundeck     | http://localhost:4440 | acme-senior / acme-senior |
| Grafana     | http://localhost:3000 | admin / acme-lab     |
| Prometheus  | http://localhost:9090 | (no auth)            |
| Alertmanager| http://localhost:9093 | (no auth)            |

---

## Lab Exercise Links

| Exercise    | Title                              | Rundeck Jobs Used                          |
|-------------|------------------------------------|--------------------------------------------|
| Exercise 13.1 | Rundeck Setup and Configuration  | (setup only — no specific job)             |
| Exercise 13.2 | Approval Workflow Simulation     | Maintenance Window, Leaf RMA, Border RMA   |
| Exercise 13.3 | Scheduled Jobs                   | Daily Health Check, Compliance Report, OS Upgrade |
| Exercise 13.4 | Emergency Change Procedure       | Emergency Change                           |
| Exercise 13.5 | Rundeck API and CI Integration   | All jobs via REST API (`import_jobs.sh`)   |

### Quick reference — playbook to job mapping

| Ansible Playbook          | Rundeck Job            | Exercise    |
|---------------------------|------------------------|-------------|
| daily_health_check.yml    | Daily Health Check     | 13.3        |
| compliance_report.yml     | Compliance Report      | 13.3        |
| maintenance_window.yml    | Maintenance Window     | 13.2        |
| rma_leaf.yml              | Leaf Switch RMA        | 13.2        |
| rma_border.yml            | Border Router RMA      | 13.2        |
| os_upgrade.yml            | OS Upgrade             | 13.3        |
| push_configs.yml          | Emergency Change       | 13.4        |
| rollback.yml              | Emergency Change       | 13.4        |
