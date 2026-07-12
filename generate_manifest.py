#!/usr/bin/env python3
"""Convert a CSV of NFT assets to a digstore collection manifest JSON.

Every column except --name-col, --file-col, and --skip columns becomes a trait attribute.
Columns with empty values are omitted from that item's attributes.

Usage:
    python3 generate_manifest.py stage --csv ./flowers.csv --assets ./assets --collection ./collection.json --capsule ./capsule --partial ./manifest.partial.json
    python3 generate_manifest.py finalize --partial ./manifest.partial.json --store-id <64-hex-id> --root-hash <64-hex-hash> --out ./items.json
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
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


def row_to_attributes(row: dict, skip_cols: set, empty_values: set) -> list:
    """Every non-skipped column becomes a trait, dropping empty-valued cells."""
    return [
        {"trait_type": col, "value": val}
        for col, val in row.items()
        if col not in skip_cols and val is not None and val.strip() not in empty_values
    ]


def item_name(row: dict, name_col: str, series_number: int) -> str:
    """Human-readable NFT name, suffixed with its 1-based series position."""
    return f"{row[name_col]} #{series_number}"


def run_stage(
    csv_path,
    assets_dir,
    collection_path,
    capsule_dir,
    partial_path,
    name_col,
    file_col,
    description,
    skip_cols,
    empty_values,
) -> int:
    """Stage assets and metadata into a capsule directory and partial manifest.

    Reads CSV, asset images, and collection metadata. Writes indexed resources
    to capsule_dir (NNN.<ext> images + NNN.json metadata) and a partial manifest
    JSON array to partial_path. Returns the count of items processed.
    """
    csv_path = Path(csv_path)
    assets_dir = Path(assets_dir)
    capsule_dir = Path(capsule_dir)
    partial_path = Path(partial_path)

    if not csv_path.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        raise SystemExit(1)

    collection = json.loads(Path(collection_path).read_text())
    col_ref = {"id": collection["id"], "name": collection["name"]}

    if capsule_dir.exists() and any(capsule_dir.iterdir()):
        print(
            f"Error: capsule dir {capsule_dir} exists and is not empty; "
            f"remove it before re-staging",
            file=sys.stderr,
        )
        raise SystemExit(1)
    capsule_dir.mkdir(parents=True, exist_ok=True)

    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    items = []
    for i, row in enumerate(rows):
        n = i + 1
        src = assets_dir / row[file_col]
        if not src.exists():
            print(f"Error: asset not found — {src}", file=sys.stderr)
            raise SystemExit(1)

        art_resource = f"{n:03d}{src.suffix}"
        metadata_resource = f"{n:03d}.json"
        attributes = row_to_attributes(row, skip_cols, empty_values)

        canonical = build_metadata_doc(
            item_name(row, name_col, n),
            description=description or None,
            collection=col_ref,
            attributes=attributes,
            series_number=n,
            series_total=total,
            minting_tool="DIG",
        )
        metadata_bytes = canonical.encode("utf-8")
        image_bytes = src.read_bytes()

        shutil.copyfile(src, capsule_dir / art_resource)
        (capsule_dir / metadata_resource).write_bytes(metadata_bytes)

        item = {"name": item_name(row, name_col, n), "attributes": attributes}
        if description:
            item["description"] = description
        item.update(
            {
                "art_resource": art_resource,
                "metadata_resource": metadata_resource,
                "data_hash": sha256_hex(image_bytes),
                "metadata_hash": sha256_hex(metadata_bytes),
            }
        )
        items.append(item)

    partial_path.write_text(json.dumps(items, indent=2))
    return total


def normalize_hex(value: str, label: str) -> str:
    """Lowercase and validate a 64-hex id, SystemExit(1) if invalid."""
    v = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", v):
        print(f"Error: --{label} must be 64 hex characters, got: {value}", file=sys.stderr)
        raise SystemExit(1)
    return v


def run_finalize(partial_path, store_id, root_hash, out_path) -> int:
    """Read partial manifest and write items.json with dig:// URNs.

    Reads the partial array, writes out_path (items.json) with media.data_uris/metadata_uris
    as dig://<store_id>:<root_hash>/<resource> and the two hashes. Returns item count.
    """
    sid = normalize_hex(store_id, "store-id")
    root = normalize_hex(root_hash, "root-hash")
    partial = json.loads(Path(partial_path).read_text())

    items = []
    for p in partial:
        item = {"name": p["name"], "attributes": p["attributes"]}
        if p.get("description"):
            item["description"] = p["description"]
        item["media"] = {
            "data_uris": [f"dig://{sid}:{root}/{p['art_resource']}"],
            "data_hash": p["data_hash"],
            "metadata_uris": [f"dig://{sid}:{root}/{p['metadata_resource']}"],
            "metadata_hash": p["metadata_hash"],
        }
        items.append(item)

    Path(out_path).write_text(json.dumps(items, indent=2))
    return len(items)


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("stage", help="Build the capsule staging dir + partial manifest (offline)")
    s.add_argument("--csv", default="./flowers.csv")
    s.add_argument("--assets", default="./assets")
    s.add_argument("--collection", default="./collection.json")
    s.add_argument("--capsule", default="./capsule")
    s.add_argument("--partial", default="./manifest.partial.json")
    s.add_argument("--name-col", default="Flower")
    s.add_argument("--file-col", default="Filename")
    s.add_argument("--desc", default="")
    s.add_argument("--skip", action="append", default=["Name"], metavar="COL")
    s.add_argument("--empty-values", nargs="*", default=[""], metavar="VAL")

    f = sub.add_parser("finalize", help="Write items.json with dig:// URNs (offline)")
    f.add_argument("--partial", default="./manifest.partial.json")
    f.add_argument("--store-id", required=True)
    f.add_argument("--root-hash", required=True)
    f.add_argument("--out", default="./items.json")

    args = p.parse_args(argv)

    if args.command == "stage":
        skip_cols = {args.name_col, args.file_col} | set(args.skip)
        count = run_stage(
            csv_path=args.csv,
            assets_dir=args.assets,
            collection_path=args.collection,
            capsule_dir=args.capsule,
            partial_path=args.partial,
            name_col=args.name_col,
            file_col=args.file_col,
            description=args.desc,
            skip_cols=skip_cols,
            empty_values=set(args.empty_values),
        )
        print(f"Staged {count} items → {args.capsule}/ and {args.partial}")
    elif args.command == "finalize":
        count = run_finalize(args.partial, args.store_id, args.root_hash, args.out)
        print(f"Wrote {count} items to {args.out}")


if __name__ == "__main__":
    main()
