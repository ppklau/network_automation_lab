#!/usr/bin/env python3
"""
scripts/bulk_import.py — ACME Investments Branch Bulk Import
Implements: Module 11.7

Converts a CSV of new branch device records into a SoT-compatible YAML file.
Validates each record against the branch schema before writing.

CSV columns (required):
  hostname, region, uplink_dc, uplink_border, asn,
  wan_prefix, wan_ip, uplink_peer_ip, lan_prefix,
  city, country, office_type, md5_password_ref

Usage:
  python3 scripts/bulk_import.py <csv_file> [--output <yaml_file>] [--dry-run]

Output:
  Writes to sot/devices/branches/<output>.yml (default: imported-branches.yml)
  Validates output against schema/branch.schema.json before writing.

Exit codes:
  0 — success
  1 — validation error (schema mismatch)
  2 — CSV parse error or missing required columns
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from collections import defaultdict

# Optional dependencies with graceful fallback
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    import yaml
    HAS_RUAMEL = False


# ── Colour helpers ────────────────────────────────────────────────────────────

def _green(msg):
    return f"{Fore.GREEN}{msg}{Style.RESET_ALL}" if HAS_COLORAMA else msg

def _yellow(msg):
    return f"{Fore.YELLOW}{msg}{Style.RESET_ALL}" if HAS_COLORAMA else msg

def _red(msg):
    return f"{Fore.RED}{msg}{Style.RESET_ALL}" if HAS_COLORAMA else msg

def _cyan(msg):
    return f"{Fore.CYAN}{msg}{Style.RESET_ALL}" if HAS_COLORAMA else msg


# ── Constants ─────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {
    "hostname", "region", "uplink_dc", "uplink_border", "asn",
    "wan_prefix", "wan_ip", "uplink_peer_ip", "lan_prefix",
    "city", "country", "office_type", "md5_password_ref",
}

COMPLIANCE_TAGS_MAP = {
    "emea-lon":     ["fca", "uk_gdpr"],
    "americas-nyc": ["sec", "finra"],
    "apac":         ["mas"],
    "eu-fra":       ["bafin", "mifid2"],
}

BORDER_ASN_MAP = {
    "emea-lon":     65001,
    "americas-nyc": 65010,
    "apac":         65020,
    "eu-fra":       65030,
}

PLATFORM   = "frr"
SECURITY_ZONES = ["CORPORATE", "MGMT_ZONE"]
INTENT_REFS    = ["INTENT-005", "INTENT-006", "INTENT-007", "INTENT-010", "INTENT-011"]


# ── YAML helpers ──────────────────────────────────────────────────────────────

def _dump_yaml(data: dict) -> str:
    """Serialise *data* to a YAML string using ruamel or PyYAML."""
    if HAS_RUAMEL:
        from io import StringIO
        yml = YAML()
        yml.default_flow_style = False
        yml.indent(mapping=2, sequence=4, offset=2)
        buf = StringIO()
        yml.dump(data, buf)
        return buf.getvalue()
    else:
        return yaml.dump(data, default_flow_style=False, sort_keys=False)


def _write_yaml(data: dict, path: Path) -> None:
    if HAS_RUAMEL:
        yml = YAML()
        yml.default_flow_style = False
        yml.indent(mapping=2, sequence=4, offset=2)
        with open(path, "w") as fh:
            yml.dump(data, fh)
    else:
        with open(path, "w") as fh:
            yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


# ── Build structures ──────────────────────────────────────────────────────────

def _build_branch_entry(row: dict) -> dict:
    """Build a single branch dict from a CSV row."""
    region        = row["region"].strip()
    uplink_border = row["uplink_border"].strip()
    remote_as     = BORDER_ASN_MAP.get(region, 65000)

    return {
        "hostname":      row["hostname"].strip(),
        "lab_state":     "sot_only",
        "asn":           int(row["asn"].strip()),
        "wan_prefix":    row["wan_prefix"].strip(),
        "wan_ip":        row["wan_ip"].strip(),
        "uplink_peer_ip": row["uplink_peer_ip"].strip(),
        "lan_prefix":    row["lan_prefix"].strip(),
        "location": {
            "city":    row["city"].strip(),
            "country": row["country"].strip(),
        },
        "office_type": row["office_type"].strip(),
        "bgp": {
            "local_as":  int(row["asn"].strip()),
            "router_id": row["wan_ip"].strip(),
            "neighbors": [
                {
                    "peer_ip":         row["uplink_peer_ip"].strip(),
                    "remote_as":       remote_as,
                    "description":     f"eBGP -> {uplink_border}",
                    "md5_password_ref": row["md5_password_ref"].strip(),
                    "route_map_in":    "RM_INTERDC_LON_NYC_IN",
                    "route_map_out":   "RM_BRANCH_OUT",
                }
            ],
        },
    }


def _build_region_doc(region: str, rows: list) -> dict:
    """Build a full region YAML document from a list of CSV rows."""
    first     = rows[0]
    uplink_dc = first["uplink_dc"].strip()
    uplink_border = first["uplink_border"].strip()

    doc = {
        "region":        region,
        "uplink_dc":     uplink_dc,
        "uplink_border": uplink_border,
        "platform":      PLATFORM,
        "compliance_tags": COMPLIANCE_TAGS_MAP.get(region, []),
        "security_zones":  SECURITY_ZONES,
        "intent_refs":     INTENT_REFS,
    }

    if region == "eu-fra":
        doc["trading_zone_prohibited"] = True

    doc["branches"] = [_build_branch_entry(row) for row in rows]
    return doc


# ── Validation ────────────────────────────────────────────────────────────────

def _load_schema(schema_path: Path):
    if not schema_path.exists():
        print(_yellow(f"[WARN] Schema not found at {schema_path} — skipping validation."))
        return None
    with open(schema_path) as fh:
        return json.load(fh)


def _validate(doc: dict, schema: dict, region: str) -> bool:
    """Return True if valid, False otherwise. Prints errors."""
    if not HAS_JSONSCHEMA:
        print(_yellow("[WARN] jsonschema not installed — skipping schema validation."))
        return True
    if schema is None:
        return True
    try:
        jsonschema.validate(instance=doc, schema=schema)
        return True
    except jsonschema.ValidationError as exc:
        print(_red(f"[ERROR] Validation failed for region '{region}': {exc.message}"))
        return False
    except jsonschema.SchemaError as exc:
        print(_red(f"[ERROR] Schema itself is invalid: {exc.message}"))
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a CSV of branch device records into SoT YAML.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "csv_file",
        help="Path to the input CSV file.",
    )
    parser.add_argument(
        "--output",
        default="sot/devices/branches/imported-branches.yml",
        metavar="YAML_FILE",
        help="Output YAML path (default: sot/devices/branches/imported-branches.yml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated YAML to stdout and exit without writing.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    csv_path    = Path(args.csv_file)
    output_path = Path(args.output)

    # ── Read CSV ──────────────────────────────────────────────────────────────
    try:
        with open(csv_path, newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                print(_red("[ERROR] CSV file is empty or has no header row."))
                return 2
            missing = REQUIRED_COLUMNS - set(f.strip() for f in reader.fieldnames)
            if missing:
                print(_red(f"[ERROR] CSV is missing required columns: {', '.join(sorted(missing))}"))
                return 2
            rows = list(reader)
    except FileNotFoundError:
        print(_red(f"[ERROR] CSV file not found: {csv_path}"))
        return 2
    except csv.Error as exc:
        print(_red(f"[ERROR] CSV parse error: {exc}"))
        return 2

    if not rows:
        print(_yellow("[WARN] CSV contains no data rows. Nothing to import."))
        return 0

    # ── Group by region ───────────────────────────────────────────────────────
    by_region: dict[str, list] = defaultdict(list)
    for row in rows:
        by_region[row["region"].strip()].append(row)

    # ── Load schema ───────────────────────────────────────────────────────────
    schema_path = Path("schema/branch.schema.json")
    schema      = _load_schema(schema_path)

    # ── Build and validate region docs ────────────────────────────────────────
    region_docs = {}
    any_invalid = False

    for region, region_rows in by_region.items():
        doc = _build_region_doc(region, region_rows)
        if not _validate(doc, schema, region):
            any_invalid = True
        region_docs[region] = doc

    if any_invalid:
        return 1

    # ── Produce output ────────────────────────────────────────────────────────
    # If multiple regions, wrap in a top-level list; single region emits dict.
    if len(region_docs) == 1:
        output_data = next(iter(region_docs.values()))
    else:
        output_data = list(region_docs.values())

    total_branches = sum(len(v["branches"]) for v in region_docs.values())
    total_regions  = len(region_docs)

    if args.dry_run:
        print(_cyan("# --- DRY RUN — not writing to disk ---"))
        print(_dump_yaml(output_data))
        print(_cyan(f"# Would import {total_branches} branch(es) across {total_regions} region(s) → {output_path}"))
        return 0

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_yaml(output_data, output_path)
    print(_green(f"Imported {total_branches} branch(es) across {total_regions} region(s) → {output_path}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
