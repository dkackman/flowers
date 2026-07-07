# Flowers NFT Collection — DIG Network Demo

An end-to-end demo of creating a Chia NFT collection on the [DIG Network](https://dig.net) using the `digstore` CLI. The collection uses original flower photography as artwork, stored permanently in a DIG capsule and minted as CHIP-0007 NFTs on Chia mainnet.

## What This Demonstrates

- Setting up and funding a `digstore` wallet
- Creating a creator DID for NFT attribution
- Writing CHIP-0007 metadata from a CSV classification dataset
- Minting a collection where artwork is stored in a DIG capsule
- Building and deploying a public drop page on DIG

## Prerequisites

- [`digstore` CLI](https://docs.dig.net/docs/digstore/cli/quickstart) installed
- [A funded Chia wallet](https://xch.network/get-wallet/) with XCH and $DIG tokens (needed for on-chain operations)

> Local operations are free. You spend XCH + $DIG only when anchoring on-chain (`init`, `commit`, `nft mint`, `collection create`).

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

Because they are easier to work with than JSON, we have our NFT metadata in a CSV file. `generate_manifest.py` reads `assets/flowers.csv` and produces `manifest.json` — an array of all items in the shape `collection mint` expects.

```bash
python3 generate_manifest.py
```

Each CSV row becomes one manifest entry. `Insect Type` is only included when the `InsectType` column is non-empty:

```json
[
  {
    "name": "Joe Pye Weed",
    "description": "Original flower photograph",
    "attributes": [
      { "trait_type": "Flower",      "value": "Joe Pye Weed" },
      { "trait_type": "Color",       "value": "purple"       },
      { "trait_type": "Insect",      "value": "bee"          },
      { "trait_type": "Insect Type", "value": "bumblebee"    }
    ],
    "media": {
      "data_uris": ["assets/DSC01177.jpeg"]
    }
  }
]
```

`digstore` handles capsule packing and computing `data_hash` — only the local file path is needed in `data_uris`.

### Step 5 — Mint the Collection

Preview first, then mint. `collection mint` bulk-mints every item in one on-chain bundle, attributed to your DID.

```bash
# Preview cost without spending
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

For minting a single NFT without a collection (e.g. testing one image first):

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

The `dig/` folder contains a scaffolded drop page — a wallet-connected website where people can browse and mint from the collection. This is published as its own DIG capsule.

### Step 6 — Initialize the Drop Page Store

```bash
cd dig
digstore init           # mints a new store singleton for the drop page (costs DIG + XCH)
```

This will return a 64-hex store ID. Add it to `dig/dig.toml`:

```toml
store-id = "<your-64-hex-store-id>"
```

### Step 7 — Configure the Drop Page

Edit `dig/app.js` to wire up your collection:

- Set the collection ID so the page can load NFTs
- Connect the mint button to your collection's on-chain mint via `window.chia`
- Point image previews at the capsule URNs from Part 1

Preview locally for free (no chain, no spend):

```bash
digstore dev
```

### Step 8 — Publish the Drop Page

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
