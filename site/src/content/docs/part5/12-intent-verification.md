---
title: "Chapter 12: Testing the Network Without Touching the Network"
---

> 🔵 **Strategic** — sections marked
> 🟡 **Practitioner** — Modules 6.1, 6.2, 4.4

---

## Scenario

> 🔵 **Strategic**

It is 11:15 on a Tuesday. An engineer is reviewing a pull request. The change adds a new access VLAN to two leaf switches in London DC1. The VLAN is for a new team that is moving into the building. Nothing about the change looks unusual.

But the VLAN ID they have used is 100. And 100 is the TRADING zone VLAN.

The engineer catches it. But they only catch it because they happen to remember the VLAN numbering scheme. If they were new. If they were tired. If the review was one of twelve that day. The chance of this slipping through is real.

Batfish would not miss it. Batfish checks every proposed config against every defined intent on every pipeline run, automatically, in under 60 seconds. No tiredness. No memory dependency. No list of things to manually check.

This chapter explains how.

---

## What Batfish actually does

> 🔵 **Strategic**

Batfish is a network analysis tool that models the entire network from device configs — without connecting to any device. It builds a complete model of forwarding behaviour, routing tables, BGP topology, and ACL evaluation from the config text alone.

Given that model, you can ask questions that would be impossible or dangerous to answer by testing the live network:

- "If I apply this config to spine-lon-01, does leaf-lon-04 still have a path to border-lon-01?"
- "With spine-lon-01 removed from the path (simulating a failure), can leaf-lon-03 still reach border-lon-01 via spine-lon-02?"
- "Does any path exist from TRADING zone to CORPORATE zone, via any routing or forwarding mechanism?"
- "Are there any BGP sessions without MD5 authentication?"

These questions are answered in milliseconds on a static model. The same questions in a live network require either careful manual analysis (slow, error-prone) or actually testing the failure (dangerous, requires a maintenance window).

> 🔴 **Deep Dive** — Batfish models forwarding at the data plane and control plane simultaneously. It understands BGP route propagation, route-map filtering, prefix-list matching, ACL evaluation, VRF separation, and ECMP path selection. For the ACME lab, the most important capabilities are: (1) VRF reachability analysis (zone isolation), (2) route propagation tracing (routing policy), and (3) BGP session topology validation (standards and resilience).

---

## The test architecture

```
batfish/
  conftest.py           ← pytest fixtures and helpers
  run_checks.sh         ← CI wrapper script
  snapshots/
    acme_lab/
      configs/          ← rendered device configs (copied from configs/)
      batfish/
        network_interfaces.json   ← node role hints for Batfish
  tests/
    test_zone_isolation.py
    test_frankfurt_isolation.py
    test_bgp_standards.py
    test_resilience.py
    test_routing_policy.py
    test_path_trace.py
```

The `conftest.py` is the heart of the test infrastructure. It creates a Batfish session and pre-computes the DataFrames that most tests need:

```python
@pytest.fixture(scope="session")
def bf():
    session = Session(host=batfish_host)
    session.set_network("acme_investments")
    session.init_snapshot(str(snapshot_path), name=snapshot_name, overwrite=True)
    return session

@pytest.fixture(scope="session")
def bgp_sessions(bf):
    return bf.q.bgpSessionStatus().answer().frame()

@pytest.fixture(scope="session")
def routes(bf):
    return bf.q.routes().answer().frame()
```

Using `scope="session"` means Batfish initialises the snapshot once and reuses the session across all tests. Initialising the snapshot takes 10–30 seconds. Running all 40+ tests against the pre-loaded session takes another 30–90 seconds. Without session scope, each test would initialise its own snapshot — the suite would take 20 minutes instead of 2.

---

## Zone isolation tests

Open `batfish/tests/test_zone_isolation.py` and look at the first class:

```bash
cat batfish/tests/test_zone_isolation.py
```

The key assertion is a reachability check:

```python
result = bf.q.reachability(
    pathConstraints=PathConstraints(
        startLocation="@enter(leaf-lon-01[Vlan100])"
    ),
    headers=HeaderConstraints(
        srcIps=TRADING_PREFIX,    # 10.1.1.0/24
        dstIps=CORPORATE_PREFIX,  # 10.1.2.0/22
    ),
    actions=["ACCEPTED"],
).answer().frame()

assert_no_rows(
    result,
    "INTENT-001 VIOLATED: Traffic from TRADING can reach CORPORATE."
)
```

`startLocation="@enter(leaf-lon-01[Vlan100])"` — traffic enters the network at the TRADING zone SVI on leaf-lon-01.

`dstIps=CORPORATE_PREFIX` — it is addressed to the CORPORATE zone.

`actions=["ACCEPTED"]` — we are asking Batfish to find any path where this traffic is ACCEPTED (reaches its destination).

`assert_no_rows` — we assert that no such path exists.

If the assertion returns any rows, the test fails: a path from TRADING to CORPORATE exists, and INTENT-001 is violated.

> 🟡 **Practitioner** — Run the zone isolation tests:

```bash
cd batfish
pytest tests/test_zone_isolation.py -v
```

```
PASSED  tests/test_zone_isolation.py::TestTradingVrfIsolation::test_no_trading_routes_in_corporate_vrf
PASSED  tests/test_zone_isolation.py::TestTradingVrfIsolation::test_trading_to_corporate_denied
PASSED  tests/test_zone_isolation.py::TestTradingVrfIsolation::test_corporate_to_trading_denied
PASSED  tests/test_zone_isolation.py::TestDmzIsolation::test_trading_to_dmz_ssh_denied
PASSED  tests/test_zone_isolation.py::TestDmzIsolation::test_firewall_on_path
...
8 passed in 12.45s
```

---

## Running the full suite

```bash
pytest batfish/tests/ -v --tb=short
```

Or using the CI wrapper (which also builds the snapshot from rendered configs):

```bash
bash batfish/run_checks.sh
```

The CI wrapper:
1. Copies `configs/*/running.conf` to `batfish/snapshots/acme_lab/configs/`
2. Waits for Batfish to be ready (polls the health endpoint)
3. Runs pytest with JUnit output

---

## Exercise 6.1 — Zone isolation verification

> 🟡 **Practitioner**

The zone isolation tests are currently passing on the clean lab state. Make them fail by introducing a routing misconfiguration.

**Set up:**
```bash
ansible-playbook scenarios/common/reset_lab.yml
```

**Inject:**
Edit `sot/devices/lon-dc1/leaf-lon-01.yml`. Find the TRADING_VRF interface (`Vlan100`) and add a static route leaking into the default VRF:

```yaml
static_routes:
  - prefix: 10.1.2.0/22    # CORPORATE subnet
    next_hop: 10.1.1.253    # fake next-hop
    vrf: default            # leaks into the default VRF
```

Render the config:
```bash
ansible-playbook playbooks/render_configs.yml --limit leaf-lon-01
```

Copy to Batfish snapshot:
```bash
cp configs/leaf-lon-01/running.conf batfish/snapshots/acme_lab/configs/leaf-lon-01.cfg
```

Run the zone isolation tests:
```bash
pytest batfish/tests/test_zone_isolation.py -v
```

Observe which tests fail and read the failure messages carefully.

**Fix:** Restore the device file and re-run the tests to confirm they pass.

```bash
git checkout sot/devices/lon-dc1/leaf-lon-01.yml
ansible-playbook playbooks/render_configs.yml --limit leaf-lon-01
cp configs/leaf-lon-01/running.conf batfish/snapshots/acme_lab/configs/leaf-lon-01.cfg
pytest batfish/tests/test_zone_isolation.py -v
```

---

## Exercise 6.2 — Frankfurt violation (caught pre-push)

> 🟡 **Practitioner** — Module 4.1

This is the VLAN 100 scenario from the chapter introduction.

**Set up:**
```bash
ansible-playbook scenarios/common/reset_lab.yml
```

**Inject:** Edit `sot/devices/fra-dc1/border-fra-01.yml` and add `100` to the vlans list:

```yaml
vlans:
  - vlan_id: 100
    name: TRADING
```

Run the validator — it should fail:

```bash
python3 scripts/validate_sot.py
```

The validator stops the pipeline before Batfish even runs. But to see what Batfish would say about a Frankfurt device that somehow had VLAN 100:

```bash
ansible-playbook playbooks/render_configs.yml --limit border-fra-01 --extra-vars "skip_validate=true"
cp configs/border-fra-01/running.conf batfish/snapshots/acme_lab/configs/border-fra-01.cfg
pytest batfish/tests/test_frankfurt_isolation.py -v
```

Observe the Batfish failures. The Frankfurt tests provide a second line of defence — even if someone managed to bypass the SoT validator, Batfish would catch the violation.

**Fix:** `git checkout sot/devices/fra-dc1/border-fra-01.yml`

*Handbook reference: Chapter 11 (Intent-based networking), Chapter 7 (Batfish and network modelling)*
