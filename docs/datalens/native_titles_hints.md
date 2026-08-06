# Dashboard Title And Hint Ownership

This project-authored policy is enforced by bundle, dashboard payload, final
attestation, and saved/published readback validation. Title ownership is based
on widget role; a native title is not a universal default.

| `title_mode` | Owner | Required metadata |
| --- | --- | --- |
| `embedded_title` | Advanced Editor runtime renders the exact `display_title` and hint | `hideTitle=true`, `enableHint=false` |
| `content_label` | KPI runtime renders its label inside the card | `hideTitle=true`, `enableHint=false` |
| `tab_only` | Dashboard tab names the content | `hideTitle=true`, `enableHint=false` |
| `native_title` | Wizard or native table header | `hideTitle=false`; a non-empty native hint uses `enableHint=true` |
| `tab_strip` | Native header owns an inner multi-tab switcher | `hideTitle=false` |

Native and runtime title or hint ownership are mutually exclusive. The server
rejects duplicated headers, missing role-owned labels, and technical object
names used in place of the accepted `display_title`. Empty states use the same
role owner as the populated state.

Selector controls may keep control-local hints where DataLens requires that
metadata in `controls.js`. The generated relation report records both
`title_contract` and derived `native_metadata`, so ownership remains traceable
before save and after readback.
