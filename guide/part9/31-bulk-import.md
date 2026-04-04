# Chapter 31: Scaling the SoT — Bulk Import from a Spreadsheet

## Scenario

ACME's Americas expansion team sends a spreadsheet. Five new branch offices are opening across the US over the next quarter: Pittsburgh, Chicago, Houston, Phoenix, Denver. Each row has a site name, location, ASN, and IP addressing. The rest follows from SoT conventions.

The traditional approach takes half a day: open the existing `us-branches.yml`, manually craft five new YAML entries, run `validate_sot.py`, fix the inevitably missed field, run it again, open an MR, get it reviewed, merge it. For five branches. Multiply by four quarters.

The automation approach: feed the spreadsheet to `bulk_import.py`. It validates every row against the branch schema before writing a single byte. If validation passes, the SoT is updated. The pipeline picks it up from there.

## 🔵 [Strategic] Why This Matters

The SoT is a database. A database can be loaded. When bulk onboarding is a data problem rather than an engineering problem, the network team can scale without adding headcount. An operations team can manage a CMDB hand-off directly into the SoT rather than going through a network engineer as an intermediary.

For a financial institution expanding into new markets, this matters directly. A new Frankfurt office must comply with BaFin/MiFID II requirements from day one. The bulk import script encodes that compliance logic (the `trading_zone_prohibited` check for `eu-fra` entries) into the import gate — so a non-compliant record cannot reach the SoT without failing validation.

## 🟡 [Practitioner] Guided Walkthrough — bulk_import.py

The script takes a CSV and produces SoT YAML.

**Input validation.** On load, it checks that all required columns are present. Missing columns exit immediately with a clear error listing what is absent.

**Grouping by region.** A SoT branch file is region-scoped (one file per region, e.g. `uk-branches.yml`). The script groups CSV rows by region and generates one YAML document per region group. Top-level fields (compliance tags, intent refs, BGP peer ASN) are derived from the region.

**Schema validation.** Before writing any file, each generated document is validated against `schema/branch.schema.json`. If a record fails validation — wrong ASN range, missing required field, TRADING zone in an EU entry — the script reports the error and exits without touching the SoT.

**Output.** The resulting YAML follows the same structure as the hand-crafted SoT files. It is a first-class SoT document, not a generated stub.

### Example

Input CSV row:
```
hostname,region,uplink_dc,uplink_border,asn,wan_prefix,wan_ip,uplink_peer_ip,lan_prefix,city,country,office_type,md5_password_ref
branch-nyc-09,americas-nyc,nyc-dc1,border-nyc-01,65128,10.120.8.0/29,10.120.8.1,10.120.8.2,10.120.16.0/29,Pittsburgh,US,operations,bgp_md5_branch_nyc_09
```

Output YAML (excerpt):
```yaml
- hostname: branch-nyc-09
  lab_state: sot_only
  asn: 65128
  wan_prefix: 10.120.8.0/29
  wan_ip: 10.120.8.1
  uplink_peer_ip: 10.120.8.2
  lan_prefix: 10.120.16.0/29
  location:
    city: Pittsburgh
    country: US
  office_type: operations
  bgp:
    local_as: 65128
    router_id: 10.120.8.1
    neighbors:
      - peer_ip: 10.120.8.2
        remote_as: 65010
        description: eBGP -> border-nyc-01
        md5_password_ref: bgp_md5_branch_nyc_09
        route_map_in: RM_INTERDC_LON_NYC_IN
        route_map_out: RM_BRANCH_OUT
```

## Exercise 11.7 — Bulk Import {#ex117}

🟡 **Practitioner**

### Scenario

Five new US branch offices. The Americas team has sent a CSV.

### Set up

```bash
ansible-playbook scenarios/ch11/ex117_inject.yml
```

This writes `/tmp/new_branches_import.csv` with five records for branch-nyc-09 through branch-nyc-13.

### Step 1 — Inspect the CSV

```bash
cat /tmp/new_branches_import.csv
```

Before running any import, review the data. Check: are the ASNs in the valid US range (65120–65135)? Do the WAN prefixes follow the branch supernet convention? Is the `md5_password_ref` field populated (not a literal password)?

### Step 2 — Dry run

```bash
python3 scripts/bulk_import.py /tmp/new_branches_import.csv --dry-run
```

The dry run prints the generated YAML to stdout without writing any files. Review it: does the BGP neighbor configuration look correct? Are the compliance tags right for `americas-nyc`?

### Step 3 — Import

```bash
python3 scripts/bulk_import.py /tmp/new_branches_import.csv \
  --output sot/devices/branches/us-branches-imported.yml
```

### Step 4 — Validate

```bash
python3 scripts/validate_sot.py
```

### Verify

```bash
ansible-playbook scenarios/ch11/ex117_verify.yml
```

### Your turn — Open

Add a `eol_date` column to the CSV and extend `bulk_import.py` to include it in the YAML output. Then write a validation rule (in `validate_sot.py` or as a separate pytest) that rejects any branch record where `eol_date` is in the past. Demonstrate that a CSV with a 2020 EOL date fails at the import gate.

### Debrief

**What makes bulk import safe:** the schema validation gate. The script does not trust the CSV. It trusts the schema. Every record is validated before it touches the SoT. An invalid record — wrong ASN range, missing required field, TRADING zone on an EU entry — causes the script to exit with a clear error message and a zero-byte impact on the SoT.

**The audit trail:** after import, `git diff` shows exactly what was added to the SoT and why. The commit message carries the source (CSV file name, import timestamp). This is a clean audit record: data in, YAML out, change tracked.

**Scaling further:** the same pattern works for CMDB exports, IPAM integrations, and network hardware procurement spreadsheets. The bulk import script is a thin, replaceable conversion layer. The schema is the contract.
