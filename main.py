import sys

if sys.version_info < (3, 13):
    raise SystemExit(
        f"EldenRingTool requires Python 3.13 or newer; current interpreter is {sys.version.split()[0]}."
    )

from eldenringtool.app import main

raise SystemExit(main())
