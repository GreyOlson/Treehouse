# plugin/ — Roblox Studio plugin

The Studio side of the tool. A toolbar button opens a dock widget with the
place-name title and two buttons; each walks the live DataModel (read-only) and
POSTs the dump to the local mailbox (`../mailbox/server.py`), which writes
the `.luau`, runs the generators, and opens the browser.

## Files

- `Plugin.server.luau` — plugin entry. Creates the toolbar button + dock widget,
  builds the GUI, and wires the buttons to dump → `HttpService:PostAsync` to
  `http://localhost:8787`.
- `AttributeToolGui.luau` — the GUI (built entirely in code, no assets). Exposes
  `M.build(host, opts)` where `opts = { onGenerateAttribute, onGenerateValue }`;
  returns `{ root, setStatus }`. Still drops into StarterGui as a LocalScript for
  a standalone preview.
- `Dumpers.luau` — read-only DataModel walkers `AttributeDump()` /
  `ValueBaseDump()` returning the exact text the Python generators parse.
- `AttributeDump_StudioCommand.luau` — the original Command-Bar dumper, kept as a
  no-plugin fallback.
- `default.project.json` — Rojo project that builds the three scripts into one
  plugin model (`Plugin.server.luau` as the Script, the other two as ModuleScript
  children).

## Build & install

```
cd plugin
rojo build -o AttributeTreeTool.rbxmx
```

Then either drag `AttributeTreeTool.rbxmx` into Studio and right-click → *Save as
Local Plugin*, or copy it into your local Plugins folder
(Studio → Plugins tab → *Plugins Folder*). For live iteration you can instead
`rojo serve` this project into a plugin place.

## Run the loop

1. Start the mailbox: `ATTRTREE_SRC=/path/to/YourGame/src python3 ../mailbox/server.py`
2. In Studio: Game Settings → Security → **Allow HTTP Requests** on.
3. Open the plugin (toolbar → Attribute Tool), click **Generate Attribute Tree**
   or **Generate ValueBase Tree**. The status line reports progress; the browser
   opens to the refreshed pages.

## Notes / remaining ideas

- `PostAsync` bodies are well under the ~1 MB request cap for current dumps; add
  chunking only if a place grows past that.
- The mailbox port is hardcoded to `8787` in `Plugin.server.luau` — change both
  sides together if needed.
- See `../docs/PluginAutomation_Feasibility.md` for the why behind the
  plugin+mailbox split.
