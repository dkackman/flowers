# Manifest Generator Design

**Date:** 2026-07-11
**Status:** Approved
**Topic:** Upgrade `generate_manifest.py` into a two-phase capsule + mint-manifest generator for the flowers NFT collection.

## Problem

`digstore collection mint` does **not** create the asset capsule. It consumes a pre-built
items manifest (`--manifest items.json`) whose every item already carries its on-chain media
fields: `data_uris`/`metadata_uris` (as `dig://<storeId>:<rootHash>/<resource>` URNs),
`data_hash`, and `metadata_hash`. digstore's own code marks the production of this manifest —
CSV ingest, per-item CHIP-0007 metadata generation, and capsule packing — as "the toolkit's
job" (a TODO in `digstore-chain/src/collection.rs`). There is no `digstore` command for it.

The existing `generate_manifest.py` produces a manifest that will **not** mint: its `data_uris`
are local paths (`assets/IMG_0033.jpeg`), and it has no `data_hash`, `metadata_uris`, or
`metadata_hash`, and it never generates the CHIP-0007 `metadata.json` documents at all.

This spec upgrades `generate_manifest.py` into the real tool.

## The forced two-phase structure

The manifest needs `data_uris = dig://<storeId>:<rootHash>/<file>`, but `rootHash` does not
exist until **after** the capsule is committed on-chain — and the capsule must contain **both**
the images **and** the generated `metadata.json` files. The CHIP-0007 metadata document does
**not** embed the data URI or hash (verified against `digstore-chain/src/metadata.rs`), so there
is no circular dependency: metadata bytes and both hashes are fully computable offline, before
the commit. The work therefore splits into two offline phases around the on-chain `digstore
commit`.

The script stays **offline**: it only reads and writes files. The on-chain steps
(`init`/`add`/`commit`/`push`, which spend real XCH + $DIG) are run deliberately by the operator
between the two phases — never shelled out by the script.

## Commands

```
python generate_manifest.py stage    --collection collection.json
python generate_manifest.py finalize --store-id <hex> --root-hash <hex>
```

### `stage` (free, no chain)

Inputs: `flowers.csv`, `assets/`, `collection.json` (from `digstore collection create --out`).

Outputs:

- `capsule/` — the digstore staging directory. Each image is copied in under a **clean,
  zero-padded index name** (`001.jpeg … 024.jpeg`) alongside its metadata document
  (`001.json … 024.json`). Index names are used because the original filenames contain spaces
  and `(1)` suffixes (e.g. `IMG_7188 (1).jpeg`), which produce invalid URNs. The image
  extension is preserved from the source file.
- `manifest.partial.json` — everything computable offline: for each item `name`, optional
  `description`, `attributes`, `data_hash`, `metadata_hash`, and the two capsule resource names
  (`art_resource`, `metadata_resource`). No URN root yet.

### `finalize` (free, no chain)

Inputs: `manifest.partial.json`, `--store-id`, `--root-hash`.

Output: `items.json` — the final mint manifest `collection mint --manifest` consumes. Fills in:

- `data_uris = ["dig://<storeId>:<rootHash>/<art_resource>"]`
- `metadata_uris = ["dig://<storeId>:<rootHash>/<metadata_resource>"]`

## Per-item content

- **name**: `"<Flower> #<n>"` where `n` is the 1-based series position (e.g. `"Cosmos #7"`).
  Guarantees unique names even though `Flower` repeats (Cosmos, Peony appear twice).
- **attributes**: every CSV column except `Name`, `Flower`, `Filename`; value must be non-empty
  and not in `--empty-values` (default `{"", "None"}`, so no-insect items get no insect traits).
  Item attributes use `trait_type`/`value` (CHIP-0007 item shape).
- **description**: optional fixed string via a flag; omitted if empty.
- **URIs**: `dig://` primary only (no https gateway fallback).

## CHIP-0007 metadata document (the correctness-critical part)

`metadata_hash` must equal `sha256` of the **exact bytes** served from the capsule. digstore and
chip35 pin a byte-for-byte canonical form (see the golden strings in
`digstore-chain/src/metadata.rs`, tests `minimal_canonical_json_is_the_pinned_byte_string` and
`full_canonical_json_field_order_is_pinned`):

- Compact JSON: `,` and `:` separators, no whitespace.
- Fixed field order: `format`, `name`, `description`, `sensitive_content`, `collection`,
  `attributes`, `series_number`, `series_total`, `minting_tool`.
- Empty optionals omitted (`description=None`, `sensitive_content=false`, empty vecs, `None`
  numbers). `collection` is `{id, name}` with its own `attributes` omitted when empty.

Each document is built as an ordered dict in exactly that field order, emitting only present
fields, and serialized with `json.dumps(doc, separators=(",", ":"), ensure_ascii=False)`.

Documents this collection emits contain: `format:"CHIP-0007"`, `name`, `collection:{id,name}`
(id/name read from `collection.json`), `attributes`, `series_number`/`series_total` (n/N),
`minting_tool:"DIG"`.

Hashing: `data_hash = sha256(image_bytes)`, `metadata_hash = sha256(canonical_metadata_bytes)`,
using stdlib `hashlib.sha256` (chia_sha2 is plain SHA-256). Both serialize into the manifest as
bare 64-character lowercase hex (no `0x`).

## Ordering & consistency

`collection mint` assigns each NFT's on-chain edition number from the item's position in the
`items.json` array. `items.json` is therefore ordered by series position, and each item's
`series_number` in its metadata document equals that same 1-based position, so off-chain and
on-chain ordering agree.

## Full operator workflow

1. `digstore collection create --name "Flowers" --royalty <bp> --out collection.json` (local, free)
2. `python generate_manifest.py stage --collection collection.json`
3. `cd capsule && digstore init && digstore add -A && digstore commit -m "flowers art" && digstore push origin` — note `storeId` + `rootHash`
4. `python generate_manifest.py finalize --store-id <sid> --root-hash <root>`
5. `digstore did create` (once, if no issuer DID yet)
6. `digstore collection mint --collection collection.json --manifest items.json --did <did>`

## Testing

- **Golden canonical-JSON tests**: replicate digstore's two pinned strings (minimal and full)
  in Python; assert byte-identical output. This is the guard that our `metadata_hash` matches
  what every verifying client computes.
- **Hash determinism**: `data_hash`/`metadata_hash` reproducible for fixed inputs; bare-hex
  encoding.
- **Round-trip**: `stage` → `finalize` yields an `items.json` matching the shape `collection
  mint` parses (array of `{name, attributes:[{trait_type,value}], media:{data_uris, data_hash,
  metadata_uris, metadata_hash}}`, hashes bare-hex, URIs `dig://`).

## Out of scope

- Driving digstore / any on-chain operation from the script.
- https gateway fallback URIs (design keeps a single `dig://` URI per asset).
- Deduplicating byte-identical images into shared capsule resources (each CSV row → one NFT).
