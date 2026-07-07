# Flowers NFT Collection — DIG Network Demo

A end-to-end demo of creating a Chia NFT collection on the [DIG Network](https://dig.net) using the `digstore` CLI. The collection uses original flower photography as artwork, stored permanently in a DIG capsule and minted as CHIP-0007 NFTs on Chia mainnet.

## What This Demonstrates

- Setting up and funding a `digstore` wallet
- Creating a creator DID for NFT attribution
- Storing artwork in a DIG capsule (content-addressed, tamper-evident)
- Minting a CHIP-0007 NFT collection where `data_uris` point to capsule URNs
- Managing offers to trade NFTs for XCH

## Prerequisites

- [`digstore` CLI](https://docs.dig.net/docs/digstore/cli/quickstart) installed
- A funded Chia wallet with XCH and $DIG tokens (needed for on-chain operations)

## Step 1 — Wallet Setup

```bash
digstore setup          # import or generate a BIP-39 seed phrase
digstore balance        # confirm XCH and DIG balances before spending
```

> Local operations are free. You spend XCH + $DIG only when anchoring on-chain (`init`, `commit`, `nft mint`).

## Step 2 — Initialize the Store

```bash
digstore init           # mints a store singleton on Chia mainnet
```

This creates a `dig.toml` manifest — safe to commit, contains no secrets.

## Step 3 — Create a Creator DID

```bash
digstore did create     # establishes issuer identity attached to the collection
```

## Step 4 — Create the Collection

```bash
digstore collection create
```

This initializes a CHIP-0007 collection on-chain. You will be prompted for collection name, description, and royalty settings.

## Step 5 — Stage and Publish Artwork

```bash
digstore add -A                     # stage all artwork files
digstore status                     # review what will be published
digstore commit --dry-run           # preview cost before spending
digstore commit -m "initial drop"   # anchor capsule on-chain
digstore push origin                # push to DIGHub
```

After committing, each file is addressable via a URN:

```
urn:dig:chia:<storeId>:<rootHash>/<filename>
```

## Step 6 — Mint NFTs

```bash
digstore nft mint --data ./IMG_0032.jpeg --metadata ./meta/IMG_0032.json
```

Each NFT's `data_uris` and `metadata_uris` reference the capsule URN, pinning the artwork bytes permanently on-chain. Coin spends are built by the CHIP-0035 WASM builder — never hand-rolled.

## Step 7 — Trading

```bash
digstore offer make     # list an NFT for XCH or CATs
digstore offer show     # inspect an offer file
digstore offer take     # accept an offer
```

## Collection Metadata

`flowers.csv` contains AI-generated classifications for each image used as NFT artwork:

| Column | Description |
|---|---|
| `Flower` | Species / common name |
| `Color` | Dominant flower color |
| `Insect` | Whether an insect is present |
| `InsectType` | Specific insect (`bumblebee`, `honeybee`, `sweat bee`, `monarch butterfly`) |

These fields map naturally to CHIP-0007 `attributes` in each NFT's metadata JSON.

## Key Concepts

| Term | Meaning |
|---|---|
| **Capsule** | Immutable `(storeId, rootHash)` pair — the atomic unit of content on DIG |
| **Store** | On-chain Chia singleton holding the content history (one capsule per commit) |
| **URN** | `urn:dig:chia:<storeId>[:<rootHash>][/<resource>]` — content address + decryption key |
| **CHIP-0007** | Chia NFT metadata standard |
| **CHIP-0035** | Chia standard for building coin spends (used internally by `digstore`) |

## Resources

- [DIG Network docs](https://docs.dig.net/docs/)
- [NFT developer guide](https://docs.dig.net/docs/audiences/nft-developers)
- [digstore CLI reference](https://docs.dig.net/docs/digstore/cli/command-reference)
- [Concepts & glossary](https://docs.dig.net/docs/concepts)
- [DIGHub](https://dighub.io) — browser-based alternative to the CLI
