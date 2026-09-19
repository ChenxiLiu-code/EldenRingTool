"""Minimal Elden Ring EMEVD reader.

Only the instruction table and raw argument blobs are needed by the map
extractors.  Elden Ring uses the 64-bit EMEVD layout introduced for Sekiro:
all section counts/offsets are int64 and each instruction record is 0x20 bytes.

This intentionally does *not* decompile event scripts.  It yields the same
(bank, id, ArgData) triplet SoulsFormats exposes, which is enough to recognize
InitializeEvent / InitializeCommonEvent calls and their literal parameters.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Instruction:
    bank: int
    id: int
    args: bytes


def iter_instructions(data: bytes) -> Iterator[Instruction]:
    """Yield every instruction in an already-decompressed ER ``.emevd``.

    Raises ``ValueError`` for a different/unsupported EMEVD layout rather than
    silently reading bogus offsets.  Elden Ring files use version 0xCD, are
    little-endian and have 64-bit section offsets.
    """
    if len(data) < 0x80 or data[:4] != b"EVD\x00":
        raise ValueError("not an EMEVD")

    big_endian = data[4] != 0
    is_64 = struct.unpack_from("<b", data, 5)[0] == -1
    version = struct.unpack_from("<i", data, 8)[0]
    if big_endian or not is_64 or version != 0xCD:
        raise ValueError(
            f"unsupported EMEVD layout: bigEndian={big_endian} "
            f"is64={is_64} version=0x{version:X}"
        )

    # Header after the fixed 0x10 bytes is a sequence of (count, offset)
    # int64 pairs.  Pair 1 = Events, pair 2 = Instructions; later pair 6 =
    # raw instruction argument data.
    p = 0x10
    _event_count, _events_off = struct.unpack_from("<qq", data, p); p += 0x10
    inst_count, inst_off = struct.unpack_from("<qq", data, p); p += 0x10
    _unknown_count, _unknown_off = struct.unpack_from("<qq", data, p); p += 0x10
    _layer_count, _layer_off = struct.unpack_from("<qq", data, p); p += 0x10
    _param_count, _param_off = struct.unpack_from("<qq", data, p); p += 0x10
    _linked_count, _linked_off = struct.unpack_from("<qq", data, p); p += 0x10
    args_len, args_off = struct.unpack_from("<qq", data, p)

    if inst_count < 0 or inst_count > 10_000_000:
        raise ValueError(f"implausible instruction count: {inst_count}")
    if not (0 <= inst_off <= len(data)) or not (0 <= args_off <= len(data)):
        raise ValueError("EMEVD section offset outside file")
    if args_len < 0 or args_off + args_len > len(data):
        raise ValueError("EMEVD argument section outside file")

    rec_size = 0x20
    if inst_off + inst_count * rec_size > len(data):
        raise ValueError("EMEVD instruction table truncated")

    for n in range(inst_count):
        o = inst_off + n * rec_size
        bank, iid = struct.unpack_from("<ii", data, o)
        arg_len, arg_rel = struct.unpack_from("<qq", data, o + 8)
        # Last int64 is the optional layer-table-relative offset; not needed.
        if arg_len < 0 or arg_rel < 0 or arg_rel + arg_len > args_len:
            continue
        a0 = args_off + arg_rel
        yield Instruction(bank, iid, data[a0:a0 + arg_len])
