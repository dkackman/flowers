# Flowers NFT Collection — DIG Network Demo

An end-to-end demo of creating a Chia NFT collection on the [DIG Network](https://dig.net) using the `digstore` CLI. The collection uses original flower photography as artwork, stored permanently in a DIG capsule and minted as CHIP-0007 NFTs on Chia mainnet.

## What This Demonstrates

- Setting up and funding a `digstore` wallet
- Creating a creator DID for NFT attribution
- Writing CHIP-0007 metadata from a CSV classification dataset
- Building the artwork capsule yourself and minting a collection whose NFTs point into it
- Building and deploying a public drop page on DIG, in its own separate capsule

## Prerequisites

- [`digstore` CLI](https://docs.dig.net/docs/digstore/cli/quickstart) installed
- [A funded Chia wallet](https://xch.network/get-wallet/) with XCH and $DIG tokens (needed for on-chain operations)

> Local operations are free. You spend XCH + $DIG only when anchoring on-chain (`collection mint`, `did create`, and each store's `init` / `commit`).

## Two Capsules, One Mechanism — and What `collection mint` Does NOT Do

This project produces **two separate DIG capsules**, both created the same way — `digstore init` → `add` → `commit`:

1. **Artwork capsule** (Part 1) — a store *you* create, containing the flower images plus one CHIP-0007 metadata JSON per item. `collection mint` does **not** create this capsule: it consumes your `manifest.json` verbatim — whatever `data_uris`/`data_hash` values are in it go straight on-chain, unchecked. (Bulk capsule packing is an explicit not-yet-implemented TODO in digstore; only the single-NFT `digstore nft mint --art` path packs a capsule for you.) That's why the manifest must carry real `dig://` URIs and sha256 hashes *before* you mint — and why the workflow below commits the artwork capsule first.
2. **Drop page capsule** (Part 2) — a website store scaffolded from the `nft-drop` template, published under `dig/`.

```
Part 1: build artwork capsule (init → add → commit)  ──► store ID + root hash
              │                                                  │
              ▼                                                  ▼
        manifest.json (real dig:// URIs + hashes)  ──►  collection mint (NFTs point into the capsule)
                                                                 │
                                                                 └─ collection ID + asset URNs ──┐
                                                                                                 ▼
Part 2: digstore new → init → (configure app.js with those values) → add → commit → push
```

Each store gets its own ID from its own `digstore init`. Never reuse one for the other.

---

## Part 1 — Mint the Collection

### Step 1 — Wallet Setup

```bash
digstore setup          # import or generate a BIP-39 seed phrase
digstore balance        # confirm XCH and DIG balances before spending
```

### Step 2 — Create or Reuse a Creator DID

A DID (Decentralized Identifier) establishes your on-chain identity as the collection issuer. Every NFT in the collection is attributed to it. You need the DID's 64-hex launcher ID for the mint step.

**If you don't have a DID yet**, create one:

```bash
digstore did create --dry-run   # preview cost
digstore did create             # mints the DID on-chain, prints the launcher ID
```

Save the 64-hex launcher ID that is returned — it looks like `a3f2...c901`.

**If you already have a DID** from a previous collection or from your Chia wallet, find its launcher ID by listing the collections already attributed to it or from your wallet UI.

```bash
digstore collection list        # groups by creator DID; shows launcher IDs
```

Either way, you'll pass the launcher ID to `collection mint` later as `--did <launcher-id>`.

> Wallets like Sage display DIDs as `did:chia:1...` (bech32m). The Did can be provided either as the 64-hex launcher ID or the bech32m format. To convert to the 64-hex launcher ID with:
>
> ```bash
> python3 did_to_hex.py did:chia:1r00z5mn...
> ```

### Step 3 — Create the Collection Definition

`collection create` takes flags (not prompts) and writes a collection definition JSON used in the mint step. The `--id` flag sets a local slug; `--royalty` is in basis points (300 = 3%).

> The CHIP-0007 spec requires `collection.id` to be a UUID.

```bash
digstore collection create \
  --name "Dig Flowers" \
  --id <a GUID> \
  --royalty 300 \
  --royalty-address <xch1...your-address> \
  -o collection.json
```

This writes `collection.json`. Open it and add `description` and `twitter` to the `attributes` array before minting — collection attributes use `type`/`value` (not `trait_type`):

```json
"attributes": [
  { "type": "description", "value": "Original flower photography minted on the DIG Network" },
  { "type": "twitter",     "value": "@yourhandle" }
]
```

Attributes will need to be re-added if you regenerate the collection JSON. The `royalty_address` must be a valid Chia address (puzzle hash) that can receive XCH royalties.

### Step 4 — Generate the Item Metadata

Because they are easier to work with than JSON, we keep the NFT metadata in a CSV file. `generate_metadata.py` reads `./flowers.csv` (repo root) and `./collection.json` (from Step 3), and writes `assets/metadata/<image>.json` — one canonical CHIP-0007 metadata document per item (byte-identical to what digstore itself would generate: collection block, `series_number`/`series_total`, `minting_tool: "DIG"`). These files ship *inside* the artwork capsule, so this must run **before** Step 5's commit:

```bash
python3 generate_metadata.py
```

Each CSV row becomes one item. The `Flower` column is the NFT `name` (and `Name` is skipped), so they don't appear as traits; every other non-empty column becomes a trait using the raw CSV column name. Empty cells (e.g. `InsectType` when no insect) are omitted. (Pass `--desc "..."` for a fixed description on every item; by default there is none.)

> If you later edit the CSV or `collection.json`, the metadata bytes change: re-run this script and re-commit the capsule (new root hash) before building the manifest.

### Step 5 — Commit the Artwork Capsule

Create the asset store with `assets/` as its content root, so URI resource paths are `<image>.jpeg` and `metadata/<image>.jpeg.json`. This is the artwork's own `init`/`add`/`commit` — `collection mint` will not do this for you:

```bash
cd assets
digstore init                           # mints the asset store's singleton (costs DIG + XCH)
digstore add -A                         # images + metadata/ JSONs, one capsule
digstore add --discovery                # AFTER add -A: stage the .well-known listing of all staged keys
digstore status                         # review what will be committed
digstore commit -m "flowers artwork"    # anchor the capsule; note store ID + ROOT HASH
cd ..
```

Record the **store ID** (from `init`) and the committed generation's **root hash** (from `commit` / `digstore log`). You can sanity-check a resource address with `digstore urn <file>`.

> **Why `--discovery`?** On DIG, a resource is readable only by someone who knows its resource key. `add --discovery` stages the conventional `.well-known/dig/manifest.json` listing every staged key, so anyone who finds the store ID on-chain can enumerate and browse the collection — without it the capsule is opaque except to holders of the NFTs (whose URIs embed the keys). Run it *after* `add -A`: it snapshots what's staged at that moment.

### Step 6 — Build the Mint Manifest

`generate_manifest.py` writes `manifest.json` — the items array `collection mint` consumes. It requires the store ID and root hash from Step 5 to form the `dig://<storeId>:<rootHash>/<resource>` URIs, and computes `data_hash`/`metadata_hash` by sha256 over the bytes on disk — exactly what went into the capsule. (It warns if a metadata file no longer matches what the current CSV/`collection.json` would generate, i.e. you edited them after Step 4.)

```bash
python3 generate_manifest.py --store-id <64-hex-store-id> --root-hash <64-hex-root-hash>
# optionally add an https fallback URI on every item:
#   --gateway https://rpc.dig.net
```

Each manifest item now looks like:

```json
{
  "name": "Joe Pye Weed",
  "attributes": [
    { "trait_type": "Color",      "value": "purple"    },
    { "trait_type": "Insect",     "value": "bee"       },
    { "trait_type": "InsectType", "value": "bumblebee" }
  ],
  "media": {
    "data_hash":     "4e4e4e5f…0094232",
    "metadata_hash": "37257d4e…5541edd",
    "data_uris":     ["dig://<storeId>:<rootHash>/DSC01177.jpeg"],
    "metadata_uris": ["dig://<storeId>:<rootHash>/metadata/DSC01177.jpeg.json"]
  }
}
```

> `collection mint` copies these `media` values on-chain **verbatim** — it does not read the files, verify the hashes, or rewrite the URIs. A manifest with missing URIs or stale hashes mints broken NFTs without any error. Don't hand-edit this file; regenerate it.

### Step 7 — Mint the Collection

Preview first, then mint. `collection mint` bulk-mints every item, attributed to your DID, auto-splitting large collections into cost-bounded batches (resumable if interrupted). Always `--dry-run` first — it prints the mint plan and cost without signing or spending.

```bash
# Preview: prints the plan, launcher IDs, and cost (no spend)
digstore collection mint \
  --collection collection.json \
  --manifest manifest.json \
  --did <64-hex-launcher-id> \
  --dry-run

# Mint for real
digstore collection mint \
  --collection collection.json \
  --manifest manifest.json \
  --did <64-hex-launcher-id>
```

For Part 2 you'll need the **collection ID** (the `id` in `collection.json`) and the **per-asset URNs** (the `data_uris` in `manifest.json`) — capture them now.

---

## Part 2 — Build the Drop Page

A drop page is a wallet-connected website where people can browse and mint from the collection, published as its **own** DIG capsule with its own store. Scaffolding and `init` (Steps 8–9) don't depend on Part 1 and can be done anytime; configuring `app.js` (Step 10) needs the collection ID and asset URNs from Part 1.

### TBD

---

## Collection Metadata

`flowers.csv` contains classifications for each image:

| Column | Description |
|---|---|
| `Flower` | Species / common name |
| `Color` | Dominant flower color |
| `Insect` | Whether an insect is present |
| `InsectType` | Specific insect (`bumblebee`, `honeybee`, `sweat bee`, `monarch butterfly`) |

## Key Concepts

| Term | Meaning |
|---|---|
| **Capsule** | Immutable `(storeId, rootHash)` pair — the atomic unit of content on DIG |
| **Store** | On-chain Chia singleton holding the content history (one capsule per commit) |
| **URN** | `urn:dig:chia:<storeId>[:<rootHash>][/<resource>]` — content address + decryption key |
| **CHIP-0007** | Chia NFT metadata standard |
| **CHIP-0035** | Chia standard for building coin spends (used internally by `digstore`) |
| **DID** | Decentralized Identifier — your on-chain creator identity |

## Resources

- [DIG Network docs](https://docs.dig.net/docs/)
- [NFT developer guide](https://docs.dig.net/docs/audiences/nft-developers)
- [digstore CLI reference](https://docs.dig.net/docs/digstore/cli/command-reference)
- [Concepts & glossary](https://docs.dig.net/docs/concepts)
- [DIGHub](https://dighub.io) — browser-based alternative to the CLI
