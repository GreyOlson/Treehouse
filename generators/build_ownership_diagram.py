#!/usr/bin/env python3
"""
build_ownership_diagram.py
==========================
Per-service node-link diagram of every uploaded asset in the place and WHO created
it -- the Ownership twin of build_network_diagram.py, using the exact same engine.

An instance is drawn if it references an uploaded asset (MeshPart.MeshId/TextureID,
SpecialMesh.MeshId/TextureId, Sound.SoundId, Animation.AnimationId, Decal/Texture
.Texture, ...). The OwnershipDump (Dumpers.luau) resolves each asset's Creator via
MarketplaceService:GetProductInfo and emits one row per asset:

    - <Property> = <CreatorName> (User|Group)

so the shared parser reads it and each asset becomes an item row beneath its host
instance -- just like attributes / collision flags. The engine sorts by instance
type (legend) AND by creator (a second filter row), across services + Global.

INPUT  : working/OwnershipTree.luau
OUTPUT : working/OwnershipNetworkDiagram.html
RE-RUN : python3 generators/build_ownership_diagram.py
"""

import os
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bat = _load("build_attribute_tree", "build_attribute_tree.py")
bnd = _load("build_network_diagram", "build_network_diagram.py")

DUMP_PATH = os.path.join(bat.PROJECT_ROOT, "working", "OwnershipTree.luau")
OUT_PATH = os.path.join(bat.PROJECT_ROOT, "working", "OwnershipNetworkDiagram.html")


def node_to_uniform(node, creators):
    """Parsed Node -> uniform {n,c,items,ch}. Each asset row becomes an item whose
    value is the creator's name and whose type is User / Group. `cr` is the creator
    key the engine's creator filter buckets by; `ct` colours it."""
    items = []
    for a in node.attrs:
        cname, ctype = a["value"], a["type"]
        cr = ctype + ":" + cname
        creators.add(cr)
        items.append({"n": a["name"], "v": cname, "t": ctype, "m": "",
                      "cr": cr, "ct": ctype})
    return {"n": node.name, "c": node.cls, "items": items,
            "ch": [node_to_uniform(c, creators) for c in node.children]}


def main():
    roots, _total = bat.parse_dump(DUMP_PATH)

    creators = set()
    services, tot_inst, tot_items = [], 0, 0
    for r in roots:
        disp = bnd.compress(node_to_uniform(r, creators))
        ic, it = bnd.count_display(disp)
        services.append(disp)
        tot_inst += ic
        tot_items += it

    summary = {
        "project": bat.PROJECT_NAME, "item_kind": "ownership",
        "item_label": "assets",
        "creators": True,            # engine: build the "sort by creator" filter row
        "creator_count": len(creators),
        "services": [{"name": s["n"], "instances": bnd.count_display(s)[0],
                      "items": bnd.count_display(s)[1]} for s in services],
        "total_instances": tot_inst, "total_items": tot_items,
    }

    html_out = bnd.render_network(services, summary)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)

    print("Wrote", OUT_PATH)
    print("asset-bearing instances:", tot_inst, "| asset rows:", tot_items,
          "| distinct creators:", len(creators))
    for s in summary["services"]:
        print(f"  {s['name']:<22} instances(+anchor)={s['instances']:<6} assets={s['items']}")


if __name__ == "__main__":
    main()
