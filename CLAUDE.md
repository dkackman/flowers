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

Images with a `-1` suffix (e.g. `IMG_7188-1.jpeg`) are edited variants of the same-numbered original — distinct artworks, not duplicates.

## DIG Network Key Concepts

- **Store** — on-chain Chia singleton with a 64-hex store ID; holds content history as a sequence of commits
- **Capsule** — immutable `(storeId, rootHash)` pair; the atomic unit of content on DIG
- **Generation** — one committed state of a store (append-only, like a Git commit)
- **URN** — `urn:dig:chia:<storeId>[:<rootHash>][/<resource>]` — content address and decryption key combined
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

# Collection & minting
digstore collection create --name "..." --id <uuid> --royalty 300 \
  --royalty-address <xch1...> -o collection.json   # write definition JSON (local, free)
digstore collection mint --collection collection.json \
  --manifest manifest.json --did <launcher-id>     # bulk-mint (on-chain, costs DIG + XCH)
digstore nft mint --art ./art.png --name "..."     # single NFT; packs its own media capsule

# Store management (asset capsule AND drop page each get their own store)
digstore init                           # create store (mints singleton, one-time cost)
digstore add -A                         # stage all files
digstore commit -m "<message>"          # anchor capsule on-chain
digstore push origin                    # push to DIGHub

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

1. Art lives in a DIG capsule **you build yourself** (`init` → `add` → `commit` from `assets/`) containing the images plus per-item CHIP-0007 metadata JSONs — `collection mint` does NOT create it; only single `nft mint --art` self-packs a capsule
2. `collection mint` copies each manifest item's `media` block (`data_uris`/`data_hash`/`metadata_uris`/`metadata_hash`) on-chain **verbatim, unvalidated** — the manifest must carry real `dig://<storeId>:<rootHash>/<resource>` URIs and sha256 hashes before minting
3. Two scripts, one per phase: `generate_metadata.py` (before the capsule commit) writes `assets/metadata/*.json`; `generate_manifest.py --store-id --root-hash` (after) hashes the on-disk bytes and writes the mintable `manifest.json` with `dig://` URIs
4. Metadata follows CHIP-0007 format; the script's output is byte-identical to digstore's own canonical generation (hash-stable)
5. Never hand-roll coin spends — the CHIP-0035 builders construct every spend; the wallet signs and broadcasts
6. Use `digstore did create` before minting to attach creator attribution

## Docs

- Overview: https://docs.dig.net/docs/
- NFT developers guide: https://docs.dig.net/docs/audiences/nft-developers
- CLI quickstart: https://docs.dig.net/docs/digstore/cli/quickstart
- CLI command reference: https://docs.dig.net/docs/digstore/cli/command-reference
- Concepts & glossary: https://docs.dig.net/docs/concepts
