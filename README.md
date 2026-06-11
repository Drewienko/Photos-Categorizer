# Photos Categorizer

AI-powered desktop app for tagging and browsing photo collections.
University project, Systemy Multimedialne, 3ID12A.

## Features

- Recursive folder import with thumbnail generation
- AI tagging via **CLIP** (offline, no API key needed) or **Google Vision** (cloud)
- Gallery with sidebar tag/filter navigation and live search
- Detail view with filmstrip, confidence bars, and per-photo re-analysis
- Manual tag add/remove
- CSV export of all tags
- Persistent SQLite storage, survives restarts

## Download

Pre-built binaries for Linux and Windows are on the [Releases](../../releases/latest) page.
**ffmpeg is bundled**, no extra installs needed.

> First launch downloads the CLIP model (~350 MB, one-time). Subsequent launches are instant.

## Run from source

Requires [uv](https://docs.astral.sh/uv/) and **ffmpeg** on PATH.

```bash
git clone https://github.com/Drewienko/Photos-Categorizer.git
cd Photos-Categorizer
uv run photos-categorizer
```

## Google Vision setup

1. Create a service account in Google Cloud Console with the **Cloud Vision API** enabled
2. Download the JSON key file
3. In the app: Settings, set the credentials path, Save

## Stack

| Package | Use |
|---|---|
| PySide6 6.11 | Qt6 desktop GUI |
| open-clip-torch 3.3 | Local CLIP ViT-B/32 tagging |
| google-cloud-vision 3.14 | Cloud tagging |
| ffmpeg-python 0.2 | Thumbnails, dimensions, format conversion |
| SQLite (stdlib) | Metadata + thumbnail cache |
