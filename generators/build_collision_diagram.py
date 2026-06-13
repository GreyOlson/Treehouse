#!/usr/bin/env python3
"""
build_collision_diagram.py
==========================
Per-service node-link diagram of every part with a NON-DEFAULT collision setting --
the Collision twin of build_network_diagram.py, using the exact same engine.

A part is "flagged" (drawn) if any of:
    CanCollide == false
    CanTouch == false
    AudioCanCollide == false
    CollisionGroup ~= "Default"
    CollisionFidelity ~= "Default"   (meshes / solid-model parts)

The CollisionDump (Dumpers.luau) emits exactly those offending properties per part,
in the same text format as the attribute dump, so the shared parser reads it and
each flagged property becomes an item row beneath its part - just like attributes.
Only flagged parts are nodes; scaffolding is path-compressed away (full path on
hover) and the Layer Mapper groups by the real 2nd layer, same as every other page.

INPUT  : working/CollisionTree.luau
OUTPUT : working/CollisionNetworkDiagram.html
RE-RUN : python3 generators/build_collision_diagram.py
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

DUMP_PATH = os.path.join(bat.PROJECT_ROOT, "working", "CollisionTree.luau")
OUT_PATH = os.path.join(bat.PROJECT_ROOT, "working", "CollisionNetworkDiagram.html")


def node_to_uniform(node):
    """Parsed Node -> uniform {n,c,items,ch}. Collision flags have no */** markers
    and aren't rojo-filtered, so each parsed attr becomes a plain item."""
    items = [{"n": a["name"], "v": a["value"], "t": a["type"], "m": ""}
             for a in node.attrs]
    return {"n": node.name, "c": node.cls, "items": items,
            "ch": [node_to_uniform(c) for c in node.children]}


def main():
    roots, _total = bat.parse_dump(DUMP_PATH)

    services, tot_inst, tot_items = [], 0, 0
    for r in roots:
        disp = bnd.compress(node_to_uniform(r))
        ic, it = bnd.count_display(disp)
        services.append(disp)
        tot_inst += ic
        tot_items += it

    summary = {
        "project": bat.PROJECT_NAME, "item_kind": "collision",
        "item_label": "collision flags",
        "services": [{"name": s["n"], "instances": bnd.count_display(s)[0],
                      "items": bnd.count_display(s)[1]} for s in services],
        "total_instances": tot_inst, "total_items": tot_items,
    }

    html_out = bnd.render_network(services, summary)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)

    print("Wrote", OUT_PATH)
    print("flagged parts:", tot_inst, "| flag rows:", tot_items)
    for s in summary["services"]:
        print(f"  {s['name']:<22} parts(+anchor)={s['instances']:<6} flags={s['items']}")


if __name__ == "__main__":
    main()
