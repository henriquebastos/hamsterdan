#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$root/output/checkpoints/pr47"
seconds=(3.5 7 17 26 34 43 53 63 74 86 99 111 123 135 149 163 175)

rm -rf "$output"
mkdir -p "$output"
cd "$root"

bun run check
for second in "${seconds[@]}"; do
  frame="$(awk -v seconds="$second" 'BEGIN { printf "%.0f", seconds * 30 }')"
  bunx remotion still src/index.ts PR47Hero "$output/${frame}.png" \
    --frame="$frame" --log=error
done

if command -v montage >/dev/null 2>&1; then
  montage "$output"/*.png -thumbnail 480x270 -tile 4x -geometry +4+4 \
    -background '#080b10' "$output/contact-sheet.jpg"
fi

printf '\nRendered checkpoints to %s\n' "$output"
