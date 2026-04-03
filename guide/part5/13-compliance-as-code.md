# Chapter 13: Compliance as Code

> 🔵 **Strategic** — sections marked
> 🟡 **Practitioner** — Modules 4.3, 4.4, 6.3, 7.1, 7.2

---

## The compliance test suite

The ACME Batfish suite covers five compliance domains, each implemented as a separate test file. Together they form a continuous compliance verification layer — run on every pipeline push, every config render, every time the snapshot is updated.

| Test file | Intent(s) | What it verifies |
|-----------|-----------|-----------------|
| `test_zone_isolation.py` | INTENT-001, 002 | TRADING/CORPORATE/DMZ zone separation |
| `test_frankfurt_isolation.py` | INTENT-003 | FRA TRADING ring-fence, APAC isolation |
| `test_bgp_standards.py` | INTENT-005 | MD5 auth, route-maps, branch prefix scope |
| `test_resilience.py` | INTENT-008 | Dual-spine, ECMP, WAN redundancy |
| `test_routing_policy.py` | INTENT-006, 010 | Route summarisation, no default origination |
| `test_path_trace.py` | REQ-007/008/020/021 | End-to-end path assertions, failover simulation |

This chapter walks through three of these in depth: BGP standards, routing policy, and resilience. Zone isolation was covered in Chapter 12.

---

## BGP standards

> 🟡 **Practitioner** — Modules 7.1, 7.2

Open `batfish/tests/test_bgp_standards.py`.

### MD5 on all sessions

```python
def test_md5_on_all_bgp_sessions(self, bgp_peer_config):
    no_auth = bgp_peer_config[
        bgp_peer_config["MD5_Auth_Enabled"].fillna(False) == False
    ]
    assert_no_rows(
        no_auth[["Node", "VRF", "Local_IP", "Remote_IP", "Session_Type"]],
        "INTENT-005 VIOLATED: BGP session(s) without MD5 authentication detected."
    )
```

This test pulls the full BGP peer configuration DataFrame and checks the `MD5_Auth_Enabled` column. Any session where this column is False (or null) is a failure.

In the ACME SoT, every `bgp.neighbors` entry has an `md5_password_ref`. The validate script checks that the ref exists in the vault. This test verifies that the rendered config actually has MD5 configured — the end-to-end check that the SoT value made it all the way to the device config.

**Exercise 7.2 setup:**

```bash
ansible-playbook scenarios/common/reset_lab.yml
ansible-playbook scenarios/ch07/ex72_inject.yml   # introduces MD5 mismatch on branch-lon-01
```

Now run the BGP standards test:

```bash
pytest batfish/tests/test_bgp_standards.py::TestBgpAuthentication -v
```

The test will pass — Batfish tests the BGP configuration, not whether the session is actually established. The MD5 mismatch will be visible when you run the health check playbook and see the session as Idle.

```bash
ansible-playbook playbooks/daily_health_check.yml --limit branch-lon-01
```

This shows why Batfish and operational state checks are complementary: Batfish validates configuration intent; operational checks validate actual state.

### Route-maps on all eBGP sessions

```python
def test_all_ebgp_sessions_have_route_maps(self, bgp_peer_config):
    ebgp = ebgp_sessions(bgp_peer_config)
    missing_import = ebgp[
        ebgp["Import_Policy"].isna() |
        (ebgp["Import_Policy"].apply(
            lambda p: len(p) == 0 if isinstance(p, list) else not p
        ))
    ]
    assert_no_rows(
        missing_import[["Node", "Remote_IP", "Remote_AS"]],
        "INTENT-005: eBGP sessions without import route-maps."
    )
```

Every eBGP session must have an explicit import and export route-map. A session without a route-map will accept or advertise any route — exactly the behaviour that causes prefix leaks. The test checks both import and export independently.

### Branch prefix scope

```python
@pytest.mark.parametrize("branch_node,assigned_prefix", [
    ("branch-lon-01", BRANCH_LON_01_PREFIX),
    ("branch-nyc-01", BRANCH_NYC_01_PREFIX),
])
def test_branch_advertises_only_assigned_prefix(
    self, routes, branch_node, assigned_prefix
):
    branch_routes = routes[
        (routes["Node"] == branch_node) &
        (routes["Protocol"] == "bgp")
    ]
    assigned_net = ipaddress.ip_network(assigned_prefix)
    violations = branch_routes[
        ~branch_routes["Network"].apply(
            lambda n: ipaddress.ip_network(n, strict=False).subnet_of(assigned_net)
        )
    ]
    assert_no_rows(
        violations[["Node", "Network"]],
        f"INTENT-005: {branch_node} advertising prefixes outside its assigned /29."
    )
```

This test is parametrized over branch nodes. For each branch, it retrieves all BGP routes visible at that node and verifies that every advertised prefix falls within the branch's assigned /29 subnet. If a branch somehow advertised a summary route or a prefix from a different subnet, this test would catch it.

---

## Routing policy

> 🟡 **Practitioner** — Modules 3.6, 4.4

Open `batfish/tests/test_routing_policy.py`.

### No more-specific than /16 at WAN stubs

```python
def test_no_more_specific_than_slash16_on_wan(self, routes):
    wan_stubs = ["border-nyc-01", "border-sin-01", "border-fra-01"]
    stub_bgp_routes = routes[
        routes["Node"].isin(wan_stubs) &
        (routes["Protocol"] == "bgp")
    ]
    too_specific = stub_bgp_routes[
        stub_bgp_routes["Network"].apply(prefix_length).isin(
            FORBIDDEN_WAN_PREFIX_LENGTHS  # {29, 30, 31, 32}
        )
    ]
    assert_no_rows(
        too_specific[["Node", "Network", "Next_Hop_IP", "Protocol"]],
        "INTENT-006 VIOLATED: More-specific prefixes are visible at WAN stub nodes."
    )
```

This test checks the routing tables of the WAN stub routers to verify that only /16 aggregates from London are visible. If border-lon-01's `aggregate-address summary-only` configuration is missing or misconfigured, individual /32 loopbacks, /31 P2P links, or /24 zone prefixes would leak to the WAN peers. The WAN stubs are the right place to check: they are the recipients of whatever London is advertising.

> 🔵 **Strategic** — Route summarisation at the WAN boundary is both a routing efficiency measure and a security control. A remote DC that can see individual /32 loopbacks from London's fabric has a detailed map of the internal topology. This information could be used in reconnaissance if the routing plane were ever compromised. Summarisation reduces the information exposed to WAN peers to the minimum necessary: "London has a 10.1.0.0/16 block."

### No default route origination

```python
def test_no_default_route_in_bgp(self, routes):
    bgp_defaults = routes[
        routes["Node"].isin(BORDER_NODES + SPINE_NODES + LEAF_NODES) &
        (routes["Network"] == "0.0.0.0/0") &
        (routes["Protocol"] == "bgp")
    ]
    assert_no_rows(
        bgp_defaults[["Node", "VRF", "Network", "Protocol"]],
        "INTENT-010 VIOLATED: A DC or border device is originating a default route via BGP."
    )
```

A default route originated inside the fabric would attract all unknown-destination traffic toward the originating device, bypassing zone enforcement. The firewalls are designed to be on the path for inter-zone traffic — a default route would create a path that bypasses them entirely. This test ensures no such route exists.

---

## Resilience

> 🟡 **Practitioner** — Modules 5.1, 5.2

Open `batfish/tests/test_resilience.py`.

### Spine failure simulation

The most interesting resilience test is in `test_path_trace.py`:

```python
def test_leaf_to_border_reachable_without_spine_lon_01(
    self, bf, leaf_node, leaf_loopback, border_loopback,
):
    result = bf.q.reachability(
        pathConstraints=PathConstraints(
            startLocation=f"@enter({leaf_node}[Loopback0])",
            forbiddenLocations="spine-lon-01",   # simulate spine failure
        ),
        headers=HeaderConstraints(
            srcIps=leaf_loopback,
            dstIps=border_loopback,
        ),
        actions=["ACCEPTED"],
    ).answer().frame()

    assert not result.empty, (
        f"INTENT-008 VIOLATED: {leaf_node} cannot reach border-lon-01 when "
        f"spine-lon-01 is down."
    )
```

`forbiddenLocations="spine-lon-01"` tells Batfish to exclude spine-lon-01 from all path computations. This is not a real failure — spine-lon-01 is still running in the lab. It is a model-based simulation: "compute reachability as if spine-lon-01 did not exist." If the result is non-empty, a path exists via spine-lon-02. If it is empty, leaf-to-border reachability fails on spine-lon-01 failure.

This test runs parametrized over all four leaf nodes and both spine failure scenarios. That is 8 test cases, each verifying a different single-spine failure mode, in approximately 2 seconds of compute time.

> 🔵 **Strategic** — In production, verifying this would require actually shutting down a spine, observing traffic, and bringing it back up. That is a maintenance window, a risk, and a test that can only be run occasionally. Batfish verifies the same property on every pipeline push, against the proposed configs, in seconds. If a config change would break single-spine failover — a missing iBGP session, a missing ECMP path, a route-map that blocks the secondary path — the pipeline fails before the change reaches production.

---

## Exercise 4.4 — Cross-border data flow assertion

> 🟡 **Practitioner**

ACME's compliance team wants a Batfish assertion that APAC-origin traffic cannot traverse the Frankfurt region. This is a topological encoding of GDPR Article 5(1)(c) — data minimisation for EU-bound routing.

The Frankfurt border stub (`border-fra-01`) should not have a direct BGP path to APAC nodes (AS 65020 for Singapore, AS 65021 for HKG). All APAC traffic at Frankfurt should arrive via London (10.0.3.x next-hop range).

Open `batfish/tests/test_frankfurt_isolation.py` and find `test_no_fra_apac_direct_path`.

1. Read the test and understand what it is checking
2. Run it: `pytest batfish/tests/test_frankfurt_isolation.py::TestFrankfurtRingfence::test_no_fra_apac_direct_path -v`
3. Look at the `bgp_edges` fixture in `conftest.py` — what does `bf.q.bgpEdges()` return?
4. Write a complementary test that verifies APAC routes at Frankfurt have a LON next-hop (10.0.3.x). A stub for this is in `test_frankfurt_isolation.py` as `test_apac_routes_via_lon_only`.

**Verify:** Your test passes on the current lab state.

*Handbook reference: Chapter 11 (Intent-based networking), Chapter 7 (Compliance automation), Chapter 4 (BGP policy)*
