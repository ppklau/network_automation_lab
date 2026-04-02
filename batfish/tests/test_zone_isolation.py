"""
ACME Investments — Zone Isolation Intent Checks
test_zone_isolation.py

Implements: INTENT-001, INTENT-002
Requirement refs: REQ-007 (MiFID II trading isolation), REQ-008 (zone segmentation)

INTENT-001: No reachability from TRADING zone to CORPORATE zone.
            TRADING_VRF (10.1.1.0/24) must be completely isolated from
            CORPORATE_VRF (10.1.2.0/22). The firewall (fw-lon-01) is the
            only permitted junction, and it must enforce a DENY policy.

INTENT-002: TRADING zone must not reach DMZ except via the firewall's
            explicitly permitted rule (TCP 443/8443/6000 for market data).
            Unrestricted TRADING → DMZ reachability is prohibited.

Lab guide exercises enabled: 6.1, 6.2, 6.3, 4.1, 11.1
"""

import pytest
import pandas as pd
from pybatfish.datamodel import HeaderConstraints, PathConstraints

from conftest import (
    TRADING_PREFIX,
    CORPORATE_PREFIX,
    DMZ_PREFIX,
    MGMT_PREFIX,
    LON_DC1_NODES,
    LEAF_NODES,
    assert_no_rows,
    ibgp_sessions,
)


class TestTradingVrfIsolation:
    """
    INTENT-001: TRADING_VRF must have no reachability to CORPORATE_VRF.
    Verified at the routing level: no routes from one VRF leak into the other.
    """

    def test_trading_routes_absent_from_corporate_vrf(self, routes):
        """
        TRADING zone prefix (10.1.1.0/24) must not appear in any node's
        CORPORATE_VRF routing table. A route leak here would bypass the
        firewall and allow unrestricted east-west traffic (REQ-007).
        """
        trading_in_corporate = routes[
            (routes["VRF"] == "CORPORATE_VRF") &
            (routes["Network"].str.startswith("10.1.1.", na=False))
        ]
        assert_no_rows(
            trading_in_corporate,
            "INTENT-001 VIOLATED: TRADING prefix found in CORPORATE_VRF route table. "
            "This constitutes a route leak that bypasses firewall enforcement (REQ-007)."
        )

    def test_corporate_routes_absent_from_trading_vrf(self, routes):
        """
        CORPORATE zone prefix (10.1.2.0/22) must not appear in TRADING_VRF.
        Prevents corporate servers from being reachable within the trading VRF.
        """
        corporate_in_trading = routes[
            (routes["VRF"] == "TRADING_VRF") &
            (routes["Network"].str.startswith("10.1.2.", na=False) |
             routes["Network"].str.startswith("10.1.3.", na=False) |
             routes["Network"].str.startswith("10.1.4.", na=False) |
             routes["Network"].str.startswith("10.1.5.", na=False))
        ]
        assert_no_rows(
            corporate_in_trading,
            "INTENT-001 VIOLATED: CORPORATE prefix found in TRADING_VRF route table (REQ-007)."
        )

    def test_no_direct_bgp_sessions_between_trading_and_corporate(self, bgp_peer_config):
        """
        No BGP session should exist that would peer a TRADING_VRF interface
        directly to a CORPORATE_VRF interface on any device. All inter-zone
        reachability must flow through fw-lon-01.
        """
        trading_vrf_sessions = bgp_peer_config[bgp_peer_config["VRF"] == "TRADING_VRF"]
        corporate_vrf_sessions = bgp_peer_config[bgp_peer_config["VRF"] == "CORPORATE_VRF"]

        # Get the peer IPs from TRADING_VRF sessions
        trading_peer_ips = set(trading_vrf_sessions["Remote_IP"].dropna().astype(str))
        # Get the local IPs from CORPORATE_VRF sessions
        corporate_local_ips = set(corporate_vrf_sessions["Local_IP"].dropna().astype(str))

        cross_zone_peers = trading_peer_ips & corporate_local_ips
        assert not cross_zone_peers, (
            f"INTENT-001 VIOLATED: Direct BGP sessions span TRADING_VRF and CORPORATE_VRF "
            f"(REQ-007). Cross-zone peer IPs: {cross_zone_peers}"
        )

    def test_trading_reachability_to_corporate_denied(self, bf):
        """
        Full reachability check: traffic from the TRADING zone (10.1.1.0/24)
        to the CORPORATE zone (10.1.2.0/22) must not be ACCEPTED anywhere
        in the network model.

        If any path shows ACCEPTED, the firewall policy is missing or mis-configured.
        DENIED results are expected (firewall DENY rule 900/901).
        """
        result = bf.q.reachability(
            pathConstraints=PathConstraints(
                startLocation="@enter(leaf-lon-01[Vlan100])",
            ),
            headers=HeaderConstraints(
                srcIps=TRADING_PREFIX,
                dstIps=CORPORATE_PREFIX,
            ),
            actions=["ACCEPTED"],
        ).answer().frame()

        assert_no_rows(
            result,
            "INTENT-001 VIOLATED: TRADING zone traffic reaches CORPORATE zone without "
            "firewall denial (REQ-007, MiFID II Article 25 — trading system isolation)."
        )

    def test_corporate_reachability_to_trading_denied(self, bf):
        """
        Reverse direction: CORPORATE → TRADING must also be blocked.
        Firewall rule 901 (DENY_CORPORATE_TRADING) enforces this.
        """
        result = bf.q.reachability(
            pathConstraints=PathConstraints(
                startLocation="@enter(leaf-lon-01[Vlan200])",
            ),
            headers=HeaderConstraints(
                srcIps=CORPORATE_PREFIX,
                dstIps=TRADING_PREFIX,
            ),
            actions=["ACCEPTED"],
        ).answer().frame()

        assert_no_rows(
            result,
            "INTENT-001 VIOLATED: CORPORATE zone traffic reaches TRADING zone without "
            "firewall denial (REQ-007, MiFID II — reverse isolation)."
        )


class TestDmzIsolation:
    """
    INTENT-002: TRADING zone has no unrestricted reachability to DMZ.
    The only permitted path is TCP 443/8443/6000 (market data feeds),
    enforced by firewall rule 100 (TRADING_TO_MARKET_DATA).
    """

    def test_dmz_routes_absent_from_trading_vrf(self, routes):
        """
        DMZ prefix (10.1.6.0/24) must not appear as a route in TRADING_VRF.
        A route here would allow unrestricted TRADING → DMZ traffic without
        firewall inspection.
        """
        dmz_in_trading = routes[
            (routes["VRF"] == "TRADING_VRF") &
            (routes["Network"].str.startswith("10.1.6.", na=False))
        ]
        assert_no_rows(
            dmz_in_trading,
            "INTENT-002 VIOLATED: DMZ prefix found in TRADING_VRF route table. "
            "Unrestricted TRADING → DMZ reachability bypasses market data firewall rule (REQ-008)."
        )

    def test_trading_unrestricted_to_dmz_denied(self, bf):
        """
        Unrestricted TCP traffic (e.g. port 22, not market data) from TRADING
        to DMZ must be DENIED. Only ports 443, 8443, 6000 are permitted
        by firewall rule 100.
        """
        result = bf.q.reachability(
            pathConstraints=PathConstraints(
                startLocation="@enter(leaf-lon-01[Vlan100])",
            ),
            headers=HeaderConstraints(
                srcIps=TRADING_PREFIX,
                dstIps=DMZ_PREFIX,
                ipProtocols=["TCP"],
                dstPorts=["22"],       # SSH — must not be permitted
            ),
            actions=["ACCEPTED"],
        ).answer().frame()

        assert_no_rows(
            result,
            "INTENT-002 VIOLATED: TRADING zone can reach DMZ on port 22 (SSH). "
            "Only market data ports 443/8443/6000 are permitted (REQ-008, FW rule 100)."
        )

    def test_fw_lon_01_is_on_path_trading_to_dmz(self, bf):
        """
        Any permitted traffic from TRADING to DMZ must pass through fw-lon-01.
        Verify that the firewall node appears in the trace for market-data TCP.
        """
        result = bf.q.traceroute(
            startLocation="@enter(leaf-lon-01[Vlan100])",
            headers=HeaderConstraints(
                srcIps="10.1.1.100",
                dstIps="10.1.6.100",
                ipProtocols=["TCP"],
                dstPorts=["443"],
            ),
        ).answer().frame()

        if result.empty:
            pytest.skip("No traceroute result — firewall config may not be in snapshot")

        # fw-lon-01 must appear in at least one trace hop
        all_nodes_in_traces = set()
        for _, row in result.iterrows():
            for trace in row.get("Traces", []):
                for hop in trace.hops:
                    all_nodes_in_traces.add(hop.node)

        assert "fw-lon-01" in all_nodes_in_traces, (
            "INTENT-002: fw-lon-01 is not on the path from TRADING to DMZ. "
            "Market data traffic must be inspected by the firewall (REQ-008)."
        )


class TestVrfSeparationTopology:
    """
    Structural checks: VRF topology must enforce zone isolation through
    interface assignment, not just routing table contents.
    """

    def test_trading_vrf_interfaces_not_in_corporate_vrf(self, interface_props):
        """
        No interface should appear in both TRADING_VRF and CORPORATE_VRF.
        Interface VRF assignment is the hardware-level enforcement boundary.
        """
        trading_intfs = set(
            interface_props[interface_props["VRF"] == "TRADING_VRF"]["Interface"]
            .astype(str)
        )
        corporate_intfs = set(
            interface_props[interface_props["VRF"] == "CORPORATE_VRF"]["Interface"]
            .astype(str)
        )
        overlap = trading_intfs & corporate_intfs
        assert not overlap, (
            f"INTENT-001: Interfaces assigned to both TRADING_VRF and CORPORATE_VRF: {overlap}. "
            "VRF boundary collapsed — zone isolation cannot be enforced."
        )
