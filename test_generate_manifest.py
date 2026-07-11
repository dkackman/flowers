import json
import shutil
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
