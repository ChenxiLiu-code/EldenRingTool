# Third-party notices

EldenRingTool's original code is licensed under LGPL-3.0-only. This does not
relicense third-party material. Existing source comments and attribution notices
are retained. Dependencies installed separately retain their respective licenses.

## Project reference

EldenRingTool references the ideas and functionality of
[egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap).
This attribution does not imply endorsement or a license grant from that project.

## Category resources and classification

[VirusAlex/ERR-MapForGoblins-DLL](https://github.com/VirusAlex/ERR-MapForGoblins-DLL)
is the source identified by the existing project for:

- `assets/icons/categories/`;
- the classifier in `tools/erlib/mfg_categories.py`;
- the reference lists and Reforged piece mappings in `data/mfg/`.

The upstream copyright and permission notices are reproduced in
[LICENSES/MapForGoblins.txt](LICENSES/MapForGoblins.txt). The existing
[category notice](assets/icons/categories/NOTICE.txt) is also retained.
The full upstream notice includes notices for its own dependencies; those entries
do not mean that all such dependencies are bundled here.

## Parameter definitions

The equipment definitions in `data/paramdefs/` are attributed to
[soulsmods/Paramdex](https://github.com/soulsmods/Paramdex/tree/master/ER/Defs)
by the existing [SOURCES.md](data/paramdefs/SOURCES.md).
That source note is retained; no blanket LGPL grant is asserted for these files.

## Save-format references

`tools/er_save.py` identifies these sources for save-format structures and algorithms:

- [ClayAmore/ER-Save-Lib](https://github.com/ClayAmore/ER-Save-Lib), including the source of `data/eventflag_bst.txt`;
- [ClayAmore/EldenRingSaveTemplate](https://github.com/ClayAmore/EldenRingSaveTemplate);
- [BenGrn/EldenRingSaveCopier](https://github.com/BenGrn/EldenRingSaveCopier).

The original source comments remain authoritative for the referenced components.
Source attribution alone is not a replacement for permission from a rights holder;
these references are not represented as covered by EldenRingTool's LGPL license.

## Excluded local content

This source distribution excludes extracted game maps, numeric game icons,
generated catalogs and markers, parse caches, user state, save files, and fetched
third-party route descriptions (`data/tips.json`). Users generate game resources
locally from their own installed copy. Game content remains the property of its
respective rights holders.
