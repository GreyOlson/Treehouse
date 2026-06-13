# mailbox/ — local HTTP bridge

> Status: implemented in `server.py` (stdlib only). Run it alongside Rojo.
>
> ```
> TREE_SRC=/path/to/YourGame/src python3 mailbox/server.py
> ```
>
> Endpoints `POST /refresh/attributes` and `POST /refresh/values` write the body
> to `../working/`, run the matching generators, and open the resulting HTML.
> Verified end-to-end against the sample dumps.


A small program you run on your machine alongside Rojo. It exists because a
Roblox plugin is sandboxed and **cannot** write files, run Python, or open a
browser. The plugin POSTs the dump here over `http://localhost`, and this process
does the rest.

## Responsibilities (spec)

1. Listen on `http://localhost:8787` (or any local port).
2. Endpoints, one per tree:
   - `POST /refresh/attributes` → write body to `../working/AttributeTree.luau`
   - `POST /refresh/values`     → write body to `../working/ValueBaseTree.luau`
3. After writing the `.luau`, run the matching generators via `subprocess`
   (`generators/build_attribute_tree.py` + `build_network_diagram.py`, or the
   ValueBase pair). Pass `TREE_SRC` so the runtime markers resolve.
4. `webbrowser.open(...)` the resulting `working/*.html` (tree + network) so a
   fresh tab shows the updated data.
5. Reply with a short status string the plugin GUI can echo (counts, "opened").

## TODO

- `server.py` — ~40–80 lines, Python stdlib `http.server` (or Flask). No
  third-party requirement to match the generators.
- Optional: a tiny `index.html` that links/embeds all four pages.
- Optional: launch automatically next to `rojo serve`.

Permissions: Studio must have *Allow HTTP Requests* enabled; all traffic is
localhost-only (nothing leaves the machine). Full rationale and alternatives are
in `../docs/PluginAutomation_Feasibility.md`.
