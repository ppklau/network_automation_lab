---
title: "Chapter 16: Compliance Reporting and Audit Artefacts"
---

## The Regulator's Question

During a MiFID II audit, a regulator asked ACME's head of network engineering a straightforward question: "Can you show me that Telnet has never been enabled on any device in your trading network?"

The answer took two engineers a full day. They SSHed into 23 devices, ran `show running-config | include telnet`, pasted results into a spreadsheet, and wrote a summary email. The email was the audit evidence.

The regulator accepted it. But she noted that the evidence was produced manually, could not be independently verified, and did not demonstrate *continuous* compliance — only compliance at the moment of the audit.

The following year, the same question took 90 seconds.

```bash
ansible-playbook playbooks/compliance_report.yml
```

The output: a machine-generated report with per-device check results, a SHA256 manifest, and a reference to the git commit hash of the SoT at the time of the run. Any claim in the report can be verified by re-running the playbook against the same SoT commit.

This chapter covers `compliance_report.yml` and `audit_artefact.yml` — the two playbooks that turn your automation into regulatory evidence.

---

## Compliance Report

`playbooks/compliance_report.yml` evaluates every device against a fixed set of REQ checks drawn from `sot/compliance/regulatory.yml`.

### Checks Performed

| Code | Check | Severity | Standard |
|---|---|---|---|
| REQ-004 | SSH configured and not shutdown | CRITICAL | FCA SYSC 8.1 |
| REQ-008 | BGP MD5 on all peers | CRITICAL | Internal policy |
| REQ-012 | NTP synchronised | WARNING | MiFID II Art. 50 |
| REQ-017 | Telnet disabled | CRITICAL | FCA SYSC 8.1 |
| REQ-019 | No default SNMP community strings | CRITICAL | Internal policy |
| REQ-022 | No interfaces in err-disabled state | WARNING | Internal policy |

The EOS checks are evaluated by `templates/compliance/eos_checks.j2` — a Jinja2 template that takes collected show command output and produces a structured JSON result per device. FRR checks run as inline Python in the playbook itself.

### Running a Compliance Check

```bash
# Full estate
ansible-playbook playbooks/compliance_report.yml

# Single device (useful for post-remediation spot check)
ansible-playbook playbooks/compliance_report.yml --limit leaf-lon-02

# Write JSON output for ingestion
ansible-playbook playbooks/compliance_report.yml -e output_format=json
```

### Reading the Report

```
ACME Network Compliance Report — 2026-04-03T09:00:00Z
=====================================================
Overall status: FAIL  (1 device failed)

leaf-lon-02:
  REQ-017  telnet_disabled          FAIL [CRITICAL]
    Detail: ip telnet server enable is present
    Remediation: conf t → no ip telnet server enable → write mem

  REQ-004  ssh_configured           PASS
  REQ-008  bgp_md5_all              PASS
  REQ-012  ntp_synchronised         PASS
  REQ-019  snmp_no_default_community PASS
  REQ-022  no_err_disabled          PASS

All other devices: PASS (11/12)

Report written to: reports/compliance_2026-04-03T090012Z.txt
```

The playbook fails with `rc=1` on any CRITICAL failure. In the CI pipeline, this makes the compliance job a hard gate — a merge to main that introduces a Telnet configuration will never deploy.

---

## Exercise 4.3 — Telnet Compliance Violation {#ex43}

🟡 **Practitioner**

### Scenario

During emergency troubleshooting of a circuit issue at the London DC, an engineer enabled Telnet on `leaf-lon-02` to test connectivity from a legacy test tool. The troubleshooting session resolved the issue, but Telnet was never disabled. The device has been running with Telnet enabled for several days.

This is a REQ-017 violation. In ACME's trading network, Telnet exposure on any network device is a reportable incident.

### Inject the Fault

```bash
ansible-playbook scenarios/ch07/ex43_inject.yml
```

### Your Task

1. **Run the compliance report:**

   ```bash
   ansible-playbook playbooks/compliance_report.yml --limit leaf-lon-02
   ```

   Confirm it fails with `REQ-017 FAIL [CRITICAL]`.

2. **Check the drift report** — does drift detection also catch this?

   ```bash
   ansible-playbook playbooks/drift_detection.yml --limit leaf-lon-02
   ```

   What severity does it classify the Telnet line as?

3. **Remediate** using `push_config.yml` to restore the SoT-defined config:

   ```bash
   ansible-playbook playbooks/push_config.yml --limit leaf-lon-02
   ```

4. **Verify:**

   ```bash
   ansible-playbook scenarios/ch07/ex43_verify.yml
   ```

5. **Re-run the compliance report** and confirm leaf-lon-02 is back to PASS.

### What to Notice

- Both drift detection and compliance reporting catch this violation, but they answer different questions. Drift says "what changed?" — the `ip telnet server enable` line is an OOB addition. Compliance says "does the device meet the standard?" — the answer is No, regardless of *how* Telnet got enabled.
- In a real audit, you would produce the compliance report *before* remediation (as evidence of detection) and *after* remediation (as evidence of fix). The `audit_artefact.yml` playbook captures exactly this pattern.

> **Critical pattern:** The compliance check is not a one-time gate. In production, it runs nightly. If someone enables Telnet at 3 AM, the 06:00 compliance job detects it and pages the on-call engineer. The time-to-detection is hours, not weeks.

---

## Audit Artefacts

`playbooks/audit_artefact.yml` generates machine-readable evidence suitable for regulatory submission. It is designed to run in two phases around a change:

```bash
# Before the change
ansible-playbook playbooks/audit_artefact.yml \
  -e "phase=pre change_id=CHG-2026-0412"

# Apply the change
ansible-playbook playbooks/push_config.yml --limit border-lon-01

# After the change
ansible-playbook playbooks/audit_artefact.yml \
  -e "phase=post change_id=CHG-2026-0412"
```

### What Gets Written

```
state/audit/CHG-2026-0412/
  pre_border-lon-01.json     # show command output before
  post_border-lon-01.json    # show command output after
  diff_border-lon-01.txt     # unified diff between pre and post
  manifest.json              # SHA256, CI metadata, regulatory refs
```

### The Manifest

`manifest.json` contains everything a regulator needs to verify the change was controlled:

```json
{
  "change_id": "CHG-2026-0412",
  "generated_at": "2026-04-03T14:22:11Z",
  "sot_commit": "a3f9c21",
  "sot_commit_author": "Alice Chen <alice@acme.com>",
  "pipeline_url": "https://gitlab.acme.internal/network/pipeline/1482",
  "devices": ["border-lon-01"],
  "diff_sha256": "8f4a2b1c...",
  "regulatory_refs": ["MiFID II Article 48", "FCA SYSC 8.1"],
  "pre_sha256": {"border-lon-01": "3c7d9e2a..."},
  "post_sha256": {"border-lon-01": "7b1f4c8d..."}
}
```

The `diff_sha256` field is the SHA256 hash of the unified diff file. Anyone can independently verify that the diff file has not been modified since the manifest was generated.

🔵 **Strategic: Why SHA256 signatures matter**

A regulator asking "what changed on your network on this date?" is asking a provenance question. Your answer needs to be verifiable — not just true, but demonstrably true.

Without SHA256 signing, the audit trail is: "here is a diff file we produced." Anyone could modify the diff file after the fact.

With SHA256 signing in a manifest committed to git: the regulator can verify that the diff file matches the hash in the manifest, and that the manifest was committed by a specific person at a specific time, and that the git commit cannot be altered without breaking the chain.

This is not paranoia. It is the same chain-of-custody reasoning that courts apply to digital evidence. MiFID II Article 48 requires firms to demonstrate that their record-keeping systems maintain integrity. SHA256 manifests, committed to a signed git history, satisfy this requirement in a way that a spreadsheet never can.

---

## Exercise 4.4 — Produce a Regulatory Artefact {#ex44}

🔴 **Deep Dive**

### Scenario

ACME's change management team is preparing documentation for a quarterly FCA submission. They need a machine-generated artefact demonstrating that a specific BGP route policy change on `border-lon-01` was applied under change control, with pre- and post-state captured.

### Your Task

1. **Capture pre-state:**

   ```bash
   ansible-playbook playbooks/audit_artefact.yml \
     -e "phase=pre change_id=CHG-2026-LAB-01" \
     --limit border-lon-01
   ```

2. **Make a controlled SoT change** — add a description to the existing `RM_INTERDC_OUT` route-map in `sot/devices/lon-dc1/border-lon-01.yml`:

   ```yaml
   route_maps:
     - name: RM_INTERDC_OUT
       description: "InterDC export policy — INTENT-008"  # add this line
   ```

3. **Push the change:**

   ```bash
   ansible-playbook playbooks/push_config.yml --limit border-lon-01
   ```

4. **Capture post-state:**

   ```bash
   ansible-playbook playbooks/audit_artefact.yml \
     -e "phase=post change_id=CHG-2026-LAB-01" \
     --limit border-lon-01
   ```

5. **Inspect the artefact:**

   ```bash
   cat state/audit/CHG-2026-LAB-01/manifest.json | python3 -m json.tool
   diff state/audit/CHG-2026-LAB-01/diff_border-lon-01.txt /dev/null
   ```

6. **Verify the SHA256:**

   ```bash
   sha256sum state/audit/CHG-2026-LAB-01/diff_border-lon-01.txt
   # Compare with diff_sha256 in manifest.json
   ```

### What to Notice

- The `manifest.json` is the document you would hand to a regulator. It references the pipeline URL, the engineer who committed the SoT change, and the specific articles being satisfied.
- In production, the GitLab CI environment variables (`CI_PIPELINE_URL`, `CI_COMMIT_AUTHOR`, `CI_JOB_ID`) are populated automatically. In the lab, they appear as empty strings, but the structure is identical.
- The SHA256 of the diff file is deterministic — run the same change twice against the same pre-state, and you get the same hash. This makes artefacts independently reproducible.

---

**Next:** Chapter 17 covers BGP prefix monitoring — a targeted check that catches route leaks and peer failures that health checks miss.
