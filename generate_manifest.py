#!/usr/bin/env python3
"""Build the digstore `collection mint` inputs from a CSV of NFT assets.

Two-pass workflow (because the dig:// URIs need the asset capsule's root hash,
which only exists after `digstore commit`):

  Pass 1 — before committing the asset store:
      python3 generate_manifest.py
    Writes one CHIP-0007 metadata JSON per item into assets/metadata/ and a
    manifest.json containing sha256 data_hash/metadata_hash but NO URIs.
    Commit the assets directory (images + metadata/) as one capsule, then:

  Pass 2 — after `digstore commit`, with the store ID and root hash it printed:
      python3 generate_manifest.py --store-id <64-hex> --root-hash <64-hex>
    Regenerates the same files (byte-identical metadata, same hashes) and fills
    in dig://<storeId>:<rootHash>/<resource> URIs. This manifest is mintable.

Every CSV column except --name-col, --file-col, and --skip columns becomes a
trait attribute; empty values are omitted from that item's attributes.

Usage:
    python3 generate_manifest.py
    python3 generate_manifest.py --store-id abc...64hex --root-hash def...64hex
    python3 generate_manifest.py --store-id ... --root-hash ... --gateway https://rpc.dig.net
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv",        default="./flowers.csv",   help="Path to input CSV (default: ./flowers.csv)")
    p.add_argument("--assets",     default="./assets",        help="Asset store content root (default: ./assets)")
    p.add_argument("--collection", default="./collection.json", help="Collection definition from `digstore collection create` (default: ./collection.json)")
    p.add_argument("--out",        default="manifest.json",   help="Output manifest path (default: manifest.json)")
    p.add_argument("--name-col",   default="Flower",          help="Column to use as the NFT name (default: Flower)")
    p.add_argument("--file-col",   default="Filename",        help="Column containing the asset filename (default: Filename)")
    p.add_argument("--desc",       default="",                help="Fixed description for every item (default: empty)")
    p.add_argument("--skip",       action="append", default=["Name"], metavar="COL",
                                                              help="Column to exclude from attributes; repeatable (default: Name)")
    p.add_argument("--store-id",   default="",                help="Asset store's 64-hex ID (from `digstore init`); enables URI output")
    p.add_argument("--root-hash",  default="",                help="Committed capsule's 64-hex root hash (from `digstore commit`/`log`); enables URI output")
    p.add_argument("--gateway",    default="",                help="Optional https gateway base (e.g. https://rpc.dig.net) for fallback URIs")
    args = p.parse_args()

    if bool(args.store_id) != bool(args.root_hash):
        p.error("--store-id and --root-hash must be given together")
    for name, val in (("--store-id", args.store_id), ("--root-hash", args.root_hash)):
        if val and not HEX64.match(val):
            p.error(f"{name} must be 64 hex characters, got {len(val)}")
    return args


def load_collection_ref(path: Path) -> dict:
    """CHIP-0007 collection block embedded in each item's metadata (id/name/attributes)."""
    definition = json.loads(path.read_text())
    ref = {"id": definition["id"], "name": definition["name"]}
    if definition.get("attributes"):
        ref["attributes"] = definition["attributes"]  # CHIP-0007 type/value pairs, passed through
    return ref


def chip0007_metadata(name: str, description: str, collection_ref: dict,
                      attributes: list, series_number: int, series_total: int) -> bytes:
    """Canonical CHIP-0007 JSON, byte-identical to digstore's generate_item_metadata output:
    fixed field order, compact separators, empty optionals omitted."""
    md = {"format": "CHIP-0007", "name": name}
    if description:
        md["description"] = description
    md["collection"] = collection_ref
    if attributes:
        md["attributes"] = attributes
    md["series_number"] = series_number
    md["series_total"] = series_total
    md["minting_tool"] = "DIG"
    return json.dumps(md, separators=(",", ":")).encode()


def dig_uri(store_id: str, root_hash: str, resource: str) -> str:
    return f"dig://{store_id}:{root_hash}/{resource}"


def gateway_uri(gateway: str, store_id: str, root_hash: str, resource: str) -> str:
    return f"{gateway.rstrip('/')}/urn:dig:chia:{store_id}:{root_hash}/{resource}"


def uris(resource: str, args) -> list:
    out = [dig_uri(args.store_id, args.root_hash, resource)]
    if args.gateway:
        out.append(gateway_uri(args.gateway, args.store_id, args.root_hash, resource))
    return out


def main():
    args = parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    collection_path = Path(args.collection)
    if not collection_path.exists():
        print(f"Error: {collection_path} not found — run `digstore collection create` first "
              f"(or pass --collection)", file=sys.stderr)
        sys.exit(1)
    collection_ref = load_collection_ref(collection_path)

    assets_dir = Path(args.assets)
    metadata_dir = assets_dir / "metadata"
    skip_cols = {args.name_col, args.file_col} | set(args.skip)

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        missing = {args.name_col, args.file_col} - set(headers)
        if missing:
            print(f"Error: column(s) not found in CSV: {', '.join(missing)}", file=sys.stderr)
            print(f"Available columns: {', '.join(headers)}", file=sys.stderr)
            sys.exit(1)
        rows = []
        for row in reader:
            asset = assets_dir / row[args.file_col]
            if not asset.exists():
                print(f"Warning: asset not found, skipping — {asset}", file=sys.stderr)
                continue
            rows.append(row)

    spaced = [r[args.file_col] for r in rows if " " in r[args.file_col]]
    if spaced:
        print(f"Warning: {len(spaced)} filename(s) contain spaces, which appear verbatim in URIs "
              f"(e.g. {spaced[0]!r}) — consider renaming", file=sys.stderr)

    metadata_dir.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    items = []
    for i, row in enumerate(rows, start=1):
        filename = row[args.file_col]
        attributes = [
            {"trait_type": col, "value": val}
            for col, val in row.items()
            if col not in skip_cols and val
        ]

        image_bytes = (assets_dir / filename).read_bytes()
        metadata_bytes = chip0007_metadata(row[args.name_col], args.desc, collection_ref,
                                           attributes, i, total)
        (metadata_dir / f"{filename}.json").write_bytes(metadata_bytes)

        # Resource paths are relative to the asset store's content root (the assets dir).
        image_resource = filename
        metadata_resource = f"metadata/{filename}.json"

        media = {
            "data_hash": hashlib.sha256(image_bytes).hexdigest(),
            "metadata_hash": hashlib.sha256(metadata_bytes).hexdigest(),
        }
        if args.store_id:
            media["data_uris"] = uris(image_resource, args)
            media["metadata_uris"] = uris(metadata_resource, args)

        item = {"name": row[args.name_col], "attributes": attributes, "media": media}
        if args.desc:
            item["description"] = args.desc
        items.append(item)

    Path(args.out).write_text(json.dumps(items, indent=2))
    print(f"Wrote {total} metadata files to {metadata_dir}/ and {total} items to {args.out}")

    if not args.store_id:
        print(
            "\nNOT MINTABLE YET — no URIs. Next:\n"
            f"  1. Commit the asset capsule ({assets_dir}/ as content root): digstore init / add -A / commit\n"
            "  2. Re-run with the values the commit printed:\n"
            f"     python3 {sys.argv[0]} --store-id <64-hex> --root-hash <64-hex>",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
