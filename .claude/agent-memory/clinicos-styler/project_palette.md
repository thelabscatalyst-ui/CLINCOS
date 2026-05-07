---
name: Warm Parchment Palette
description: ClinicOS actual color palette is warm sepia/brown, not the neutral grey described in agent defaults
type: project
---

ClinicOS uses a **warm parchment/sepia** palette, not the default grey system described in the agent prompt.

Key corrections:
- Dark bg: `#1a1612` (warm dark brown), not `#080808`
- Cards: `#211d18`, not `#111111`
- Light bg: `#ede7de` (warm cream), not `#f4f4f5`
- Borders are warm tan (`#3d3630` dark, `#c2a98a` light), not neutral grey
- The navbar and dock are **always** `#2e1e0c` (dark brown) — no light theme override
- `--success` is `#c8b49a` (warm beige), not green
- Badge palette is unified warm beige (`rgba(200,175,145,0.14)` bg, `#c4b09a` text) across ALL badge types
- Pagination/active-chip accent is `#6b4a28` (deep brown), not blue/grey

**Why:** The project evolved from a neutral design to a warm Indian clinic aesthetic (parchment paper feel).

**How to apply:** Always use CSS custom properties from `:root` / `html.light` — never hard-code neutral greys from the agent system prompt defaults.
