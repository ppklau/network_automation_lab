"""
ACME Investments — Path Trace Intent Checks
test_path_trace.py

Parameterised reachability and traceroute assertions.
Used as: pre/post change verification, exercise 9.5 (path analysis),
         and as the "show me the proof" layer over zone isolation assertions.

These tests verify that the CORRECT paths exist (positive assertions)
and that forbidden paths do not (negative assertions). Together with
test_zone_isolation.py they form the complete reachability proof.

Requirement refs: REQ-007, REQ-008, REQ-020, REQ-021
Lab guide exercises enabled: 9.5, 5.1, 5.2, 6.1, 6.2
"""

import pytest
import pandas as pd
from pybatfish.datamodel import HeaderConstraints, PathConstraints

from conftest import (
    TRADING_PREFIX,
    CORPORATE_PREFIX,
    DMZ_PREFIX,
    MGMT_PREFIX,
    LON_LOOPBACK_RANGE,
    LON_SUPERNET,
    NYC_SUPERNET,
    SIN_SUPERNET,
    assert_no_rows,
)


# ── Positive path assertions ──────────────────────────────────────────────────
# These paths MUST be reachable. Failures here indicate a config or routing error.

POSITIVE_PATH_CASES = [
    pytest.param(
        "@enter(leaf-lon-01[Vlan100])",  # start: TRADING zone on leaf-lon-01
        "10.1.1.100",                    # src IP: TRADING host
        "10.1.1.200",                    # dst IP: another TRADING host
        "DELIVERED_TO_SUBNET",           # dst is a host in a connected subnet, not the router's own IP
        None,                            # IP protocol (None = any)
        None,                            # dst port (None = any)
        "TRADING_intra_zone_reachability",
        "Trading hosts on the same VLAN must be able to reach each other (intra-zone).",
        id="trading-intra-zone",
    ),
    pytest.param(
        "@enter(leaf-lon-01[Vlan200])",
        "10.1.2.100",
        "10.1.2.200",
        "DELIVERED_TO_SUBNET",           # dst is a host in a connected subnet, not the router's own IP
        None,
        None,
        "CORPORATE_intra_zone_reachability",
        "Corporate hosts on the same VLAN must reach each other (intra-zone).",
        id="corporate-intra-zone",
    ),
    pytest.param(
        "@enter(leaf-lon-01[Ethernet1])",
        "10.1.255.11",                  # leaf-lon-01 loopback
        "10.1.255.1",                   # spine-lon-01 loopback
        "ACCEPTED",
        None,
        None,
        "fabric_loopback_reachability",
        "Fabric loopbacks must be mutually reachable (iBGP update-source, INTENT-008).",
        id="fabric-loopback-reachability",
    ),
    pytest.param(
        "@enter(border-lon-01[Ethernet3])",
        "10.0.1.1",                     # NYC border WAN IP
        "10.1.255.20",                  # border-lon-01 loopback
        "ACCEPTED",
        None,
        None,
        "WAN_session_reachability",
        "WAN BGP session (LON ↔ NYC) must have mutual reachability for eBGP.",
        id="wan-ebgp-reachability",
    ),
    pytest.param(
        "@enter(leaf-lon-03[Vlan100])",  # leaf-lon-03 eth2 connects directly to fw-lon-01
        "10.1.1.100",
        "10.1.6.80",                    # DMZ host — market data server
        "DELIVERED_TO_SUBNET",          # fw-lon-01 eth1 is 10.1.6.254/24; host is in that subnet
        "TCP",
        "443",
        "TRADING_to_DMZ_market_data",
        "TRADING can reach DMZ on TCP 443 (market data feed — firewall rule 100).",
        id="trading-to-dmz-https-permitted",
    ),
]


# ── Negative path assertions ──────────────────────────────────────────────────
# These paths must NOT be reachable. Any ACCEPTED result is a policy violation.

NEGATIVE_PATH_CASES = [
    pytest.param(
        "@enter(leaf-lon-01[Vlan100])",  # TRADING zone
        "10.1.1.100",
        "10.1.2.100",                   # CORPORATE zone
        "TCP",
        None,
        "TRADING_to_CORPORATE_denied",
        "TRADING must not reach CORPORATE (INTENT-001, REQ-007, MiFID II).",
        id="trading-to-corporate-denied",
    ),
    pytest.param(
        "@enter(leaf-lon-01[Vlan200])",  # CORPORATE zone
        "10.1.2.100",
        "10.1.1.100",                   # TRADING zone
        "TCP",
        None,
        "CORPORATE_to_TRADING_denied",
        "CORPORATE must not reach TRADING (INTENT-001, REQ-007).",
        id="corporate-to-trading-denied",
    ),
    pytest.param(
        "@enter(leaf-lon-01[Vlan100])",
        "10.1.1.100",
        "10.1.6.100",                   # DMZ
        "TCP",
        "22",                           # SSH — not permitted
        "TRADING_to_DMZ_ssh_denied",
        "TRADING must not reach DMZ on SSH (INTENT-002, only ports 443/8443/6000 permitted).",
        id="trading-to-dmz-ssh-denied",
    ),
    pytest.param(
        "@enter(leaf-lon-01[Vlan200])",
        "10.1.2.100",
        "10.1.6.200",
        "TCP",
        "22",                           # SSH to DMZ from Corporate — not permitted
        "CORPORATE_to_DMZ_ssh_denied",
        "CORPORATE must not SSH to DMZ servers directly (INTENT-002).",
        id="corporate-to-dmz-ssh-denied",
    ),
]


class TestPositiveReachability:
    """
    Positive reachability: paths that MUST work.
    Failures here indicate a misconfiguration that breaks legitimate traffic.
    """

    @pytest.mark.parametrize(
        "start_location,src_ip,dst_ip,actions,protocol,dst_port,name,description",
        POSITIVE_PATH_CASES,
    )
    def test_permitted_path_is_accepted(
        self,
        bf,
        start_location,
        src_ip,
        dst_ip,
        actions,
        protocol,
        dst_port,
        name,
        description,
    ):
        """
        Verify that traffic permitted by policy actually reaches its destination.
        """
        header_kwargs = {"srcIps": src_ip, "dstIps": dst_ip}
        if protocol:
            header_kwargs["ipProtocols"] = [protocol]
        if dst_port:
            header_kwargs["dstPorts"] = [dst_port]

        result = bf.q.reachability(
            pathConstraints=PathConstraints(startLocation=start_location),
            headers=HeaderConstraints(**header_kwargs),
            actions=actions,
        ).answer().frame()

        assert not result.empty, (
            f"{name}: No ACCEPTED path found from {src_ip} to {dst_ip}. "
            f"{description}"
        )


class TestNegativeReachability:
    """
    Negative reachability: paths that must be DENIED.
    Any ACCEPTED result is a zone isolation violation.
    """

    @pytest.mark.parametrize(
        "start_location,src_ip,dst_ip,protocol,dst_port,name,description",
        NEGATIVE_PATH_CASES,
    )
    def test_forbidden_path_is_denied(
        self,
        bf,
        start_location,
        src_ip,
        dst_ip,
        protocol,
        dst_port,
        name,
        description,
    ):
        """
        Verify that traffic prohibited by policy is never ACCEPTED.
        """
        header_kwargs = {"srcIps": src_ip, "dstIps": dst_ip}
        if protocol:
            header_kwargs["ipProtocols"] = [protocol]
        if dst_port:
            header_kwargs["dstPorts"] = [dst_port]

        accepted = bf.q.reachability(
            pathConstraints=PathConstraints(startLocation=start_location),
            headers=HeaderConstraints(**header_kwargs),
            actions="ACCEPTED",
        ).answer().frame()

        assert_no_rows(
            accepted,
            f"{name}: POLICY VIOLATION — forbidden traffic is ACCEPTED. {description}"
        )


class TestSpineFailureResilience:
    """
    Simulate spine failure: with spine-lon-01 removed from the path,
    traffic must still flow between any leaf and border-lon-01.
    This validates INTENT-008 ECMP failover behaviour.
    """

    @pytest.mark.parametrize("leaf_node,leaf_loopback,border_loopback", [
        ("leaf-lon-01", "10.1.255.11", "10.1.255.20"),
        ("leaf-lon-02", "10.1.255.12", "10.1.255.20"),
        ("leaf-lon-03", "10.1.255.13", "10.1.255.20"),
        ("leaf-lon-04", "10.1.255.14", "10.1.255.20"),
    ])
    def test_leaf_to_border_reachable_without_spine_lon_01(
        self,
        bf,
        leaf_node,
        leaf_loopback,
        border_loopback,
    ):
        """
        With spine-lon-01 failed (deactivated node), the leaf must still
        reach border-lon-01 via spine-lon-02. Tests ECMP failover.
        """
        fork_name = "acme_lab_no_spine_lon_01"
        bf.fork_snapshot(
            base_name="acme_lab",
            name=fork_name,
            deactivate_nodes=["spine-lon-01"],
            overwrite=True,
        )
        bf.set_snapshot(fork_name)
        try:
            result = bf.q.reachability(
                pathConstraints=PathConstraints(
                    startLocation=f"@enter({leaf_node}[Ethernet1])",
                ),
                headers=HeaderConstraints(
                    srcIps=leaf_loopback,
                    dstIps=border_loopback,
                ),
                actions="ACCEPTED",
            ).answer().frame()
        finally:
            bf.set_snapshot("acme_lab")

        assert not result.empty, (
            f"INTENT-008 VIOLATED: {leaf_node} cannot reach border-lon-01 when "
            f"spine-lon-01 is down. Traffic must failover to spine-lon-02 (REQ-020)."
        )

    @pytest.mark.parametrize("leaf_node,leaf_loopback,border_loopback", [
        ("leaf-lon-01", "10.1.255.11", "10.1.255.20"),
        ("leaf-lon-03", "10.1.255.13", "10.1.255.20"),
    ])
    def test_leaf_to_border_reachable_without_spine_lon_02(
        self,
        bf,
        leaf_node,
        leaf_loopback,
        border_loopback,
    ):
        """
        Symmetric: with spine-lon-02 failed (deactivated node), leaves must
        still reach border via spine-lon-01.
        """
        fork_name = "acme_lab_no_spine_lon_02"
        bf.fork_snapshot(
            base_name="acme_lab",
            name=fork_name,
            deactivate_nodes=["spine-lon-02"],
            overwrite=True,
        )
        bf.set_snapshot(fork_name)
        try:
            result = bf.q.reachability(
                pathConstraints=PathConstraints(
                    startLocation=f"@enter({leaf_node}[Ethernet1])",
                ),
                headers=HeaderConstraints(
                    srcIps=leaf_loopback,
                    dstIps=border_loopback,
                ),
                actions="ACCEPTED",
            ).answer().frame()
        finally:
            bf.set_snapshot("acme_lab")

        assert not result.empty, (
            f"INTENT-008 VIOLATED: {leaf_node} cannot reach border-lon-01 when "
            f"spine-lon-02 is down. Traffic must failover to spine-lon-01 (REQ-020)."
        )
