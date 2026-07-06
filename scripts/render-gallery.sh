#!/bin/sh
# Regenerate the README gallery (docs/gallery/*.svg).
# 12 parts spanning bricks/round/slopes/SNOT/technic, varied angles, colors,
# and render params — including one translucent tile (--opacity < 1 disables
# hidden-geometry culling). Backgrounds are transparent (the default).
set -e
cd "$(dirname "$0")/.."
BI=".venv/bin/python -m brick_icons.cli"
OUT="docs/gallery"
G="--format svg --shading outline --shade-style flat3 --out $OUT"

$BI 3001  $G --part-color 0xc91a09                            # 2x4 brick, red
$BI 3941  $G --part-color 0x0055bf --opacity 0.55             # 2x2 round, trans-blue
$BI 3960  $G --part-color 0x9ba19d                            # dish 4x4 inverted
$BI 4589  $G --part-color 0xf2cd37                            # cone 1x1, yellow
$BI 3040b $G --part-color 0x237841 --angle 30,20              # slope 45, green
$BI 4070  $G --part-color 0xe4cd9e                            # headlight brick, tan
$BI 3649  $G --part-color 0xa0a5a9 --angle 55,15              # gear 40t
$BI 50950 $G --part-color 0xfe8a18                            # curved slope, orange
$BI 99781 $G --part-color 0x36aebf                            # bracket, azure
$BI 32062 $G --part-color 0x582a12 --angle 25,65 \
          --line-width 3 --silhouette-width 3                 # axle 2, heavy line
$BI 87087 $G --part-color 0xffffff                            # 1x1 side stud, white
$BI 54200 $G --part-color 0xd05098 --angle 35,55              # cheese slope, pink
