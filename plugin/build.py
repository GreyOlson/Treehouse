#!/usr/bin/env python3
"""
build.py - package the plugin .luau sources into installable Roblox models.

A tiny, Rojo-free packager. Emits one model file per product:

    Treehouse.rbxm        (PAID / full)  Script  <- Plugin.server.luau
      AttributeToolGui    ModuleScript
      Dumpers             ModuleScript

    Treehouse[Free].rbxm  (FREE)         Script  <- free/AttributeTreeFree.server.luau
      (no children - fully self-contained)

so the paid entry's `require(script.AttributeToolGui)` / `require(script.Dumpers)`
resolve, and the free entry stands alone.

Standard library only. Run after editing any script:

    python3 plugin/build.py

Then drop the .rbxm files in Studio's Plugins folder (or right-click -> Save as
Local Plugin) and restart Studio.
"""

import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Each product: output filename, root (name, class, source file), and children.
PRODUCTS = [
    {
        "out": "Treehouse.rbxm",
        "root": ("Treehouse", "Script", "Plugin.server.luau"),
        "children": [
            ("AttributeToolGui", "ModuleScript", "AttributeToolGui.luau"),
            ("Dumpers", "ModuleScript", "Dumpers.luau"),
        ],
    },
    {
        "out": "Treehouse[Free].rbxm",
        "root": ("Treehouse[Free]", "Script", "free/AttributeTreeFree.server.luau"),
        "children": [],
    },
]


def read(rel_path: str) -> str:
    with open(os.path.join(HERE, rel_path), encoding="utf-8") as f:
        return f.read()


def esc(s: str) -> str:
    # Escape &, <, > for XML text content (ProtectedString, matching Roblox).
    return html.escape(s, quote=False)


def item(ref: int, name: str, cls: str, source: str, children: str = "") -> str:
    return (
        f'<Item class="{cls}" referent="RBX{ref}">'
        f"<Properties>"
        f'<string name="Name">{esc(name)}</string>'
        f'<ProtectedString name="Source">{esc(source)}</ProtectedString>'
        f"</Properties>{children}</Item>"
    )


def build(product: dict) -> None:
    ref = 0
    child_xml = ""
    for name, cls, src_file in product["children"]:
        ref += 1
        child_xml += item(ref, name, cls, read(src_file))

    root_name, root_cls, root_file = product["root"]
    root_xml = item(0, root_name, root_cls, read(root_file), child_xml)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<roblox version="4">\n'
        f"{root_xml}\n"
        "</roblox>\n"
    )

    out = os.path.join(HERE, product["out"])
    with open(out, "w", encoding="utf-8") as f:
        f.write(xml)
    kids = ", ".join(c[0] for c in product["children"]) or "(none)"
    print(f"wrote {product['out']:24} ({os.path.getsize(out):>6} bytes)  children: {kids}")


def main() -> None:
    for product in PRODUCTS:
        build(product)


if __name__ == "__main__":
    main()
