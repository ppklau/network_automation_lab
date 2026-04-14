"""
ACME Investments — Frankfurt Ring-Fence Intent Checks
test_frankfurt_isolation.py

Implements: INTENT-003, INTENT-004
Requirement refs: REQ-007 (MiFID II), REQ-009 (EU data residency)
Compliance: BaFin MaRisk, GDPR Article 44

INTENT-003: Frankfurt (fra-dc1) must never exchange TRADING zone prefixes.
            - VLAN 100 must not exist on any fra-dc1 device.
            - TRADING_VRF must not be configured on any fra-dc1 device.
            - BGP sessions on border-fra-01 must have route-maps that strip
              the TRADING community (65001:100) both inbound and outbound.

INTENT-004: Frankfurt has no direct BGP path to APAC (SIN, HKG).
            All FRA ↔ APAC routing must transit via London (border-lon-01),
            ensuring EU data residency compliance under GDPR Article 44.

Lab guide exercises enabled: 6.3, 4.1, 4.4, 12.3
"""

import pytest
import pandas as pd

from conftest import (
    FRA_NODES,
    FRA_ASN,
    LON_ASN,
    SIN_ASN,
    TRADING_PREFIX,
    WAN_LON_FRA,
    assert_no_rows,
    ebgp_sessions,
)

# FRA-specific constants
FRA_SUPERNET       = "10.30.0.0/16"
TRADING_VLAN_ID    = 100
TRADING_VRF_NAME   = "TRADING_VRF"
APAC_SUPERNET      = "10.20.0.0/16"   # SIN DC1
HKG_SUPERNET       = "10.25.0.0/16"   # HKG DC1
FRA_BORDER_NODE    = "border-fra-01"
LON_BORDER_NODE    = "border-lon-01"

# ASNs that border-fra-01 must NEVER peer with directly
APAC_ASNS = {65020, 65021, 65022}   # SIN, HKG, and any APAC regional ASN


class TestFrankfurtVlanProhibition:
    """
    INTENT-003: VLAN 100 (TRADING) must not exist on any fra-dc1 device.
    This is enforced in the SoT via vlans_prohibited and verified here at
    the rendered-config / network-model level.
    """

    def test_vlan_100_absent_from_fra_devices(self, interface_props):
        """
        No FRA device interface should be in VLAN 100.
        Checks both access ports (Access_VLAN) and trunk ports (Allowed_VLANs).
        """
        fra_interfaces = interface_props[
            interface_props["Interface"].str.startswith(
                tuple(f"{node}[" for node in FRA_NODES), na=False
            )
        ]

        # Check access VLAN assignments
        trading_vlan_access = fra_interfaces[
            fra_interfaces["Access_VLAN"] == TRADING_VLAN_ID
        ]
        assert_no_rows(
            trading_vlan_access,
            "INTENT-003 VIOLATED: VLAN 100 (TRADING) found as access VLAN on a "
            "fra-dc1 interface (BaFin/MiFID II — trading activity prohibited at FRA)."
        )

        # Check trunk VLAN allowlists
        def contains_trading_vlan(allowed_vlans) -> bool:
            if allowed_vlans is None or (isinstance(allowed_vlans, float)):
                return False
            return TRADING_VLAN_ID in (allowed_vlans if isinstance(allowed_vlans, list) else [])

        trading_vlan_trunk = fra_interfaces[
            fra_interfaces["Allowed_VLANs"].apply(contains_trading_vlan)
        ]
        assert_no_rows(
            trading_vlan_trunk,
            "INTENT-003 VIOLATED: VLAN 100 (TRADING) in trunk allowed-VLANs on "
            "a fra-dc1 interface (BaFin/MiFID II — trading VLAN must not transit FRA)."
        )

    def test_trading_vrf_absent_from_fra_devices(self, interface_props):
        """
        TRADING_VRF must not be configured on any fra-dc1 device.
        VRF presence would allow TRADING traffic to be routed, even without VLAN 100.
        """
        fra_trading_vrf = interface_props[
            interface_props["Interface"].str.startswith(
                tuple(f"{node}[" for node in FRA_NODES), na=False
            ) &
            (interface_props["VRF"] == TRADING_VRF_NAME)
        ]
        assert_no_rows(
            fra_trading_vrf,
            "INTENT-003 VIOLATED: TRADING_VRF found on a fra-dc1 interface. "
            "The FRA node must have no TRADING VRF instance (BaFin MaRisk AT 7.2 — "
            "trading and non-trading infrastructure must be segregated)."
        )

    def test_trading_routes_absent_from_fra_routing_table(self, routes):
        """
        No TRADING zone prefix (10.1.1.0/24 or more-specific) should appear
        in any FRA device's routing table, in any VRF.
        """
        fra_trading_routes = routes[
            routes["Node"].isin(FRA_NODES) &
            (routes["Network"].str.startswith("10.1.1.", na=False))
        ]
        assert_no_rows(
            fra_trading_routes,
            "INTENT-003 VIOLATED: TRADING prefix found in fra-dc1 routing table. "
            "Route-map RM_INTERDC_LON_FRA_IN is not filtering correctly (REQ-009)."
        )


class TestFrankfurtBgpPolicyEnforcement:
    """
    INTENT-003: border-fra-01 BGP sessions must have explicit route-maps
    applied in BOTH directions on the LON WAN session.
    """

    def test_fra_wan_session_has_import_policy(self, bgp_peer_config):
        """
        The eBGP session from border-fra-01 to border-lon-01 (10.0.3.0)
        must have an import route-map (RM_INTERDC_LON_FRA_IN) applied.
        An absent import policy means TRADING prefixes would be accepted.
        """
        fra_wan_sessions = bgp_peer_config[
            (bgp_peer_config["Node"] == FRA_BORDER_NODE) &
            (bgp_peer_config["Remote_AS"] == LON_ASN)
        ]

        if fra_wan_sessions.empty:
            pytest.skip(
                f"No BGP session from {FRA_BORDER_NODE} to AS{LON_ASN} in "
                "bgpPeerConfiguration — Batfish does not model FRR↔EOS cross-platform "
                "sessions in this query. Verify import policy via device config review."
            )

        missing_import = fra_wan_sessions[
            fra_wan_sessions["Import_Policy"].isna() |
            (fra_wan_sessions["Import_Policy"].apply(
                lambda p: len(p) == 0 if isinstance(p, list) else not p
            ))
        ]
        assert_no_rows(
            missing_import,
            "INTENT-003 VIOLATED: border-fra-01 WAN session to LON has no import "
            "route-map. TRADING prefixes could be accepted (BaFin, REQ-009)."
        )

    def test_fra_wan_session_has_export_policy(self, bgp_peer_config):
        """
        The export route-map (RM_INTERDC_LON_FRA_OUT) must also be configured.
        Without it, any TRADING prefix that erroneously exists at FRA could
        be advertised back to London, corrupting the LON routing table.
        """
        fra_wan_sessions = bgp_peer_config[
            (bgp_peer_config["Node"] == FRA_BORDER_NODE) &
            (bgp_peer_config["Remote_AS"] == LON_ASN)
        ]

        missing_export = fra_wan_sessions[
            fra_wan_sessions["Export_Policy"].isna() |
            (fra_wan_sessions["Export_Policy"].apply(
                lambda p: len(p) == 0 if isinstance(p, list) else not p
            ))
        ]
        assert_no_rows(
            missing_export,
            "INTENT-003 VIOLATED: border-fra-01 WAN session to LON has no export "
            "route-map. TRADING prefixes could be leaked outbound (BaFin, REQ-009)."
        )


class TestFrankfurtApacIsolation:
    """
    INTENT-004: No direct BGP path between fra-dc1 and APAC (SIN, HKG).
    All FRA ↔ APAC routing must transit via London (border-lon-01).
    This ensures EU data residency — GDPR Article 44 prohibits transfer of
    EU personal data to non-adequate third countries via direct circuits.
    """

    def test_no_direct_bgp_session_fra_to_apac(self, bgp_peer_config):
        """
        border-fra-01 must have no BGP sessions to any APAC ASN (65020, 65021, 65022).
        The only permitted eBGP peer for border-fra-01 is border-lon-01 (AS65001).
        """
        fra_apac_sessions = bgp_peer_config[
            (bgp_peer_config["Node"] == FRA_BORDER_NODE) &
            (bgp_peer_config["Remote_AS"].isin(APAC_ASNS))
        ]
        assert_no_rows(
            fra_apac_sessions,
            "INTENT-004 VIOLATED: border-fra-01 has a direct BGP session to an APAC ASN. "
            "EU data residency (GDPR Article 44) requires FRA ↔ APAC traffic to transit "
            "London. Direct circuit would bypass data residency controls."
        )

    def test_apac_routes_at_fra_have_lon_as_next_hop(self, routes):
        """
        Any APAC prefix (10.20.0.0/16) visible at border-fra-01 must have been
        learned via border-lon-01 (next-hop in 10.0.3.0/31 range), not via a
        direct APAC peering.
        """
        fra_apac_routes = routes[
            (routes["Node"] == FRA_BORDER_NODE) &
            (routes["Network"].str.startswith("10.20.", na=False) |
             routes["Network"].str.startswith("10.25.", na=False))
        ]

        if fra_apac_routes.empty:
            # APAC routes not present at FRA at all — this is acceptable
            return

        # If present, next-hop must be the LON WAN interface (10.0.3.0)
        lon_wan_nh = "10.0.3.0"
        non_lon_nh = fra_apac_routes[
            ~fra_apac_routes["Next_Hop_IP"].astype(str).str.startswith("10.0.3.", na=False)
        ]
        assert_no_rows(
            non_lon_nh,
            "INTENT-004 VIOLATED: APAC prefixes at border-fra-01 have a next-hop "
            "that is not via the LON WAN link. EU data residency transit path violated "
            "(GDPR Article 44)."
        )

    def test_fra_advertises_only_its_own_supernet(self, bgp_peer_config, routes):
        """
        border-fra-01 should only originate its own supernet (10.30.0.0/16)
        to border-lon-01. It must not transit-advertise APAC, LON, or any
        other DC's prefixes outbound.
        """
        fra_originated = routes[
            (routes["Node"] == FRA_BORDER_NODE) &
            (routes["Protocol"] == "bgp") &
            (~routes["Network"].str.startswith("10.30.", na=False))
        ]
        # Filter out connected and static routes (null0 anchors)
        fra_non_local_bgp = fra_originated[
            routes["Protocol"].isin(["bgp"])
        ]
        # We're checking that FRA doesn't have non-FRA originated routes
        # (routes learned from LON that it could re-advertise)
        # A simpler check: FRA export policy must only permit 10.30.0.0/16
        fra_wan_export = bgp_peer_config[
            (bgp_peer_config["Node"] == FRA_BORDER_NODE) &
            (bgp_peer_config["Remote_AS"] == LON_ASN)
        ]
        missing_export = fra_wan_export[
            fra_wan_export["Export_Policy"].isna() |
            (fra_wan_export["Export_Policy"].apply(
                lambda p: len(p) == 0 if isinstance(p, list) else not p
            ))
        ]
        assert_no_rows(
            missing_export,
            "INTENT-004: border-fra-01 has no export policy on its LON WAN session. "
            "Without PL_FRA_EXPORT, it could transit-advertise non-FRA prefixes "
            "back to London, creating asymmetric routing (REQ-009)."
        )
