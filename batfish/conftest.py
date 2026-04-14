"""
ACME Investments — Batfish pytest fixtures and helpers
conftest.py — loaded automatically by pytest for all tests in batfish/tests/

Fixtures:
    bf          Initialised pybatfish Session with snapshot loaded (session-scoped)
    snapshot    Path to the snapshot directory

Helpers:
    assert_no_rows(df, message)  — fail the test if a DataFrame is non-empty
    ebgp_sessions(df)            — filter a bgpSessionStatus frame to eBGP only
    ibgp_sessions(df)            — filter to iBGP only

Environment variables:
    BATFISH_HOST   Batfish server hostname/IP (default: localhost)
    SNAPSHOT_NAME  Batfish snapshot name    (default: acme_lab)
"""

import os
import pathlib
import pytest
import pandas as pd

from pybatfish.client.session import Session
from pybatfish.datamodel import HeaderConstraints, PathConstraints

# ── Constants derived from the SoT ───────────────────────────────────────────
# Kept here so every test file can import from conftest rather than hard-coding.

# London DC1 zone subnets
TRADING_PREFIX   = "10.1.1.0/24"
CORPORATE_PREFIX = "10.1.2.0/23"
DMZ_PREFIX       = "10.1.6.0/24"
MGMT_PREFIX      = "10.1.0.0/25"

# Loopback range for LON DC1 fabric
LON_LOOPBACK_RANGE = "10.1.255.0/24"

# WAN transit subnets (point-to-point /31s)
WAN_LON_NYC = "10.0.1.0/31"
WAN_LON_SIN = "10.0.2.0/31"
WAN_LON_FRA = "10.0.3.0/31"

# DC aggregate supernets
LON_SUPERNET = "10.1.0.0/16"
NYC_SUPERNET = "10.10.0.0/16"
SIN_SUPERNET = "10.20.0.0/16"
FRA_SUPERNET = "10.30.0.0/16"

# Branch aggregates
UK_BRANCH_SUPERNET  = "10.100.0.0/16"
US_BRANCH_SUPERNET  = "10.101.0.0/16"

# Individual branch /29s
BRANCH_LON_01_PREFIX = "10.100.0.0/29"
BRANCH_NYC_01_PREFIX = "10.101.0.0/29"

# ASNs
LON_ASN = 65001
NYC_ASN = 65010
SIN_ASN = 65020
FRA_ASN = 65030

# Active nodes by role (must match inventory lab_active group)
SPINE_NODES  = ["spine-lon-01", "spine-lon-02"]
LEAF_NODES   = ["leaf-lon-01", "leaf-lon-02", "leaf-lon-03", "leaf-lon-04"]
BORDER_NODES = ["border-lon-01", "border-nyc-01", "border-sin-01", "border-fra-01"]
FW_NODES     = ["fw-lon-01"]
BRANCH_NODES = ["branch-lon-01", "branch-nyc-01"]
FRA_NODES    = ["border-fra-01"]
LON_DC1_NODES = SPINE_NODES + LEAF_NODES + ["border-lon-01", "fw-lon-01"]


# ── Session fixture ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def bf():
    """
    Initialised pybatfish Session with the acme_lab snapshot loaded.
    Session-scoped: Batfish snapshot is initialised once per pytest run,
    not once per test. This is important — snapshot init is expensive (~10-30s).
    """
    batfish_host  = os.environ.get("BATFISH_HOST", "localhost")
    snapshot_name = os.environ.get("SNAPSHOT_NAME", "acme_lab")
    snapshot_path = (
        pathlib.Path(__file__).parent / "snapshots" / "acme_lab"
    )

    if not snapshot_path.exists():
        pytest.fail(
            f"Snapshot directory not found: {snapshot_path}\n"
            "Run batfish/run_checks.sh to build it from rendered configs."
        )

    session = Session(host=batfish_host)
    session.set_network("acme_investments")
    session.init_snapshot(str(snapshot_path), name=snapshot_name, overwrite=True)

    return session


@pytest.fixture(scope="session")
def bgp_sessions(bf):
    """DataFrame of all BGP session statuses in the snapshot."""
    return bf.q.bgpSessionStatus().answer().frame()


@pytest.fixture(scope="session")
def bgp_peer_config(bf):
    """DataFrame of all BGP peer configurations (includes auth, policies)."""
    return bf.q.bgpPeerConfiguration().answer().frame()


@pytest.fixture(scope="session")
def bgp_edges(bf):
    """DataFrame of all established BGP edges."""
    return bf.q.bgpEdges().answer().frame()


@pytest.fixture(scope="session")
def bgp_peer_config_enriched(bgp_peer_config, bgp_sessions):
    """bgpPeerConfiguration enriched with Remote_Node from bgpSessionStatus.

    bgpPeerConfiguration does not include Remote_Node in all pybatfish versions.
    bgpSessionStatus does — so we left-join on (Node, VRF, Local_IP, Remote_IP).
    """
    if "Remote_Node" in bgp_peer_config.columns:
        return bgp_peer_config
    remote_node_map = bgp_sessions[
        ["Node", "VRF", "Local_IP", "Remote_IP", "Remote_Node"]
    ].drop_duplicates()
    return bgp_peer_config.merge(
        remote_node_map,
        on=["Node", "VRF", "Local_IP", "Remote_IP"],
        how="left",
    )


@pytest.fixture(scope="session")
def routes(bf):
    """DataFrame of the full routing table across all nodes and VRFs."""
    return bf.q.routes().answer().frame()


@pytest.fixture(scope="session")
def interface_props(bf):
    """DataFrame of interface properties across all nodes."""
    return bf.q.interfaceProperties().answer().frame()


@pytest.fixture(scope="session")
def node_props(bf):
    """DataFrame of node properties."""
    return bf.q.nodeProperties().answer().frame()


# ── Assertion helpers ─────────────────────────────────────────────────────────

def assert_no_rows(df: pd.DataFrame, message: str) -> None:
    """Fail the test if df has any rows, printing them for diagnosis."""
    if not df.empty:
        pytest.fail(f"{message}\n\nOffending rows:\n{df.to_string()}")


def ebgp_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Filter a bgpSessionStatus or bgpPeerConfiguration frame to eBGP peers."""
    if "Session_Type" in df.columns:
        return df[df["Session_Type"].str.startswith("EBGP", na=False)]
    # bgpPeerConfiguration: Remote_AS may be str while Local_AS is int (pybatfish type variance)
    return df[df["Remote_AS"].astype(str) != df["Local_AS"].astype(str)]


def ibgp_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Filter a bgpSessionStatus or bgpPeerConfiguration frame to iBGP peers."""
    if "Session_Type" in df.columns:
        return df[df["Session_Type"].str.startswith("IBGP", na=False)]
    return df[df["Remote_AS"].astype(str) == df["Local_AS"].astype(str)]
