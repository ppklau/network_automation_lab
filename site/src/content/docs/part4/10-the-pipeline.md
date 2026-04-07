---
title: "Chapter 10: What the Pipeline Replaces"
---

# Part 4 — The Pipeline

# Chapter 10: What the Pipeline Replaces

> 🔵 **Strategic** — sections marked
> 🟡 **Practitioner** — Module 4.1, 4.2

---

## Before and after

> 🔵 **Strategic**

Consider a change that ACME's network team made frequently before automation: adding a new branch office.

**Before (manual process):**

1. Receive a ticket from the business. Clarify details over email over several days.
2. Allocate an ASN by searching a spreadsheet, hoping the last person kept it up to date.
3. Allocate an IP subnet by searching a different spreadsheet.
4. Write the branch router config by hand, adapting from a previous branch config.
5. Write the upstream border router config changes by hand.
6. Email the config to a colleague for peer review. Wait.
7. Schedule a maintenance window (2-hour window for a 15-minute change, because something always goes wrong).
8. Log into the branch router, paste the config, verify BGP comes up.
9. Log into border-lon-01, add the neighbor, verify BGP comes up.
10. Email the requestor that the branch is live.
11. Hopefully update the spreadsheets. Sometimes forget.

Elapsed time: 3–5 business days. Change risk: moderate (hand-typed configs, no automated verification). Audit evidence: an email chain and a ticket. Consistency with other branches: depends on the engineer.

**After (pipeline-driven):**

1. A team member adds the branch record to `sot/devices/branches/uk_branches.yml` — one YAML block. 5 minutes.
2. Push to GitLab. The pipeline validates the ASN (unique, in correct pool), the subnet (from branch pool, not overlapping), the zone permissions (CORPORATE only — branches cannot have TRADING).
3. Batfish verifies the rendered configs. BGP standards pass (MD5 configured, route-maps present, only the /29 prefix is advertised).
4. An engineer reviews and approves the diff in GitLab.
5. The pipeline pushes the rendered config to the branch router and the updated config to border-lon-01.
6. The verify stage confirms BGP Established.
7. Artefacts stored. SoT is authoritative and up to date.

Elapsed time: 30–60 minutes (mostly waiting for pipeline stages). Change risk: low (SoT-rendered, Batfish-validated, automated verification). Audit evidence: GitLab pipeline run, diff artefact, pre/post BGP state. Consistency: identical process for every branch.

The pipeline does not just make this faster. It makes it auditable, consistent, and repeatable in a way that the manual process never could be.

---

## The seven stages

```
┌──────────┐   ┌──────────────┐   ┌────────┐   ┌──────┐
│ validate │ → │ intent-check │ → │ render │ → │ diff │
└──────────┘   └──────────────┘   └────────┘   └──────┘
                                                    │
                                              ┌─────▼──────┐
                                              │   approve  │ ← manual gate
                                              └─────┬──────┘
                                                    │
                                       ┌────────────┼────────────┐
                                       │                         │
                                  ┌────▼───┐             ┌───────▼────────┐
                                  │  push  │             │ rollback-on-   │
                                  └────┬───┘             │ failure        │
                                       │                 │ (on_failure)   │
                                  ┌────▼────┐            └────────────────┘
                                  │ verify  │
                                  └─────────┘
```

### Stage 1: validate

What runs:
- `yamllint` on all YAML in `sot/`, `design_intents/`, `requirements/`, `inventory/`, `playbooks/`
- `python3 scripts/validate_sot.py` — schema checks, cross-file consistency, Frankfurt constraint
- Change freeze check — if a freeze is active, non-emergency pipelines fail here

What it catches: syntax errors, schema violations, duplicate ASNs, invalid intent_refs, prohibited VLANs, frozen change windows.

**If it fails:** No rendering happens. No Batfish analysis. No device is touched. Fix the error and push again.

### Stage 2: intent-check

What runs:
- Batfish starts with the rendered configs (from the last successful render artefact)
- `batfish/run_checks.sh` — builds a snapshot, runs the full pytest suite
- JUnit report published to GitLab as a test report

What it catches: zone isolation violations, routing policy violations, BGP standard failures, resilience gaps — all without connecting to any device.

> 🔴 **Deep Dive** — Batfish analyses the proposed configs, not the currently deployed configs. This means Batfish catches violations that would exist after the push, not violations that already exist. If someone made an out-of-band change that creates a zone violation, Batfish will not catch it here (it is not modelling the running config). The drift detection and compliance playbooks in Module 8 address this.

### Stage 3: render

What runs:
- `ansible-playbook playbooks/render_configs.yml`
- Runs locally on the GitLab runner — no device connections
- Rendered configs published as a pipeline artefact (retained 12 weeks)

**Why render after intent-check, not before?** Batfish in stage 2 uses the configs from the last successful render. For a new change, Batfish has already validated the proposed SoT state, which is sufficient for most validation. The render in stage 3 produces the artefact that stage 6 (push) will use.

### Stage 4: diff

What runs:
- Shell diff between the newly rendered configs and the configs from the last push
- Diff published as a pipeline artefact

This is the human-readable record of what will change. Reviewers look at this before approving the push.

### Stage 5: approve (manual gate)

A human engineer reviews the diff and clicks **Run** in GitLab to release the push. This is the manual control that corresponds to the "change approved by a second engineer" requirement in FCA SYSC 8.

The gate only appears on the `main` branch. Feature branches can push to the render and diff stages automatically — useful for development — but only `main` can reach the push stage.

> 🔵 **Strategic** — The approve stage is often the most contentious part of the pipeline design. Some teams want fully automated deployments (no manual approval). Some want approval at every stage. ACME's approach is a reasonable middle ground: automated validation (Batfish, schema checks) replaces the reviewer's need to audit the config line by line; the human reviewer's job is to assess the business impact of the change, not to validate the syntax. That division of labour makes the approval meaningful rather than theatrical.

### Stage 6: push

What runs:
- `ansible-playbook playbooks/push_configs.yml`
- Targets only `lab_state: active` devices
- Serial 20%: pushes to 20% of devices at a time, not all at once
- Captures pre/post state
- If any device fails, the push stops

### Stage 7: verify

What runs:
- `ansible-playbook playbooks/verify_state.yml`
- BGP session status, interface up/down, reachability checks
- If any check fails, the `rollback-on-failure` job triggers

---

## The change freeze gate

```bash
cat gitlab/change_freeze.yml
```

```yaml
CHANGE_FREEZE_ENABLED: "false"
FREEZE_START: "2024-12-20T18:00:00"
FREEZE_END: "2025-01-02T08:00:00"
FREEZE_REASON: "Year-end trading halt — all non-emergency changes frozen"
FREEZE_SCOPE: "all"
EMERGENCY_KEYWORD: "[emergency]"
EMERGENCY_APPROVERS:
  - "head.of.network@acme.example.com"
  - "ciso@acme.example.com"
```

When `CHANGE_FREEZE_ENABLED: "true"`, the validate stage reads this file and fails any pipeline whose commit message does not contain the emergency keyword. This is a technical enforcement of a business policy — changes are not just discouraged during freeze windows, they are blocked.

> 🔵 **Strategic** — The emergency bypass (`[emergency]`) is important. A freeze that cannot be bypassed for genuine emergencies is a freeze that engineers will circumvent by going directly to devices. The bypass keyword should be logged and reviewed: any pipeline that used the emergency bypass during a freeze window should be reviewed by the emergency approvers after the fact. The audit trail makes circumvention visible — and visible circumvention, reviewed retrospectively, is a much better outcome than invisible circumvention.

---

## Exercise 4.1 — Trigger a pipeline failure

> 🟡 **Practitioner**

Run the full pipeline locally to see what each stage produces:

```bash
# Stage 1: validate
yamllint sot/ && python3 scripts/validate_sot.py
echo "Validate: $?"

# Stage 2: intent-check (requires Batfish running)
bash batfish/run_checks.sh
echo "Intent-check: $?"

# Stage 3: render
ansible-playbook playbooks/render_configs.yml
echo "Render: $?"
```

Now introduce a validate-stage failure. Edit `sot/devices/lon-dc1/leaf-lon-01.yml` and add an invalid platform:

```yaml
platform: invalid_platform
```

Run stage 1 again. Observe the failure. Restore the file. Run stage 1 again to confirm it passes.

**Question:** If stage 1 fails in the real GitLab pipeline, does stage 2 (Batfish) still run? Look at the `needs:` directives in `.gitlab-ci.yml`.

---

## Exercise 4.2 — Read the audit trail

> 🟡 **Practitioner**

After any config push (from Chapter 9 or your own change), examine the full audit trail:

```bash
ls state/
cat state/push_record_*.yml | head -30
cat state/pre_push_leaf-lon-01_*.json | python3 -m json.tool | grep -A5 "bgp"
```

Answer:
1. What timestamp is recorded in the push record?
2. Is the pre-push BGP state stored per-device or aggregated?
3. If a regulator asked "what was the BGP state of leaf-lon-01 at 14:32 on the day of change X?", could you answer that from the stored state?

*Handbook reference: Chapter 5 (CI/CD for network changes), Chapter 9 (Change management and compliance)*
