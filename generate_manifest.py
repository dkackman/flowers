#!/usr/bin/env python3
"""Build the manifest.json that `digstore collection mint` consumes.

Run this AFTER generate_metadata.py and after committing the artwork capsule —
it needs the asset store's ID and the committed generation's root hash to form
the urn:dig:chia:<storeId>:<rootHash>/<resource> URIs, and it hashes the image
and metadata bytes exactly as they sit on disk (i.e. what went into the capsule).

`collection mint` copies each item's media block on-chain verbatim, so this
manifest is the single source of truth for the NFTs' URIs and hashes.

Usage:
    python3 generate_manifest.py --store-id <64-hex> --root-hash <64-hex>
    python3 generate_manifest.py --store-id ... --root-hash ... --gateway https://rpc.dig.net
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from generate_metadata import (
    add_shared_args,
    item_metadata_bytes,
    load_collection_ref,
    read_rows,
    row_attributes,
)

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_shared_args(p)
    p.add_argument("--out",       default="manifest.json", help="Output manifest path (default: manifest.json)")
    p.add_argument("--store-id",  required=True,           help="Asset store's 64-hex ID (from `digstore init`)")
    p.add_argument("--root-hash", required=True,           help="Committed capsule's 64-hex root hash (from `digstore commit`/`log`)")
    p.add_argument("--gateway",   default="",               help="Optional https gateway base (e.g. https://rpc.dig.net) for fallback URIs")
    args = p.parse_args()

    for name, val in (("--store-id", args.store_id), ("--root-hash", args.root_hash)):
        if not HEX64.match(val):
            p.error(f"{name} must be 64 hex characters, got {len(val)}")
    return args


def uris(resource: str, args) -> list:
    urn = f"urn:dig:chia:{args.store_id}:{args.root_hash}/{resource}"
    out = [urn]
    if args.gateway:
        out.append(f"{args.gateway.rstrip('/')}/{urn}")
    return out


def main():
    args = parse_args()

    collection_path = Path(args.collection)
    if not collection_path.exists():
        print(f"Error: {collection_path} not found (or pass --collection)", file=sys.stderr)
        sys.exit(1)
    collection_ref = load_collection_ref(collection_path)

    assets_dir = Path(args.assets)
    metadata_dir = assets_dir / "metadata"
    rows = read_rows(args)
    total = len(rows)

    items = []
    stale = []
    for i, row in enumerate(rows, start=1):
        filename = row[args.file_col]
        metadata_path = metadata_dir / f"{filename}.json"
        if not metadata_path.exists():
            print(f"Error: {metadata_path} not found — run generate_metadata.py first", file=sys.stderr)
            sys.exit(1)

        metadata_bytes = metadata_path.read_bytes()
        if metadata_bytes != item_metadata_bytes(row, args, collection_ref, i, total):
            stale.append(filename)

        item = {
            "name": row[args.name_col],
            "attributes": row_attributes(row, args),
            "media": {
                "data_hash": hashlib.sha256((assets_dir / filename).read_bytes()).hexdigest(),
                "metadata_hash": hashlib.sha256(metadata_bytes).hexdigest(),
                "data_uris": uris(filename, args),
                "metadata_uris": uris(f"metadata/{filename}.json", args),
            },
        }
        if args.desc:
            item["description"] = args.desc
        items.append(item)

    if stale:
        print(f"Warning: {len(stale)} metadata file(s) differ from what the current CSV/collection.json "
              f"would generate (e.g. {stale[0]!r}). The manifest hashes the on-disk bytes — fine if the "
              f"capsule was committed from them, but if you edited the CSV or collection.json since, "
              f"re-run generate_metadata.py and re-commit the capsule first.", file=sys.stderr)

    Path(args.out).write_text(json.dumps(items, indent=2))
    print(f"Wrote {total} items to {args.out}")


if __name__ == "__main__":
    main()
