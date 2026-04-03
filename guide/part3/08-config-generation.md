# Part 3 — Config Generation

# Chapter 8: From YAML to Config — Jinja2 Templates

> 🟡 **Practitioner** — Modules 0.3, 11.4
> 🔴 **Deep Dive** — sections marked

*Estimated time: 40 minutes*

---

## Scenario

You are reviewing a pull request that modifies the BGP hold-timer globally from 90 seconds to 30 seconds. The change is one line in `sot/global/platform_defaults.yml`. The diff in the MR shows 1 file changed.

But when the pipeline renders configs, the change touches 7 device configs — all the EOS nodes. A reviewer unfamiliar with the templating system asks: "Why do so many files change if only one line in the SoT changed?"

This chapter answers that question, and in answering it demonstrates why template-driven config generation is more maintainable than managing configs per-device.

---

## The template relationship

```
sot/global/platform_defaults.yml   ←── bgp_timers, ntp_keys, snmp settings
sot/devices/lon-dc1/leaf-lon-01.yml ←── interfaces, BGP neighbors, VRFs
          ↓
templates/arista_eos/base.j2        ←── hostname, AAA, NTP, SNMP, SSH
templates/arista_eos/interfaces.j2  ←── interface stanzas
templates/arista_eos/vrfs.j2        ←── VRF definitions
templates/arista_eos/bgp.j2         ←── BGP process, neighbors, route-maps
templates/arista_eos/vlans.j2       ←── VLAN database
          ↓
configs/leaf-lon-01/running.conf    ←── assembled from all section outputs
```

The playbook `playbooks/render_configs.yml` orchestrates this: it loads the SoT variables, runs each template for each device, and assembles the outputs into a single `running.conf` file.

---

## Reading a template

Open the base template:

```bash
cat templates/arista_eos/base.j2
```

The first section renders hostname, domain name, and banners:

```jinja2
hostname {{ hostname }}
ip domain-name {{ platform_defaults.domain_name }}
!
banner motd
  {{ platform_defaults.banners.motd }}
EOF
!
banner login
  {{ platform_defaults.banners.login }}
EOF
```

`{{ hostname }}` comes from the device file. `{{ platform_defaults.domain_name }}` comes from `sot/global/platform_defaults.yml`, loaded by the playbook as a variable available to all templates.

The NTP section shows how vault references work:

```jinja2
ntp authenticate
ntp authentication-key 1 md5 {{ vault_ntp_keys['ntp_key_primary'] }}
ntp trusted-key 1
ntp source-interface Management0
{% for server in platform_defaults.ntp.servers %}
ntp server {{ server }}
{% endfor %}
```

`vault_ntp_keys` is a dictionary defined in `inventory/group_vars/vault.yml`. In the lab, all vault values are set to `CHANGEME`. In production, this file would be encrypted with Ansible Vault or replaced with a secrets manager lookup. The template does not care which — it just dereferences the variable.

---

## The VLAN template — Frankfurt gate

```bash
cat templates/arista_eos/vlans.j2
```

The Frankfurt constraint is enforced here:

```jinja2
vlan database
{% for vlan in vlans %}
{% if vlan.vlan_id in (site_data.vlans_prohibited | default([])) %}
! SKIPPED: VLAN {{ vlan.vlan_id }} ({{ vlan.name }}) is prohibited at {{ site }} — {{ site_data.prohibition_reason | default('regulatory constraint') }}
{% else %}
vlan {{ vlan.vlan_id }}
   name {{ vlan.name }}
{% endif %}
{% endfor %}
```

When rendering a Frankfurt device, `site_data.vlans_prohibited` contains `[100]`. The template skips VLAN 100 and leaves a comment explaining why. The comment survives in the rendered config and is visible in the pipeline diff — a reviewer can see exactly why VLAN 100 was not rendered on this device.

> 🔴 **Deep Dive** — The comment is not just informational. When the drift detection playbook compares the SoT-rendered config to the running config, it skips comment lines. This means a device that was previously configured with VLAN 100 (perhaps before the Frankfurt constraint was added) will show a drift alert: the running config has VLAN 100, the SoT-rendered config does not. The drift is the compliance signal.

---

## The BGP template — handling route reflectors

```bash
cat templates/arista_eos/bgp.j2
```

The spine/leaf distinction is handled with a conditional:

```jinja2
router bgp {{ bgp.local_as }}
   router-id {{ bgp.router_id }}
   maximum-paths 4 ecmp 4
   graceful-restart
   !
{% for neighbor in bgp.neighbors %}
   neighbor {{ neighbor.peer }} remote-as {{ neighbor.remote_as }}
   neighbor {{ neighbor.peer }} description {{ neighbor.description }}
{% if neighbor.md5_password_ref is defined %}
   neighbor {{ neighbor.peer }} password {{ vault_bgp_passwords[neighbor.md5_password_ref] }}
{% endif %}
{% if bgp.role == 'route_reflector' and neighbor.route_reflector_client | default(false) %}
   neighbor {{ neighbor.peer }} route-reflector-client
{% endif %}
{% endfor %}
```

A spine (`bgp.role == 'route_reflector'`) renders `route-reflector-client` for each neighbor flagged as such. A leaf (`bgp.role == 'rr_client'`) never renders that line — the conditional is never true.

The password lookup — `vault_bgp_passwords[neighbor.md5_password_ref]` — dereferences the password dict using the reference name as a key. In the lab vault:

```yaml
vault_bgp_passwords:
  ibgp_lon_leaf01_spine01: CHANGEME
  ibgp_lon_leaf01_spine02: CHANGEME
  ebgp_lon_nyc: CHANGEME
  ...
```

Every BGP session has its own named password. In production, these would be unique, rotated values managed by a secrets manager. In the lab they are all `CHANGEME` — and the Batfish tests verify that every session has `md5_password_ref` set, catching any session that was inadvertently left without authentication.

---

## The FRR templates

FRR config structure is different from EOS, but the SoT data is the same:

```bash
cat templates/frr/bgp.j2
```

Frankfurt TRADING filter is rendered conditionally:

```jinja2
{% if site == 'fra-dc1' %}
! Frankfurt regulatory ring-fence (INTENT-003, REQ-007, REQ-009)
ip prefix-list PL_DENY_TRADING seq 5 deny 10.1.1.0/24 le 32
ip prefix-list PL_DENY_TRADING seq 10 permit any
!
route-map RM_INTERDC_LON_FRA_IN permit 10
 match ip address prefix-list PL_DENY_TRADING
{% endif %}
```

The same ACME zone isolation requirement (`INTENT-003`) is enforced in both the EOS template (skip VLAN 100) and the FRR template (add DENY_TRADING prefix-list). The SoT does not specify HOW to enforce it — it specifies WHAT must be true. The template is the how.

This is the multi-vendor templating pattern the Handbook describes: the SoT is platform-agnostic; the templates are platform-specific; the rendered configs are platform-correct.

---

## Exercise 11.4 — Multi-vendor templating

> 🟡 **Practitioner**

Compare how the TRADING zone constraint is handled in EOS vs FRR:

1. Find where VLAN 100 is excluded in `templates/arista_eos/vlans.j2`
2. Find where TRADING prefixes are filtered in `templates/frr/bgp.j2`
3. Find where TRADING_VRF is excluded in `templates/arista_eos/vrfs.j2`

Answer:
- How does the EOS template enforce isolation (at the VLAN layer)?
- How does the FRR template enforce isolation (at the routing policy layer)?
- Which mechanism is more robust, and why? (Consider: what happens if someone adds a static route?)

**Debrief:** EOS enforcement is VLAN-based — TRADING traffic never enters the switching fabric on Frankfurt devices because the VLAN does not exist. FRR enforcement is routing-policy-based — TRADING prefixes are dropped at the BGP import. Both are correct and complementary: the EOS enforcement stops the traffic; the FRR enforcement stops the routing information. A defence-in-depth approach. Batfish tests both.

---

## Exercise 0.3 — Trace a render

> 🟡 **Practitioner**

Run the render playbook for a single device:

```bash
ansible-playbook playbooks/render_configs.yml --limit leaf-lon-01
```

Then inspect the output:

```bash
cat configs/leaf-lon-01/running.conf
```

Match each section of the config back to its template:
1. The hostname line — which template? which SoT variable?
2. The `vlan 100` entry — which template? what SoT value controls whether it appears?
3. The `neighbor 10.1.255.1 route-reflector-client` line — is it there? Why or why not?
4. The `neighbor 10.1.255.1 password` line — where does the value come from?

*Handbook reference: Chapter 6 (Jinja2 templating), Chapter 7 (Multi-vendor automation)*
