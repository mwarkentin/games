#!/bin/sh
# Downloads the card's fonts (SIL Open Font License 1.1) as TTF from Google
# Fonts, which serves TTF to an old user agent. Run from prototypes/share-card.
set -eu
mkdir -p fonts
css=$(curl -fsS -A 'Mozilla/4.0' 'https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@800&family=Martian+Mono:wght@400;500&family=Schibsted+Grotesk:wght@500;600')
set -- BigShouldersDisplay-800 MartianMono-400 MartianMono-500 SchibstedGrotesk-500 SchibstedGrotesk-600
for url in $(printf '%s\n' "$css" | grep -o 'https://[^)]*\.ttf'); do
  curl -fsS -o "fonts/$1.ttf" "$url"
  shift
done
ls -l fonts
