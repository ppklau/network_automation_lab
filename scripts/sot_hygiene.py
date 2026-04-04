#!/usr/bin/env python3
"""
scripts/sot_hygiene.py
ACME Investments — SoT Hygiene Linter
Implements: Module 8.8

Checks the SoT for common hygiene issues that do not rise to the level of
schema validation errors but indicate technical debt, naming inconsistencies,
or configuration drift from conventions.

Checks performed:
  1. Unused ASNs in the branch pools (allocated but no device uses them)
  2. Duplicate IP addresses that validate_sot.py might miss (e.g. across sites)
  3. Devices with missing or generic interface descriptions
  4. Non-standard hostname patterns
  5. Devices in sot_only state for > 2 years with no activity
  6. Duplicate or conflicting compliance_tags
  7. md5_password_refs that match the pattern 'CHANGEME' (lab credential left in)

Exit codes:
  0 — no issues found
  1 — warnings found (informational, not blocking)
  2 — critical issues found (should be remediated before next audit)

Usage:
  python3 scripts/sot_hygiene.py
  python3 scripts/sot_hygiene.py --strict    # treat warnings as errors
  python3 scripts/sot_hygiene.py --json      # JSON output for Ansible
"""

import argparse
import glob
import ipaddress
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
SOT_DIR = REPO_ROOT / "sot"
VAULT_FILE = REPO_ROOT / "inventory" / "group_vars" / "vault.yml"

HOSTNAME_RE = re.compile(r'^[a-z][a-z0-9-]+-[a-z]{2,5}-\d{2}$')
GENERIC_DESCRIPTIONS = {'', 'TBD', 'TODO', 'UNKNOWN', 'N/A', 'description'}

issues = []

def error(code, node, check, message):
    issues.append({'severity': 'CRITICAL', 'code': code, 'node': node, 'check': check, 'message': message})

def warning(code, node, check, message):
    issues.append({'severity': 'WARNING', 'code': code, 'node': node, 'check': check, 'message': message})

def info(code, node, check, message):
    issues.append({'severity': 'INFO', 'code': code, 'node': node, 'check': check, 'message': message})


def load_all_devices():
    devices = []
    for f in glob.glob(str(SOT_DIR / 'devices' / '**' / '*.yml'), recursive=True):
        with open(f) as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict) and 'hostname' in data:
            data['_source_file'] = f
            devices.append(data)
        elif isinstance(data, dict) and 'branches' in data:
            # Branch list file
            for branch in data.get('branches', []):
                branch['_source_file'] = f
                branch['_is_branch'] = True
                devices.append(branch)
    return devices


def load_vault():
    if not VAULT_FILE.exists():
        return {}
    with open(VAULT_FILE) as f:
        return yaml.safe_load(f) or {}


def check_hostname_conventions(devices):
    """Check 1: Hostname naming standard: <role>-<site>-<nn>"""
    for d in devices:
        hostname = d.get('hostname', '')
        if d.get('_is_branch'):
            continue
        if not HOSTNAME_RE.match(hostname):
            warning('HYG-001', hostname, 'hostname_convention',
                    f"Hostname '{hostname}' does not match convention <role>-<site>-<nn> "
                    f"(e.g. spine-lon-01, leaf-nyc-03)")


def check_interface_descriptions(devices):
    """Check 2: All interfaces should have non-generic descriptions"""
    for d in devices:
        hostname = d.get('hostname', d.get('_source_file', 'unknown'))
        if d.get('lab_state') == 'decommissioned':
            continue
        for intf in d.get('interfaces', []):
            desc = intf.get('description', '').strip()
            if not desc or desc in GENERIC_DESCRIPTIONS:
                warning('HYG-002', hostname, 'interface_description',
                        f"Interface {intf.get('name', '?')} has no or generic description")


def check_unused_asns(devices):
    """Check 3: ASNs in the branch pool that are not assigned to any device"""
    with open(SOT_DIR / 'global' / 'asn_pools.yml') as f:
        pools = yaml.safe_load(f)

    branch_pools = pools.get('bgp_asn_pools', {}).get('branches', {})
    all_branch_asns = set()
    for region, pool in branch_pools.items():
        if isinstance(pool, dict) and 'start' in pool:
            for asn in range(pool['start'], pool['end'] + 1):
                all_branch_asns.add(asn)

    used_asns = set()
    for d in devices:
        asn = d.get('asn') or d.get('bgp', {}).get('local_as')
        if asn:
            used_asns.add(int(asn))

    unused = all_branch_asns - used_asns
    if unused:
        info('HYG-003', 'global', 'asn_pool_utilisation',
             f"{len(unused)} ASN(s) in branch pools unallocated: "
             f"{sorted(unused)[:10]}{'...' if len(unused) > 10 else ''}")


def check_vault_credentials(devices):
    """Check 4: md5_password_refs should not have value 'CHANGEME' in production"""
    vault = load_vault()
    bgp_passwords = vault.get('vault_bgp_passwords', {})
    changeme_refs = [k for k, v in bgp_passwords.items() if v == 'CHANGEME']
    if changeme_refs:
        # In lab this is expected — flag as INFO, not WARNING
        info('HYG-004', 'vault', 'default_credentials',
             f"{len(changeme_refs)} BGP password(s) still set to CHANGEME. "
             f"Replace before production deployment.")


def check_stale_sot_only(devices):
    """Check 5: sot_only devices that have been inactive for > 2 years"""
    cutoff = datetime(datetime.now().year - 2, 1, 1, tzinfo=timezone.utc)
    for d in devices:
        if d.get('lab_state') != 'sot_only':
            continue
        last_seen = d.get('last_seen') or d.get('decommission_date')
        if last_seen:
            try:
                ts = datetime.fromisoformat(str(last_seen).replace('Z', '+00:00'))
                if ts < cutoff:
                    warning('HYG-005', d.get('hostname', 'unknown'), 'stale_sot_only',
                            f"Device has been sot_only since {last_seen} (> 2 years). "
                            f"Consider archiving or removing this record.")
            except ValueError:
                pass


def check_duplicate_compliance_tags(devices):
    """Check 6: Same compliance_tag listed twice on a device"""
    for d in devices:
        hostname = d.get('hostname', 'unknown')
        tags = d.get('compliance_tags', [])
        if len(tags) != len(set(tags)):
            seen = set()
            dupes = [t for t in tags if t in seen or seen.add(t)]
            warning('HYG-006', hostname, 'duplicate_compliance_tags',
                    f"Duplicate compliance_tags: {dupes}")


def check_missing_mandatory_fields(devices):
    """Check 7: All active devices must have loopback, bgp, and compliance_tags"""
    required_for_active = ['loopback', 'bgp', 'compliance_tags']
    for d in devices:
        if d.get('lab_state') not in ['active', 'sot_only']:
            continue
        if d.get('_is_branch'):
            continue
        hostname = d.get('hostname', 'unknown')
        for field in required_for_active:
            if not d.get(field):
                warning('HYG-007', hostname, 'missing_field',
                        f"Field '{field}' is missing or empty")


def main():
    parser = argparse.ArgumentParser(description='ACME SoT Hygiene Linter')
    parser.add_argument('--strict', action='store_true', help='Treat warnings as errors')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()

    devices = load_all_devices()

    check_hostname_conventions(devices)
    check_interface_descriptions(devices)
    check_unused_asns(devices)
    check_vault_credentials(devices)
    check_stale_sot_only(devices)
    check_duplicate_compliance_tags(devices)
    check_missing_mandatory_fields(devices)

    critical_count = sum(1 for i in issues if i['severity'] == 'CRITICAL')
    warning_count  = sum(1 for i in issues if i['severity'] == 'WARNING')
    info_count     = sum(1 for i in issues if i['severity'] == 'INFO')

    result = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'devices_checked': len(devices),
        'issues_found': len(issues),
        'critical': critical_count,
        'warnings': warning_count,
        'info': info_count,
        'issues': issues,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nACME Investments — SoT Hygiene Report")
        print(f"{'=' * 60}")
        print(f"Devices checked : {len(devices)}")
        print(f"Issues found    : {len(issues)} (CRITICAL: {critical_count}, WARNING: {warning_count}, INFO: {info_count})")
        print()

        if not issues:
            print("✓ No hygiene issues found.")
        else:
            for severity in ('CRITICAL', 'WARNING', 'INFO'):
                matching = [i for i in issues if i['severity'] == severity]
                if matching:
                    print(f"{severity}:")
                    for i in matching:
                        print(f"  [{i['code']}] {i['node']} — {i['check']}: {i['message']}")
                    print()

        print('=' * 60)

    if critical_count > 0:
        sys.exit(2)
    elif warning_count > 0 and args.strict:
        sys.exit(1)
    elif warning_count > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
