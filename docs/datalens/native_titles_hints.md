# Native Dashboard Titles And Hints

This project-authored policy is enforced by dashboard payload validation and
saved readback checks.

- Standard for non-control widgets: native dashboard `title`, native `hint`, `hideTitle=false`, `enableHint=true` when the DataLens item supports hints.
- Advanced Editor bodies render data content and empty states, not top-level title rows, inline question-mark hint icons or dashboard-level tooltip renderers.
- Selector controls may keep control-local hints where DataLens requires that metadata in `controls.js`.
- Empty states must still rely on the native dashboard title/hint for widget meaning.
- The generated object-relation report records each non-control widget's
  `native_metadata` so title and hint preservation is testable before live save.
- Multi-tab widgets must keep `hideTitle=false`; otherwise DataLens can hide the header area and inner tab strip.
