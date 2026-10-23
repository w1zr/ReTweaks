# RETWEAKS crosshair gallery

`gallery.json` is the list the **Crosshair → Gallery** tab in RETWEAKS downloads from
`https://raw.githubusercontent.com/w1zr/ReTweaks/main/crosshairs/gallery.json`.
RETWEAKS checks every entry before showing it; entries that don't pass are skipped.

## Share your crosshair

1. In RETWEAKS open **Crosshair → Share** and press **Copy code** (codes start with `RTX1-`).
2. Open a pull request on this repository that adds one entry to the `crosshairs` list in `gallery.json`:

```json
{ "name": "Your crosshair name", "author": "Your name or tag", "code": "RTX1-..." }
```

- `name`: up to 40 characters.
- `author`: up to 40 characters (optional).
- `code`: the share code exactly as RETWEAKS copied it.

Keep it friendly: no offensive names. Image crosshairs work too, but the image must be a PNG of at most
128 × 128 pixels (RETWEAKS shrinks it for you when you pick it).

## Format

```json
{
  "format": "retweaks-crosshair-gallery",
  "version": 1,
  "crosshairs": [ { "name": "...", "author": "...", "code": "RTX1-..." } ]
}
```

The built-in RETWEAKS designs are listed first. RETWEAKS shows at most 500 entries.
