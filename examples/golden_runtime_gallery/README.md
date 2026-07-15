# Golden Runtime Gallery

This directory contains generated static contracts for the DataLens route-family gallery.
The source of truth is `config/golden_runtime_gallery_inventory.json`; regenerate with:

```bash
python3 scripts/build_golden_runtime_gallery.py --write
```

Live saved, published, and browser proof are intentionally marked unavailable unless a future run supplies
a disposable workbook, an implementation request, and browser evidence.

- Supported families: `39`
- Families by route: `{"editor_advanced": 9, "editor_js_control": 6, "editor_markdown": 6, "ql_explicit": 1, "wizard_native": 17}`
