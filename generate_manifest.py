#!/usr/bin/env python3
"""Convert a CSV of NFT assets to a digstore collection manifest JSON.

Every column except --name-col, --file-col, and --skip columns becomes a trait attribute.
Columns with empty values are omitted from that item's attributes.

Usage:
    python3 generate_manifest.py
    python3 generate_manifest.py --csv ./flowers.csv --name-col Flower --file-col Filename
    python3 generate_manifest.py --csv other.csv --name-col Title --file-col Image --skip ID --out manifest.json
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path


def sha256_hex(data: bytes) -> str:
    """SHA-256 of bytes as lowercase 64-hex (the on-chain hash encoding)."""
    return hashlib.sha256(data).hexdigest()


def build_metadata_doc(
    name,
    *,
    description=None,
    collection=None,
    attributes=None,
    series_number=None,
    series_total=None,
    minting_tool=None,
    sensitive_content=False,
) -> str:
    """Build a CHIP-0007 metadata document as canonical compact JSON.

    Byte-for-byte compatible with digstore/chip35: fixed field order, empty
    optionals omitted, compact separators. The returned string's UTF-8 bytes are
    exactly what `metadata_hash` is computed over and what is written to the capsule.
    """
    doc = {"format": "CHIP-0007", "name": name}
    if description is not None:
        doc["description"] = description
    if sensitive_content:
        doc["sensitive_content"] = True
    if collection is not None:
        col = {"id": collection["id"], "name": collection["name"]}
        col_attrs = collection.get("attributes") or []
        if col_attrs:
            col["attributes"] = col_attrs
        doc["collection"] = col
    if attributes:
        doc["attributes"] = attributes
    if series_number is not None:
        doc["series_number"] = series_number
    if series_total is not None:
        doc["series_total"] = series_total
    if minting_tool is not None:
        doc["minting_tool"] = minting_tool
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv",      default="./flowers.csv",  help="Path to input CSV (default: ./flowers.csv)")
    p.add_argument("--assets",   default="./assets",       help="Directory prepended to each filename (default: ./assets)")
    p.add_argument("--out",      default="manifest.json",  help="Output path (default: manifest.json)")
    p.add_argument("--name-col", default="Flower",         help="Column to use as the NFT name (default: Flower)")
    p.add_argument("--file-col", default="Filename",       help="Column containing the asset filename (default: Filename)")
    p.add_argument("--desc",     default="",               help="Fixed description for every item (default: empty)")
    p.add_argument("--skip",     action="append", default=["Name"], metavar="COL",
                                                             help="Column to exclude from attributes; repeatable (default: Name)")
    return p.parse_args()


def row_to_item(row: dict, name_col: str, file_col: str, assets_dir: Path, description: str, skip_cols: set) -> dict:
    attributes = [
        {"trait_type": col, "value": val}
        for col, val in row.items()
        if col not in skip_cols and val
    ]

    item = {
        "name": row[name_col],
        "attributes": attributes,
        "media": {
            "data_uris": [str(assets_dir / row[file_col])],
        },
    }

    if description:
        item["description"] = description

    return item


def main():
    args = parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    assets_dir = Path(args.assets)
    skip_cols = {args.name_col, args.file_col} | set(args.skip)

    items = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        missing = {args.name_col, args.file_col} - set(headers)
        if missing:
            print(f"Error: column(s) not found in CSV: {', '.join(missing)}", file=sys.stderr)
            print(f"Available columns: {', '.join(headers)}", file=sys.stderr)
            sys.exit(1)

        for row in reader:
            asset = assets_dir / row[args.file_col]
            if not asset.exists():
                print(f"Warning: asset not found, skipping — {asset}", file=sys.stderr)
                continue
            items.append(row_to_item(row, args.name_col, args.file_col, assets_dir, args.desc, skip_cols))

    Path(args.out).write_text(json.dumps(items, indent=2))
    print(f"Wrote {len(items)} items to {args.out}")


if __name__ == "__main__":
    main()
