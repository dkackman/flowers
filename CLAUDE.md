# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

An NFT collection on the [DIG Network](https://docs.dig.net/docs/) (a PoS Layer 2 on Chia blockchain) using the flower photographs in this directory as NFT artwork. The collection follows the CHIP-0007 standard with artwork permanently stored in a DIG capsule.

## Data

`flowers.csv` — AI-generated classifications for each image:
- `Name` / `Filename` — image identifier
- `Flower` — species/common name
- `Color` — dominant flower color
- `Insect` / `InsectType` — insect presence and type (`bumblebee`, `honeybee`, `sweat bee`, `monarch butterfly`)

Some images have duplicates with ` (1)` or ` (2)` suffixes — same bytes, treat as identical.

## DIG Network Key Concepts

- **Store** — on-chain Chia singleton with a 64-hex store ID; holds content history as a sequence of commits
- **Capsule** — immutable `(storeId, rootHash)` pair; the atomic unit of content on DIG
- **Generation** — one committed state of a store (append-only, like a Git commit)
- **URN** — `urn:dig:chia:<storeId>[:<rootHash>][/<resource>]` — content address and decryption key combined (the on-chain mint manifest / capsule addresses use the equivalent `dig://<storeId>:<rootHash>/<resource>` representation)
- **dig.toml** — project manifest (safe to commit; contains no secrets)
- On-chain operations (`init`, `commit`) spend real XCH + $DIG tokens; local operations are free

## digstore CLI Workflow

```bash
# One-time setup
digstore setup                          # import/generate seed, optional DIGHub login
digstore balance                        # verify wallet funded (needs XCH + DIG)

# Project scaffold (free)
digstore new nft-drop                   # scaffold from nft-drop template
# or: npm create dig-app@latest my-drop -- --template nft-drop

# Creator identity
digstore did create                     # establish issuer DID for attribution

# 1. Asset capsule — SEPARATE, prerequisite step (create + publish the art bytes)
digstore init                           # create store (mints singleton, one-time cost)
digstore add -A                         # stage art + CHIP-0007 metadata.json
digstore commit -m "<message>"          # anchor capsule on-chain -> storeId:rootHash
digstore push origin                    # publish bytes to DIGHub so URNs resolve

# 2. Collection & minting (on-chain, costs DIG + XCH)
digstore collection create --name "Flowers" --royalty 300 --out collection.json
                                        # write collection definition JSON (LOCAL, free — no chain)
digstore collection mint --collection collection.json --manifest items.json --did <did>
                                        # bulk-mint items that ALREADY reference capsule URNs/hashes

# Single-NFT mint (the ONLY path that packs a capsule inline)
digstore nft mint --art ./art.png --name "<name>" [--description <d>] [--did <did>]

# Inspection (free)
digstore status                         # staged/modified files and capacity
digstore log                            # deployment history and root hashes
digstore commit --dry-run               # preview costs before spending
digstore doctor                         # preflight checks before publishing
digstore urn <file>                     # preview URN for a file

# NFT trading
digstore offer make/take/show           # trade NFTs for XCH or CATs
```

## NFT Collection Approach

For a bulk collection, capsule creation and minting are **two distinct on-chain phases** — `collection mint` does NOT create the capsule. It consumes an `items.json` manifest whose items already carry their capsule addresses (`data_uris`/`metadata_uris` as `dig://<storeId>:<rootHash>/...`) and pinned `data_hash`/`metadata_hash`.

1. **Define the collection** — `digstore collection create --out collection.json` writes a local JSON definition (no chain, no spend).
2. **Generate the capsule + manifest** with `generate_manifest.py` (offline, two phases around the on-chain commit):
   - `python generate_manifest.py stage --collection collection.json` → writes `capsule/` (index-named images `NNN.jpeg` + canonical CHIP-0007 `NNN.json` docs) and `manifest.partial.json`, computing `data_hash`/`metadata_hash` from the real bytes.
   - Publish the capsule: `cd capsule && digstore init && digstore add -A && digstore commit -m "flowers art" && digstore push origin` — note the printed `storeId` + `rootHash`.
   - `python generate_manifest.py finalize --store-id <sid> --root-hash <root>` → writes `items.json` with the real `dig://` URNs. See `docs/superpowers/specs/2026-07-11-manifest-generator-design.md`.
3. **Mint** — `digstore did create` (once, for attribution), then `digstore collection mint --collection collection.json --manifest items.json --did <did>`.

Notes:

- The CHIP-0007 `metadata.json` bytes are byte-for-byte canonical (compact JSON, fixed field order) so `metadata_hash` matches what every verifying client computes. `generate_manifest.py` pins this against digstore's golden strings.
- `digstore nft mint` flags are `--art`/`--name` (no `--data`/`--metadata`); its metadata JSON is generated from `--name`/`--description`. Only single `nft mint` packs a capsule inline.
- Never hand-roll coin spends — the CHIP-0035 WASM builder constructs every spend; the wallet signs once and broadcasts once.

## Docs

- Overview: https://docs.dig.net/docs/
- NFT developers guide: https://docs.dig.net/docs/audiences/nft-developers
- CLI quickstart: https://docs.dig.net/docs/digstore/cli/quickstart
- CLI command reference: https://docs.dig.net/docs/digstore/cli/command-reference
- Concepts & glossary: https://docs.dig.net/docs/concepts
