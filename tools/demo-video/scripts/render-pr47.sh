#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$root/output/hamsterdan-pr47-hero.mp4"
silent_output="$root/output/.hamsterdan-pr47-hero-silent.mp4"

mkdir -p "$root/output"
cd "$root"

bun run check
bunx remotion render src/index.ts PR47Hero "$output" \
  --codec=h264 --crf=22 --log=error

# Remotion may add a nominal silent AAC stream. The approved deliverable has no
# audio stream so media QA does not mistake that stream for damaged audio.
ffmpeg -loglevel error -y -i "$output" -map 0:v:0 -c:v copy "$silent_output"
mv "$silent_output" "$output"

ffprobe -v error \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate \
  -show_entries format=duration,size \
  -of default=nw=1 "$output"

printf '\nRendered %s\n' "$output"
