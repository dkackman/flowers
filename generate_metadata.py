#!/usr/bin/env python3
"""Generate one CHIP-0007 metadata JSON per NFT item from a CSV of assets.

Run this BEFORE committing the artwork capsule — the metadata files it writes to
<assets>/metadata/ must be part of the same commit as the images, because the
NFTs' metadata_uris point into that capsule. After committing, build the mint
manifest with generate_manifest.py.

The output is byte-identical to digstore's own canonical CHIP-0007 generation
(fixed field order, compact separators, empty optionals omitted), so the
metadata_hash pinned on-chain is reproducible.

Every CSV column except --name-col, --file-col, and --skip columns becomes a
trait attribute; empty values are omitted from that item's attributes.

Usage:
    python3 generate_metadata.py
    python3 generate_metadata.py --csv ./flowers.csv --collection ./collection.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def add_shared_args(p: argparse.ArgumentParser):
    """CSV/collection arguments shared with generate_manifest.py."""
    p.add_argument("--csv",        default="./flowers.csv",   help="Path to input CSV (default: ./flowers.csv)")
    p.add_argument("--assets",     default="./assets",        help="Asset store content root (default: ./assets)")
    p.add_argument("--collection", default="./collection.json", help="Collection definition from `digstore collection create` (default: ./collection.json)")
    p.add_argument("--name-col",   default="Flower",          help="Column to use as the NFT name (default: Flower)")
    p.add_argument("--file-col",   default="Filename",        help="Column containing the asset filename (default: Filename)")
    p.add_argument("--desc",       default="",                help="Fixed description for every item (default: empty)")
    p.add_argument("--skip",       action="append", default=["Name"], metavar="COL",
                                                              help="Column to exclude from attributes; repeatable (default: Name)")


def load_collection_ref(path: Path) -> dict:
    """CHIP-0007 collection block embedded in each item's metadata (id/name/attributes)."""
    definition = json.loads(path.read_text())
    ref = {"id": definition["id"], "name": definition["name"]}
    if definition.get("attributes"):
        ref["attributes"] = definition["attributes"]  # CHIP-0007 type/value pairs, passed through
    return ref


def read_rows(args) -> list:
    """CSV rows whose asset file exists, in CSV order. Exits on missing columns/files."""
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    assets_dir = Path(args.assets)
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
    return rows


def row_attributes(row: dict, args) -> list:
    skip_cols = {args.name_col, args.file_col} | set(args.skip)
    return [
        {"trait_type": col, "value": val}
        for col, val in row.items()
        if col not in skip_cols and val
    ]


def chip0007_metadata(name: str, description: str, collection_ref: dict,
                      attributes: list, series_number: int, series_total: int) -> bytes:
    """Canonical CHIP-0007 JSON, byte-identical to digstore's generate_item_metadata output."""
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


def item_metadata_bytes(row: dict, args, collection_ref: dict,
                        series_number: int, series_total: int) -> bytes:
    return chip0007_metadata(row[args.name_col], args.desc, collection_ref,
                             row_attributes(row, args), series_number, series_total)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_shared_args(p)
    args = p.parse_args()

    collection_path = Path(args.collection)
    if not collection_path.exists():
        print(f"Error: {collection_path} not found — run `digstore collection create` first "
              f"(or pass --collection)", file=sys.stderr)
        sys.exit(1)
    collection_ref = load_collection_ref(collection_path)

    rows = read_rows(args)
    metadata_dir = Path(args.assets) / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    total = len(rows)
    for i, row in enumerate(rows, start=1):
        filename = row[args.file_col]
        metadata_bytes = item_metadata_bytes(row, args, collection_ref, i, total)
        (metadata_dir / f"{filename}.json").write_bytes(metadata_bytes)

    print(f"Wrote {total} metadata files to {metadata_dir}/")
    print(
        "\nNext:\n"
        f"  1. Commit the asset capsule ({args.assets}/ as content root): digstore init / add -A / commit\n"
        "  2. Build the mint manifest with the values the commit printed:\n"
        "     python3 generate_manifest.py --store-id <64-hex> --root-hash <64-hex>",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
