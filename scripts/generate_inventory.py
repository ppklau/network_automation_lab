#!/usr/bin/env python3
"""
ACME Investments — Ansible Inventory Generator
===============================================
Generates inventory/hosts.yml from the SoT device files.

Only devices with lab_state: active are included in the inventory.
sot_only devices are excluded — they have no live counterpart to connect to.

Groups generated:
  all          — all active devices (always present)
  lab_active   — alias for all (explicit group for pipeline filtering)
  spine        — all active spine switches
  leaf         — all active leaf switches
  border       — all active border routers
  firewall     — all active firewalls (fw role)
  branch       — all active branch CPEs
  site_{code}  — per-site groups (e.g. site_lon_dc1)

Host variables set per device:
  ansible_host         — management IP (without prefix length)
  ansible_network_os   — mapped from platform (arista_eos → eos, frr → frr)
  ansible_connection   — network_cli (EOS) or network_cli (FRR)
  site                 — site code
  region               — region code
  role                 — device role

Usage:
  python3 scripts/generate_inventory.py [--sot-dir SOT_DIR] [--output OUTPUT]
  python3 scripts/generate_inventory.py --dry-run    # print to stdout only

Dependencies:
  pip install pyyaml
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


# ── Constants ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
SOT_DIR = REPO_ROOT / "sot"
INVENTORY_DIR = REPO_ROOT / "inventory"
OUTPUT_FILE = INVENTORY_DIR / "hosts.yml"

# Platform → Ansible network_os mapping
PLATFORM_TO_NETWORK_OS = {
    "arista_eos": "eos",
    "frr":        "frr",
}

# Platform → Ansible connection plugin
PLATFORM_TO_CONNECTION = {
    "arista_eos": "network_cli",
    "frr":        "network_cli",
}

# Normalise role values (site files use 'firewall', device files use 'fw')
ROLE_NORMALISE = {
    "firewall": "firewall",
    "fw":       "firewall",
    "spine":    "spine",
    "leaf":     "leaf",
    "border":   "border",
}


# ── YAML helpers ───────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict | list | None:
    try:
        with path.open() as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(f"ERROR: YAML parse error in {path}: {exc}", file=sys.stderr)
        return None


def dump_yaml(data: Any) -> str:
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ── Device discovery ───────────────────────────────────────────────────────────

def collect_dc_devices(sot_dir: Path) -> list[dict]:
    """
    Collect all active DC devices from sot/devices/{site}/*.yml.
    Branch files (in sot/devices/branches/) are handled separately.
    Returns a list of dicts, each with keys: hostname, role, platform, site,
    region, lab_state, management_ip, network_os, connection.
    """
    devices = []
    device_dir = sot_dir / "devices"

    for device_path in sorted(device_dir.rglob("*.yml")):
        # Skip branch files
        if device_path.parent.name == "branches":
            continue

        data = load_yaml(device_path)
        if data is None or not isinstance(data, dict):
            continue

        # Only include active devices
        if data.get("lab_state") != "active":
            continue

        hostname = data.get("hostname")
        if not hostname:
            print(f"WARN: {device_path} has no hostname — skipping", file=sys.stderr)
            continue

        platform = data.get("platform", "")
        role_raw = data.get("role", "")
        role = ROLE_NORMALISE.get(role_raw, role_raw)

        # Extract management IP (strip prefix length)
        mgmt = data.get("management", {})
        mgmt_ip_raw = mgmt.get("ip", "") if isinstance(mgmt, dict) else ""
        mgmt_ip = mgmt_ip_raw.split("/")[0] if mgmt_ip_raw else ""

        site_code = data.get("site", "")
        # Normalise site code for use as group name: lon-dc1 → site_lon_dc1
        site_group = "site_" + site_code.replace("-", "_") if site_code else "site_unknown"

        devices.append({
            "hostname":    hostname,
            "role":        role,
            "platform":    platform,
            "site":        site_code,
            "site_group":  site_group,
            "region":      data.get("region", ""),
            "lab_state":   "active",
            "ansible_host": mgmt_ip,
            "ansible_network_os": PLATFORM_TO_NETWORK_OS.get(platform, platform),
            "ansible_connection": PLATFORM_TO_CONNECTION.get(platform, "network_cli"),
        })

    return devices


def collect_branch_devices(sot_dir: Path) -> list[dict]:
    """
    Collect active branch CPEs from sot/devices/branches/*.yml.
    Returns same structure as collect_dc_devices().
    """
    devices = []
    branches_dir = sot_dir / "devices" / "branches"

    for branch_file in sorted(branches_dir.glob("*.yml")):
        data = load_yaml(branch_file)
        if data is None or not isinstance(data, dict):
            continue

        region = data.get("region", "")
        platform = data.get("platform", "frr")

        for branch in data.get("branches", []):
            if not isinstance(branch, dict):
                continue
            if branch.get("lab_state") != "active":
                continue

            hostname = branch.get("hostname")
            if not hostname:
                continue

            mgmt_ip_raw = branch.get("management_ip", "")
            mgmt_ip = mgmt_ip_raw.split("/")[0] if mgmt_ip_raw else ""

            # Branch site group based on uplink DC
            uplink_dc = data.get("uplink_dc", "")
            site_group = "site_" + uplink_dc.replace("-", "_") if uplink_dc else "site_unknown"

            devices.append({
                "hostname":    hostname,
                "role":        "branch",
                "platform":    platform,
                "site":        uplink_dc,
                "site_group":  site_group,
                "region":      region,
                "lab_state":   "active",
                "ansible_host": mgmt_ip,
                "ansible_network_os": PLATFORM_TO_NETWORK_OS.get(platform, platform),
                "ansible_connection": PLATFORM_TO_CONNECTION.get(platform, "network_cli"),
            })

    return devices


# ── Inventory builder ─────────────────────────────────────────────────────────

def build_inventory(devices: list[dict]) -> dict:
    """
    Build the Ansible inventory dict from the list of active devices.

    Structure:
      all:
        hosts:
          {hostname}:
            ansible_host: ...
            ansible_network_os: ...
            ansible_connection: ...
            site: ...
            region: ...
            role: ...
        children:
          spine: { hosts: {hostname: null, ...} }
          leaf:  { hosts: {...} }
          border:   { hosts: {...} }
          firewall: { hosts: {...} }
          branch:   { hosts: {...} }
          lab_active: { hosts: {...} }
          site_lon_dc1: { hosts: {...} }
          ...
    """
    # Build the 'all' hosts block with full hostvars
    all_hosts: dict[str, dict] = {}
    role_groups: dict[str, dict] = defaultdict(dict)
    site_groups: dict[str, dict] = defaultdict(dict)

    for device in devices:
        hostname = device["hostname"]

        # Host vars
        hostvars = {
            "ansible_host":        device["ansible_host"],
            "ansible_network_os":  device["ansible_network_os"],
            "ansible_connection":  device["ansible_connection"],
            "site":                device["site"],
            "region":              device["region"],
            "role":                device["role"],
        }
        # Omit empty values to keep the inventory clean
        hostvars = {k: v for k, v in hostvars.items() if v}
        all_hosts[hostname] = hostvars

        # Role group (spine/leaf/border/firewall/branch)
        role_groups[device["role"]][hostname] = None

        # Site group
        site_groups[device["site_group"]][hostname] = None

    # lab_active = all active devices (same as 'all' but explicit for pipeline use)
    lab_active_hosts = {h: None for h in all_hosts}

    # Compose children dict
    children: dict[str, Any] = {}

    for role in ("spine", "leaf", "border", "firewall", "branch"):
        hosts = role_groups.get(role, {})
        if hosts:
            children[role] = {"hosts": hosts}

    children["lab_active"] = {"hosts": lab_active_hosts}

    for site_group, hosts in sorted(site_groups.items()):
        if hosts:
            children[site_group] = {"hosts": hosts}

    inventory = {
        "all": {
            "hosts": all_hosts,
            "children": children,
        }
    }

    return inventory


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Ansible inventory/hosts.yml from ACME Investments SoT"
    )
    parser.add_argument(
        "--sot-dir",
        type=Path,
        default=SOT_DIR,
        help=f"Path to sot/ directory (default: {SOT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help=f"Output path for hosts.yml (default: {OUTPUT_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print inventory to stdout instead of writing to file",
    )
    args = parser.parse_args()

    # Collect devices
    dc_devices = collect_dc_devices(args.sot_dir)
    branch_devices = collect_branch_devices(args.sot_dir)
    all_devices = dc_devices + branch_devices

    active_count = len(all_devices)
    if active_count == 0:
        print("WARN: No active devices found in SoT. Is lab_state set correctly?", file=sys.stderr)

    # Build inventory
    inventory = build_inventory(all_devices)

    # Output
    header = (
        "# ACME Investments — Ansible Inventory\n"
        "# Generated by scripts/generate_inventory.py — do not edit by hand.\n"
        "# Re-generate with: python3 scripts/generate_inventory.py\n"
        "#\n"
        "# Only lab_state: active devices are included.\n"
        "# Groups: spine, leaf, border, firewall, branch, site_{code}, lab_active\n"
        "#\n"
    )
    output_yaml = header + dump_yaml(inventory)

    if args.dry_run:
        print(output_yaml)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_yaml)
        print(f"Wrote {active_count} active devices to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
