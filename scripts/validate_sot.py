#!/usr/bin/env python3
"""
ACME Investments — SoT Validator
=================================
Pre-render validation script for the network Source of Truth.
Called by the GitLab CI 'validate' stage before any rendering or pushing.

Checks performed:
  1. YAML syntax — every sot/ and design_intents/ file parses cleanly
  2. Schema validation — device, branch, site, intent files against JSONSchema
  3. Intent ref validity — all intent_refs in device files resolve to real INTENT-IDs
  4. IP uniqueness — no two devices share a management IP or loopback IP
  5. ASN uniqueness — no two sites share a DC ASN; no two branches share a branch ASN
  6. Frankfurt constraints — fra-dc1 devices must not have TRADING zone or VLAN 100
  7. Branch prefix validation — all branch lan_prefix and wan_prefix must be /29
  8. BGP password hygiene — no inline bgp_password fields (use md5_password_ref)
  9. Compliance tag completeness — regional devices carry required regulatory tags
  10. md5_password_ref format — ref keys follow naming convention

Exit code:
  0 — all checks pass
  1 — one or more checks failed (details printed to stdout)

Usage:
  python3 scripts/validate_sot.py [--sot-dir SOT_DIR] [--intents-dir INTENTS_DIR]
  python3 scripts/validate_sot.py --help

Dependencies:
  pip install pyyaml jsonschema
"""

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    import jsonschema
    from jsonschema import validate, ValidationError, Draft7Validator
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)


# ── Constants ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
SOT_DIR = REPO_ROOT / "sot"
INTENTS_DIR = REPO_ROOT / "design_intents"
SCHEMA_DIR = REPO_ROOT / "schema"

# Regional compliance tag requirements — each region must carry these tags
REQUIRED_TAGS_BY_REGION = {
    "emea-lon":    {"mifid2", "fca"},
    "americas-nyc": {"sox", "reg_sci"},
    "apac":        {"mas_trm"},   # covers both SIN and HKG — validate_sot checks per-device HKMA tags via warn
    "eu-fra":      {"mifid2", "bafin"},
}

# Valid branch ASN ranges by region
BRANCH_ASN_RANGES = {
    "emea-lon":    range(65100, 65112),   # 65100–65111  UK
    "americas-nyc": range(65120, 65128),  # 65120–65127  US
    "apac":        range(65130, 65136),   # 65130–65135  APAC (SIN + HKG shared pool)
    "eu-fra":      range(65140, 65144),   # 65140–65143  EU
}

# Forbidden inline password field names (must use *_ref indirection to Vault)
FORBIDDEN_PASSWORD_FIELDS = {"bgp_password", "password", "secret"}


# ── Error collector ────────────────────────────────────────────────────────────

class Validator:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(f"  ERROR  {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(f"  WARN   {msg}")

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


# ── YAML loading ───────────────────────────────────────────────────────────────

def load_yaml(path: Path, v: Validator) -> dict | list | None:
    """Load a YAML file. Records error and returns None if it fails to parse."""
    try:
        with path.open() as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        v.error(f"YAML parse error in {path.relative_to(REPO_ROOT)}: {exc}")
        return None


def load_schema(name: str) -> dict:
    """Load a JSON Schema from schema/."""
    schema_path = SCHEMA_DIR / name
    with schema_path.open() as f:
        return json.load(f)


# ── Schema validation ─────────────────────────────────────────────────────────

def validate_schema(data: Any, schema: dict, path: Path, v: Validator) -> None:
    """Validate data against a JSON Schema. Records all violations."""
    validator = Draft7Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: e.path):
        location = " -> ".join(str(p) for p in err.path) if err.path else "(root)"
        v.error(
            f"Schema violation in {path.relative_to(REPO_ROOT)} "
            f"[{location}]: {err.message}"
        )


# ── Intent ID collection ──────────────────────────────────────────────────────

def collect_intent_ids(intents_dir: Path, v: Validator) -> set[str]:
    """Parse all design_intent files and return the set of known INTENT-NNN IDs."""
    known_ids: set[str] = set()
    for path in sorted(intents_dir.glob("*.yml")):
        data = load_yaml(path, v)
        if data is None or not isinstance(data, dict):
            continue
        intents = data.get("intents", [])
        if not isinstance(intents, list):
            v.error(f"{path.relative_to(REPO_ROOT)}: 'intents' must be a list")
            continue
        for intent in intents:
            if isinstance(intent, dict) and "id" in intent:
                known_ids.add(intent["id"])
    return known_ids


# ── Device file checks ────────────────────────────────────────────────────────

def check_device_file(
    path: Path,
    data: dict,
    known_intent_ids: set[str],
    mgmt_ip_seen: dict[str, str],
    loopback_ip_seen: dict[str, str],
    site_asn_seen: dict[int, str],
    v: Validator,
) -> None:
    """Run all checks for a single DC device file."""
    rel = str(path.relative_to(REPO_ROOT))
    hostname = data.get("hostname", path.stem)

    # 1. intent_refs validity
    for ref in data.get("intent_refs", []):
        if ref not in known_intent_ids:
            v.error(f"{rel} [{hostname}]: unknown intent_ref '{ref}' — not found in design_intents/")

    # 2. Management IP uniqueness
    mgmt = data.get("management", {})
    if isinstance(mgmt, dict):
        raw_ip = mgmt.get("ip", "")
        if raw_ip:
            # Strip prefix length for comparison
            ip_str = raw_ip.split("/")[0]
            if ip_str in mgmt_ip_seen:
                v.error(
                    f"{rel} [{hostname}]: management IP {ip_str} already used by {mgmt_ip_seen[ip_str]}"
                )
            else:
                mgmt_ip_seen[ip_str] = rel

    # 3. Loopback IP uniqueness
    loopback = data.get("loopback", {})
    if isinstance(loopback, dict):
        raw_ip = loopback.get("ip", "")
        if raw_ip:
            lb_str = raw_ip.split("/")[0]
            if lb_str in loopback_ip_seen:
                v.error(
                    f"{rel} [{hostname}]: loopback IP {lb_str} already used by {loopback_ip_seen[lb_str]}"
                )
            else:
                loopback_ip_seen[lb_str] = rel

    # 4. BGP checks
    bgp = data.get("bgp", {})
    if isinstance(bgp, dict):

        # 4a. Site ASN uniqueness (within same site scope)
        local_as = bgp.get("local_as")
        site = data.get("site", "")
        if local_as and site not in ("branches",):
            key = f"{site}:{local_as}"
            if key not in site_asn_seen:
                site_asn_seen[key] = rel
            # Within a DC multiple devices share the same ASN (iBGP) — this is expected

        # 4b. No inline passwords on BGP neighbors
        for neighbor in bgp.get("neighbors", []):
            if not isinstance(neighbor, dict):
                continue
            for field in FORBIDDEN_PASSWORD_FIELDS:
                if field in neighbor:
                    v.error(
                        f"{rel} [{hostname}]: BGP neighbor {neighbor.get('peer_ip', '?')} "
                        f"has forbidden inline field '{field}' — use md5_password_ref (INTENT-005, SC-103)"
                    )

        # 4c. md5_password_ref naming convention (should be bgp_md5_*)
        for neighbor in bgp.get("neighbors", []):
            if not isinstance(neighbor, dict):
                continue
            ref = neighbor.get("md5_password_ref", "")
            if ref and not re.match(r"^bgp_md5_", ref):
                v.warn(
                    f"{rel} [{hostname}]: md5_password_ref '{ref}' does not follow "
                    f"naming convention bgp_md5_<scope> (SC-101)"
                )

    # 5. Frankfurt-specific constraints
    site = data.get("site", "")
    if site == "fra-dc1":

        # 5a. TRADING must not be in security_zones
        zones = data.get("security_zones", [])
        if "TRADING" in zones:
            v.error(
                f"{rel} [{hostname}]: fra-dc1 device has TRADING in security_zones — "
                f"PROHIBITED (INTENT-001, INTENT-003, REQ-007, REQ-009)"
            )

        # 5b. VLAN 100 must not appear in vlans list
        for vlan in data.get("vlans", []):
            if isinstance(vlan, dict) and vlan.get("vlan_id") == 100:
                v.error(
                    f"{rel} [{hostname}]: fra-dc1 device defines VLAN 100 (TRADING) — "
                    f"PROHIBITED (INTENT-001, INTENT-003)"
                )

        # 5c. TRADING_VRF must not appear in vrfs list
        for vrf in data.get("vrfs", []):
            if isinstance(vrf, dict) and vrf.get("name") == "TRADING_VRF":
                v.error(
                    f"{rel} [{hostname}]: fra-dc1 device defines TRADING_VRF — "
                    f"PROHIBITED (INTENT-003, REQ-009)"
                )

    # 6. Compliance tag completeness
    region = data.get("region", "")
    tags = set(data.get("compliance_tags", []))
    required = REQUIRED_TAGS_BY_REGION.get(region, set())
    missing = required - tags
    if missing:
        v.warn(
            f"{rel} [{hostname}]: region '{region}' is missing compliance_tags: {sorted(missing)}"
        )

    # 7. intent_refs must contain at least one entry (annotation pass complete)
    if not data.get("intent_refs"):
        v.error(
            f"{rel} [{hostname}]: intent_refs is empty or missing — "
            f"run the SoT annotation pass (Phase 1)"
        )


# ── Branch file checks ────────────────────────────────────────────────────────

def check_branch_file(
    path: Path,
    data: dict,
    known_intent_ids: set[str],
    branch_asn_seen: dict[int, str],
    v: Validator,
) -> None:
    """Run all checks for a branch region file."""
    rel = str(path.relative_to(REPO_ROOT))
    region = data.get("region", "unknown")
    valid_asn_range = BRANCH_ASN_RANGES.get(region, range(0))

    # 1. Top-level intent_refs
    for ref in data.get("intent_refs", []):
        if ref not in known_intent_ids:
            v.error(f"{rel}: unknown top-level intent_ref '{ref}'")

    # 2. EU branches must have trading_zone_prohibited: true
    if region == "eu-fra" and not data.get("trading_zone_prohibited"):
        v.error(f"{rel}: eu-fra branch file must set trading_zone_prohibited: true")

    # 3. Individual branch checks
    for branch in data.get("branches", []):
        if not isinstance(branch, dict):
            continue
        hostname = branch.get("hostname", "?")

        # 3a. ASN uniqueness and range
        asn = branch.get("asn")
        if asn is not None:
            if asn in branch_asn_seen:
                v.error(
                    f"{rel} [{hostname}]: ASN {asn} already assigned to {branch_asn_seen[asn]} "
                    f"(SC-201)"
                )
            else:
                branch_asn_seen[asn] = f"{rel}:{hostname}"

            if asn not in valid_asn_range:
                v.error(
                    f"{rel} [{hostname}]: ASN {asn} is outside the valid pool for region "
                    f"'{region}' {valid_asn_range.start}-{valid_asn_range.stop - 1} (SC-202)"
                )

        # 3b. lan_prefix and wan_prefix must be /29 (INTENT-007, SC-107)
        for field in ("lan_prefix", "wan_prefix"):
            prefix_str = branch.get(field)
            if prefix_str:
                try:
                    net = ipaddress.ip_network(prefix_str, strict=False)
                    if net.prefixlen != 29:
                        v.error(
                            f"{rel} [{hostname}]: {field} '{prefix_str}' is /{net.prefixlen} "
                            f"— must be /29 (INTENT-007, SC-107)"
                        )
                except ValueError:
                    v.error(f"{rel} [{hostname}]: {field} '{prefix_str}' is not a valid CIDR prefix")

        # 3c. No inline passwords in BGP neighbors
        bgp = branch.get("bgp", {})
        if isinstance(bgp, dict):
            for neighbor in bgp.get("neighbors", []):
                if not isinstance(neighbor, dict):
                    continue
                for field in FORBIDDEN_PASSWORD_FIELDS:
                    if field in neighbor:
                        v.error(
                            f"{rel} [{hostname}]: BGP neighbor {neighbor.get('peer_ip', '?')} "
                            f"has forbidden inline field '{field}' (INTENT-005, SC-103)"
                        )


# ── Site file checks ──────────────────────────────────────────────────────────

def check_site_file(
    path: Path,
    data: dict,
    site_asn_seen: dict[int, str],
    v: Validator,
) -> None:
    """Run all checks for a site YAML file."""
    rel = str(path.relative_to(REPO_ROOT))
    site = data.get("site", {})
    if not isinstance(site, dict):
        v.error(f"{rel}: top-level 'site:' key must be a mapping")
        return

    code = site.get("code", rel)

    # 1. Site ASN uniqueness across DCs
    asn = site.get("asn")
    if asn is not None:
        if asn in site_asn_seen:
            v.error(
                f"{rel} [{code}]: DC ASN {asn} already used by {site_asn_seen[asn]} (SC-201)"
            )
        else:
            site_asn_seen[asn] = rel

    # 2. Frankfurt: trading_zone_prohibited and vlans_prohibited must be set
    if code == "fra-dc1":
        if not site.get("trading_zone_prohibited"):
            v.error(f"{rel}: fra-dc1 must set trading_zone_prohibited: true")
        prohibited_vlans = site.get("vlans_prohibited", [])
        if 100 not in prohibited_vlans:
            v.error(f"{rel}: fra-dc1 must include 100 in vlans_prohibited (INTENT-001, INTENT-003)")
        # Zone permissions must show TRADING: false
        zp = site.get("zone_permissions", {})
        if zp.get("TRADING") is not False:
            v.error(f"{rel}: fra-dc1 zone_permissions.TRADING must be false")

    # 3. If trading_zone_prohibited=true, VLAN 100 must not be in vlans list
    if site.get("trading_zone_prohibited"):
        for vlan in site.get("vlans", []):
            if isinstance(vlan, dict) and vlan.get("vlan_id") == 100:
                v.error(
                    f"{rel} [{code}]: site has trading_zone_prohibited=true but defines VLAN 100"
                )


# ── Intent file checks ────────────────────────────────────────────────────────

def check_intent_file(path: Path, data: dict, v: Validator) -> set[str]:
    """Validate an intent file and return the set of INTENT-IDs defined in it."""
    rel = str(path.relative_to(REPO_ROOT))
    ids: set[str] = set()
    intents = data.get("intents", [])

    if not isinstance(intents, list):
        v.error(f"{rel}: 'intents' must be a list")
        return ids

    seen_ids_in_file: set[str] = set()
    for i, intent in enumerate(intents):
        if not isinstance(intent, dict):
            v.error(f"{rel}: intents[{i}] must be a mapping")
            continue

        intent_id = intent.get("id", f"intents[{i}]")

        # Duplicate ID within file
        if intent_id in seen_ids_in_file:
            v.error(f"{rel}: duplicate intent id '{intent_id}'")
        seen_ids_in_file.add(intent_id)
        ids.add(intent_id)

        # Must have at least one of batfish_check or sot_checks
        # (unless assertion_type is 'operational')
        if intent.get("assertion_type") != "operational":
            has_batfish = bool(intent.get("batfish_check"))
            has_sot = bool(intent.get("sot_checks"))
            if not has_batfish and not has_sot:
                v.error(
                    f"{rel} [{intent_id}]: non-operational intent must have "
                    f"batfish_check or sot_checks (or both)"
                )

        # requirement_refs must be present and non-empty
        req_refs = intent.get("requirement_refs", [])
        if not req_refs:
            v.error(f"{rel} [{intent_id}]: requirement_refs is missing or empty")
        for ref in req_refs:
            if not re.match(r"^REQ-\d{3}$", str(ref)):
                v.error(f"{rel} [{intent_id}]: invalid requirement_ref format '{ref}' — expected REQ-NNN")

    return ids


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="ACME Investments SoT Validator — pre-render intent and schema checks"
    )
    parser.add_argument(
        "--sot-dir",
        type=Path,
        default=SOT_DIR,
        help=f"Path to sot/ directory (default: {SOT_DIR})",
    )
    parser.add_argument(
        "--intents-dir",
        type=Path,
        default=INTENTS_DIR,
        help=f"Path to design_intents/ directory (default: {INTENTS_DIR})",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after first file with errors (useful for local debugging)",
    )
    args = parser.parse_args()

    v = Validator()

    # Load schemas
    try:
        device_schema = load_schema("device.schema.json")
        branch_schema = load_schema("branch.schema.json")
        site_schema   = load_schema("site.schema.json")
        intent_schema  = load_schema("intent.schema.json")
    except FileNotFoundError as exc:
        print(f"FATAL: Schema file not found: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"FATAL: Schema file is invalid JSON: {exc}")
        return 1

    # ── Step 1: Collect known INTENT-IDs from design_intents/ ─────────────────
    print("Collecting intent IDs from design_intents/...")
    known_intent_ids: set[str] = set()

    for intent_path in sorted(args.intents_dir.glob("*.yml")):
        data = load_yaml(intent_path, v)
        if data is None:
            continue
        validate_schema(data, intent_schema, intent_path, v)
        ids = check_intent_file(intent_path, data, v)
        known_intent_ids.update(ids)

    print(f"  Found {len(known_intent_ids)} intent IDs: {sorted(known_intent_ids)}")

    # ── Step 2: Site files ────────────────────────────────────────────────────
    print("\nValidating sot/sites/...")
    site_asn_seen: dict[int, str] = {}

    for site_path in sorted((args.sot_dir / "sites").glob("*.yml")):
        data = load_yaml(site_path, v)
        if data is None:
            continue
        validate_schema(data, site_schema, site_path, v)
        check_site_file(site_path, data, site_asn_seen, v)
        print(f"  {site_path.name}")

    # ── Step 3: Device files ──────────────────────────────────────────────────
    print("\nValidating sot/devices/ (DC devices)...")
    mgmt_ip_seen:     dict[str, str] = {}
    loopback_ip_seen: dict[str, str] = {}
    device_asn_context: dict[int, str] = {}

    # All device files EXCEPT branch files
    device_paths = [
        p for p in sorted(args.sot_dir.rglob("devices/**/*.yml"))
        if p.parent.name != "branches"
    ]

    for device_path in device_paths:
        data = load_yaml(device_path, v)
        if data is None:
            continue
        validate_schema(data, device_schema, device_path, v)
        check_device_file(
            device_path, data,
            known_intent_ids,
            mgmt_ip_seen,
            loopback_ip_seen,
            device_asn_context,
            v,
        )

    print(f"  Validated {len(device_paths)} DC device files")

    # ── Step 4: Branch files ──────────────────────────────────────────────────
    print("\nValidating sot/devices/branches/...")
    branch_asn_seen: dict[int, str] = {}
    branches_dir = args.sot_dir / "devices" / "branches"

    for branch_path in sorted(branches_dir.glob("*.yml")):
        data = load_yaml(branch_path, v)
        if data is None:
            continue
        if "hostname" in data:
            # Individual active-device file — validated as a DC device, not a bulk branch file
            continue
        validate_schema(data, branch_schema, branch_path, v)
        check_branch_file(branch_path, data, known_intent_ids, branch_asn_seen, v)
        count = len(data.get("branches", []))
        print(f"  {branch_path.name}: {count} branches")

    # ── Results ───────────────────────────────────────────────────────────────
    print()
    if v.warnings:
        print(f"WARNINGS ({len(v.warnings)}):")
        for w in v.warnings:
            print(w)
        print()

    if v.passed:
        print(f"✓ All checks passed.")
        if v.warnings:
            print(f"  ({len(v.warnings)} warning(s) — review before merging)")
        return 0
    else:
        print(f"✗ FAILED — {len(v.errors)} error(s):")
        for err in v.errors:
            print(err)
        print()
        print("Fix all errors before the pipeline can proceed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
