# Self-hosted fonts

Fonts are self-hosted so the app works offline and makes no third-party requests.

Download these and place the `.woff2` files here:

- `space-grotesk-600.woff2` — Space Grotesk 600 (https://fonts.google.com/specimen/Space+Grotesk)
- `ibm-plex-mono-500.woff2` — IBM Plex Mono 500 (https://fonts.google.com/specimen/IBM+Plex+Mono)

Body text deliberately uses the device's own system font, so no download is needed for it.

If a file is missing the app still works — `@font-face` falls back to the system stack.
