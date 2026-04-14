"""
ACME Investments — BGP Standards Intent Checks
test_bgp_standards.py

Implements: INTENT-005
Requirement refs: REQ-012 (BGP MD5 on all sessions), REQ-013 (eBGP route-maps)

INTENT-005: All BGP sessions must use MD5 authentication.
            All eBGP sessions must have explicit import AND export route-maps.
            No branch may advertise a prefix outside its assigned /29.

This implements the BGP hygiene baseline that prevents:
  - BGP session hijacking (MD5 enforcement)
  - Route leaks via open eBGP policies (route-map enforcement)
  - Branch prefix sprawl (branch /29 advertisement check)

Lab guide exercises enabled: 4.3, 7.1, 7.2, 3.6
"""

import ipaddress
import pytest
import pandas as pd

from conftest import (
    SPINE_NODES,
    LEAF_NODES,
    BORDER_NODES,
    FW_NODES,
    BRANCH_NODES,
    BRANCH_LON_01_PREFIX,
    BRANCH_NYC_01_PREFIX,
    assert_no_rows,
    ebgp_sessions,
    ibgp_sessions,
)

# Branch prefixes by hostname — used for prefix-advertisement check
BRANCH_ASSIGNED_PREFIXES = {
    "branch-lon-01": ipaddress.ip_network(BRANCH_LON_01_PREFIX),
    "branch-nyc-01": ipaddress.ip_network(BRANCH_NYC_01_PREFIX),
}


class TestBgpMd5Authentication:
    """
    INTENT-005 / REQ-012: Every BGP session must have MD5 authentication.
    This applies to iBGP (fabric) and eBGP (WAN, branch) equally.
    Authentication protects against BGP hijacking and route injection.
    """

    def test_all_bgp_sessions_have_authentication(self, bgp_peer_config):
        """
        No BGP peer configuration should have a null or empty authentication field.
        Every session — iBGP or eBGP — must have md5_password_ref set in the SoT
        and rendered as a password in the device config.
        """
        # Batfish exposes authentication via 'MD5' or boolean in 'Authentication' column
        if "Authentication" not in bgp_peer_config.columns:
            pytest.skip(
                "bgpPeerConfiguration does not expose 'Authentication' column in this "
                "Batfish version — check with bf.q.bgpPeerConfiguration().answer().frame().columns"
            )

        no_auth = bgp_peer_config[
            bgp_peer_config["Authentication"].isna() |
            (bgp_peer_config["Authentication"] == "") |
            (bgp_peer_config["Authentication"] == False)  # noqa: E712
        ]
        assert_no_rows(
            no_auth[["Node", "VRF", "Local_IP", "Remote_IP", "Remote_AS"]],
            "INTENT-005 VIOLATED: BGP sessions without MD5 authentication (REQ-012). "
            "Each session must have md5_password_ref set in the SoT device file."
        )

    def test_no_bgp_password_in_plaintext(self, bgp_peer_config):
        """
        Regression guard: BGP passwords must never appear as plaintext in the
        network model. Batfish shouldn't be loading cleartext secrets, but
        this check guards against accidental vault.yml exposure.
        """
        if "Authentication" not in bgp_peer_config.columns:
            pytest.skip("Authentication column not available")

        # If authentication is a string that looks like a real password
        # (not a hash indicator), flag it
        def looks_like_plaintext(auth) -> bool:
            if not isinstance(auth, str):
                return False
            return auth.lower() not in ("true", "false", "md5", "none", "") \
                   and not auth.startswith("7 ")   # EOS type-7 hash prefix

        plaintext_auth = bgp_peer_config[
            bgp_peer_config["Authentication"].apply(looks_like_plaintext)
        ]
        assert_no_rows(
            plaintext_auth[["Node", "VRF", "Remote_IP"]],
            "SECURITY: BGP peer config appears to contain a plaintext password. "
            "Passwords must be rendered as EOS type-7 hashes or FRR encrypted strings "
            "(INTENT-005, SC-103 — no inline plaintext BGP passwords)."
        )


class TestEbgpRouteMaps:
    """
    INTENT-005 / REQ-013: All eBGP sessions must have explicit route-maps
    applied inbound AND outbound. An open eBGP session (no route-map) is
    a route-leak vector.
    """

    def test_all_ebgp_sessions_have_import_policy(self, bgp_peer_config):
        """
        Every eBGP peer (Remote_AS != Local_AS) must have at least one
        import route-map configured. This ensures no route is accepted
        without explicit policy review.
        """
        ebgp = ebgp_sessions(bgp_peer_config)

        missing_import = ebgp[
            ebgp["Import_Policy"].isna() |
            (ebgp["Import_Policy"].apply(
                lambda p: (len(p) == 0) if isinstance(p, list) else (not p)
            ))
        ]
        assert_no_rows(
            missing_import[["Node", "VRF", "Local_IP", "Remote_IP", "Remote_AS"]],
            "INTENT-005 VIOLATED: eBGP sessions without an import route-map (REQ-013). "
            "An open inbound policy accepts all routes from the peer without filtering."
        )

    def test_all_ebgp_sessions_have_export_policy(self, bgp_peer_config):
        """
        Every eBGP peer must have at least one export route-map configured.
        Without an export policy, all locally-known prefixes (including transit
        routes) could be advertised to the peer.
        """
        ebgp = ebgp_sessions(bgp_peer_config)

        missing_export = ebgp[
            ebgp["Export_Policy"].isna() |
            (ebgp["Export_Policy"].apply(
                lambda p: (len(p) == 0) if isinstance(p, list) else (not p)
            ))
        ]
        assert_no_rows(
            missing_export[["Node", "VRF", "Local_IP", "Remote_IP", "Remote_AS"]],
            "INTENT-005 VIOLATED: eBGP sessions without an export route-map (REQ-013). "
            "An open outbound policy leaks all known prefixes to the eBGP peer."
        )

    def test_ibgp_spine_sessions_have_route_reflector_config(self, bgp_peer_config_enriched):
        """
        Spine nodes must have route-reflector-client configured on all leaf/border
        iBGP sessions. This is not a security check but a correctness check —
        missing RR client config would cause iBGP black-holing (INTENT-008 dependency).
        """
        spine_sessions = bgp_peer_config_enriched[
            bgp_peer_config_enriched["Node"].isin(SPINE_NODES)
        ]
        ibgp = ibgp_sessions(spine_sessions)

        if "Route_Reflector_Client" not in ibgp.columns:
            pytest.skip("Route_Reflector_Client column not available in this Batfish version")

        # Spine-to-spine sessions are not RR clients (they're peer RRs)
        # All other iBGP sessions from a spine should be RR clients
        spine_to_non_spine = ibgp[~ibgp["Remote_Node"].isin(SPINE_NODES)]
        not_rr_client = spine_to_non_spine[
            ~spine_to_non_spine["Route_Reflector_Client"].fillna(False)
        ]
        assert_no_rows(
            not_rr_client[["Node", "Remote_Node", "Remote_IP"]],
            "INTENT-008 dependency: Spine iBGP sessions to non-spine peers should have "
            "route-reflector-client configured. Missing RR client causes split-horizon "
            "blocking and iBGP black-holes across the fabric."
        )


class TestBranchPrefixAdvertisements:
    """
    INTENT-005 / INTENT-007 / REQ-013:
    Branch routers must only advertise their assigned /29 prefix.
    No branch should inject a default route, a supernet, or any prefix
    from outside its assigned allocation.
    """

    @pytest.mark.parametrize("branch_node,assigned_prefix", [
        ("branch-lon-01", BRANCH_LON_01_PREFIX),
        ("branch-nyc-01", BRANCH_NYC_01_PREFIX),
    ])
    def test_branch_advertises_only_assigned_prefix(
        self, routes, branch_node, assigned_prefix
    ):
        """
        The BGP RIB at the branch's upstream border should contain only the
        branch's assigned /29, not any more-specifics, supernets, or foreign prefixes.
        """
        assigned_net = ipaddress.ip_network(assigned_prefix)

        # Find all prefixes originated by this branch (protocol=bgp, learned at border)
        border_node = "border-lon-01" if "lon" in branch_node else "border-nyc-01"
        branch_routes = routes[
            (routes["Node"] == border_node) &
            (routes["Protocol"] == "bgp")
        ]

        # Identify prefixes that could have come from this branch
        # (next-hop in the branch /29 subnet)
        branch_next_hops = branch_routes[
            branch_routes["Next_Hop_IP"].apply(
                lambda nh: _ip_in_network(str(nh), assigned_net) if pd.notna(nh) else False
            )
        ]

        # All prefixes from this branch must be the assigned /29 exactly
        non_assigned = branch_next_hops[
            branch_next_hops["Network"].apply(
                lambda net: not _prefix_is_exactly(net, assigned_net)
            )
        ]
        assert_no_rows(
            non_assigned[["Node", "Network", "Next_Hop_IP", "Protocol"]],
            f"INTENT-007 VIOLATED: {branch_node} is advertising prefixes beyond its "
            f"assigned /29 ({assigned_prefix}). Branches must only advertise their "
            f"allocation (REQ-013 — branch prefix containment)."
        )

    def test_no_branch_advertises_default_route(self, routes):
        """
        No branch router should originate a default route (0.0.0.0/0).
        A default route from a branch would attract all traffic in the DC fabric.
        """
        branch_defaults = routes[
            routes["Node"].isin(BRANCH_NODES) &
            (routes["Network"] == "0.0.0.0/0") &
            (routes["Protocol"] == "bgp")
        ]
        assert_no_rows(
            branch_defaults[["Node", "Network", "Protocol"]],
            "INTENT-007 VIOLATED: A branch node is originating a default route (0.0.0.0/0). "
            "This would attract all fabric traffic toward the branch uplink (REQ-013)."
        )


def _ip_in_network(ip_str: str, network: ipaddress.IPv4Network) -> bool:
    """Return True if ip_str (no prefix len) falls within network."""
    try:
        return ipaddress.ip_address(ip_str.split("/")[0]) in network
    except ValueError:
        return False


def _prefix_is_exactly(prefix_str: str, expected: ipaddress.IPv4Network) -> bool:
    """Return True if prefix_str is exactly the expected network."""
    try:
        return ipaddress.ip_network(prefix_str, strict=False) == expected
    except ValueError:
        return False
