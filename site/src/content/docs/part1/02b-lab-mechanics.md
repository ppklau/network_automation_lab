---
title: "Lab Mechanics: ContainerLab, Render, and Push"
---

> 🟡 **Practitioner** — reference for Chapter 2
> 🔴 **Deep Dive** — sections marked

*This page explains what is happening under the hood when you run the Chapter 2 setup steps. Read it alongside Chapter 2 or return to it when you want to understand a specific mechanism in more depth.*

---

## How ContainerLab sets up the lab

When you run `sudo containerlab deploy --topo topology/containerlab.yml`, ContainerLab reads a single YAML file and orchestrates the entire lab from it. Open it and work through its structure:

```bash
cat topology/containerlab.yml
```

The file has three main sections: `mgmt`, `topology.kinds`, and `topology.nodes` / `topology.links`.

### The management network

```yaml
mgmt:
  network: acme-mgmt
  ipv4-subnet: 172.20.20.0/24
```

ContainerLab creates a dedicated Docker bridge network (`acme-mgmt`) and assigns each node a fixed management IP from this range. These IPs — `172.20.20.11` for `spine-lon-01`, `172.20.20.21` for `leaf-lon-01`, and so on — are the addresses Ansible uses to connect to devices. They appear as `Management0` on the Arista cEOS nodes and as `eth0` on the FRR (Linux) nodes.

ContainerLab sets `Management0` automatically. You will notice that the startup configs deliberately contain no `Management0` configuration — ContainerLab handles it, and writing it yourself would conflict.

### Kind-level defaults

```yaml
kinds:
  ceos:
    image: ceos:4.32.2F
    env:
      INTFTYPE: eth
      ETBA: 1
      SKIP_ZEROTOUCH_BARRIER_IN_SYSDBINIT: 1
      CEOS: 1
      EOS_PLATFORM: ceoslab
      container: docker
    exec:
      - "Cli -p 15 -c 'configure\nmanagement api http-commands\nprotocol http\nno shutdown'"
      - "Cli -p 15 -c 'configure\nusername ansible privilege 15 role network-admin secret CHANGEME'"

  linux:
    image: quay.io/frrouting/frr:9.1.3
```

The `env` block sets environment variables that cEOS requires to initialise correctly inside a container. `INTFTYPE: eth` maps EOS interface names to `ethN` naming. `EOS_PLATFORM: ceoslab` tells EOS it is running in a virtual environment. These are not configuration choices — they are requirements for the container image to function.

The `exec` block runs EOS CLI commands after boot. This is a workaround for a known cEOS behaviour: eAPI settings from `startup-config` are occasionally not applied reliably during the first boot. The `exec` commands guarantee that eAPI HTTP is available and that the `ansible` user exists — both required for Ansible to connect. Without these, Ansible's initial `ping` check would fail on a freshly deployed node.

> 🔴 **Deep Dive** — The `exec` hook runs at priority 15 (`-p 15`) — slightly below the default EOS process priority — to avoid racing against other initialisation tasks. This detail matters in timing-sensitive lab restarts. If you have ever seen `ansible lab_active -m ping` fail immediately after `containerlab deploy` but succeed 30 seconds later, this race is the cause.

### Nodes and startup configs

Each node entry in `topology.nodes` specifies a management IP and either a `startup-config` file path or a `binds` list. The two are different mechanisms for the two different container types.

**Arista cEOS nodes** use `startup-config`:

```yaml
spine-lon-01:
  kind: ceos
  mgmt-ipv4: 172.20.20.11
  startup-config: startup_configs/spine-lon-01.cfg
```

ContainerLab copies the `.cfg` file into the cEOS container as its initial running configuration. The file is applied during boot, equivalent to booting a physical Arista switch with a pre-loaded startup config.

**FRR (Linux) nodes** use `binds`:

```yaml
fw-lon-01:
  kind: linux
  mgmt-ipv4: 172.20.20.32
  binds:
    - startup_configs/fw-lon-01/frr.conf:/etc/frr/frr.conf:ro
    - startup_configs/fw-lon-01/daemons:/etc/frr/daemons:ro
```

FRR runs as a Linux process inside the container. ContainerLab mounts the host files directly into the container filesystem. `frr.conf` is the FRR routing configuration (BGP, interfaces, route maps). `daemons` is a simple text file that tells FRR which daemons to start — in this lab, always `bgpd` and `zebra`.

The `:ro` suffix mounts the files read-only inside the container. This prevents FRR's `vtysh save` command from overwriting the startup config on disk.

### Where to explore the startup configs

```bash
ls topology/startup_configs/
```

You will find:
- `spine-lon-01.cfg`, `spine-lon-02.cfg`, `leaf-lon-01.cfg` … `border-lon-01.cfg` — Arista EOS bootstrap configs
- `fw-lon-01/`, `border-nyc-01/`, `border-sin-01/`, `border-fra-01/`, `branch-lon-01/`, `branch-nyc-01/` — FRR node directories, each with `frr.conf` and `daemons`

**Read an EOS bootstrap config:**

```bash
cat topology/startup_configs/spine-lon-01.cfg
```

You will find that it contains only what is needed for Ansible to connect: hostname, a local admin user, eAPI enabled on HTTP, SSH enabled, and local AAA. That is all. No interfaces, no BGP, no VRFs. The comment at the top of the file makes the intent explicit: *"This is a BOOTSTRAP config only."*

**Read an FRR startup config:**

```bash
cat topology/startup_configs/border-nyc-01/frr.conf
```

FRR stub nodes are different. Because they represent remote ends of WAN circuits that will never receive a full Ansible push (they are regional stubs, not managed devices), their `frr.conf` contains a complete working configuration: interfaces with IPs, BGP session definitions, route maps, and null routes for aggregate anchoring. What they get in `frr.conf` is what they run — forever.

### The links section

```yaml
links:
  - endpoints: ["spine-lon-01:eth1", "leaf-lon-01:eth1"]   # 10.1.100.0/31
  - endpoints: ["spine-lon-01:eth2", "leaf-lon-02:eth1"]   # 10.1.100.2/31
  ...
```

Each `endpoints` entry creates a virtual Ethernet cable between two containers. ContainerLab uses Linux virtual Ethernet pairs (`veth`) under the hood. The `eth1` interface on `spine-lon-01` connects to `eth1` on `leaf-lon-01`. On the EOS side, this maps to `Ethernet1` (ContainerLab handles the name translation automatically). On the FRR side, it remains `eth1`.

The IP addresses shown in the comments are assigned by the SoT and pushed by Ansible — ContainerLab only creates the link, not the addressing.

---

## How `render_configs.yml` works

The render playbook converts your SoT YAML into device config files. Open it:

```bash
cat playbooks/render_configs.yml
```

It runs with `connection: local` — no devices are involved. Everything happens on the control machine.

### Step 1 — Load global SoT data

The playbook's `pre_tasks` section loads global SoT files first:

```yaml
- name: Load platform defaults
  ansible.builtin.include_vars:
    file: "{{ sot_global_dir }}/platform_defaults.yml"
    name: global_platform_defaults
  run_once: true
```

`platform_defaults.yml` contains values that are consistent across all devices of a given platform — DNS servers, NTP server IPs and key IDs, AAA server IPs, logging facilities, SNMP users, and SSH settings. It is loaded once per play (`run_once: true`) and then shared to all hosts. When ACME changes its syslog server IP, this is the only file that changes.

After loading global data, the playbook resolves which platform defaults apply to the current host:

```yaml
- name: Set platform_defaults for arista_eos hosts
  ansible.builtin.set_fact:
    platform_defaults: "{{ global_platform_defaults.platforms.arista_eos }}"
  when: hostvars[inventory_hostname].platform | default('') == 'arista_eos'
```

An EOS host gets the `arista_eos` defaults. An FRR host gets the `frr` defaults. Each template can then reference `platform_defaults.ntp.servers` or `platform_defaults.aaa.tacacs_servers` without needing to know which platform it is targeting.

### Step 2 — Load the device SoT file

```yaml
- name: Find device SoT file
  ansible.builtin.find:
    paths: "{{ sot_device_dir }}"
    patterns: "{{ inventory_hostname }}.yml"
    recurse: true

- name: Load device SoT data
  ansible.builtin.include_vars:
    file: "{{ device_sot_search.files[0].path }}"
```

The playbook searches `sot/devices/` recursively for a file named `<hostname>.yml`. When found, it loads its contents directly as Ansible variables. Every key in the device YAML file — `hostname`, `platform`, `bgp`, `interfaces`, `vrfs`, `vlans` — becomes an Ansible variable available to the Jinja2 templates. No manual variable mapping is needed.

You can trace this: `sot/devices/lon-dc1/spine-lon-01.yml` defines `bgp.neighbors`. The `bgp.j2` template iterates `bgp.neighbors` to produce neighbor statements. The connection is direct.

### Step 3 — Render Jinja2 templates

For an EOS device, five render tasks run in sequence:

| Task | Template | Output file |
|------|----------|-------------|
| Base config | `templates/arista_eos/base.j2` | `01_base.conf` |
| VRF config | `templates/arista_eos/vrfs.j2` | `02_vrfs.conf` |
| VLAN config | `templates/arista_eos/vlans.j2` | `03_vlans.conf` |
| Interface config | `templates/arista_eos/interfaces.j2` | `04_interfaces.conf` |
| BGP config | `templates/arista_eos/bgp.j2` | `05_bgp.conf` |

Each task uses a `when` condition — for example, `when: platform == 'arista_eos' and vlans is defined`. If a device has no `vlans:` key in its SoT file (a spine never does), the VLAN task is skipped and no `03_vlans.conf` is produced. Only the sections that apply to a device are rendered.

FRR devices follow the same pattern with their own template set under `templates/frr/`.

**Explore the templates:**

```bash
ls templates/arista_eos/
# base.j2  bgp.j2  interfaces.j2  vlans.j2  vrfs.j2

cat templates/arista_eos/base.j2
```

`base.j2` produces the hostname, AAA, NTP, logging, SNMP, and eAPI stanzas. Notice that it reads from `platform_defaults` for shared values and from device variables for device-specific ones (`{{ hostname }}`, `{{ site }}`, `{{ role }}`).

```bash
cat templates/arista_eos/bgp.j2
```

`bgp.j2` iterates `bgp.neighbors` to produce neighbor statements and distinguishes iBGP from eBGP (if `neighbor.remote_as == bgp.local_as`, it is iBGP). If `bgp.role == 'route_reflector'` and `neighbor.route_reflector_client == true`, it adds the `route-reflector-client` keyword. This logic runs on every render — the template is the source of truth for how BGP config is expressed, not the device config file.

> 🔴 **Deep Dive** — Notice the comment at the top of every rendered config: `Rendered by automation pipeline — do NOT edit manually.` This is enforced by the template (`base.j2` writes it into every EOS config). Its purpose is not just documentation — it is a signal to anyone looking at device config directly that the file they are reading is an output, not an authoritative source.

### Step 4 — Assemble the full config

```yaml
- name: Assemble EOS full running config
  ansible.builtin.assemble:
    src: "{{ configs_output_dir }}/{{ inventory_hostname }}"
    dest: "{{ configs_output_dir }}/{{ inventory_hostname }}/running.conf"
    delimiter: "!"
    regexp: "^0[1-5]_.*\\.conf$"
```

The `assemble` module concatenates the numbered section files in alphabetical order (`01_base.conf`, `02_vrfs.conf`, `03_vlans.conf`, ...) into a single `running.conf`. The `regexp` filter means only files matching the `0[1-5]_*.conf` pattern are included — skipping the final `running.conf` itself to prevent circular inclusion. A `!` delimiter is inserted between sections, which is valid EOS config syntax (a comment line) and makes the file readable.

After the render playbook completes, you can inspect the output:

```bash
ls configs/spine-lon-01/
# 01_base.conf  05_bgp.conf  running.conf

cat configs/spine-lon-01/running.conf
```

The `running.conf` file is what gets pushed to the device. It is plain text — readable, diffable with `git diff`, and auditable. Compare it against the device's running config after a push to see exactly what changed.

---

## How `push_configs.yml` works

The push playbook connects to live devices and applies the rendered configs. Open it:

```bash
cat playbooks/push_configs.yml
```

### Pre-tasks — verify and capture state

Before touching any device, the playbook runs two safety checks:

**1. Verify the rendered config exists:**

```yaml
- name: Check rendered config exists
  ansible.builtin.stat:
    path: "{{ configs_dir }}/{{ inventory_hostname }}/running.conf"
  register: rendered_config

- name: Fail if rendered config missing
  ansible.builtin.fail:
    msg: >
      No rendered config found for {{ inventory_hostname }}.
      Run: ansible-playbook playbooks/render_configs.yml --limit {{ inventory_hostname }}
  when: not rendered_config.stat.exists
```

If you run `push_configs.yml` without first running `render_configs.yml`, the push fails immediately with a clear error message pointing to the solution. No device is touched.

**2. Capture pre-push state:**

For EOS devices, the playbook captures `show running-config` and `show bgp summary` before making any change. These are written to `configs/<hostname>/state/pre_push_<timestamp>.conf` and `pre_push_bgp_<timestamp>.txt`. This is the rollback baseline — if the push causes an issue, you have the exact pre-push state saved locally.

### EOS push — NAPALM atomic replace

```yaml
- name: Push config to EOS device (napalm replace)
  napalm.napalm.napalm_install_config:
    hostname: "{{ ansible_host }}"
    dev_os: eos
    config_file: "{{ configs_dir }}/{{ inventory_hostname }}/running.conf"
    commit_changes: true
    replace_config: true
    get_diffs: true
    diff_file: "{{ state_dir }}/diff_{{ push_timestamp }}.txt"
```

`replace_config: true` is the critical flag. This is an **atomic replace**, not a merge. NAPALM loads the rendered config as a candidate config on the EOS device, computes a diff against the current running config, and if `commit_changes: true`, replaces the running config in a single operation. If anything fails during the replace, EOS rolls back to the previous config automatically.

The diff is saved to `configs/<hostname>/state/diff_<timestamp>.txt`. You can inspect it after the push:

```bash
cat configs/spine-lon-01/state/diff_<timestamp>.txt
```

Lines beginning with `+` are additions. Lines beginning with `-` are removals. An empty diff means the device was already in the intended state — `render_configs.yml` is idempotent by design.

> 🔴 **Deep Dive** — The atomic replace approach means the push is all-or-nothing per device. If the `running.conf` you push would orphan a BGP session that is not in the SoT, that session is gone after the push. This is intentional: the SoT is the complete description of what the device should be. Anything not in the SoT does not belong on the device. This is what makes drift detection meaningful — if something appears on the device that is not in the SoT, it is drift, not a deliberate omission.

### FRR push — Docker exec

FRR nodes cannot use NAPALM. They are Linux containers; there is no EOS API. Instead, the push uses Docker directly:

```yaml
- name: Copy FRR running config to container
  ansible.builtin.shell: >
    docker exec -i clab-acme-lab-{{ inventory_hostname }}
    sh -c 'cat > /tmp/frr_push.conf'
    < {{ configs_dir }}/{{ inventory_hostname }}/running.conf
  delegate_to: localhost

- name: Reload FRR config via vtysh
  ansible.builtin.command: >
    docker exec clab-acme-lab-{{ inventory_hostname }} vtysh -f /tmp/frr_push.conf
  delegate_to: localhost
```

Both tasks use `delegate_to: localhost` — they run on the control machine and issue `docker exec` commands to the running container. The first task pipes the rendered config into the container as `/tmp/frr_push.conf`. The second task runs `vtysh -f` to load that config file into FRR's running state.

Unlike the NAPALM atomic replace, the FRR push via `vtysh -f` is a **merge**, not a replace. FRR applies the commands in the file additionally to what is already running. For the stub nodes in this lab, this is acceptable because their configs are static and fully contained in their `frr.conf` startup files.

### Post-tasks — capture and record

After the push, the playbook captures post-push BGP state and writes a push record:

```bash
cat configs/spine-lon-01/state/push_record_<timestamp>.yml
```

```yaml
hostname: spine-lon-01
timestamp: 20241015T142307
platform: arista_eos
result: success
rendered_config: configs/spine-lon-01/running.conf
diff: configs/spine-lon-01/state/diff_20241015T142307.txt
pre_state: configs/spine-lon-01/state/pre_push_bgp_20241015T142307.txt
post_state: configs/spine-lon-01/state/post_push_bgp_20241015T142307.txt
```

Every push leaves a traceable record: what was pushed, when, whether it succeeded, what changed, and what the BGP state looked like before and after. This is the audit trail that the compliance tooling in later chapters reads.

### Batching with `serial`

```yaml
serial: "{{ push_serial | default('20%') }}"
```

The `serial` keyword controls how many devices are pushed simultaneously. The default `20%` means with 13 active nodes, 2–3 devices are pushed at a time. This limits the blast radius if a push causes an unexpected issue — not all devices are changed at once.

To push a single device for testing:

```bash
ansible-playbook playbooks/push_configs.yml --limit spine-lon-01
```

To push all devices at once (useful for a clean lab rebuild):

```bash
ansible-playbook playbooks/push_configs.yml -e push_serial=100%
```

---

## The full picture

The sequence from SoT to running device config:

```
sot/global/platform_defaults.yml  ─┐
sot/global/ntp.yml                 ├─→ render_configs.yml ─→ configs/<host>/running.conf
sot/devices/<site>/<host>.yml     ─┘         │
         │                                    │ (Jinja2 templates)
         │                                    ↓
         │                          templates/arista_eos/*.j2
         │                          templates/frr/*.j2
         │
         └──→ push_configs.yml ──→ device (NAPALM replace / vtysh -f)
                                    │
                                    └──→ configs/<host>/state/ (diff, pre/post state, push record)
```

ContainerLab is responsible for the network topology and initial connectivity. The startup configs provide just enough bootstrap for Ansible to connect. `render_configs.yml` converts intent (SoT YAML) into syntax (device config files) without touching any device. `push_configs.yml` applies those files to the devices and records the result. The SoT is the only authoritative source; the device config is an output of it.

*Relevant source files to explore:*
- `topology/containerlab.yml` — lab topology definition
- `topology/startup_configs/` — bootstrap configs for all nodes
- `playbooks/render_configs.yml` — rendering playbook
- `playbooks/push_configs.yml` — push playbook
- `templates/arista_eos/` — EOS Jinja2 templates
- `templates/frr/` — FRR Jinja2 templates
- `configs/` — rendered config output (generated, not committed to git)
