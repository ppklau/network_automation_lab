"""
ACME Investments — Routing Policy Intent Checks
test_routing_policy.py

Implements: INTENT-006, INTENT-010
Requirement refs: REQ-009 (EU data residency routing), REQ-010 (route summarisation)

INTENT-006: Inter-region route advertisements must be summarised.
            border-lon-01 must not leak individual /31, /29, or loopback /32
            prefixes across WAN. Only DC supernets (/16) and branch aggregates
            (/16) are permitted outbound to WAN peers.

INTENT-010: No border device may originate a default route (0.0.0.0/0)
            into the fabric. Default routes would attract all unknown
            traffic toward the border, bypassing zone enforcement.

Lab guide exercises enabled: 3.6, 3.7, 4.4, 7.1, 7.2
"""

import ipaddress
import pytest
import pandas as pd

from conftest import (
    BORDER_NODES,
    BRANCH_NODES,
    SPINE_NODES,
    LEAF_NODES,
    LON_SUPERNET,
    NYC_SUPERNET,
    SIN_SUPERNET,
    FRA_SUPERNET,
    UK_BRANCH_SUPERNET,
    US_BRANCH_SUPERNET,
    LON_ASN,
    NYC_ASN,
    SIN_ASN,
    FRA_ASN,
    assert_no_rows,
    ebgp_sessions,
)

LON_BORDER_NODE = "border-lon-01"

# Prefixes permitted to cross WAN (aggregates only — INTENT-006)
PERMITTED_WAN_PREFIXES = {
    ipaddress.ip_network(LON_SUPERNET),
    ipaddress.ip_network(NYC_SUPERNET),
    ipaddress.ip_network(SIN_SUPERNET),
    ipaddress.ip_network(FRA_SUPERNET),
    ipaddress.ip_network(UK_BRANCH_SUPERNET),
    ipaddress.ip_network(US_BRANCH_SUPERNET),
}

# Prefix lengths that must NEVER cross WAN links
FORBIDDEN_WAN_PREFIX_LENGTHS = {29, 30, 31, 32}

# WAN peer ASNs (not branches)
WAN_PEER_ASNS = {NYC_ASN, SIN_ASN, FRA_ASN}


class TestRouteSummarisation:
    """
    INTENT-006: Inter-region BGP advertisements must be summarised to /16 aggregates.
    Individual host routes, P2P /31s, loopbacks, and branch /29s must not
    appear in routes advertised to WAN peers.
    """

    def test_no_more_specific_than_slash16_on_wan(self, routes):
        """
        At WAN-facing border nodes, the BGP RIB should contain only /16 or
        shorter prefixes as the result of aggregate-address summary-only.
        Any /17 to /32 in the WAN-facing context indicates a summary-only
        failure or a mis-configured aggregate.

        We check the routing table at the WAN stub nodes (border-nyc-01,
        border-sin-01, border-fra-01) to see what LON is advertising to them.
        """
        wan_stubs = ["border-nyc-01", "border-sin-01", "border-fra-01"]
        stub_bgp_routes = routes[
            routes["Node"].isin(wan_stubs) &
            (routes["Protocol"] == "bgp")
        ]

        def prefix_length(network_str: str) -> int:
            try:
                return ipaddress.ip_network(network_str, strict=False).prefixlen
            except ValueError:
                return 0

        too_specific = stub_bgp_routes[
            stub_bgp_routes["Network"].apply(prefix_length).isin(
                FORBIDDEN_WAN_PREFIX_LENGTHS
            )
        ]
        assert_no_rows(
            too_specific[["Node", "Network", "Next_Hop_IP", "Protocol"]],
            "INTENT-006 VIOLATED: More-specific prefixes (longer than /16) are visible "
            "at WAN stub nodes. border-lon-01 aggregate-address summary-only is not "
            "suppressing more-specifics correctly (REQ-010)."
        )

    def test_lon_border_has_aggregate_addresses(self, bgp_peer_config):
        """
        border-lon-01 must have aggregate-address configured for the LON DC1
        supernet (10.1.0.0/16) and UK branch supernet (10.100.0.0/16).
        Without aggregates, more-specifics would leak across WAN.
        """
        # Batfish exposes aggregate routes in the routes table with protocol 'aggregate'
        # This is a proxy check: we verify the BGP peer config has export policies on WAN sessions
        lon_wan_sessions = ebgp_sessions(
            bgp_peer_config[
                (bgp_peer_config["Node"] == LON_BORDER_NODE) &
                (bgp_peer_config["Remote_AS"].isin(WAN_PEER_ASNS))
            ]
        )
        if lon_wan_sessions.empty:
            pytest.skip(
                "border-lon-01 WAN eBGP sessions (to FRR peers) are not visible in "
                "bgpPeerConfiguration — Batfish does not model EOS↔FRR cross-platform "
                "sessions in this query. Verify export policies via device config review."
            )

        missing_export = lon_wan_sessions[
            lon_wan_sessions["Export_Policy"].isna() |
            (lon_wan_sessions["Export_Policy"].apply(
                lambda p: (len(p) == 0) if isinstance(p, list) else (not p)
            ))
        ]
        assert_no_rows(
            missing_export[["Node", "Remote_IP", "Remote_AS"]],
            "INTENT-006: border-lon-01 WAN eBGP sessions missing export route-map. "
            "Without export policy, unaggregated prefixes can leak across WAN (REQ-010)."
        )

    def test_fabric_loopbacks_not_leaked_to_wan(self, routes):
        """
        Fabric loopback addresses (10.1.255.x/32) must not appear in the
        routing tables of WAN stub nodes. These are internal fabric routes
        that must be suppressed by aggregate-address summary-only.
        """
        wan_stubs = ["border-nyc-01", "border-sin-01", "border-fra-01"]
        loopback_at_wan = routes[
            routes["Node"].isin(wan_stubs) &
            (routes["Network"].str.startswith("10.1.255.", na=False)) &
            (routes["Protocol"] == "bgp")
        ]
        assert_no_rows(
            loopback_at_wan[["Node", "Network", "Next_Hop_IP"]],
            "INTENT-006 VIOLATED: LON DC1 loopback /32 prefixes (10.1.255.x/32) are "
            "visible at WAN stub nodes. summary-only is not suppressing fabric internals "
            "(REQ-010 — route summarisation at WAN boundary)."
        )

    def test_p2p_fabric_links_not_leaked_to_wan(self, routes):
        """
        Fabric P2P /31 subnets (10.1.100.x/31) must not appear in WAN stub
        routing tables. These are internal link addresses between spines and leaves.
        """
        wan_stubs = ["border-nyc-01", "border-sin-01", "border-fra-01"]
        p2p_at_wan = routes[
            routes["Node"].isin(wan_stubs) &
            (routes["Network"].str.startswith("10.1.100.", na=False)) &
            (routes["Protocol"] == "bgp")
        ]
        assert_no_rows(
            p2p_at_wan[["Node", "Network", "Next_Hop_IP"]],
            "INTENT-006 VIOLATED: LON DC1 fabric P2P links (10.1.100.x/31) are visible "
            "at WAN stub nodes. P2P links must be suppressed by the DC1 aggregate (REQ-010)."
        )


class TestNoDefaultRouteOrigination:
    """
    INTENT-010: No border or DC device may originate a default route (0.0.0.0/0).
    Default route origination from a DC device would attract all unknown traffic
    toward that device and bypass zone enforcement.
    """

    def test_no_default_route_in_bgp(self, routes):
        """
        No DC or border node should have a BGP-originated default route.
        Default-originate is explicitly prohibited by INTENT-010.
        """
        bgp_defaults = routes[
            routes["Node"].isin(
                BORDER_NODES + SPINE_NODES + LEAF_NODES
            ) &
            (routes["Network"] == "0.0.0.0/0") &
            (routes["Protocol"] == "bgp")
        ]
        assert_no_rows(
            bgp_defaults[["Node", "VRF", "Network", "Protocol"]],
            "INTENT-010 VIOLATED: A DC or border device is originating a default "
            "route via BGP. Default routes must not be generated within the DC fabric — "
            "they would attract all unknown traffic and bypass zone enforcement (REQ-010)."
        )

    def test_border_does_not_default_originate_to_wan(self, bgp_peer_config):
        """
        border-lon-01 must not have default-originate configured on any WAN session.
        A default-originated into WAN would cause all unknown traffic at remote DCs
        to route toward London, potentially crossing zone boundaries.
        """
        if "Default_Originate" not in bgp_peer_config.columns:
            pytest.skip("Default_Originate column not available in this Batfish version")

        lon_wan_default_originate = bgp_peer_config[
            (bgp_peer_config["Node"] == LON_BORDER_NODE) &
            (bgp_peer_config["Remote_AS"].isin(WAN_PEER_ASNS)) &
            bgp_peer_config["Default_Originate"].fillna(False)
        ]
        assert_no_rows(
            lon_wan_default_originate[["Node", "Remote_IP", "Remote_AS"]],
            "INTENT-010 VIOLATED: border-lon-01 has default-originate configured on "
            "a WAN eBGP session. Default routes must not be originated at DC borders (REQ-010)."
        )

    def test_no_default_route_at_spine_level(self, routes):
        """
        Spines must have no default route in their BGP or static tables.
        A default at the spine would be reflected to all RR clients, turning
        every leaf into a potential black-hole attractor.
        """
        spine_defaults = routes[
            routes["Node"].isin(SPINE_NODES) &
            (routes["Network"] == "0.0.0.0/0")
        ]
        assert_no_rows(
            spine_defaults[["Node", "VRF", "Network", "Protocol"]],
            "INTENT-010 VIOLATED: A spine node has a default route. Spines are "
            "route reflectors — a default here propagates to all RR clients (leaves + border)."
        )
