# Chapter 11: Change Freeze — Technical Enforcement of a Business Policy

> 🟡 **Practitioner** — Module 8.5
> 🔵 **Strategic** — sections marked

*Estimated time: 20 minutes*

---

## Scenario

It is 22 December. ACME's year-end trading halt starts on 20 December and runs through 2 January. The change management policy says: no non-emergency network changes during this period. Last year, an engineer pushed a "trivial" BGP timer change during the freeze. It caused an unexpected session flap. The trading platform raised an alert. The incident report took three weeks to close.

This year, ACME's head of network automation asked: "Can we make it technically impossible to push changes during the freeze, rather than relying on people remembering?"

The answer is yes, and the implementation is 40 lines of Python in a CI job.

---

## How the freeze works

> 🔵 **Strategic**

The freeze is a CI gate — a pipeline stage that fails non-emergency pipelines when a freeze is active. The gate runs as the first step in the validate stage, before any rendering or validation. If it fails, the pipeline stops immediately.

Three important design choices:

1. **Configuration, not code.** The freeze is activated by editing `gitlab/change_freeze.yml` and pushing to `main`. The change is audited in git. Activating or deactivating the freeze is itself a pipeline run.

2. **Emergency bypass exists and is logged.** Any pipeline whose commit message contains `[emergency]` passes the freeze check. The bypass is not a secret — it is documented in the freeze config. Every use of the bypass is visible in the git history.

3. **The gate is in the CI runner, not the approval step.** An engineer cannot circumvent the freeze by simply clicking the approve button — the validate stage fails before approve is ever reached. The only way past the freeze is the emergency keyword in the commit message.

---

## The freeze configuration

```bash
cat gitlab/change_freeze.yml
```

```yaml
CHANGE_FREEZE_ENABLED: "false"

# ISO 8601 timestamps — runner uses UTC
FREEZE_START: "2024-12-20T18:00:00"
FREEZE_END:   "2025-01-02T08:00:00"

FREEZE_REASON: "Year-end trading halt — all non-emergency changes frozen"
FREEZE_SCOPE: "all"   # or: ["push", "rollback"] — only specific pipeline types

EMERGENCY_KEYWORD: "[emergency]"
EMERGENCY_APPROVERS:
  - "head.of.network@acme.example.com"
  - "ciso@acme.example.com"

# Optional: recurring freeze (e.g., every Friday 17:00 – Monday 08:00)
FREEZE_RECURRING: false
FREEZE_RECURRING_START_DAY: "Friday"
FREEZE_RECURRING_START_TIME: "17:00"
FREEZE_RECURRING_END_DAY: "Monday"
FREEZE_RECURRING_END_TIME: "08:00"
```

---

## The freeze check in the pipeline

The validate stage in `.gitlab-ci.yml` includes:

```yaml
change-freeze-check:
  stage: validate
  script:
    - python3 -c "
import yaml, datetime, sys, os

config = yaml.safe_load(open('gitlab/change_freeze.yml'))
if config.get('CHANGE_FREEZE_ENABLED', 'false').lower() != 'true':
    print('No active freeze window — proceeding.')
    sys.exit(0)

commit_msg = os.environ.get('CI_COMMIT_MESSAGE', '')
emergency_kw = config.get('EMERGENCY_KEYWORD', '[emergency]')
if emergency_kw in commit_msg:
    print(f'Emergency bypass detected. Allowing pipeline. REVIEW REQUIRED.')
    print(f'Emergency approvers: {config.get(\"EMERGENCY_APPROVERS\", [])}')
    sys.exit(0)

now = datetime.datetime.utcnow()
freeze_start = datetime.datetime.fromisoformat(config['FREEZE_START'])
freeze_end   = datetime.datetime.fromisoformat(config['FREEZE_END'])

if freeze_start <= now <= freeze_end:
    print(f'CHANGE FREEZE ACTIVE: {config[\"FREEZE_REASON\"]}')
    print(f'Freeze window: {freeze_start} → {freeze_end} UTC')
    print(f'To bypass: include \"{emergency_kw}\" in your commit message.')
    print(f'Emergency approvers: {config[\"EMERGENCY_APPROVERS\"]}')
    sys.exit(1)
else:
    print(f'Freeze configured but not currently active ({now} UTC).')
    sys.exit(0)
"
```

---

## Exercise 8.5 — Activate the freeze

> 🟡 **Practitioner**

**Part 1 — Enable the freeze:**

Edit `gitlab/change_freeze.yml`:

```yaml
CHANGE_FREEZE_ENABLED: "true"
FREEZE_START: "2020-01-01T00:00:00"   # past date — freeze is always active
FREEZE_END:   "2099-12-31T23:59:59"   # far future — freeze never expires
FREEZE_REASON: "Test freeze — lab exercise 8.5"
```

Now run the freeze check locally:

```bash
CI_COMMIT_MESSAGE="Add description to leaf-lon-01 Ethernet3" \
python3 -c "
import yaml, datetime, sys, os

config = yaml.safe_load(open('gitlab/change_freeze.yml'))
# ... (paste the full check script from .gitlab-ci.yml)
"
```

Expected: the check fails with `CHANGE FREEZE ACTIVE`.

**Part 2 — Test the emergency bypass:**

```bash
CI_COMMIT_MESSAGE="[emergency] Fix BGP session drop on border-lon-01" \
python3 -c "..."
```

Expected: the check passes with `Emergency bypass detected`.

**Part 3 — Restore the freeze config:**

```bash
git checkout gitlab/change_freeze.yml
```

Verify the freeze check passes (no freeze active).

---

## What this means for operations

> 🔵 **Strategic**

The change freeze is an example of a broader principle: operational constraints that are documented in policy documents and enforced by human memory are weaker than operational constraints that are enforced by tooling.

ACME's trading halt requirement (no network changes during the year-end period) is not a regulatory obligation in itself — it is a risk management decision. But it interacts with regulatory obligations: a network incident during the trading halt that disrupts trading platform operations becomes an MiFID II reporting event. The freeze gate converts a soft constraint into a hard one.

The same principle applies to other operational constraints:
- "Changes to the TRADING zone require CTO approval" → an Ansible tower approval workflow or a dedicated GitLab approval rule
- "No push during market hours (07:30–17:30 London time)" → a time-window check in the validate stage
- "BGP changes require two senior engineers to approve" → `approval_rules` in GitLab with a minimum approval count

Each of these can be encoded in CI. Each one converts a procedural control into a technical control. Technical controls are cheaper to audit, more consistent to enforce, and less dependent on individual compliance.

*Handbook reference: Chapter 9 (Change management), Chapter 10 (Compliance automation)*
