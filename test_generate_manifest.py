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
