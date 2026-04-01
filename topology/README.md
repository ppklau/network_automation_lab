# ACME Investments — Containerlab Topology

Lab topology for the ACME Investments Network Automation Lab.

13 nodes, 18 links. London DC1 is fully instantiated (Arista cEOS). Regional DC stubs and branches use FRRouting (FRR) to minimise memory footprint.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| containerlab | ≥ 0.54 | `bash -c "$(curl -sL https://get.containerlab.tools)"` |
| Docker | ≥ 24 | Standard Docker Engine or Docker Desktop |
| Arista cEOS image | 4.32.2F | Requires Arista account — see below |
| FRR image | frrouting/frr:9.1.0 | Public Docker Hub — pulled automatically |
| RAM | ≥ 16 GB | ~1 GB per cEOS node; 7 cEOS nodes = ~7 GB |
| CPU | ≥ 8 cores | cEOS is CPU-heavy during boot |

### Obtain the cEOS image

1. Register at [arista.com](https://www.arista.com/en/support/software-download) (free)
2. Download `cEOS64-lab-4.32.2F.tar.xz` from Software Downloads → EOS → cEOS-lab
3. Import the image:

```bash
docker import cEOS64-lab-4.32.2F.tar.xz ceos:4.32.2F
```

Verify:

```bash
docker images ceos
# REPOSITORY   TAG       IMAGE ID       CREATED         SIZE
# ceos         4.32.2F   <id>           <date>          ~2 GB
```

---

## Deploy the lab

```bash
cd topology
sudo containerlab deploy -t containerlab.yml
```

Containerlab will:
1. Create the `acme-mgmt` Docker bridge (172.20.20.0/24)
2. Pull `frrouting/frr:9.1.0` if not present
3. Start all 13 nodes and wire the 18 links
4. Assign management IPs via `mgmt-ipv4` (see table below)

Boot takes 2–4 minutes. cEOS nodes emit `System ready` to their console when up.

---

## Management IP map

| Node | Role | mgmt-ipv4 | Platform |
|---|---|---|---|
| spine-lon-01 | Spine (RR) | 172.20.20.11 | Arista cEOS |
| spine-lon-02 | Spine (RR) | 172.20.20.12 | Arista cEOS |
| leaf-lon-01 | Leaf | 172.20.20.21 | Arista cEOS |
| leaf-lon-02 | Leaf | 172.20.20.22 | Arista cEOS |
| leaf-lon-03 | Leaf | 172.20.20.23 | Arista cEOS |
| leaf-lon-04 | Leaf | 172.20.20.24 | Arista cEOS |
| border-lon-01 | Border (WAN hub) | 172.20.20.31 | Arista cEOS |
| fw-lon-01 | Firewall | 172.20.20.32 | FRR |
| border-nyc-01 | Regional stub (NYC) | 172.20.20.41 | FRR |
| border-sin-01 | Regional stub (SIN) | 172.20.20.42 | FRR |
| border-fra-01 | Regional stub (FRA) | 172.20.20.43 | FRR |
| branch-lon-01 | Branch CPE (UK) | 172.20.20.51 | FRR |
| branch-nyc-01 | Branch CPE (US) | 172.20.20.52 | FRR |

SSH to a cEOS node:

```bash
ssh admin@172.20.20.11   # admin / admin
```

Shell into an FRR node:

```bash
sudo docker exec -it clab-acme-lab-fw-lon-01 vtysh
```

---

## Verify the lab is up

### cEOS — check management API (required for Ansible)

```bash
ssh admin@172.20.20.11 "show management api http-commands"
# Expect: Enabled   HTTP server: running on port 80
```

### FRR — check BGP status on border stubs

```bash
# border-nyc-01 should have eBGP to border-lon-01 in Idle/Active
# (production config not yet pushed; bootstrap only)
sudo docker exec clab-acme-lab-border-nyc-01 vtysh -c "show bgp summary"
```

### Verify all nodes are running

```bash
sudo containerlab inspect -t containerlab.yml
```

All 13 nodes should show `running`.

---

## Bootstrap vs. production config

**cEOS nodes** start with a minimal bootstrap config (`startup_configs/*.cfg`):
- Hostname set
- `admin` user (privilege 15, password `admin`)
- eAPI enabled (HTTP, no HTTPS)
- SSH enabled
- Local AAA

**Management0** is NOT configured in the bootstrap — containerlab assigns it automatically via `mgmt-ipv4`.

**Full production configs** (interfaces, BGP, VRFs, VLANs, ACLs, NTP, syslog) are pushed by Ansible from the SoT:

```bash
ansible-playbook playbooks/push_configs.yml
```

**FRR nodes** start with their full config in `startup_configs/<node>/frr.conf`. BGP sessions on FRR stubs will be in `Idle`/`Active` until the cEOS border node receives its full config from Ansible.

---

## Topology diagram

```
           ┌──────────────┐     ┌──────────────┐
           │ spine-lon-01 │     │ spine-lon-02 │
           │  AS65001 RR  │     │  AS65001 RR  │
           └──┬──┬──┬──┬──┘     └──┬──┬──┬──┬──┘
    E1-4 eBGP │  │  │  │           │  │  │  │
              │  │  │  │           │  │  │  │ E1-4
         ┌────┘  │  │  └──────┐    │  │  │  │
   ┌─────┘       │  └──────┐  │    │  │  │  │
   │   leaf-lon-01   leaf-lon-02  leaf-lon-03  leaf-lon-04
   │   172.20.20.21  .22         .23           .24
   │
   │  (E5 on each spine → border-lon-01)
   │
   │         ┌─────────────────┐
   └─────────┤  border-lon-01  ├── E3 ──▶ border-nyc-01 (AS65010)
             │    AS65001      ├── E4 ──▶ border-sin-01 (AS65020)
             │  172.20.20.31   ├── E5 ──▶ border-fra-01 (AS65030) [TRADING-filtered]
             │                 ├── E6 ──▶ fw-lon-01 [DMZ boundary]
             │                 └── E7 ──▶ branch-lon-01 (AS65100)
             └─────────────────┘

             border-nyc-01 E4 ──▶ branch-nyc-01 (AS65120)

  leaf-lon-03 E5 ──▶ fw-lon-01 eth2 [TRADING+CORPORATE]
  leaf-lon-04 E5 ──▶ fw-lon-01 eth3 [DMZ+MGMT]
```

---

## Destroy the lab

```bash
cd topology
sudo containerlab destroy -t containerlab.yml --cleanup
```

`--cleanup` removes the Docker bridge and all container state. Lab data in `topology/` is not affected.

---

## Memory footprint (approximate)

| Node type | Count | RAM each | Total |
|---|---|---|---|
| Arista cEOS 4.32.2F | 7 | ~1.0 GB | ~7.0 GB |
| FRRouting 9.1.0 | 6 | ~64 MB | ~0.4 GB |
| **Total** | **13** | | **~7.5 GB** |

A host with 16 GB RAM is comfortable. 12 GB is marginal if other processes are running.
