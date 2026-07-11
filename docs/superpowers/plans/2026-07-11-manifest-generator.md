# Manifest Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `generate_manifest.py` into a two-phase offline tool that builds the CHIP-0007 capsule (images + metadata docs) and the final `collection mint` items manifest with real `dig://` URNs and pinned hashes.

**Architecture:** A single Python script exposing two subcommands. `stage` (offline) reads `flowers.csv` + `assets/` + `collection.json`, writes a capsule staging dir (indexed images + canonical CHIP-0007 `metadata.json` docs) and a `manifest.partial.json` holding every offline-computable field. The operator runs `digstore init/add/commit/push` on the capsule (on-chain, not scripted). `finalize` (offline) reads the partial file plus the printed `storeId`/`rootHash` and writes the final `items.json`.

**Tech Stack:** Python 3, standard library only (`argparse`, `csv`, `json`, `hashlib`, `pathlib`, `shutil`, `re`). Tests use stdlib `unittest`.

## Global Constraints

- Python 3, **standard library only** — no third-party dependencies.
- The script is **offline**: it never invokes `digstore` or touches the chain/wallet.
- CHIP-0007 metadata JSON must be **byte-identical** to digstore/chip35's canonical form: compact separators `(",", ":")`, `ensure_ascii=False`, fixed field order `format, name, description, sensitive_content, collection, attributes, series_number, series_total, minting_tool`, empty optionals omitted. Golden strings to match (from `digstore-chain/src/metadata.rs`):
  - Minimal: `{"format":"CHIP-0007","name":"Item"}`
  - Full: `{"format":"CHIP-0007","name":"DIG Punk #2","description":"a punk","collection":{"id":"col1","name":"DIG Punks"},"attributes":[{"trait_type":"Background","value":"Blue"}],"series_number":2,"series_total":10,"minting_tool":"DIG"}`
- Hashes are lowercase bare 64-hex (no `0x`), `hashlib.sha256`.
- Item attributes use `trait_type`/`value`.
- The exact metadata bytes written into the capsule must equal the bytes hashed into `metadata_hash`.
- Run all commands from the repo root (`/Users/don/src/dkackman/flowers`).

---

## File Structure

- `generate_manifest.py` (modify/rewrite) — the whole tool: helpers + `stage` + `finalize` + argparse.
- `test_generate_manifest.py` (create) — `unittest` suite, run from repo root.

---

### Task 1: Canonical metadata builder + hash helper

**Files:**
- Modify: `generate_manifest.py`
- Test: `test_generate_manifest.py`

**Interfaces:**
- Produces: `sha256_hex(data: bytes) -> str` (lowercase 64-hex).
- Produces: `build_metadata_doc(name, *, description=None, collection=None, attributes=None, series_number=None, series_total=None, minting_tool=None, sensitive_content=False) -> str` — returns the canonical compact JSON string. `collection` is `{"id": str, "name": str, "attributes"?: list}`; `attributes` is a list of `{"trait_type","value"}` dicts.

- [ ] **Step 1: Write the failing tests** (create `test_generate_manifest.py`)

```python
import json
import unittest

import generate_manifest as gm


class CanonicalMetadataTests(unittest.TestCase):
    def test_minimal_matches_pinned_string(self):
        self.assertEqual(
            gm.build_metadata_doc("Item"),
            '{"format":"CHIP-0007","name":"Item"}',
        )

    def test_full_matches_pinned_string(self):
        got = gm.build_metadata_doc(
            "DIG Punk #2",
            description="a punk",
            collection={"id": "col1", "name": "DIG Punks"},
            attributes=[{"trait_type": "Background", "value": "Blue"}],
            series_number=2,
            series_total=10,
            minting_tool="DIG",
        )
        self.assertEqual(
            got,
            '{"format":"CHIP-0007","name":"DIG Punk #2","description":"a punk",'
            '"collection":{"id":"col1","name":"DIG Punks"},'
            '"attributes":[{"trait_type":"Background","value":"Blue"}],'
            '"series_number":2,"series_total":10,"minting_tool":"DIG"}',
        )

    def test_sensitive_content_false_is_omitted(self):
        self.assertNotIn("sensitive_content", gm.build_metadata_doc("X"))

    def test_empty_collection_attributes_omitted(self):
        doc = gm.build_metadata_doc("X", collection={"id": "a", "name": "b", "attributes": []})
        self.assertEqual(json.loads(doc)["collection"], {"id": "a", "name": "b"})


class Sha256Tests(unittest.TestCase):
    def test_known_vector(self):
        # sha256(b"") well-known digest
        self.assertEqual(
            gm.sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_is_lowercase_64_hex(self):
        h = gm.sha256_hex(b"the real media bytes")
        self.assertRegex(h, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_generate_manifest -v`
Expected: FAIL — `AttributeError: module 'generate_manifest' has no attribute 'build_metadata_doc'` (and `sha256_hex`).

- [ ] **Step 3: Add the helpers to `generate_manifest.py`**

Add near the top of the module (after imports, before `parse_args`). Add `import hashlib` to the imports.

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_generate_manifest -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add generate_manifest.py test_generate_manifest.py
git commit -m "feat: canonical CHIP-0007 metadata builder + sha256 helper"
```

---

### Task 2: Row → attributes and item name

**Files:**
- Modify: `generate_manifest.py`
- Test: `test_generate_manifest.py`

**Interfaces:**
- Produces: `row_to_attributes(row: dict, skip_cols: set, empty_values: set) -> list` — `[{"trait_type","value"}]`, preserving CSV column order, dropping skipped columns and values whose stripped form is in `empty_values`.
- Produces: `item_name(row: dict, name_col: str, series_number: int) -> str` — `"<value> #<n>"`.

- [ ] **Step 1: Write the failing tests** (append this class to `test_generate_manifest.py`)

```python
class RowMappingTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "Name": "IMG_0033",
            "Filename": "IMG_0033.jpeg",
            "Flower": "New England Aster",
            "Color": "purple",
            "Insect": "bee",
            "InsectType": "bumblebee",
        }
        self.skip = {"Name", "Flower", "Filename"}

    def test_attributes_keep_order_and_drop_skipped(self):
        attrs = gm.row_to_attributes(self.row, self.skip, {""})
        self.assertEqual(
            attrs,
            [
                {"trait_type": "Color", "value": "purple"},
                {"trait_type": "Insect", "value": "bee"},
                {"trait_type": "InsectType", "value": "bumblebee"},
            ],
        )

    def test_empty_value_dropped_but_none_kept(self):
        row = dict(self.row, Insect="None", InsectType="")
        attrs = gm.row_to_attributes(row, self.skip, {""})
        self.assertIn({"trait_type": "Insect", "value": "None"}, attrs)
        self.assertNotIn("InsectType", [a["trait_type"] for a in attrs])

    def test_item_name_appends_series_number(self):
        self.assertEqual(gm.item_name(self.row, "Flower", 7), "New England Aster #7")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_generate_manifest.RowMappingTests -v`
Expected: FAIL — `module 'generate_manifest' has no attribute 'row_to_attributes'`.

- [ ] **Step 3: Add the functions to `generate_manifest.py`**

Replace the existing `row_to_item` function with these two functions (it is superseded by the `stage` logic in Task 3):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_generate_manifest.RowMappingTests -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add generate_manifest.py test_generate_manifest.py
git commit -m "feat: row-to-attributes and series-numbered item name"
```

---

### Task 3: `stage` command

**Files:**
- Modify: `generate_manifest.py`
- Test: `test_generate_manifest.py`

**Interfaces:**
- Consumes: `sha256_hex`, `build_metadata_doc`, `row_to_attributes`, `item_name`.
- Produces: `run_stage(csv_path, assets_dir, collection_path, capsule_dir, partial_path, name_col, file_col, description, skip_cols, empty_values) -> int` — writes `capsule_dir/` (indexed images + `NNN.json` docs) and `partial_path` (JSON array of partial items); returns item count. Each partial item: `{"name", "description"?, "attributes", "art_resource", "metadata_resource", "data_hash", "metadata_hash"}`.

- [ ] **Step 1: Write the failing test** (append this class)

```python
import shutil
import tempfile
from pathlib import Path


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.assets = self.tmp / "assets"
        self.assets.mkdir()
        (self.assets / "a.jpeg").write_bytes(b"IMG-A-BYTES")
        (self.assets / "b.jpeg").write_bytes(b"IMG-B-BYTES")
        (self.tmp / "flowers.csv").write_text(
            "Name,Filename,Flower,Color,Insect,InsectType\n"
            "n1,a.jpeg,Cosmos,pink,None,\n"
            "n2,b.jpeg,Peony,red,bee,bumblebee\n"
        )
        (self.tmp / "collection.json").write_text(
            json.dumps({"id": "flowers", "name": "Flowers"})
        )
        self.capsule = self.tmp / "capsule"
        self.partial = self.tmp / "manifest.partial.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        return gm.run_stage(
            csv_path=self.tmp / "flowers.csv",
            assets_dir=self.assets,
            collection_path=self.tmp / "collection.json",
            capsule_dir=self.capsule,
            partial_path=self.partial,
            name_col="Flower",
            file_col="Filename",
            description="",
            skip_cols={"Name", "Flower", "Filename"},
            empty_values={""},
        )

    def test_stage_writes_capsule_and_partial(self):
        count = self._run()
        self.assertEqual(count, 2)
        # Indexed resources exist.
        self.assertTrue((self.capsule / "001.jpeg").exists())
        self.assertTrue((self.capsule / "001.json").exists())
        self.assertTrue((self.capsule / "002.jpeg").exists())
        items = json.loads(self.partial.read_text())
        self.assertEqual([i["name"] for i in items], ["Cosmos #1", "Peony #2"])
        self.assertEqual(items[0]["art_resource"], "001.jpeg")
        self.assertEqual(items[0]["metadata_resource"], "001.json")

    def test_metadata_hash_matches_written_bytes(self):
        self._run()
        items = json.loads(self.partial.read_text())
        written = (self.capsule / "001.json").read_bytes()
        self.assertEqual(items[0]["metadata_hash"], gm.sha256_hex(written))
        self.assertEqual(items[0]["data_hash"], gm.sha256_hex(b"IMG-A-BYTES"))

    def test_insect_none_kept_as_trait(self):
        self._run()
        items = json.loads(self.partial.read_text())
        traits = {a["trait_type"]: a["value"] for a in items[0]["attributes"]}
        self.assertEqual(traits.get("Insect"), "None")
        self.assertNotIn("InsectType", traits)

    def test_existing_nonempty_capsule_is_refused(self):
        self.capsule.mkdir()
        (self.capsule / "stale.txt").write_text("x")
        with self.assertRaises(SystemExit):
            self._run()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_generate_manifest.StageTests -v`
Expected: FAIL — `module 'generate_manifest' has no attribute 'run_stage'`.

- [ ] **Step 3: Implement `run_stage`**

Add to `generate_manifest.py`. Ensure `import shutil` and `import sys` and `from pathlib import Path` are present (`sys`/`Path` already are; add `shutil`).

```python
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

    rows = list(csv.DictReader(csv_path.open(newline="")))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_generate_manifest.StageTests -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add generate_manifest.py test_generate_manifest.py
git commit -m "feat: stage command builds capsule + partial manifest"
```

---

### Task 4: `finalize` command

**Files:**
- Modify: `generate_manifest.py`
- Test: `test_generate_manifest.py`

**Interfaces:**
- Produces: `normalize_hex(value: str, label: str) -> str` — lowercases and validates a 64-hex id, `SystemExit(1)` otherwise.
- Produces: `run_finalize(partial_path, store_id, root_hash, out_path) -> int` — reads the partial array, writes `out_path` (`items.json`) with `media.data_uris`/`metadata_uris` as `dig://<store_id>:<root_hash>/<resource>` and the two hashes; returns item count.

- [ ] **Step 1: Write the failing test** (append this class)

```python
class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.partial = self.tmp / "manifest.partial.json"
        self.partial.write_text(json.dumps([
            {
                "name": "Cosmos #1",
                "attributes": [{"trait_type": "Color", "value": "pink"}],
                "art_resource": "001.jpeg",
                "metadata_resource": "001.json",
                "data_hash": "aa" * 32,
                "metadata_hash": "bb" * 32,
            }
        ]))
        self.out = self.tmp / "items.json"
        self.sid = "11" * 32
        self.root = "22" * 32

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finalize_builds_dig_urns_and_shape(self):
        count = gm.run_finalize(self.partial, self.sid, self.root, self.out)
        self.assertEqual(count, 1)
        item = json.loads(self.out.read_text())[0]
        self.assertEqual(item["name"], "Cosmos #1")
        media = item["media"]
        self.assertEqual(media["data_uris"], [f"dig://{self.sid}:{self.root}/001.jpeg"])
        self.assertEqual(media["metadata_uris"], [f"dig://{self.sid}:{self.root}/001.json"])
        self.assertEqual(media["data_hash"], "aa" * 32)
        self.assertEqual(media["metadata_hash"], "bb" * 32)
        # Internal staging keys must not leak into the mint manifest.
        self.assertNotIn("art_resource", item)

    def test_bad_store_id_is_rejected(self):
        with self.assertRaises(SystemExit):
            gm.run_finalize(self.partial, "nothex", self.root, self.out)

    def test_uppercase_hex_is_normalized(self):
        gm.run_finalize(self.partial, ("AB" * 32), self.root, self.out)
        item = json.loads(self.out.read_text())[0]
        self.assertIn(f"dig://{'ab' * 32}:", item["media"]["data_uris"][0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_generate_manifest.FinalizeTests -v`
Expected: FAIL — `module 'generate_manifest' has no attribute 'run_finalize'`.

- [ ] **Step 3: Implement `normalize_hex` and `run_finalize`**

Add to `generate_manifest.py`. Add `import re` to the imports.

```python
def normalize_hex(value: str, label: str) -> str:
    v = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", v):
        print(f"Error: --{label} must be 64 hex characters, got: {value}", file=sys.stderr)
        raise SystemExit(1)
    return v


def run_finalize(partial_path, store_id, root_hash, out_path) -> int:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_generate_manifest.FinalizeTests -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add generate_manifest.py test_generate_manifest.py
git commit -m "feat: finalize command writes items.json with dig:// URNs"
```

---

### Task 5: Subcommand CLI wiring + round-trip + docs

**Files:**
- Modify: `generate_manifest.py` (replace `parse_args`/`main` with subcommand dispatch and update the module docstring)
- Test: `test_generate_manifest.py`

**Interfaces:**
- Consumes: `run_stage`, `run_finalize`.
- Produces: `main(argv=None) -> None` dispatching `stage`/`finalize` subcommands.

- [ ] **Step 1: Write the failing round-trip test** (append this class)

```python
class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.assets = self.tmp / "assets"
        self.assets.mkdir()
        (self.assets / "a.jpeg").write_bytes(b"IMG-A")
        (self.assets / "b.jpeg").write_bytes(b"IMG-B")
        (self.tmp / "flowers.csv").write_text(
            "Name,Filename,Flower,Color,Insect,InsectType\n"
            "n1,a.jpeg,Cosmos,pink,None,\n"
            "n2,b.jpeg,Peony,red,bee,bumblebee\n"
        )
        (self.tmp / "collection.json").write_text(json.dumps({"id": "flowers", "name": "Flowers"}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_then_finalize_matches_mint_shape(self):
        cap = self.tmp / "capsule"
        partial = self.tmp / "manifest.partial.json"
        out = self.tmp / "items.json"
        gm.main([
            "stage",
            "--csv", str(self.tmp / "flowers.csv"),
            "--assets", str(self.assets),
            "--collection", str(self.tmp / "collection.json"),
            "--capsule", str(cap),
            "--partial", str(partial),
        ])
        gm.main([
            "finalize",
            "--partial", str(partial),
            "--store-id", "11" * 32,
            "--root-hash", "22" * 32,
            "--out", str(out),
        ])
        items = json.loads(out.read_text())
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertIn("name", it)
            self.assertTrue(all(set(a) == {"trait_type", "value"} for a in it["attributes"]))
            m = it["media"]
            self.assertTrue(m["data_uris"][0].startswith("dig://"))
            self.assertRegex(m["data_hash"], r"^[0-9a-f]{64}$")
            self.assertRegex(m["metadata_hash"], r"^[0-9a-f]{64}$")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test_generate_manifest.RoundTripTests -v`
Expected: FAIL — `main()` does not accept an argv list / subcommands not wired.

- [ ] **Step 3: Replace `parse_args` and `main`**

Remove the old `parse_args` and `main`. Update the module docstring's `Usage:` section to describe `stage`/`finalize`. Add:

```python
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
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `python3 -m unittest test_generate_manifest -v`
Expected: PASS (all tests across all classes).

- [ ] **Step 5: Commit**

```bash
git add generate_manifest.py test_generate_manifest.py
git commit -m "feat: wire stage/finalize subcommands + round-trip test"
```

---

### Task 6: Update project docs to reference the tool

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Update the workflow in `CLAUDE.md`**

In the "NFT Collection Approach" section, replace the step 2 note that says manifest generation has "NO `digstore` command" and "generate `items.json` yourself" with a reference to the actual tool:

```markdown
2. **Generate the capsule + manifest** with `generate_manifest.py` (offline, two phases):
   - `python generate_manifest.py stage --collection collection.json` → writes `capsule/` (indexed images + CHIP-0007 `metadata.json` docs) and `manifest.partial.json`.
   - After committing the capsule on-chain (step 1 above), `python generate_manifest.py finalize --store-id <sid> --root-hash <root>` → writes `items.json` with real `dig://` URNs and pinned `data_hash`/`metadata_hash`. See `docs/superpowers/specs/2026-07-11-manifest-generator-design.md`.
```

- [ ] **Step 2: Verify the doc reads correctly**

Run: `grep -n "generate_manifest.py" CLAUDE.md`
Expected: shows the new `stage`/`finalize` references.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: point collection workflow at generate_manifest.py"
```

---

## Self-Review

**Spec coverage:**
- Two-phase offline structure → Tasks 3 (`stage`), 4 (`finalize`), 5 (wiring). ✓
- Canonical CHIP-0007 metadata + golden strings → Task 1. ✓
- Hashes bare-hex sha256 → Task 1 + asserted in Tasks 3/4. ✓
- Name `<Flower> #<n>` → Task 2. ✓
- Attributes with `--empty-values` default `{""}`, `Insect: None` kept → Tasks 2, 3. ✓
- Collection ref + series + `minting_tool:DIG` → Task 3 (via Task 1 builder). ✓
- `dig://` only URNs → Task 4. ✓
- Indexed resource names avoiding spaces/`(1)` → Task 3. ✓
- Exact metadata bytes written == bytes hashed → Task 3 (`test_metadata_hash_matches_written_bytes`). ✓
- Ordering: `series_number` == array position → Task 3 loop uses `n=i+1`; round-trip preserves order (Task 5). ✓
- Operator workflow + docs → Task 6. ✓
- Out of scope (no chain calls, no gateway, no dedup) → honored; nothing scripts digstore. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code. ✓

**Type consistency:** `run_stage`/`run_finalize`/`build_metadata_doc`/`sha256_hex`/`row_to_attributes`/`item_name`/`normalize_hex`/`main` names and signatures are consistent across the Interfaces blocks and call sites. Partial-item keys (`art_resource`, `metadata_resource`, `data_hash`, `metadata_hash`, `name`, `attributes`, `description`) written in Task 3 match the keys read in Task 4. ✓
