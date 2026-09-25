"""Inspect local game event scripts for quest-related flag references."""
from __future__ import annotations

import argparse
import struct

from erlib.dcx import decompress
from erlib.dvdbnd import DvdBnd
from erlib.emevd import iter_instructions
from erlib.oodle import make_helper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--event", action="append", required=True)
    parser.add_argument("--range", type=int, nargs=2)
    parser.add_argument("flags", type=int, nargs="+")
    args = parser.parse_args()
    dvd = DvdBnd(args.game_dir)
    oodle = make_helper(args.game_dir)
    try:
        for event in args.event:
            path = f"/event/{event}.emevd.dcx"
            data = decompress(dvd.read(path), oodle)
            print(path)
            for index, instruction in enumerate(iter_instructions(data)):
                if args.range and args.range[0] <= index <= args.range[1]:
                    print(index, f"{instruction.bank}:{instruction.id}", instruction.args.hex(" "))
                matched = [flag for flag in args.flags if struct.pack("<I", flag) in instruction.args]
                if matched and not args.range:
                    print(index, f"{instruction.bank}:{instruction.id}", matched, instruction.args.hex(" "))
    finally:
        dvd.close()


if __name__ == "__main__":
    main()
