#!/usr/bin/env python3
"""Convert a Chia DID (did:chia:1...) to the 64-hex launcher ID digstore expects.

Usage:
    python3 did_to_hex.py did:chia:1r00z5mnm8j77akw8mzp4talfzfffra86zasur2usvegftkxu0czqqynhn8
"""

import sys

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def convertbits(data, frombits, tobits, pad=True):
    acc, bits, ret = 0, 0, []
    maxv = (1 << tobits) - 1
    for v in data:
        acc = ((acc << frombits) | v) & 0xFFFFFFFF
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def did_to_hex(did: str) -> str:
    if not did.startswith("did:chia:"):
        raise ValueError(f"Expected did:chia:... format, got: {did!r}")

    encoded = did[len("did:chia:"):]
    pos = encoded.rfind("1")
    if pos < 0:
        raise ValueError("Invalid bech32m encoding — no separator found")

    data = [CHARSET.find(c) for c in encoded[pos + 1:]]
    if any(v < 0 for v in data):
        raise ValueError("Invalid bech32m character in DID")

    decoded = convertbits(data[:-6], 5, 8, False)  # strip 6-char checksum
    if len(decoded) != 32:
        raise ValueError(f"Expected 32 bytes, got {len(decoded)}")

    return bytes(decoded).hex()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} did:chia:1...", file=sys.stderr)
        sys.exit(1)

    try:
        print(did_to_hex(sys.argv[1]))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
