# Third-Party Notices

This lab guide references, integrates with, or instructs the use of the following third-party
software. Each is subject to its own licence, independent of the proprietary licence governing
this Product. You are responsible for reviewing and complying with the terms of each.

---

## Arista cEOS

**Used for:** DC spine, leaf, and border router nodes in the containerlab topology.

Arista cEOS is proprietary software published by Arista Networks, Inc. A free account at
arista.com is required to download the cEOS image. Use is subject to Arista's End User
Licence Agreement (EULA).

- Licence type: Proprietary (Arista EULA)
- Download: [arista.com/en/support/software-download](https://www.arista.com/en/support/software-download)
- Image used in this lab: `ceos:4.32.2F` (or later)

This Product does not include or distribute the cEOS image. Instructions are provided for
obtaining it through the authorised Arista channel.

---

## FRRouting (FRR)

**Used for:** Branch routers, regional border stubs, and the lab firewall node in the
containerlab topology.

- Licence type: GNU General Public Licence v2 (GPL-2.0)
- Source and documentation: [frrouting.org](https://frrouting.org)
- Container image: `frrouting/frr` (Docker Hub)

The FRR container image used in this lab is pulled directly from Docker Hub. This Product
does not modify or redistribute FRR source code. The GPL-2.0 licence does not impose any
obligation on users of this Product beyond compliance with FRR's own licence when running FRR.

---

## containerlab

**Used for:** Orchestrating the lab topology — deploying and interconnecting all network nodes.

- Licence type: BSD 2-Clause
- Source and documentation: [containerlab.dev](https://containerlab.dev)

---

## Ansible

**Used for:** Rendering and pushing configuration to lab devices.

- Licence type: GNU General Public Licence v3 (GPL-3.0)
- Source and documentation: [ansible.com](https://www.ansible.com) / [github.com/ansible/ansible](https://github.com/ansible/ansible)

Ansible collections used in this lab (to be documented as installed):
- `ansible.netcommon` — Apache 2.0
- `arista.eos` — Apache 2.0
- `community.network` — GNU GPL v3

---

## Batfish / pybatfish

**Used for:** Network model analysis and intent verification (pre-push validation).

- Licence type: Apache 2.0
- Source and documentation: [batfish.org](https://www.batfish.org) / [github.com/batfish/batfish](https://github.com/batfish/batfish)
- pybatfish (Python client): Apache 2.0 — [github.com/batfish/pybatfish](https://github.com/batfish/pybatfish)

---

## GitLab CE (Community Edition)

**Used for:** CI/CD pipeline hosting in the lab environment.

- Licence type: MIT Expat (CE edition)
- Source and documentation: [gitlab.com](https://gitlab.com) / [gitlab.com/gitlab-org/gitlab-foss](https://gitlab.com/gitlab-org/gitlab-foss)

GitLab CE is run as a Docker container in the lab. This Product provides CI/CD pipeline
configuration (`.gitlab-ci.yml`) that runs within GitLab CE. The pipeline configuration itself
is part of this Product and is subject to this Product's proprietary licence.

---

## Prometheus

**Used for:** Metrics collection in the monitoring stack (Phase 9).

- Licence type: Apache 2.0
- Source and documentation: [prometheus.io](https://prometheus.io)

---

## Grafana

**Used for:** Dashboards and alerting in the monitoring stack (Phase 9).

- Licence type: GNU Affero General Public Licence v3 (AGPL-3.0)
- Source and documentation: [grafana.com](https://grafana.com)

Note: The Grafana AGPL-3.0 licence applies to Grafana itself. The dashboard JSON files included
in this Product (which configure Grafana) are part of this Product and subject to its proprietary
licence.

---

## Python standard library and dependencies

Python scripts in this lab (`scripts/`, `batfish/`) use the Python standard library and
third-party packages. Key dependencies and their licences:

| Package | Licence | Purpose |
|---------|---------|---------|
| `pyyaml` | MIT | YAML parsing in scripts |
| `jsonschema` | MIT | SoT schema validation |
| `jinja2` | BSD 3-Clause | Template rendering |
| `pytest` | MIT | Batfish test runner |
| `pybatfish` | Apache 2.0 | Batfish Python client |
| `netmiko` | MIT | Device connectivity |
| `napalm` | Apache 2.0 | Network device abstraction |

All packages are installed by the Purchaser via standard package managers (pip, Poetry).
This Product does not redistribute any of these packages.

---

## Network Automation Handbook

The conceptual framework and chapter references in this lab guide relate to the
**Network Automation Handbook** by Patrick Lau, published under Creative Commons
Attribution-NonCommercial 4.0 International (CC BY-NC 4.0).

- Published at: [ppklau.github.io/network_automation_handbook](https://ppklau.github.io/network_automation_handbook/)
- The Handbook is a separate work. Its CC BY-NC 4.0 licence does not apply to this Product.
- Cross-references to Handbook chapters are for navigational convenience and do not constitute
  incorporation of Handbook content into this Product.

---

*This file is provided for informational purposes. It is not legal advice. If you have questions
about licence compliance for specific third-party components, consult the respective project's
licence documentation.*
