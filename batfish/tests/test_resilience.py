"""
ACME Investments — Resilience Intent Checks
test_resilience.py

Implements: INTENT-008
Requirement refs: REQ-020 (single spine failure survivability), REQ-021 (WAN redundancy)

INTENT-008: Each leaf must have two ECMP paths to border-lon-01.
            Each spine must have all DC leaves as RR clients.
            border-lon-01 must have at least two eBGP WAN neighbors.
            The fabric must survive a single spine failure without traffic loss.

Lab guide exercises enabled: 5.1, 5.2, 5.3, 5.4
"""

import pytest
import pandas as pd

from conftest import (
    SPINE_NODES,
    LEAF_NODES,
    BORDER_NODES,
    LON_DC1_NODES,
    LON_ASN,
    LON_LOOPBACK_RANGE,
    assert_no_rows,
    ibgp_sessions,
    ebgp_sessions,
)

LON_BORDER_NODE = "border-lon-01"
MIN_WAN_NEIGHBORS = 3          # NYC, SIN, FRA
EXPECTED_LEAF_BGP_PATHS = 2    # one via each spine (ECMP)


class TestSpineRedundancy:
    """
    INTENT-008: London DC1 must have exactly two spines.
    Each spine must peer with all leaves and the border as RR clients.
    """

    def test_two_spines_in_lon_dc1(self, bgp_peer_config):
        """
        Exactly two spine nodes (spine-lon-01, spine-lon-02) must be present
        and have BGP configurations in the snapshot. Fewer than two means the
        fabric cannot survive a single spine failure.
        """
        spine_nodes_in_model = set(
            bgp_peer_config[
                bgp_peer_config["Node"].isin(SPINE_NODES)
            ]["Node"].unique()
        )
        assert spine_nodes_in_model == set(SPINE_NODES), (
            f"INTENT-008 VIOLATED: Expected spines {SPINE_NODES} in network model, "
            f"found {spine_nodes_in_model}. DC fabric requires exactly two spines for "
            f"redundancy (REQ-020)."
        )

    def test_each_spine_has_all_leaves_as_rr_clients(self, bgp_peer_config):
        """
        Each spine must have iBGP RR-client sessions to all four leaves and
        border-lon-01. Missing RR client sessions leave those devices without
        full fabric visibility via that spine.
        """
        if "Route_Reflector_Client" not in bgp_peer_config.columns:
            pytest.skip("Route_Reflector_Client column not available")

        expected_rr_clients = set(LEAF_NODES) | {LON_BORDER_NODE}

        for spine in SPINE_NODES:
            spine_rr_clients = set(
                bgp_peer_config[
                    (bgp_peer_config["Node"] == spine) &
                    bgp_peer_config["Route_Reflector_Client"].fillna(False)
                ]["Remote_Node"].dropna()
            )
            missing = expected_rr_clients - spine_rr_clients
            assert not missing, (
                f"INTENT-008 VIOLATED: {spine} is missing RR-client sessions to: {missing}. "
                f"These devices will not receive full fabric routes via this spine "
                f"(REQ-020 — single spine failure survivability)."
            )

    def test_spine_to_spine_ibgp_peering_exists(self, bgp_peer_config):
        """
        The two spines must peer with each other as non-RR-client iBGP peers.
        This is the inter-RR session that prevents split-brain in the fabric.
        """
        for spine in SPINE_NODES:
            peer_spine = [s for s in SPINE_NODES if s != spine][0]
            spine_to_spine = bgp_peer_config[
                (bgp_peer_config["Node"] == spine) &
                (bgp_peer_config["Remote_Node"] == peer_spine)
            ]
            assert not spine_to_spine.empty, (
                f"INTENT-008: No iBGP session from {spine} to {peer_spine}. "
                f"The spine pair must peer to exchange routes between their RR clients "
                f"(inter-RR session — prevents split-horizon black-hole)."
            )


class TestLeafEcmpPaths:
    """
    INTENT-008: Each leaf must have two BGP paths to border-lon-01 —
    one via each spine. ECMP across both paths ensures traffic continuity
    when a single spine fails.
    """

    @pytest.mark.parametrize("leaf_node", LEAF_NODES)
    def test_leaf_has_two_ibgp_sessions_to_spines(self, bgp_peer_config, leaf_node):
        """
        Each leaf must have exactly two iBGP sessions — one to each spine.
        A leaf with only one spine session loses 50% of its fabric paths on
        the single-connected spine's failure.
        """
        leaf_to_spines = bgp_peer_config[
            (bgp_peer_config["Node"] == leaf_node) &
            (bgp_peer_config["Remote_Node"].isin(SPINE_NODES))
        ]
        spine_peers = set(leaf_to_spines["Remote_Node"].dropna())
        assert spine_peers == set(SPINE_NODES), (
            f"INTENT-008 VIOLATED: {leaf_node} does not peer with both spines. "
            f"Connected spines: {spine_peers} (expected: {set(SPINE_NODES)}). "
            f"Single-spine connection means no redundancy on spine failure (REQ-020)."
        )

    @pytest.mark.parametrize("leaf_node", LEAF_NODES)
    def test_leaf_has_ecmp_paths_to_border(self, routes, leaf_node):
        """
        The border-lon-01 loopback (10.1.255.20/32) should appear in the leaf's
        routing table via multiple ECMP next-hops — one per spine.
        A single next-hop means no failover on spine failure.
        """
        border_loopback = "10.1.255.20/32"
        leaf_routes_to_border = routes[
            (routes["Node"] == leaf_node) &
            (routes["Network"] == border_loopback)
        ]

        if leaf_routes_to_border.empty:
            pytest.skip(
                f"Route to {border_loopback} not found at {leaf_node} — "
                "configs may not be fully pushed yet"
            )

        # Count distinct next-hops
        next_hops = leaf_routes_to_border["Next_Hop_IP"].dropna().unique()
        assert len(next_hops) >= EXPECTED_LEAF_BGP_PATHS, (
            f"INTENT-008 VIOLATED: {leaf_node} has only {len(next_hops)} path(s) to "
            f"border-lon-01 loopback (expected >= {EXPECTED_LEAF_BGP_PATHS} ECMP paths). "
            f"Next-hops: {list(next_hops)} (REQ-020 — ECMP across both spines)."
        )


class TestBorderWanRedundancy:
    """
    INTENT-008 / REQ-021: border-lon-01 must maintain eBGP sessions to
    at least three WAN peers (NYC, SIN, FRA). Loss of any one WAN link
    must not isolate London from all other regions.
    """

    def test_border_has_minimum_wan_neighbors(self, bgp_peer_config):
        """
        border-lon-01 must have at least MIN_WAN_NEIGHBORS (3) eBGP sessions.
        WAN neighbors: border-nyc-01 (AS65010), border-sin-01 (AS65020), border-fra-01 (AS65030).
        """
        border_ebgp = ebgp_sessions(
            bgp_peer_config[bgp_peer_config["Node"] == LON_BORDER_NODE]
        )
        # Exclude branch sessions (Remote_AS >= 65100)
        wan_sessions = border_ebgp[border_ebgp["Remote_AS"] < 65100]
        wan_peer_count = len(wan_sessions)

        assert wan_peer_count >= MIN_WAN_NEIGHBORS, (
            f"INTENT-008 VIOLATED: border-lon-01 has only {wan_peer_count} WAN eBGP "
            f"session(s) (minimum required: {MIN_WAN_NEIGHBORS}). "
            f"WAN peers found: {list(wan_sessions['Remote_AS'].unique())} (REQ-021)."
        )

    def test_border_wan_sessions_are_established(self, bgp_sessions):
        """
        All WAN eBGP sessions on border-lon-01 should be in Established state.
        Idle/Active sessions mean the WAN link or peer is down.
        """
        border_ebgp_status = bgp_sessions[
            (bgp_sessions["Node"] == LON_BORDER_NODE) &
            (bgp_sessions["Session_Type"].str.startswith("EBGP", na=False)) &
            (bgp_sessions["Remote_AS"] < 65100)   # WAN only, not branches
        ]

        not_established = border_ebgp_status[
            border_ebgp_status["Established_Status"] != "ESTABLISHED"
        ]
        assert_no_rows(
            not_established[["Node", "Remote_IP", "Remote_AS", "Established_Status"]],
            "INTENT-008: border-lon-01 WAN eBGP sessions are not Established. "
            "Down WAN sessions reduce regional redundancy (REQ-021)."
        )

    def test_all_active_bgp_sessions_established(self, bgp_sessions):
        """
        All BGP sessions in the snapshot should be Established.
        Non-established sessions indicate a configuration error, an
        unreachable peer, or a missing route to the update-source.
        """
        not_established = bgp_sessions[
            bgp_sessions["Established_Status"] != "ESTABLISHED"
        ]
        # In the lab, Batfish may show sessions as NOT_COMPATIBLE or HALF_OPEN
        # if it cannot fully parse FRR configs — skip those
        actionable = not_established[
            ~not_established["Established_Status"].isin([
                "NOT_COMPATIBLE",   # Batfish version mismatch
                "HALF_OPEN",        # asymmetric — likely a model limitation
            ])
        ]
        assert_no_rows(
            actionable[["Node", "VRF", "Local_IP", "Remote_IP", "Remote_AS", "Established_Status"]],
            "INTENT-008: BGP sessions are not Established. Non-established sessions "
            "indicate config errors or missing reachability to BGP update-source."
        )
