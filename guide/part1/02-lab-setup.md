# Chapter 2: Setting Up the Lab

> 🟡 **Practitioner** — Module 0.1

*Estimated time: 45–60 minutes (most of that is image download and container startup)*

---

## What you are building

By the end of this chapter you will have 18 network nodes running on your laptop, BGP sessions established between them, and the full automation stack ready to use.

```
London DC1 (fully instantiated)
  spine-lon-01, spine-lon-02    [Arista cEOS]
  leaf-lon-01 .. leaf-lon-04    [Arista cEOS]
  border-lon-01                 [Arista cEOS]
  fw-lon-01                     [FRRouting]

Regional stubs (BGP peers only)
  border-nyc-01                 [FRRouting]
  border-sin-01                 [FRRouting]
  border-fra-01                 [FRRouting]

Branch stubs
  branch-lon-01                 [FRRouting]
  branch-nyc-01                 [FRRouting]

Management plane
  172.20.20.0/24 Docker bridge
```

---

## Step 1 — Clone the repository

```bash
git clone <repo-url> network-automation-lab
cd network-automation-lab
```

All commands in this guide assume you are working from the repository root unless otherwise stated.

---

## Step 2 — Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `requirements.txt` includes Ansible, pybatfish, jsonschema, PyYAML, and pytest.

---

## Step 3 — Get the Arista cEOS image

cEOS is Arista's containerised EOS. It is free but requires an Arista account.

1. Register at [arista.com](https://www.arista.com) (free)
2. Navigate to **Software Downloads → EOS → cEOS-lab**
3. Download `cEOS64-lab-4.32.2F.tar.xz`
4. Import the image:

```bash
docker import cEOS64-lab-4.32.2F.tar.xz ceos:4.32.2F
```

Verify:

```bash
docker images | grep ceos
# ceos   4.32.2F   <id>   <size>
```

The FRRouting image is pulled automatically by containerlab from Docker Hub.

---

## Step 4 — Start the lab

```bash
sudo containerlab deploy --topo topology/containerlab.yml
```

This will:
- Create Docker networks for the management plane and all inter-device links
- Start all 18 nodes (cEOS nodes take about 60–90 seconds to boot)
- Apply the startup configs from `topology/startup_configs/`

**Expected output (abbreviated):**

```
INFO[0000] Containerlab v0.54.0 started
INFO[0000] Parsing & checking topology file: topology/containerlab.yml
INFO[0001] Creating lab directory: /root/clab-acme_lab
INFO[0002] Creating container: spine-lon-01
...
INFO[0087] 18 nodes created
+---+------------------+-------+-----------+---------+------------------+
| # | Name             | Kind  | Image     | State   | IPv4 Address     |
+---+------------------+-------+-----------+---------+------------------+
| 1 | spine-lon-01     | ceos  | ceos:4... | running | 172.20.20.11/24  |
| 2 | spine-lon-02     | ceos  | ceos:4... | running | 172.20.20.12/24  |
| 3 | leaf-lon-01      | ceos  | ceos:4... | running | 172.20.20.21/24  |
...
```

---

## Step 5 — Verify basic reachability

```bash
# All management IPs should be reachable
ansible -i inventory/hosts.yml lab_active -m ping
```

**Expected:** All nodes return `"ping": "pong"`.

If some nodes are not reachable yet, wait 30 seconds and try again. cEOS takes a moment to initialise eAPI after first boot.

---

## Step 6 — Push the initial configs

The startup configs in `topology/startup_configs/` are minimal bootstrap configs — enough for Ansible connectivity, nothing more. The full working configs come from the SoT.

```bash
ansible-playbook playbooks/render_configs.yml
ansible-playbook playbooks/push_configs.yml
```

This renders the full device configs from the SoT (Jinja2 templates + device YAML) and pushes them to all active nodes.

The first push takes about 3–4 minutes as it connects to all 18 nodes sequentially.

---

## Step 7 — Verify BGP convergence

```bash
ansible-playbook playbooks/verify_state.yml
```

You should see all tasks passing. If any BGP sessions are not yet Established, the playbook will retry up to 6 times with a 10-second delay — BGP convergence across 18 nodes can take up to a minute.

**To check manually on a cEOS node:**

```bash
ssh admin@172.20.20.11       # spine-lon-01
spine-lon-01# show bgp summary
```

```
BGP summary information for VRF default
Router identifier 10.1.255.1, local AS number 65001
Neighbor        AS     MsgRcvd  MsgSent  InQ  OutQ  Up/Down  State/PfxRcd
10.1.255.11     65001  47       48       0    0     00:02:14 4
10.1.255.12     65001  46       47       0    0     00:02:13 4
10.1.255.13     65001  45       46       0    0     00:02:12 4
10.1.255.14     65001  44       45       0    0     00:02:11 4
10.1.255.20     65001  43       44       0    0     00:02:10 6
```

**To check an FRR node:**

```bash
ssh admin@172.20.20.51       # border-nyc-01
border-nyc-01# vtysh -c "show bgp summary"
```

---

## Step 8 — Start Batfish

Batfish runs as a Docker container. It analyses device configs without connecting to devices — it models the entire network offline.

```bash
docker run -d \
  --name batfish \
  -p 9997:9997 -p 9996:9996 \
  batfish/batfish:latest
```

Verify it is running:

```bash
curl -s http://localhost:9996/
# {"version":"...","status":"healthy"}
```

---

## Management IP reference

| Node | Role | IP |
|------|------|----|
| spine-lon-01 | Spine | 172.20.20.11 |
| spine-lon-02 | Spine | 172.20.20.12 |
| leaf-lon-01 | Leaf | 172.20.20.21 |
| leaf-lon-02 | Leaf | 172.20.20.22 |
| leaf-lon-03 | Leaf | 172.20.20.23 |
| leaf-lon-04 | Leaf | 172.20.20.24 |
| border-lon-01 | Border | 172.20.20.30 |
| fw-lon-01 | Firewall | 172.20.20.40 |
| border-nyc-01 | Stub | 172.20.20.51 |
| border-sin-01 | Stub | 172.20.20.52 |
| border-fra-01 | Stub | 172.20.20.53 |
| branch-lon-01 | Branch | 172.20.20.61 |
| branch-nyc-01 | Branch | 172.20.20.62 |

---

## Estimated resource usage

| Component | RAM | Notes |
|-----------|-----|-------|
| 7× Arista cEOS | ~1.4 GB | ~200 MB each |
| 6× FRRouting | ~300 MB | ~50 MB each |
| Batfish | ~1.5 GB | Spikes during analysis |
| GitLab CE (optional) | ~3.0 GB | Skip if using gitlab.com |
| OS + tooling | ~3.0 GB | Python, Docker overhead |
| **Total (without GitLab)** | **~6.2 GB** | Comfortable on 16 GB |
| **Total (with GitLab)** | **~9.2 GB** | Fine on 16 GB, tight on 8 GB |

---

## Teardown

When you are done with a session:

```bash
sudo containerlab destroy --topo topology/containerlab.yml
```

This removes all containers and network interfaces. Your SoT files and rendered configs are unchanged — they live in the repo, not in the containers.

---

## Troubleshooting

**cEOS node not reachable after 3 minutes:** Check Docker logs: `docker logs clab-acme_lab-spine-lon-01`. The most common cause is eAPI not starting — this sometimes requires a config restart: `docker exec -it clab-acme_lab-spine-lon-01 Cli -c "reload"`

**FRR node not running vtysh correctly:** Run `docker exec -it clab-acme_lab-border-nyc-01 vtysh` directly. If frr.conf was not applied, check `docker exec clab-acme_lab-border-nyc-01 cat /etc/frr/frr.conf`.

**BGP not converging after 5 minutes:** Run `ansible-playbook playbooks/collect_state.yml` and inspect `state/latest.json`. The most common issue is a startup config not being applied cleanly on first boot — re-running `push_configs.yml` resolves it.

**Out of disk space:** Arista cEOS images are large (~1.3 GB each uncompressed). Ensure you have at least 20 GB free before starting.
