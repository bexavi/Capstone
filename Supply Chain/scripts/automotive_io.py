"""
Load Moetz et al. automotive multi-echelon dataset from .xlsb or exported CSVs.
Falls back to a deterministic toy network if no source files are present.

See: https://data.mendeley.com/datasets/pr3sdy5vp3/1
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _as_id(val: Any) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    s = str(val).strip()
    if len(s) > 2 and s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    return s


def _sheet_ci(dfs: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    for k in dfs:
        if k.lower() == name.lower():
            return dfs[k]
    raise KeyError(name)


def _is_mendeley_automotive_workbook(dfs: dict[str, pd.DataFrame]) -> bool:
    keys = {k.lower() for k in dfs}
    return {"products", "nodes", "arcs", "bom", "operations"}.issubset(keys)


def parse_mendeley_automotive_workbook(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Moetz et al. Mendeley workbook layout (sheet names are lowercase after norm).
    See DOI 10.17632/pr3sdy5vp3.1
    """
    products_raw = _sheet_ci(dfs, "products").copy()
    bom_raw = _sheet_ci(dfs, "bom").copy()
    arcs_raw = _sheet_ci(dfs, "arcs").copy()
    nodes_raw = _sheet_ci(dfs, "nodes").copy()
    ops = _sheet_ci(dfs, "operations").copy()
    cap = next((dfs[k] for k in dfs if k.lower() == "capacity_at_arc"), None)
    init_f = next((dfs[k] for k in dfs if k.lower() == "initial_flows"), None)
    inv = next((dfs[k] for k in dfs if k.lower() == "initial_inventories"), None)

    products_raw.columns = [_norm_col(c) for c in products_raw.columns]
    bom_raw.columns = [_norm_col(c) for c in bom_raw.columns]
    arcs_raw.columns = [_norm_col(c) for c in arcs_raw.columns]
    nodes_raw.columns = [_norm_col(c) for c in nodes_raw.columns]
    ops.columns = [_norm_col(c) for c in ops.columns]

    node_names = nodes_raw["node_n"].astype(str).tolist()
    def tier_for_node(name: str) -> int:
        if name.startswith("zp"):
            return 0
        if "gear-supplier" in name:
            return 2
        return 1

    geo = {
        "zp7": (48.78, 11.42),
        "zp8": (48.37, 10.88),
        "seat-supplier_inv": (50.11, 8.68),
        "seat-supplier_prod": (50.11, 8.68),
        "seat-supplier_trans": (49.45, 11.08),
        "battery-supplier_inv": (50.94, 6.96),
        "battery-supplier_prod": (50.94, 6.96),
        "battery-supplier_trans": (51.34, 12.37),
        "gear-supplier_inv": (49.20, 16.61),
        "gear-supplier_prod": (49.20, 16.61),
        "engine-supplier_inv": (48.78, 9.18),
        "engine-supplier_prod": (48.78, 9.18),
    }

    if inv is not None and not inv.empty:
        inv = inv.copy()
        inv.columns = [_norm_col(c) for c in inv.columns]
        g = inv.groupby("node_n").agg(
            initial_inventory=("initial_inventory_i_np0", "sum"),
            max_inventory=("max_inventory", "max"),
        ).reset_index()
    else:
        g = pd.DataFrame({"node_n": node_names, "initial_inventory": 0.0, "max_inventory": 0.0})

    rows_n = []
    for n in node_names:
        sub = g.loc[g["node_n"] == n]
        if sub.empty:
            ii, mx = 0.0, 0.0
        else:
            ii = float(sub["initial_inventory"].iloc[0])
            mx = float(sub["max_inventory"].iloc[0])
        lat, lon = geo.get(n, (51.16, 10.45))
        rows_n.append(
            {
                "node_id": n,
                "name": n,
                "tier": tier_for_node(n),
                "country": "Germany",
                "lat": lat,
                "lon": lon,
                "initial_inventory": ii,
                "max_inventory": mx,
            }
        )
    nodes = pd.DataFrame(rows_n)

    cap_mean = None
    if cap is not None and not cap.empty:
        cap = cap.copy()
        cap.columns = [_norm_col(c) for c in cap.columns]
        cap_mean = cap.groupby(["starting_node_i", "ending_node_j"], as_index=False)["capacity_c_ijt"].mean()

    flow_sum = None
    if init_f is not None and not init_f.empty:
        init_f = init_f.copy()
        init_f.columns = [_norm_col(c) for c in init_f.columns]
        flow_sum = init_f.groupby(["starting_node_i", "ending_node_j"], as_index=False)["initial_flow"].sum()

    arcs_m = arcs_raw.merge(cap_mean, on=["starting_node_i", "ending_node_j"], how="left") if cap_mean is not None else arcs_raw.copy()
    if flow_sum is not None:
        arcs_m = arcs_m.merge(flow_sum, on=["starting_node_i", "ending_node_j"], how="left")
    else:
        arcs_m["initial_flow"] = 0.0

    arcs_out = pd.DataFrame(
        {
            "from_node": arcs_m["starting_node_i"].astype(str),
            "to_node": arcs_m["ending_node_j"].astype(str),
            "lead_time_days": pd.to_numeric(arcs_m["process_lead_time_l_ij"], errors="coerce").fillna(0.0),
            "capacity_per_period": pd.to_numeric(arcs_m.get("capacity_c_ijt", 0), errors="coerce").fillna(0.0),
            "initial_flow": pd.to_numeric(arcs_m.get("initial_flow", 0), errors="coerce").fillna(0.0),
        }
    )

    pr = products_raw.copy()
    pr["product_id"] = pr["product_p"].astype(str).str.replace(r"\.0$", "", regex=True)
    pr["name"] = pr["product_id"]
    pr["product_type"] = pr["group_g"].astype(str)
    pr["transportation_size_s"] = pd.to_numeric(pr.get("transportation_size_s", 0), errors="coerce").fillna(0.0)

    bom = pd.DataFrame(
        {
            "parent_id": bom_raw["mother"].astype(str).str.replace(r"\.0$", "", regex=True),
            "child_id": bom_raw["child"].astype(str).str.replace(r"\.0$", "", regex=True),
            "quantity": pd.to_numeric(bom_raw["individual_input_quantity_q_mc"], errors="coerce").fillna(1.0),
        }
    )

    type_base_level = {
        "car": 0,
        "engine": 1,
        "gear": 1,
        "seat": 1,
        "battery": 1,
        "seat_componment": 2,
        "battery_componment": 2,
    }
    pr["level"] = pr["product_type"].str.lower().map(lambda t: type_base_level.get(t, 3))

    ops_e = ops.copy()
    ops_e["_g"] = ops_e["output_product_group_y"].astype(str)
    pr_e = pr[["product_id", "product_type"]].copy()
    pr_e["_g"] = pr_e["product_type"].astype(str)
    merged = ops_e.merge(pr_e, on="_g", how="inner")
    produces = pd.DataFrame(
        {"node_id": merged["node_n"].astype(str), "product_id": merged["product_id"].astype(str)}
    )

    products_out = pr[["product_id", "name", "product_type", "level", "transportation_size_s"]].copy()

    return nodes, arcs_out, products_out, bom, produces


def _norm_col(c: str) -> str:
    s = str(c).strip().lower().replace("\n", " ")
    s = re.sub(r"\s+", "_", s)
    return s


def read_xlsb_all_sheets(path: Path) -> dict[str, pd.DataFrame]:
    """Read all sheets; prefer pandas + pyxlsb (vectorized) for speed on large workbooks."""
    try:
        raw = pd.read_excel(path, sheet_name=None, engine="pyxlsb")
        return {str(k): df.rename(columns=_norm_col) for k, df in raw.items()}
    except Exception:
        pass

    from pyxlsb import open_workbook

    out: dict[str, pd.DataFrame] = {}
    with open_workbook(str(path)) as wb:
        for name in wb.sheets:
            rows: list[list[Any]] = []
            with wb.get_sheet(name) as sh:
                for row in sh.rows():
                    rows.append([c.v for c in row])
            if not rows:
                out[name] = pd.DataFrame()
                continue
            header = [_norm_col(x) if x is not None else f"col_{i}" for i, x in enumerate(rows[0])]
            body = rows[1:] if len(rows) > 1 else []
            out[name] = pd.DataFrame(body, columns=header)
    return out


def _rename_map(df: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    d = {_norm_col(c): c for c in df.columns}
    new_cols = {}
    for want, options in aliases.items():
        for opt in options:
            k = _norm_col(opt)
            if k in d:
                new_cols[d[k]] = want
                break
    return df.rename(columns=new_cols)


def detect_and_normalize(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Return (nodes, arcs, products, bom, produces_or_none)."""
    nodes = arcs = products = bom = None
    produces: pd.DataFrame | None = None

    scored: list[tuple[str, pd.DataFrame, int]] = []
    for name, df in dfs.items():
        if df is None or df.empty:
            continue
        scored.append((name, df, len(df)))

    scored.sort(key=lambda x: x[2])

    # Heuristic: smallest non-tiny sheet ~12 rows => nodes; ~11 rows => arcs
    for name, df, n in scored:
        cols = {_norm_col(c) for c in df.columns}
        if nodes is None and 8 <= n <= 20 and (
            {"tier", "node_id"} <= cols
            or {"tier", "id"} <= cols
            or "knoten" in name.lower()
            or ("inventory" in cols and "node" in "".join(cols))
        ):
            nodes = df.copy()
            nodes.columns = [_norm_col(c) for c in nodes.columns]
            continue
        if arcs is None and 8 <= n <= 30 and (
            {"from_node", "to_node"} <= cols
            or {"from", "to"} <= cols
            or {"source", "target"} <= cols
            or "arc" in name.lower()
            or "bogen" in name.lower()
        ):
            arcs = df.copy()
            arcs.columns = [_norm_col(c) for c in arcs.columns]
            continue

    for name, df, n in sorted(scored, key=lambda x: -x[2]):
        cols = {_norm_col(c) for c in df.columns}
        if products is None and n > 1000 and (
            "product_id" in cols
            or "product" in cols
            or "teil" in cols
            or "produkt" in name.lower()
        ):
            products = df.copy()
            products.columns = [_norm_col(c) for c in products.columns]
            continue
        if bom is None and n > 100 and (
            ({"parent", "child"} <= cols)
            or ({"parent_id", "child_id"} <= cols)
            or ({"parent_product_id", "component_product_id"} <= cols)
            or "bom" in name.lower()
            or "stückliste" in name.lower()
        ):
            bom = df.copy()
            bom.columns = [_norm_col(c) for c in df.columns]
            continue
        if produces is None and 50 <= n < 50000 and (
            ({"node_id", "product_id"} <= cols)
            or ({"node", "product"} <= cols)
            or "produces" in name.lower()
            or "zuordnung" in name.lower()
        ):
            produces = df.copy()
            produces.columns = [_norm_col(c) for c in produces.columns]

    if nodes is None or arcs is None or products is None or bom is None:
        raise ValueError(
            "Could not infer required sheets from workbook. "
            f"Sheets found: {list(dfs.keys())}. "
            "Export CSVs to data/csv/ or use synthetic_fallback()."
        )

    # Standard column names
    def coalesce(df: pd.DataFrame, mapping: list[tuple[str, list[str]]]) -> pd.DataFrame:
        for target, candidates in mapping:
            for c in candidates:
                if c in df.columns:
                    if target not in df.columns:
                        df[target] = df[c]
                    break
        return df

    nodes = coalesce(
        nodes,
        [
            ("node_id", ["node_id", "id", "knoten", "node"]),
            ("name", ["name", "node_name", "bezeichnung"]),
            ("tier", ["tier", "stufe", "echelon"]),
            ("location", ["location", "standort", "country", "land"]),
            ("initial_inventory", ["initial_inventory", "inventory", "startbestand"]),
            ("max_inventory", ["max_inventory", "max_inv", "maximalbestand"]),
        ],
    )
    arcs = coalesce(
        arcs,
        [
            ("from_node", ["from_node", "from", "source", "von", "origin"]),
            ("to_node", ["to_node", "to", "target", "nach", "dest"]),
            ("lead_time", ["lead_time", "lead_time_days", "liefertzeit", "lt"]),
            ("capacity", ["capacity", "capacity_per_period", "kapazität", "transportkapazität"]),
            ("initial_flow", ["initial_flow", "flow", "anfangsdurchsatz"]),
        ],
    )
    products = coalesce(
        products,
        [
            ("product_id", ["product_id", "id", "product"]),
            ("name", ["name", "product_name", "bezeichnung"]),
            ("product_type", ["product_type", "type", "typ", "category"]),
            ("level", ["level", "stufe", "hierarchy_level", "bom_level"]),
        ],
    )
    bom = coalesce(
        bom,
        [
            ("parent_id", ["parent_product_id", "parent_id", "parent", "vater"]),
            ("child_id", ["component_product_id", "child_id", "child", "kind"]),
            ("quantity", ["quantity", "qty", "menge", "quantity_required"]),
        ],
    )
    if produces is not None:
        produces = coalesce(
            produces,
            [
                ("node_id", ["node_id", "node", "knoten"]),
                ("product_id", ["product_id", "product", "teil"]),
            ],
        )

    return nodes, arcs, products, bom, produces


def synthetic_fallback(random_seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Deterministic toy network: 12 facilities, 11 supply arcs, many products + BOM + PRODUCES.
    Risk proxies are derived from lead time and capacity for analysis aligned with the course proposal.
    """
    rng = np.random.default_rng(random_seed)
    countries = [
        ("Germany", 51.1657, 10.4515),
        ("Germany", 48.7758, 9.1829),
        ("Czech Republic", 49.8175, 15.4730),
        ("Hungary", 47.1625, 19.5033),
        ("Poland", 51.9194, 19.1451),
        ("Romania", 45.9432, 24.9668),
        ("Slovakia", 48.6690, 19.6990),
        ("Italy", 41.8719, 12.5674),
        ("Spain", 40.4637, -3.7492),
        ("France", 46.2276, 2.2137),
        ("Austria", 47.5162, 14.5501),
        ("Netherlands", 52.1326, 5.2913),
    ]
    tiers = [0] + [1] * 4 + [2] * 2 + [1] * 5
    names = [
        "OEM_Assembly",
        "Tier1_Powertrain",
        "Tier1_Electronics",
        "Tier1_Chassis",
        "Tier1_Interiors",
        "Tier2_Metals",
        "Tier2_Polymers",
        "Tier1_Logistics_Hub_A",
        "Tier1_Logistics_Hub_B",
        "Tier1_Seating",
        "Tier1_Body",
        "Tier1_Thermal",
    ]
    nodes = pd.DataFrame(
        {
            "node_id": range(1, 13),
            "name": names,
            "tier": tiers,
            "country": [c[0] for c in countries],
            "lat": [c[1] for c in countries],
            "lon": [c[2] for c in countries],
            "initial_inventory": rng.integers(50, 200, size=12),
            "max_inventory": rng.integers(250, 400, size=12),
        }
    )

    edges = [
        (6, 2),
        (6, 4),
        (7, 3),
        (7, 5),
        (6, 8),
        (7, 9),
        (2, 1),
        (3, 1),
        (4, 1),
        (5, 1),
        (8, 1),
    ]
    lt = rng.uniform(0.5, 4.0, size=len(edges))
    cap = rng.uniform(80.0, 220.0, size=len(edges))
    arcs = pd.DataFrame(
        {
            "from_node": [a for a, _ in edges],
            "to_node": [b for _, b in edges],
            "lead_time_days": lt,
            "capacity_per_period": cap,
            "initial_flow": rng.uniform(10.0, 60.0, size=len(edges)),
        }
    )

    n_products = 3500
    levels = rng.integers(0, 8, size=n_products)
    types = np.where(levels == 0, "car", np.where(levels < 3, "system", np.where(levels < 6, "component", "part")))
    products = pd.DataFrame(
        {
            "product_id": range(1, n_products + 1),
            "name": [f"SKU_{i:05d}" for i in range(1, n_products + 1)],
            "level": levels,
            "product_type": types,
        }
    )

    bom_rows: list[dict[str, Any]] = []
    order = np.argsort(levels)
    seen: set[int] = {int(order[0]) + 1}
    for idx in order[1:]:
        pid = int(idx) + 1
        candidates = [s for s in seen if levels[s - 1] < levels[pid - 1]]
        if not candidates:
            parent = 1
        else:
            parent = int(rng.choice(candidates))
        qty = float(rng.uniform(0.5, 4.0))
        bom_rows.append({"parent_id": parent, "child_id": pid, "quantity": qty})
        seen.add(pid)
    bom = pd.DataFrame(bom_rows)

    produces_rows: list[dict[str, Any]] = []
    for pid in range(1, n_products + 1):
        tier_p = levels[pid - 1]
        if tier_p == 0:
            nid = 1
        elif tier_p <= 2:
            nid = int(rng.choice([2, 3, 4, 5, 8, 9, 10, 11, 12]))
        elif tier_p <= 4:
            nid = int(rng.choice([2, 3, 4, 5, 6, 7]))
        else:
            nid = int(rng.choice([6, 7]))
        produces_rows.append({"node_id": nid, "product_id": pid})
    produces = pd.DataFrame(produces_rows)

    return nodes, arcs, products, bom, produces


def load_dataset(
    xlsb_path: Path | None = None,
    csv_dir: Path | None = None,
    use_synthetic: bool = False,
) -> dict[str, Any]:
    """
    Returns dict with keys: nodes, arcs, products, bom, produces, source (str), sheets (optional).
    """
    if use_synthetic:
        n, a, p, b, pr = synthetic_fallback()
        return {
            "nodes": n,
            "arcs": a,
            "products": p,
            "bom": b,
            "produces": pr,
            "source": "synthetic_fallback",
        }

    if xlsb_path and Path(xlsb_path).is_file():
        dfs = read_xlsb_all_sheets(Path(xlsb_path))
        meta = {"sheets": {k: v.shape for k, v in dfs.items()}}
        if _is_mendeley_automotive_workbook(dfs):
            n, a, p, b, pr = parse_mendeley_automotive_workbook(dfs)
            return {
                "nodes": n,
                "arcs": a,
                "products": p,
                "bom": b,
                "produces": pr,
                "source": f"xlsb_mendeley:{xlsb_path}",
                **meta,
            }
        try:
            n, a, p, b, pr = detect_and_normalize(dfs)
            return {
                "nodes": n,
                "arcs": a,
                "products": p,
                "bom": b,
                "produces": pr,
                "source": f"xlsb:{xlsb_path}",
                **meta,
            }
        except ValueError:
            n, a, p, b, pr = synthetic_fallback()
            return {
                "nodes": n,
                "arcs": a,
                "products": p,
                "bom": b,
                "produces": pr,
                "source": f"synthetic_fallback_unparsed_xlsb:{xlsb_path}",
                **meta,
            }

    cdir = Path(csv_dir) if csv_dir else ROOT / "data" / "csv"
    if cdir.is_dir():
        files = {p.stem.lower(): p for p in cdir.glob("*.csv")}
        def read_csv_key(key: str) -> pd.DataFrame:
            for k, path in files.items():
                if key in k:
                    return pd.read_csv(path)
            raise FileNotFoundError(f"Missing {key} in {cdir}")

        try:
            nodes = read_csv_key("node")
            arcs = read_csv_key("arc")
            products = read_csv_key("product")
            bom = read_csv_key("bom")
            produces = read_csv_key("produce")
        except FileNotFoundError:
            n, a, p, b, pr = synthetic_fallback()
            return {"nodes": n, "arcs": a, "products": p, "bom": b, "produces": pr, "source": "synthetic_fallback_no_csv"}

        nodes.columns = [_norm_col(c) for c in nodes.columns]
        arcs.columns = [_norm_col(c) for c in arcs.columns]
        products.columns = [_norm_col(c) for c in products.columns]
        bom.columns = [_norm_col(c) for c in bom.columns]
        produces.columns = [_norm_col(c) for c in produces.columns]
        return {
            "nodes": nodes,
            "arcs": arcs,
            "products": products,
            "bom": bom,
            "produces": produces,
            "source": f"csv_dir:{cdir}",
        }

    n, a, p, b, pr = synthetic_fallback()
    return {"nodes": n, "arcs": a, "products": p, "bom": b, "produces": pr, "source": "synthetic_fallback_default"}


def facility_label(tier: Any) -> str:
    try:
        t = int(float(tier))
    except (TypeError, ValueError):
        t = -1
    if t == 0:
        return "OEM"
    if t == 1:
        return "Tier1Supplier"
    if t == 2:
        return "Tier2Supplier"
    return "Facility"


def add_risk_edges(arcs: pd.DataFrame) -> pd.DataFrame:
    a = arcs.copy()
    lt = pd.to_numeric(a["lead_time_days"] if "lead_time_days" in a.columns else a.get("lead_time", 1), errors="coerce").fillna(1.0)
    cap = pd.to_numeric(a["capacity_per_period"] if "capacity_per_period" in a.columns else a.get("capacity", 1), errors="coerce").fillna(1.0)
    lt_max = float(lt.max()) if len(lt) else 1.0
    if lt_max <= 0:
        lt_max = 1.0
    a["delay_probability_proxy"] = (lt / lt_max) * 0.85 + 0.05
    a["disruption_likelihood_proxy"] = (1.0 / cap.replace(0, np.nan)).fillna(1.0)
    a["disruption_likelihood_proxy"] /= a["disruption_likelihood_proxy"].max()
    a["disruption_likelihood_proxy"] = a["disruption_likelihood_proxy"].clip(0.05, 0.95)
    return a


def export_csv_for_neo4j(d: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = d["nodes"].copy()
    if "country" not in n.columns:
        n["country"] = n["location"] if "location" in n.columns else ""
    if "lat" not in n.columns:
        n["lat"] = ""
    if "lon" not in n.columns:
        n["lon"] = ""
    n.to_csv(out_dir / "nodes.csv", index=False)
    add_risk_edges(d["arcs"]).to_csv(out_dir / "arcs.csv", index=False)
    d["products"].to_csv(out_dir / "products.csv", index=False)
    d["bom"].to_csv(out_dir / "bom.csv", index=False)
    d["produces"].to_csv(out_dir / "node_products.csv", index=False)
    meta = {"source": d.get("source"), "sheets": d.get("sheets")}
    (out_dir / "load_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def build_networkx_graph(d: dict[str, Any]):
    import networkx as nx

    G = nx.MultiDiGraph()
    nodes = d["nodes"]
    arcs = add_risk_edges(d["arcs"])
    products = d["products"]
    bom = d["bom"]
    produces = d["produces"]

    fac_nodes: list[tuple[str, dict[str, Any]]] = []
    for row in nodes.to_dict(orient="records"):
        nid = _as_id(row.get("node_id"))
        tr = row.get("tier")
        tier_val = int(float(tr)) if tr is not None and str(tr).strip() != "" and pd.notna(tr) else -1
        lat_v = row.get("lat")
        lon_v = row.get("lon")
        fac_nodes.append(
            (
                f"F:{nid}",
                {
                    "name": str(row.get("name", nid)),
                    "tier": tier_val,
                    "label": facility_label(tr),
                    "country": str(row.get("country", row.get("location", ""))),
                    "lat": float(lat_v) if lat_v is not None and str(lat_v) != "" and pd.notna(lat_v) else None,
                    "lon": float(lon_v) if lon_v is not None and str(lon_v) != "" and pd.notna(lon_v) else None,
                },
            )
        )
    G.add_nodes_from(fac_nodes)

    prod_nodes: list[tuple[str, dict[str, Any]]] = []
    for row in products.to_dict(orient="records"):
        pid = _as_id(row.get("product_id"))
        lv = row.get("level")
        lvl = int(float(lv)) if lv is not None and str(lv).strip() != "" and pd.notna(lv) else -1
        prod_nodes.append(
            (
                f"P:{pid}",
                {
                    "name": str(row.get("name", pid)),
                    "product_type": str(row.get("product_type", "")),
                    "level": lvl,
                    "label": "Product",
                },
            )
        )
    G.add_nodes_from(prod_nodes)

    sup_e: list[tuple[str, str, str, dict[str, Any]]] = []
    for row in arcs.to_dict(orient="records"):
        fn, tn = _as_id(row.get("from_node")), _as_id(row.get("to_node"))
        sup_e.append(
            (
                f"F:{fn}",
                f"F:{tn}",
                "SUPPLIES",
                {
                    "type": "SUPPLIES",
                    "lead_time_days": float(row.get("lead_time_days", row.get("lead_time", 0)) or 0),
                    "capacity_per_period": float(row.get("capacity_per_period", row.get("capacity", 0)) or 0),
                    "delay_probability_proxy": float(row.get("delay_probability_proxy", 0.5)),
                    "disruption_likelihood_proxy": float(row.get("disruption_likelihood_proxy", 0.5)),
                },
            )
        )
    G.add_edges_from(sup_e)

    bom_e: list[tuple[str, str, str, dict[str, Any]]] = []
    for row in bom.to_dict(orient="records"):
        pa, ch = _as_id(row.get("parent_id")), _as_id(row.get("child_id"))
        bom_e.append(
            (
                f"P:{pa}",
                f"P:{ch}",
                "CONTAINS",
                {"type": "CONTAINS", "quantity_required": float(row.get("quantity", 1) or 1)},
            )
        )
    G.add_edges_from(bom_e)

    pr_e: list[tuple[str, str, str, dict[str, Any]]] = []
    for row in produces.to_dict(orient="records"):
        nid, pid = _as_id(row.get("node_id")), _as_id(row.get("product_id"))
        pr_e.append((f"F:{nid}", f"P:{pid}", "PRODUCES", {"type": "PRODUCES"}))
    G.add_edges_from(pr_e)

    return G


def supplier_product_collapsed_graph(G):
    """Undirected bipartite-style graph: Supplier (facility) — Product for centrality."""
    import networkx as nx

    H = nx.Graph()
    for u, v, k, data in G.edges(keys=True, data=True):
        if data.get("type") != "PRODUCES":
            continue
        fu, pv = u, v
        if not fu.startswith("F:") or not pv.startswith("P:"):
            continue
        H.add_node(fu, **G.nodes[fu])
        H.add_node(pv, **G.nodes[pv])
        H.add_edge(fu, pv, weight=1.0)
    return H
