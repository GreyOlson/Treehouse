#!/usr/bin/env python3
"""
build_value_network_diagram.py
==============================
Per-service node-link diagram of every ValueBase object -- the Value twin of
build_network_diagram.py, using the exact same rendering engine.

DESIGN: only containers that DIRECTLY hold Value objects are drawn as nodes;
value-less scaffolding containers are path-compressed away (full path on hover).
Each container's Value objects are drawn as indented child rows beneath it,
showing  Name [ValueClass] = value (type)  with the */** marker.

Reuses build_network_diagram.py (engine + compression) and build_valuebase_tree.py
(parsing + */** marker layer).

INPUT  : Trees/ValueBaseTree.luau + src/
OUTPUT : Trees/ValueNetworkDiagram.html
RE-RUN : python3 Trees/build_value_network_diagram.py
"""

import os
import json
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bnd = _load("build_network_diagram", "build_network_diagram.py")
bvt = _load("build_valuebase_tree", "build_valuebase_tree.py")

OUT_PATH = os.path.join(bvt.PROJECT_ROOT, "working", "ValueNetworkDiagram.html")


def _item(ch, writes, nil_writes):
    it = {"n": ch.name, "v": ch.value, "t": ch.vtype,
          "m": bvt.marker_for(ch.name, writes, nil_writes), "c": ch.cls}
    if ch.cls in bvt.NON_CONVERTIBLE:
        it["nc"] = True
    return it


def to_uniform(node, writes, nil_writes):
    """Value Node -> uniform {n,c,items,ch}.
      - a leaf Value child  -> an item under this node
      - a Value child that ALSO has children (e.g. animation StringValues that
        hold Folders of nested Values) -> a container node carrying its own value
        as a self-item, recursed so nested Values aren't lost
      - a plain container child -> recurse
    Every ValueBase object is therefore counted exactly once."""
    items, kids = [], []
    for ch in node.children:
        ch_is_value = ch.value is not None
        if ch_is_value and not ch.children:
            items.append(_item(ch, writes, nil_writes))
        elif ch_is_value and ch.children:
            u = to_uniform(ch, writes, nil_writes)
            u["items"] = [_item(ch, writes, nil_writes)] + u["items"]
            kids.append(u)
        else:
            kids.append(to_uniform(ch, writes, nil_writes))
    return {"n": node.name, "c": node.cls, "items": items, "ch": kids}


def main():
    writes, nil_writes, _refs = bvt.scan_value_writes(bvt.SRC_DIR)
    roots, _tn, total_values = bvt.parse_dump(bvt.DUMP_PATH)

    services, tot_inst, tot_items = [], 0, 0
    for r in roots:
        disp = bnd.compress(to_uniform(r, writes, nil_writes))
        ic, it = bnd.count_display(disp)
        services.append(disp)
        tot_inst += ic
        tot_items += it

    summary = {
        "project": bvt.PROJECT_NAME, "item_kind": "value", "item_label": "values",
        "nc_note": True,
        "runtime": bool(writes or nil_writes),  # was the src/value-write scan run?
        "services": [{"name": s["n"], "instances": bnd.count_display(s)[0],
                      "items": bnd.count_display(s)[1]} for s in services],
        "total_instances": tot_inst, "total_items": tot_items,
    }

    # render_network titles the page "<project> - Value* Treehouse" from
    # summary.item_kind == "value", so no post-hoc relabel is needed.
    html_out = bnd.render_network(services, summary)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)

    print("Wrote", OUT_PATH)
    print("value-bearing containers:", tot_inst, "| value rows:", tot_items,
          "(should equal total values in the dump)")
    for s in summary["services"]:
        print(f"  {s['name']:<22} containers(+anchor)={s['instances']:<6} values={s['items']}")


if __name__ == "__main__":
    main()
