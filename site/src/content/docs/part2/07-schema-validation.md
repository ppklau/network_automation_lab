---
title: "Chapter 7: Schema Validation — The Pipeline's First Gate"
---

> 🟡 **Practitioner** — Modules 4.1, 0.3
> 🔴 **Deep Dive** — sections marked

*Estimated time: 20 minutes*

---

## Scenario

A junior engineer is adding a new UK branch to the SoT. They copy an existing branch record and modify it — but accidentally assign the same ASN as an existing branch. They push the commit.

Without validation, the pipeline renders the config, pushes it to the device, and you have two branches advertising the same ASN into your BGP fabric. The failure mode is not immediate — BGP might still establish, but route propagation becomes unpredictable. The root cause takes 30 minutes to trace.

With validation, the pipeline fails at the first stage — before rendering, before Batfish, before any device connection:

```
[FAIL] Duplicate ASN detected: 65103 is assigned to branch-lon-03 and branch-lon-05
Exit code: 1
```

Thirty seconds of CI time instead of 30 minutes of troubleshooting.

---

## Three validation layers

The ACME pipeline uses three complementary validation tools, each catching a different class of error:

| Tool | What it catches | When it runs |
|------|-----------------|--------------|
| `yamllint` | Syntax errors, inconsistent indentation, trailing whitespace | Every git push |
| `jsonschema` (via `validate_sot.py`) | Wrong field types, missing required fields, invalid enum values | Every git push |
| `validate_sot.py` cross-checks | Duplicate ASNs/IPs, invalid intent_refs, Frankfurt constraint | Every git push |

All three run in the `validate` pipeline stage, before any rendering or Batfish work.

---

## yamllint

```bash
cat .yamllint.yml
```

```yaml
extends: default
rules:
  line-length:
    max: 120
  truthy:
    allowed-values: ['true', 'false']
  indentation:
    spaces: 2
    indent-sequences: true
  comments:
    min-spaces-from-content: 1
```

Run it manually:

```bash
yamllint sot/ design_intents/ requirements/
```

YAML syntax errors are the most common class of SoT mistake — a missing colon, a tab instead of spaces, a string that needs quoting. yamllint catches all of them in under a second. It is the first gate because it is the cheapest.

---

## JSONSchema validation

The `schema/` directory contains JSONSchema definitions for each SoT file type.

```bash
cat schema/device.schema.json
```

Key constraints in the device schema:

```json
{
  "required": ["hostname", "platform", "role", "site", "lab_state"],
  "properties": {
    "platform": {
      "enum": ["arista_eos", "frr", "cisco_ios"]
    },
    "role": {
      "enum": ["spine", "leaf", "border", "firewall", "branch"]
    },
    "lab_state": {
      "enum": ["active", "sot_only", "decommissioned"]
    },
    "loopback": {
      "required": ["ip"],
      "properties": {
        "ip": {
          "pattern": "^\\d+\\.\\d+\\.\\d+\\.\\d+/32$"
        }
      }
    }
  }
}
```

The `platform` and `role` fields are enums — any value not in the list fails validation. The loopback IP must be a `/32` — the regex pattern enforces this. If someone accidentally writes a `/24` for a loopback, the validator catches it before Jinja2 tries to render it.

```bash
# Try it: temporarily break a device file
cat > /tmp/test_device.yml << 'EOF'
hostname: test-device
platform: juniper_eos    # invalid platform
role: spine
site: lon-dc1
lab_state: active
EOF

python3 -c "
import jsonschema, yaml, json
schema = json.load(open('schema/device.schema.json'))
device = yaml.safe_load(open('/tmp/test_device.yml'))
jsonschema.validate(device, schema)
"
```

```
jsonschema.exceptions.ValidationError: 'juniper_eos' is not one of ['arista_eos', 'frr', 'cisco_ios']
```

> 🔴 **Deep Dive** — The schema for branch records (`schema/branch.schema.json`) includes an ASN range check: branch ASNs must be in the range 65100–65143. This is enforced with a `minimum`/`maximum` constraint. However, JSONSchema cannot check uniqueness across multiple files — that requires the cross-validation script. This is a deliberate separation: the schema validates structure; the script validates cross-file consistency.

---

## `validate_sot.py` — cross-file validation

```bash
python3 scripts/validate_sot.py --verbose
```

The script performs checks that JSON Schema cannot:

**1. ASN uniqueness**
```python
# Collects all ASNs across all device and branch files
# Fails if any ASN appears more than once
```

**2. IP uniqueness**
```python
# Collects all interface IPs
# Fails if any /32 or host IP appears more than once
# Ignores /31 P2P links (both ends of a /31 are different hosts)
```

**3. Intent reference integrity**
```python
# Collects all INTENT-xxx IDs from design_intents/
# For every intent_refs: [INTENT-001, ...] in any SoT file,
# verifies the referenced ID exists
```

**4. Frankfurt constraint**
```python
# Loads vlans_prohibited from sot/sites/fra-dc1.yml
# For every device at fra-dc1, verifies no referenced VLAN ID
# appears in vlans_prohibited
```

**5. Vault reference integrity**
```python
# Collects all md5_password_ref values from device files
# Verifies each one appears as a key in inventory/group_vars/vault.yml
```

---

## Breaking the validator intentionally

> 🟡 **Practitioner** — Exercise 7.1

This exercise walks through what the pipeline catches.

**Test 1 — Frankfurt TRADING violation:**

```bash
# Add VLAN 100 to a Frankfurt device
python3 -c "
import yaml

with open('sot/devices/fra-dc1/border-fra-01.yml') as f:
    device = yaml.safe_load(f)

device.setdefault('vlans', []).append({'vlan_id': 100, 'name': 'TRADING'})

with open('sot/devices/fra-dc1/border-fra-01.yml', 'w') as f:
    yaml.dump(device, f)
"

python3 scripts/validate_sot.py
```

Expected:
```
[FAIL] fra-dc1: border-fra-01 references VLAN 100 — prohibited at this site
SoT validation FAILED — 1 error
```

```bash
git checkout sot/devices/fra-dc1/border-fra-01.yml
```

**Test 2 — Duplicate ASN:**

```bash
# Set branch-lon-02's ASN to the same value as branch-lon-01
# Edit sot/devices/branches/uk_branches.yml — find branch-lon-02 and change asn: 65101 to asn: 65100

python3 scripts/validate_sot.py
```

Expected:
```
[FAIL] Duplicate ASN 65100: assigned to branch-lon-01 and branch-lon-02
SoT validation FAILED — 1 error
```

```bash
git checkout sot/devices/branches/uk_branches.yml
```

**Test 3 — Missing vault ref:**

```bash
# In sot/devices/lon-dc1/leaf-lon-01.yml, change an md5_password_ref to a non-existent key
# Find an md5_password_ref value and append "_typo" to it

python3 scripts/validate_sot.py
```

Expected:
```
[FAIL] md5_password_ref 'ibgp_lon_leaf01_spine01_typo' not found in vault.yml
SoT validation FAILED — 1 error
```

```bash
git checkout sot/devices/lon-dc1/leaf-lon-01.yml
```

After each test, verify the validator returns clean:

```bash
python3 scripts/validate_sot.py
# SoT validation passed — 75 devices, 0 errors
```

---

## `generate_inventory.py`

```bash
python3 scripts/generate_inventory.py
cat inventory/hosts.yml
```

The inventory is generated from the SoT — not hand-edited. Key logic:

- Only devices with `lab_state: active` are included
- Devices are grouped by `role` (spine, leaf, border, branch), by `site`, and into an `all` group
- Connection variables (IP, network OS, connection type) are derived from `platform`

```yaml
all:
  children:
    lab_active:
      hosts:
        spine-lon-01:
          ansible_host: 172.20.20.11
          ansible_network_os: arista.eos.eos
          ansible_connection: ansible.netcommon.httpapi
        leaf-lon-01:
          ansible_host: 172.20.20.21
          ...
    spine:
      hosts:
        spine-lon-01: {}
        spine-lon-02: {}
    leaf:
      hosts:
        leaf-lon-01: {}
        ...
```

When you add a new device to the SoT with `lab_state: active`, re-run `generate_inventory.py` and it appears in the inventory automatically. No hand-editing.

---

## Exercise 7.1 — Catch a pipeline violation before it reaches production {#ex71}

> 🟡 **Practitioner**

Your team lead has asked you to add a new spine to London DC1. They give you a device record to add:

```yaml
hostname: spine-lon-03
platform: arista_eos
role: spine
site: lon-dc1
lab_state: active
loopback:
  ip: 10.1.255.3/24       # bug: should be /32
  description: "spine-lon-03 router-ID"
bgp:
  local_as: 65001
  router_id: 10.1.255.3
  role: route_reflector
```

1. Add this record to `sot/devices/lon-dc1/spine-lon-03.yml`
2. Run `python3 scripts/validate_sot.py`
3. The validator should fail. How many errors does it catch?
4. Fix all errors and re-run until the validator passes
5. Do **not** push — this is a validation-only exercise. Remove the file when done.

**Verify:** `python3 scripts/validate_sot.py` returns `0 errors`.

**Debrief:** The loopback `/24` is caught by the JSONSchema regex (`^\\d+\\.\\d+\\.\\d+\\.\\d+/32$`). A new spine also needs all its iBGP neighbors defined — are they? Would the Batfish resilience tests pass with a third spine that is not configured as an RR for all leaves? These are the questions the validation layer forces you to consider before a device ever gets configured.

*Handbook reference: Chapter 5 (Pipeline design), Chapter 3 (SoT schema)*
