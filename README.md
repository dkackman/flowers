# Flowers NFT Collection — DIG Network Demo

An end-to-end demo of creating a Chia NFT collection on the [DIG Network](https://dig.net) using the `digstore` CLI. The collection uses original flower photography as artwork, stored permanently in a DIG capsule and minted as CHIP-0007 NFTs on Chia mainnet.

## What This Demonstrates

- Setting up and funding a `digstore` wallet
- Creating a creator DID for NFT attribution
- Writing CHIP-0007 metadata from a CSV classification dataset
- Minting a collection whose artwork is packed into a DIG capsule by the mint itself
- Building and deploying a public drop page on DIG, in its own separate capsule

## Prerequisites

- [`digstore` CLI](https://docs.dig.net/docs/digstore/cli/quickstart) installed
- [A funded Chia wallet](https://xch.network/get-wallet/) with XCH and $DIG tokens (needed for on-chain operations)

> Local operations are free. You spend XCH + $DIG only when anchoring on-chain (`collection mint`, `nft mint`, `did create`, and the drop page's `init` / `commit`).

## Two Capsules, Two Mechanisms

This project produces **two separate DIG capsules**, each created a *different* way — don't conflate them:

1. **Artwork capsule** (Part 1) — created **by `collection mint` itself**. The mint command packs the flower images into a fresh capsule, computes the hashes from the real bytes, and pins the NFTs' media URIs to that capsule's address. **You do not run `digstore init` for the artwork** — mint owns that capsule's whole lifecycle. (In fact `nft mint` refuses to run in a directory that already has an initialized store.)
2. **Drop page capsule** (Part 2) — a website store you create yourself with `digstore new` → `digstore init` → `add` → `commit`, published under `dig/`. This is the one and only place `digstore init` belongs.

```
Part 1: collection mint ──► creates the artwork capsule + NFTs (needs DID + collection def + manifest)
                                     │
                                     └─ produces the collection ID + asset URNs ──┐
                                                                                  ▼
Part 2: digstore new → init → (configure app.js with those values) → add → commit → push
        (scaffold + init are independent; configuring app.js needs Part 1's output)
```

The drop page store's ID (from its own `digstore init`) is unrelated to the artwork capsule's ID. Never reuse one for the other.

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

> Wallets like Sage display DIDs as `did:chia:1...` (bech32m). Convert to the 64-hex launcher ID with:
>
> ```bash
> python3 did_to_hex.py did:chia:1r00z5mn...
> ```

### Step 3 — Create the Collection Definition

`collection create` takes flags (not prompts) and writes a collection definition JSON used in the mint step. The `--id` flag sets a local slug; `--royalty` is in basis points (300 = 3%).

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

> The CHIP-0007 spec requires `collection.id` to be a UUID. Verify the generated `collection.json` contains a UUID, not the slug, before minting.

### Step 4 — Build the Items Manifest

Because they are easier to work with than JSON, we keep the NFT metadata in a CSV file. `generate_manifest.py` reads `./flowers.csv` (repo root), prepends `./assets/` to each `Filename`, and writes `manifest.json` — an array of all items in the shape `collection mint` expects.

```bash
python3 generate_manifest.py
```

Each CSV row becomes one manifest entry. The `Flower` column is used as the NFT `name` (and `Name` is skipped), so they don't appear as traits; every other non-empty column becomes a trait, using the raw CSV column name. Empty cells (e.g. `InsectType` when no insect) are omitted for that item:

```json
[
  {
    "name": "Joe Pye Weed",
    "attributes": [
      { "trait_type": "Color",      "value": "purple"    },
      { "trait_type": "Insect",     "value": "bee"       },
      { "trait_type": "InsectType", "value": "bumblebee" }
    ],
    "media": {
      "data_uris": ["assets/DSC01177.jpeg"]
    }
  }
]
```

`digstore` handles capsule packing and computing `data_hash` — only the local file path is needed in `data_uris`. (Pass `--desc "..."` to `generate_manifest.py` if you want a fixed description on every item; by default there is none.)

### Step 5 — Mint the Collection

Preview first, then mint. `collection mint` bulk-mints every item in one on-chain bundle, attributed to your DID. **This command creates the artwork capsule itself** — it packs each `assets/*.jpeg`, computes the `data_hash` from the real bytes, and sets every NFT's media URI to that capsule's address. There is no separate `init`/`add`/`commit` for the artwork.

Run it from the repo root so the relative `assets/...` paths in `manifest.json` resolve. Always `--dry-run` first — it prints the resulting `dig://` URNs, computed hashes, and cost without signing or spending.

```bash
# Preview: prints the dig:// URNs, hashes, and cost (no spend)
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

The `--dry-run` output is where you read off the **collection ID** and the **per-asset URNs** you'll wire into the drop page in Part 2 — capture them now.

For minting a single NFT without a collection (e.g. testing one image first). Note `nft mint` creates its own store, so run it from a directory that does **not** already contain an initialized `.dig` store:

```bash
digstore nft mint \
  --art ./assets/IMG_0032.jpeg \
  --name "Hosta" \
  --description "Original flower photograph" \
  --royalty 300 \
  --did <64-hex-launcher-id> \
  --dry-run
```

---

## Part 2 — Build the Drop Page

A drop page is a wallet-connected website where people can browse and mint from the collection, published as its **own** DIG capsule — the one place `digstore init` belongs. Scaffolding and `init` (Steps 6–7) don't depend on Part 1 and can be done anytime; configuring `app.js` (Step 8) needs the collection ID and asset URNs from Part 1's mint.

### Step 6 — Scaffold the Drop Page

The `dig/` folder isn't in this repo — scaffold it fresh from the `nft-drop` template:

```bash
digstore new nft-drop --dir dig
# or: npm create dig-app@latest dig -- --template nft-drop
```

This is a local, free operation — no wallet or chain interaction. It generates the `dig/` project including `dig.toml` and `app.js`.

### Step 7 — Initialize the Drop Page Store

```bash
cd dig
digstore init           # mints the drop page's own store singleton (costs DIG + XCH)
```

This returns a 64-hex store ID — the drop page's own, unrelated to any artwork capsule from Part 1. Add it to `dig/dig.toml`:

```toml
store-id = "<your-64-hex-store-id>"
```

### Step 8 — Configure the Drop Page

Edit `dig/app.js` to wire up your collection, using the values Part 1's mint produced (read them from its `--dry-run` output or `collection show`):

- Set the collection ID to the `id` from your `collection.json` so the page loads the right NFTs — replace the placeholder `COLLECTION` array with a fetch against that ID instead of hardcoded `Genesis #00N` entries.
- In the `mintBtn` click handler, replace the `// TODO: build + submit your collection's mint spend here` comment with a `chia.request(...)` (or equivalent CHIP-0035 call) that submits a mint spend for that same collection ID, attributed to your DID launcher ID from Step 2.
- Point each card's `.art` preview at the asset's `dig://`/`urn:dig:chia:...` URI from the mint (the `data_uris` value baked into each NFT), instead of the empty `<div class="art"></div>`.

Preview locally for free (no chain, no spend, live reload over the actual `chia://` read path):

```bash
digstore dev
```

### Step 9 — Publish the Drop Page

```bash
digstore add -A                         # stage all drop page files
digstore status                         # review what will be published
digstore commit --dry-run               # preview cost
digstore commit -m "initial drop page"  # anchor capsule on-chain
digstore push origin                    # push to DIGHub
```

After pushing, your drop page is live at:

```
chia://<storeId>
```

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
