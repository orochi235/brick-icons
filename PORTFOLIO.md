---
title: brick-icons
tagline: LEGO parts rendered as icons for bin labels
tags: [graphics, python, cli]
featured: true
order: 30
media: { kind: image, src: docs/gallery/3001.svg, span: 1, aspect: "3/2" }
---

Renders LDraw parts through LDView into 1-bit dithered, grayscale, or color PNGs and potrace SVGs,
sized for the bins they end up labelling. Three shading modes — normal, cel, and outline — with
`--line-width` and `--silhouette-width` controlling how interior edges read once the icon is small
enough to print on tape.

The image core is pure: LDView is a thin wrapper at the edge, so everything downstream of the render
is testable without a GUI toolchain under Rosetta.
