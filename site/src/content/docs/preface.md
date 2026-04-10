---
title: "Preface"
---

## What this guide is

This guide puts you inside a real network automation transformation. Not a toy lab with three VLANs and a handful of commands to copy-paste — but a working financial services environment with zone isolation, regulatory constraints, multi-region BGP, a GitLab CI/CD pipeline, and automated compliance verification.

The organisation is ACME Investments: a fictional firm, but the problems are real. Trading systems that must be isolated from corporate users. A Frankfurt data centre with EU data residency requirements. Branch offices that need provisioning in minutes, not weeks. Change windows enforced technically, not just procedurally. Audit trails that satisfy regulators, not just internal review boards.

You inherit that environment, and you operate it. Every exercise is something a network engineer or architect actually does — diagnosing a BGP failure, detecting configuration drift, generating a compliance report, verifying that a Frankfurt leaf has no TRADING VLAN even after someone tried to add one.

This guide is the companion to the [Network Automation Handbook](https://ppklau.github.io/network_automation_handbook/). The Handbook explains what and why. This guide shows you how — in a working lab you can run on a 16GB laptop.

---

## How to use this guide

### Choose your track

Every section is labelled with one or more track markers. Pick the track that fits your role and read accordingly.

> **🔵 Strategic** — Narrative explanation, decision rationale, outcome framing. No CLI commands. For architects and managers who need to understand what is being built and why, without needing to build it themselves.

> **🟡 Practitioner** — The actual lab exercises: commands, configs, and output. For engineers doing the work.

> **🔴 Deep Dive** — Optional extensions that go further into implementation detail, edge cases, and advanced patterns. For senior engineers who want to understand the internals.

A manager can read every 🔵 section and skip the rest. An architect reads 🔵 sections and selectively dips into 🟡 to understand what they are specifying. An engineer reads everything.

### The exercise structure

Each practitioner exercise follows the same structure:

1. **Scenario** — a realistic business situation that motivates the exercise. Read this before doing anything.
2. **Guided walkthrough** — the first time a tool is introduced, every step is shown and explained.
3. **Your task** — apply the same tooling to a related problem with progressively less guidance.
4. **Verify** — run a provided script to confirm you achieved the learning objective.
5. **Debrief** — what was behind the problem, what a real incident involving this looked like, what you should remember.

### Lab state

Every exercise chapter starts with a reset command:

```bash
ansible-playbook scenarios/common/reset_lab.yml
ansible-playbook scenarios/common/verify_lab_healthy.yml
```

This returns the lab to a known-good state regardless of what you did in the previous chapter. You can reset at any time. Experimenting and breaking things is encouraged — you can always get back to a clean starting point.

---

## Prerequisites

Before starting Part 1, you need:

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker Engine | ≥ 24.0 | Docker Desktop works on macOS and Windows |
| containerlab | ≥ 0.54 | `bash -c "$(curl -sL https://get.containerlab.dev)"` |
| Python | ≥ 3.11 | Used for SoT validation scripts and Batfish interaction |
| Ansible | ≥ 9.0 (core 2.16) | `pip install ansible` |
| pybatfish | ≥ 0.36 | `pip install pybatfish` |
| Arista cEOS image | 4.32.2F | Requires free Arista account at arista.com |
| Git | any recent | Used throughout |

**RAM:** 16 GB minimum. 32 GB recommended if running GitLab locally.

**GitLab:** The pipeline exercises use GitLab CE. You can run it locally in Docker (`monitoring/docker-compose.yml` includes a GitLab stack), use a hosted GitLab.com account (free tier), or adapt the `.gitlab-ci.yml` for GitHub Actions.

---

## Handbook cross-references

Each chapter notes which Handbook chapters are most relevant. If an exercise touches a concept you want to understand more deeply, the Handbook is the place to start. The two products are designed to complement each other: the Handbook gives you the mental model, this guide gives you the working implementation.

---

## A note on the financial services context

ACME Investments is a financial services firm. That context is deliberate. Financial services networks have requirements that general-purpose network automation guides rarely address: zone isolation mandated by MiFID II, data residency constraints under GDPR, change traceability requirements from FCA SYSC 8, and auditability standards that mean "we reviewed it" is not enough — you need a signed, time-stamped record of what changed and why.

These requirements make the automation problem harder and more interesting. They also make the solutions more valuable: when automation generates your compliance evidence automatically, a task that once required a team of analysts working for days becomes a pipeline artefact produced on every push.

You do not need to work in financial services to benefit from this. Every organisation has compliance obligations, change control processes, and audit requirements. ACME's constraints are a particularly rigorous version of a universal problem.

---

*This is a proprietary commercial product. Purchased access is for individual use. Redistribution in any form is prohibited. See `LICENSE.md` for the full licence terms.*
