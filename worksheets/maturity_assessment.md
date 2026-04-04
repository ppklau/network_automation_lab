# Network Automation Maturity Assessment
## ACME Investments Lab — Module 12.4

This worksheet is designed to help you honestly evaluate where your organisation sits today across eight critical dimensions of network automation maturity. Rate each dimension on a scale from 0 to 4 using the scoring guide below. Work through each dimension with your team — disagreement between individuals is itself useful data. The ACME Investments lab, once completed, demonstrates Level 3 or higher on most dimensions. Use those benchmarks as a calibration anchor. After scoring all eight dimensions, transfer your scores to the Scoring Summary table and consult the Interpreting Your Score section to identify your maturity band and likely next initiatives.

---

## How to Score

| Score | Description |
|-------|-------------|
| 0 | Not started — manual process, no automation |
| 1 | Ad-hoc — some scripts exist, not standardised |
| 2 | Repeatable — documented process, runs consistently |
| 3 | Defined — SoT-driven, pipeline-enforced, auditable |
| 4 | Optimised — self-healing, continuously measured, evidence-based change |

---

## Dimension 1 — Source of Truth

The Source of Truth (SoT) is the authoritative record of your intended network state. In a financial institution, an accurate and governed SoT is a regulatory as well as an operational requirement: auditors expect to be able to trace every device configuration back to an approved record. Without a SoT, every configuration change is an undocumented deviation, and compliance evidence must be assembled manually after the fact. A well-structured SoT eliminates this burden by making the intended state explicit, version-controlled, and machine-readable. This dimension measures not just whether a SoT exists, but whether it is genuinely authoritative — meaning configs are generated from it, and discrepancies between it and the live network are surfaced as alerts rather than discovered during incidents.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** Device configurations are the source of truth; no structured record of intent exists
- **1:** A spreadsheet or wiki exists but is rarely updated and is not machine-readable
- **2:** Structured YAML or a CMDB exists and is maintained manually; used for documentation
- **3:** SoT is authoritative; all configurations are generated from it; discrepancies between SoT and live devices raise alerts
- **4:** SoT is continuously reconciled against devices; drift is auto-detected, reported, and can trigger automated remediation

**ACME lab after Phase 3:** Level 3

---

## Dimension 2 — Configuration Generation

Configuration generation measures how reliably and consistently your organisation produces device configurations from its declared intent. Manual configuration authoring is a primary source of human error and change-induced outages; templating removes this variability by separating intent from syntax. For a multi-vendor environment — common in financial institutions that have grown through acquisition — a disciplined templating approach is especially valuable because it enforces policy consistency regardless of platform. This dimension also covers whether templates are version-controlled, peer-reviewed, and testable as code artefacts in their own right.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** Configs are written by hand, directly on devices or in a text editor
- **1:** Copy-paste templates exist in email or wikis; used inconsistently across the team
- **2:** Jinja2 or equivalent templates exist in version control; used for most standard changes
- **3:** All configs are rendered from SoT data through a pipeline; multi-vendor differences are abstracted; no hand-edited configs reach production
- **4:** Templates are linted, unit-tested, and covered by regression tests; any template change triggers a full render-and-diff across the device estate

**ACME lab after Phase 4:** Level 3

---

## Dimension 3 — Change Pipeline

A change pipeline is the structured, auditable path that a network change must follow from intent to deployment. In a regulated financial environment, change control is a compliance requirement as well as an operational safeguard: every change must be traceable to an approver, a ticket, and a test result. An automated pipeline enforces this discipline consistently, whereas manual change processes depend on individuals following procedures correctly under time pressure. This dimension measures whether your pipeline is merely documented or whether it is mechanically enforced — meaning a change cannot reach production without passing defined gates.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** Changes are applied directly to devices by individuals; no formal process
- **1:** A change management process exists on paper; compliance is manual and inconsistent
- **2:** Changes go through a ticketing system; peer review is expected but not enforced
- **3:** A CI/CD pipeline exists; changes must pass automated lint and syntax checks before an approval gate; deployment is logged and auditable
- **4:** Pipeline includes diff review, automated rollback on failure, and post-deployment verification; full audit trail meets regulatory review requirements

**ACME lab after Phase 5:** Level 3

---

## Dimension 4 — Intent Verification

Intent verification is the practice of asserting, before deployment, that a proposed change will produce the intended network behaviour. Tools such as Batfish allow the network to be modelled mathematically so that reachability, routing policy, and security zone isolation can be verified against design intents without touching a live device. For a financial institution, this is particularly important for proving that trading zone isolation and regulatory segmentation requirements will be maintained through any change. This dimension measures whether verification is an afterthought — performed manually post-deployment — or a mandatory gate that every change must pass.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** No formal verification; changes are validated by observation after deployment
- **1:** Manual peer review of configs before deployment; no automated checking
- **2:** Automated syntax and lint checks exist; some manual spot-checks for routing or ACLs
- **3:** Model-based verification (e.g., Batfish) checks reachability and policy for every change; design intents are encoded as automated tests
- **4:** Compliance-as-code tests cover all regulatory requirements; intent tests run in CI and block merges; test coverage is measured and reported

**ACME lab after Phase 6:** Level 3

---

## Dimension 5 — Day-2 Operations

Day-2 operations covers the ongoing work of keeping the network aligned with its intended state: detecting configuration drift, running compliance checks, performing health assessments, and producing evidence for audits. Many organisations have strong deployment automation but neglect the steady-state monitoring of whether what was deployed has remained as intended. In a financial institution, drift between intended and actual configuration is both an operational risk and a compliance risk — regulators increasingly expect continuous evidence of controls, not point-in-time snapshots. This dimension measures whether Day-2 tasks are automated and scheduled, or depend on periodic manual effort.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** No systematic drift detection; issues discovered through incidents or complaints
- **1:** Ad-hoc scripts run occasionally; no scheduled compliance reporting
- **2:** Manual compliance checks run regularly; drift detection exists but is not automated end-to-end
- **3:** Scheduled pipelines run drift detection, compliance reports, and health checks; results are stored and trended; deviations generate tickets
- **4:** All Day-2 tasks are automated and self-documenting; compliance reports are generated on-demand for regulators; anomalies trigger automated investigation workflows

**ACME lab after Phase 7:** Level 3

---

## Dimension 6 — Hardware Lifecycle

Hardware lifecycle automation covers the provisioning and decommissioning of physical devices: Zero-Touch Provisioning (ZTP) for new deployments, structured RMA workflows for hardware failures, and tracked OS upgrade campaigns. Manual provisioning is slow, error-prone, and expensive at scale; in a geographically distributed financial institution with branch offices in multiple jurisdictions, it is also a significant source of configuration inconsistency. This dimension also covers OS version governance — whether your estate runs approved, tracked OS versions or has accumulated uncontrolled diversity across sites.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** All device provisioning is manual; OS versions are untracked; RMA requires on-site engineer
- **1:** Provisioning runbooks exist; OS versions are documented informally; RMA process is ad-hoc
- **2:** Provisioning checklist is documented and followed consistently; OS version tracking exists in a spreadsheet or CMDB
- **3:** ZTP is operational for at least one platform; RMA workflow is automated through SoT update; approved OS versions are enforced through the pipeline
- **4:** ZTP covers all platforms; OS upgrade campaigns are automated; lifecycle state is visible in dashboards; EoL/EoS alerts are generated automatically

**ACME lab after Phase 8:** Level 3

---

## Dimension 7 — Observability

Observability measures how well your organisation can understand the current and historical state of the network from collected data. Metrics, alerting, and dashboards are the operational foundation for rapid incident detection and diagnosis; without them, MTTR is dominated by the time required to manually gather state. For a financial institution, observability is also a component of regulatory reporting: evidence of monitoring coverage, alert response times, and incident timelines may be required by compliance frameworks. This dimension measures not just whether monitoring tools exist, but whether the data they produce is acted upon and whether MTTR is measured and improving.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** No structured monitoring; issues discovered by users or manual polling
- **1:** SNMP or basic ping monitoring exists; alerts go to email; no dashboards
- **2:** Metrics collected and visualised; alerting is configured but may be noisy; MTTR is not formally measured
- **3:** Comprehensive metrics pipeline (e.g., SNMP/gNMI to InfluxDB/Prometheus); dashboards cover all critical paths; alerting is tuned and actionable; MTTR is measured
- **4:** Observability data feeds automated remediation workflows; dashboards include SLO/SLA tracking; alert noise is continuously reduced; MTTR trend is formally reported to management

**ACME lab after Phase 9:** Level 3

---

## Dimension 8 — Operational Resilience

Operational resilience measures how confidently your organisation can recover from failures — both of individual network components and of the automation tooling itself. Resilience is not just about having backups; it requires that DR procedures have been tested, that rollback from a failed change is a defined and practiced operation, and that runbooks accurately reflect current architecture. For a financial institution, resilience obligations are typically codified in regulatory frameworks (e.g., DORA in the EU) that require documented, tested, and evidenced recovery capabilities. A high score here means that failures are expected, planned for, and recoverable without heroic effort.

Score: [ ] 0   [ ] 1   [ ] 2   [ ] 3   [ ] 4

Evidence / notes:
_____________________________________________

Indicators by level:
- **0:** No DR testing; rollback means manually reverting configs; runbooks are out of date or absent
- **1:** DR procedures are documented but untested; rollback is manual and undocumented; runbooks exist but are not maintained
- **2:** DR procedures are tested annually; rollback is documented and practiced; runbooks are reviewed periodically
- **3:** DR is tested at least quarterly with recorded results; automated rollback is proven in the pipeline; runbooks are version-controlled and reviewed with each major change
- **4:** DR tests are automated and run as part of the change pipeline; rollback RTO is measured and meets SLA; runbook accuracy is enforced through automated validation; resilience evidence is available on-demand for regulators

**ACME lab after Phase 10 / Capstone:** Level 3

---

## Scoring Summary

| Dimension | Score (0–4) | Priority |
|-----------|-------------|----------|
| 1. Source of Truth | | |
| 2. Configuration Generation | | |
| 3. Change Pipeline | | |
| 4. Intent Verification | | |
| 5. Day-2 Operations | | |
| 6. Hardware Lifecycle | | |
| 7. Observability | | |
| 8. Operational Resilience | | |
| **Total** | **/32** | |

---

## Interpreting Your Score

| Range | Maturity Band | Typical Profile |
|-------|---------------|-----------------|
| 0–8   | Initial | Manual operations; automation is opportunistic and individual-led |
| 9–16  | Developing | First pipeline exists; SoT partially adopted; repeatability improving |
| 17–24 | Defined | SoT-driven; pipeline enforced; changes are auditable end-to-end |
| 25–28 | Managed | Intent verification in place; Day-2 automated; MTTR measured |
| 29–32 | Optimised | Self-healing capabilities; DR proven; compliance artefacts generated automatically |

---

## Next Initiatives

Based on your lowest-scoring dimensions, here are typical next steps:

**If Source of Truth < 3:** Adopt a YAML-based SoT using the structure demonstrated in this lab; start with a single site or device type and expand incrementally. Version-control the SoT repository from day one, and enforce the rule that no configuration reaches a device unless it was generated from the SoT. Assign a named owner for SoT governance.

**If Change Pipeline < 3:** Implement a Git-based workflow for all configuration changes, with CI checks (linting, syntax validation) as a mandatory gate before peer review. Even a simple pipeline that validates configs before deployment eliminates a significant class of outage. Document the pipeline and train all team members before making it mandatory.

**If Intent Verification < 2:** Introduce Batfish or an equivalent model-based verification tool for your highest-risk change types first — typically BGP routing policy and security zone changes. Encode your top five design intents as automated tests, run them in a sandbox environment initially, and build confidence before integrating them into the change pipeline as blocking gates.

**If Day-2 Operations < 2:** Schedule a weekly automated drift detection run using the tooling demonstrated in this lab. Produce a compliance report in a format that can be shared with your security and audit teams, even if it requires manual distribution initially. Automate the distribution once the content of the report is stable and trusted.

**If Observability < 2:** Deploy a metrics pipeline for your most critical devices first — core switches, border routers, and WAN edges. Use the Telegraf/InfluxDB/Grafana stack demonstrated in this lab as a starting point. Define three to five key dashboards that your operations team will actually use daily; avoid over-engineering the first deployment. Establish MTTR as a tracked metric from the beginning.

**If Operational Resilience < 2:** Run a tabletop DR exercise within the next quarter using your current runbooks; document every gap you find and assign remediation owners. Practice automated rollback in a lab environment until the team is confident. Review and update runbooks immediately after every major change; stale runbooks are worse than no runbooks because they create false confidence during an incident.

---

## Using This Assessment for Engagement Planning

This worksheet is designed to function as both a self-improvement tool and a structured basis for consulting engagement scoping. Each dimension with a score below 3 represents a defined gap between current state and a well-governed, audit-ready network automation practice — and each of those gaps corresponds to a scoped body of work that can be delivered incrementally. In practice, organisations rarely need to lift every dimension simultaneously; the Scoring Summary table makes it straightforward to prioritise the two or three dimensions that carry the greatest operational and regulatory risk, and to build a phased roadmap from there. For managers and architects preparing a business case, the dimension scores provide concrete, evidence-backed language for communicating risk exposure and investment rationale to leadership. An experienced network automation consultant can use this assessment as the foundation for a discovery engagement: validating the scores against observed evidence, mapping gaps to deliverables, and producing a costed roadmap that connects each initiative to a measurable improvement in maturity band and regulatory posture.

---

*This worksheet accompanies the ACME Investments Network Automation Lab Guide.*
*For consulting enquiries: contact the author via the Handbook (ppklau.github.io/network_automation_handbook/).*
