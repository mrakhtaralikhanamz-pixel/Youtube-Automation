# Space & Science Mysteries — Automated Shorts Pipeline

Fully automated pipeline that turns a written script into a finished, uploaded YouTube Short — using **only free tools**:

- **Voice**: `edge-tts` (Microsoft Edge's cloud TTS, free, no API key)
- **Footage**: Pexels + Pixabay (free API keys) and NASA Image & Video Library (free, no key — public domain)
- **Assembly/captions**: `ffmpeg` (free, open source)
- **Thumbnail**: Pillow (free, open source)
- **Upload**: YouTube Data API v3 (free, 10,000 quota units/day — an upload costs 100, so ~100 uploads/day headroom)
- **Scheduling**: GitHub Actions cron (free tier — GitHub-hosted runners come with ffmpeg preinstalled)

**Scripts are the one part left to a human/Claude.** Writing genuinely original commentary per video (not a generic template) is both the highest-leverage part of quality and a hard requirement of YouTube's "inauthentic content" monetization policy — so scripts are written in batches (by Claude, in chat, for free) and dropped into `content_queue/` as JSON files. Everything downstream is 100% automated.

## Why this architecture, specifically

This was designed and partially tested from a Claude Cowork cloud sandbox. That sandbox's own outbound network is locked to a small allowlist (only `anthropic.com` and `github.com` are reachable — `pypi.org`, `pexels.com`, `nasa.gov` etc. all returned `403 host_not_allowed` when tested directly), so the sandbox itself can't run the live TTS/footage/upload calls. GitHub Actions runners are a separate, unrestricted environment with full internet and a generous free tier, so the pipeline is built to run *there* instead — completely free, on a schedule, with no ongoing involvement from the Cowork session at all once it's deployed.

## One-time setup (all free, ~20 minutes total)

1. **Create a GitHub account** (if you don't have one) and a **private** repo. Push this folder to it.
2. **Pexels API key**: sign up free at pexels.com/api → copy your key.
3. **Pixabay API key** (optional, extra footage variety): sign up free at pixabay.com/service/about/api.
4. **YouTube Data API v3 access** (free):
   - Go to console.cloud.google.com → create a project (free).
   - Enable "YouTube Data API v3" under APIs & Services.
   - Create OAuth 2.0 credentials, type **Desktop app**. Download the client ID + secret.
   - Run `python scripts/get_youtube_refresh_token.py` **on your own computer** (needs a real browser to log into your Google/YouTube account once) to get a refresh token.
5. In your GitHub repo → Settings → Secrets and variables → Actions, add these repo secrets:
   - `PEXELS_API_KEY`
   - `PIXABAY_API_KEY` (optional)
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`
6. Enable GitHub Actions on the repo. The workflow in `.github/workflows/daily_upload.yml` runs on a daily cron and also supports manual trigger ("Run workflow" button) for testing.

## Keeping the content queue full

Ask Claude (me) to batch-write, say, 14 scripts at a time in this niche and save them as `content_queue/0001.json`, `0002.json`, etc. (see the 5 starter scripts already included). Each run of the pipeline consumes the oldest file in `content_queue/` and moves it to `content_done/` when finished, so it never repeats a video and never runs dry unannounced — just keep restocking the queue every couple of weeks.

## Human-in-the-loop safety valve

Uploads default to `privacyStatus: "private"` (`config.py`). This is intentional: a 10-second glance at each video before flipping it to Public catches TTS mispronunciations, mismatched footage, or anything that reads as too generic/templated — which protects both quality and monetization eligibility. Flip `DEFAULT_PRIVACY` to `"public"` once you trust the pipeline's output.

## File map

```
content_queue/        # scripts waiting to be produced (JSON) — restocked by Claude/you
content_done/          # scripts already produced, for history/audit
pipeline/tts.py        # script text -> narration.mp3 + captions.srt (edge-tts)
pipeline/footage.py    # keyword tags -> downloaded b-roll clips (Pexels/Pixabay/NASA)
pipeline/assemble.py   # clips + narration + captions -> final vertical .mp4 (ffmpeg)
pipeline/thumbnail.py  # final .mp4 -> thumbnail .jpg (Pillow)
pipeline/upload.py     # final .mp4 + thumbnail -> YouTube upload (Data API v3)
main.py                # orchestrates the above end-to-end for one queued script
scripts/get_youtube_refresh_token.py  # one-time OAuth helper, run locally
.github/workflows/daily_upload.yml    # free scheduled automation
```
