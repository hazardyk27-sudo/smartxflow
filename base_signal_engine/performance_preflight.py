"""Read-only SQL-plan interpretation; never assumes production index availability.

Accept PostgreSQL EXPLAIN (FORMAT JSON) output collected by an authorized DBA
after SELECT-only preflight. No production queries are performed by this module.
"""
from __future__ import annotations

_EXPECTED = "idx_sxf_base_mw_snapshot_uid_time"
_INDEX_NODES = {"Index Scan", "Index Only Scan", "Bitmap Index Scan"}


def snapshot_index_evidence(explain_json: object) -> dict:
    if not isinstance(explain_json, list) or len(explain_json) != 1:
        raise ValueError("expected single PostgreSQL EXPLAIN JSON result")
    payload = explain_json[0]
    if not isinstance(payload, dict) or not isinstance(payload.get("Plan"), dict):
        raise ValueError("missing PostgreSQL plan tree")
    visited = []
    def visit(node):
        if not isinstance(node, dict):
            raise ValueError("malformed plan node")
        node_type = node.get("Node Type")
        if not isinstance(node_type, str):
            raise ValueError("missing plan node type")
        visited.append({"node_type": node_type,
                        "index": node.get("Index Name")})
        for child in node.get("Plans", []):
            visit(child)
    visit(payload["Plan"])
    matching = any(v["node_type"] in _INDEX_NODES and v["index"] == _EXPECTED
                   for v in visited)
    other_index = any(v["node_type"] in _INDEX_NODES for v in visited)
    return {
        "expected_index_used": matching,
        "other_index_used": other_index and not matching,
        "seq_scan_present": any(v["node_type"] == "Seq Scan" for v in visited),
        "observed_nodes": visited,
        "production_plan_verified": False,  # only an operator can certify origin
        "result": "PROPOSED_INDEX_USED" if matching else "INDEX_USAGE_NOT_CONFIRMED",
    }
