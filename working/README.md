# working/ — per-project input & output

This is the scratch area the generators read from and write to. It is **not** part
of the tool's logic — it holds the data for whatever game you're currently
analyzing.

## In (you provide)

- `AttributeTree.luau` — the attribute dump from Studio.
- `ValueBaseTree.luau` — the ValueBase dump from Studio.

(The two `.luau` here now are sample dumps from the TsunamiGame place.)

## Out (generators write)

- `AttributeTree.html`, `NetworkDiagram.html`
- `ValueBaseTree.html`, `ValueNetworkDiagram.html`

## Note on the game source

The generators also scan the analyzed game's Rojo `src/` to derive the `*`/`**`
runtime markers. That source lives in the game's own repo, not here — point the
generators at it with the `ATTRTREE_SRC` env var (see the root README). If you
analyze multiple games, give each its own `working/` (or subfolder) to avoid
mixing dumps.
