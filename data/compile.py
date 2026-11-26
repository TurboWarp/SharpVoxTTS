import argparse
import os
import sys

import re
import struct

MAGIC = b"STDK"
VERSION = 2
HEADER_SIZE = 32
# Every RESTART_INTERVAL-th entry stores its whole word so lookups can binary
# search those entries, then step forward through at most this many entries.
RESTART_INTERVAL = 16
WORD_END = 0x0A
PHONS_END = 0xFF

PHONEME_NAMES = {
    0: "IY", 1: "IH", 2: "EH", 3: "AE", 4: "IX", 5: "AX", 6: "ER", 7: "AH",
    8: "AA", 9: "AO", 10: "UH", 11: "UW", 12: "EY", 13: "AY", 14: "OY",
    15: "AW", 16: "OW", 17: "YU", 18: "IR", 19: "XR", 20: "AR", 21: "OR",
    22: "UR", 23: "SIL", 24: "M", 25: "N", 26: "NG", 27: "W", 28: "Y",
    29: "R", 30: "L", 31: "RX", 32: "LX", 33: "EL", 34: "EN", 35: "F",
    36: "V", 37: "TH", 38: "DH", 39: "S", 40: "Z", 41: "SH", 42: "ZH",
    43: "HH", 44: "P", 45: "B", 46: "T", 47: "D", 48: "K", 49: "G",
    50: "CH", 51: "JH", 52: "TX", 53: "DX", 54: "QX", 55: "DD",
}
NAME_TO_ID = {name: pid for pid, name in PHONEME_NAMES.items()}

VOWEL_IDS = set(range(0, 23))
STRESS_PRIMARY = 56
STRESS_SECONDARY = 57


def phons_to_tokens(phons):
    tokens = []
    pending = ""
    for b in phons:
        if b == STRESS_PRIMARY:
            pending = "1"
            continue
        if b == STRESS_SECONDARY:
            pending = "2"
            continue
        name = PHONEME_NAMES.get(b)
        if name is None:
            raise ValueError("unknown phoneme byte %d" % b)
        if pending:
            if b not in VOWEL_IDS:
                raise ValueError("stress marker before non-vowel %s" % name)
            name += pending
            pending = ""
        tokens.append(name)
    if pending:
        raise ValueError("trailing stress marker with no vowel")
    return tokens


def tokens_to_phons(tokens):
    phons = []
    for tok in tokens:
        base, stress = tok, ""
        if tok and tok[-1] in "012" and tok[:-1] in NAME_TO_ID:
            base, stress = tok[:-1], tok[-1]
        pid = NAME_TO_ID.get(base)
        if pid is None:
            raise ValueError("unknown phoneme token %r" % tok)
        if stress in ("1", "2"):
            if pid not in VOWEL_IDS:
                raise ValueError("stress on non-vowel token %r" % tok)
            phons.append(STRESS_PRIMARY if stress == "1" else STRESS_SECONDARY)
        phons.append(pid)
    return phons


# Stress markers are folded into the vowel that follows them, which makes the
# phoneme stream about 10% smaller and compress better.
FOLD_PRIMARY = 64
FOLD_SECONDARY = 128


def fold_stress(phons):
    folded = []
    stress = 0
    for b in phons:
        if b == STRESS_PRIMARY:
            stress = FOLD_PRIMARY
        elif b == STRESS_SECONDARY:
            stress = FOLD_SECONDARY
        else:
            folded.append(b + stress)
            stress = 0
    return folded


def unfold_stress(folded):
    phons = []
    for b in folded:
        if b >= FOLD_SECONDARY:
            phons += [STRESS_SECONDARY, b - FOLD_SECONDARY]
        elif b >= FOLD_PRIMARY:
            phons += [STRESS_PRIMARY, b - FOLD_PRIMARY]
        else:
            phons.append(b)
    return phons


def parse_blob(blob):
    if blob[:4] != MAGIC:
        raise ValueError("bad STDICT magic")
    version, interval, word_count, words_off, words_len, phons_off, phons_len = \
        struct.unpack_from("<HHIIIII", blob, 4)
    if version != VERSION:
        raise ValueError("unsupported STDICT version %d" % version)
    entries = []
    w = words_off
    p = phons_off
    word = b""
    for _ in range(word_count):
        prefix = blob[w]
        end = blob.index(WORD_END, w + 1)
        word = word[:prefix] + blob[w + 1:end]
        w = end + 1
        end = blob.index(PHONS_END, p)
        entries.append((word.decode("ascii"), unfold_stress(blob[p:end])))
        p = end + 1
    return entries


def build_blob(entries):
    ordered = sorted(entries, key=lambda e: e[0].encode("ascii"))

    words = bytearray()
    phons = bytearray()
    previous = b""
    for i, (word, entry_phons) in enumerate(ordered):
        wb = word.encode("ascii")
        if not wb or len(wb) > 255 or WORD_END in wb:
            raise ValueError("bad word: %r" % word)
        prefix = 0
        if i % RESTART_INTERVAL != 0:
            limit = min(len(previous), len(wb), 255)
            while prefix < limit and previous[prefix] == wb[prefix]:
                prefix += 1
        words += bytes([prefix]) + wb[prefix:] + bytes([WORD_END])
        previous = wb

        folded = fold_stress(entry_phons)
        if any(b >= PHONS_END for b in folded) or unfold_stress(folded) != entry_phons:
            raise ValueError("phonemes don't round trip: %r" % word)
        phons += bytes(folded) + bytes([PHONS_END])

    words_off = HEADER_SIZE
    phons_off = words_off + len(words)
    header = MAGIC + struct.pack("<HHIIIII", VERSION, RESTART_INTERVAL, len(ordered),
                                 words_off, len(words), phons_off, len(phons))
    header += bytes(HEADER_SIZE - len(header))

    blob = header + bytes(words) + bytes(phons)
    if parse_blob(blob) != ordered:
        raise ValueError("blob doesn't round trip")
    return blob


CPP_HEADER = (
    '#include "LibraryData.h"\n\n'
    "namespace SharpVox {\n\n"
    "const uint8_t LibraryData::dictionary[] =\n"
    "{\n"
)
CPP_FOOTER = (
    "};\n\n"
    "const int32_t LibraryData::dictionarySize = sizeof(LibraryData::dictionary);\n\n"
    "}  // namespace SharpVox\n"
)


def blob_to_cpp(blob):
    lines = [CPP_HEADER, "// %d bytes\n" % len(blob)]
    for i in range(0, len(blob), 16):
        chunk = blob[i:i + 16]
        lines.append(", ".join("0x%02X" % b for b in chunk) + ",\n")
    lines.append(CPP_FOOTER)
    return "".join(lines)


def cpp_to_blob(text):
    m = re.search(r"dictionary\[\]\s*=\s*\{(.*?)\};", text, re.S)
    if not m:
        raise ValueError("dictionary array not found")
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1)))

def load_source(path):
    entries = []
    seen = set()
    with open(path, "r") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line or line.lstrip().startswith("#"):
                continue
            if "\t" in line:
                word, rest = line.split("\t", 1)
            else:
                parts = line.split(None, 1)
                word, rest = parts[0], (parts[1] if len(parts) > 1 else "")
            word = word.strip().upper()
            if not word:
                continue
            if word in seen:
                raise ValueError("line %d: duplicate word %r" % (lineno, word))
            seen.add(word)
            try:
                phons = tokens_to_phons(rest.split())
            except ValueError as e:
                raise ValueError("line %d (%s): %s" % (lineno, word, e))
            entries.append((word, phons))
    return entries


entries = load_source("english.dict")
blob = build_blob(entries)

with open("../src/LibraryDataDictionary.cpp", "w") as f:
    f.write(blob_to_cpp(blob))

print("compiled %d entries, %d byte blob into the C++" % (len(entries), len(blob)))
