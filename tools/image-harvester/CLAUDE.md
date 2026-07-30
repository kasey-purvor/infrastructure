# image-harvester

## What & Why
> Harvest all images from an Instagram profile via the ScrapFly web-scraping API, saved to disk
> with a metadata manifest. The crawl/enumeration goes through ScrapFly (anti-bot); the image
> binaries download directly from Instagram's CDN (free). Scope is **Instagram only** — a deliberate
> v1 decision (a modularity audit showed the backend was Instagram-shaped; rather than genericise,
> we own that and build a focused tool).

## Current Status
- **State**: Working — full `madtev` profile harvested (4,032 images, 0 failures, 2013→2026, 906 MB)
- **Last touched**: 2026-06-04
- **Blockers**: none

## Next Actions
- [x] Implement all modules + tests (TDD) — 54 tests passing
- [x] Live run verified end-to-end (enumeration, downloads, validation, resume, dry-run)
- [x] `--all` pagination working via the feed endpoint (logged-out, full profile)
- [x] Full profile harvested (4,032 imgs, 0 failures); global-pool downloads + `--page-delay` pacing added
- [ ] (optional) Fix the partial-resume manifest gap (see Gotchas) — observed ~2 dup/partial lines after the kill+resume
- [ ] (optional) Sort the manifest `images[]` by `index` (currently completion order)
- [ ] (optional) Decouple enumeration into a producer thread so a slow feed page doesn't idle the download workers

### Confirmed against reality (live)
- **ScrapFly request/response shape** — `fetch_api_json` (`asp=true`, `render_js=false`, `format=json`,
  custom headers as `headers[Name]=value`) and `envelope["result"]["content"]` parsing both work live.
- **Feed pagination** — `i.instagram.com/api/v1/feed/user/{id}/` with `next_max_id` paginates the whole
  profile logged-out. (The old `www.instagram.com/graphql/query` `doc_id` path returned HTTP 400 and was removed.)

## Architecture

Pipeline: **enumerate (ScrapFly) → for each image: skip-if-on-disk, else download (direct) + validate → persist + manifest.**

Layout (`src/image_harvester/`):

| Module | Interface | Responsibility |
|--------|-----------|----------------|
| `cli.py` | `main(argv=None) -> int` | Thin argparse layer → builds objects → calls `harvest()`. |
| `config.py` | `resolve_api_key(cli_value) -> str` | `SCRAPFLY_KEY` env, `--api-key` override; raise a clear error if missing. |
| `models.py` | dataclasses | `Post`, `MediaItem`, `DownloadResult`, `PlannedPath`, `HarvestSummary`. |
| `scrapfly_client.py` | `ScrapflyClient(api_key).fetch_api_json(url, headers) -> dict` | The single ScrapFly seam. Hides api.scrapfly.io, `asp=true`, `render_js=false`, `country`, envelope parsing, error mapping. Intent method, not a knob bag. |
| `instagram.py` | `InstagramSource(client).iter_posts(username, fetch_all) -> Iterator[Post]` | **DEEP.** Resolves username→id via `web_profile_info`, then pages the private feed API (`feed/user/{id}/`, follow `next_max_id`) — paginates logged-out, returns full-res (~1440px) candidates. Flattens carousels, drops video children/posts (`Post.images` is images-only). Fail-loud on non-`ok` shape. Accepts username or URL. |
| `downloader.py` | `Downloader().fetch(url) -> DownloadResult` | **DEEP.** Direct `httpx` GET to the CDN. Validates: status 200 + `Content-Type: image/*` + image magic bytes + `Content-Length` (if present). Retry w/ exponential backoff + jitter. `oe`-expiry pre-check (skip doomed URLs). Returns validated bytes + content_type, or typed failure. (ScrapFly download-fallback is a deferred seam — not built.) |
| `output_store.py` | `OutputStore(base_dir, username)` → `target_for(post, index) -> PlannedPath`, `exists(planned) -> bool`, `commit(planned, content, content_type) -> Path` | **DEEP.** Owns the filename convention, extension derivation (from content-type), skip-by-presence, atomic write (temp + rename). |
| `manifest.py` | `Manifest(path).record(post, image_results) -> None` | Owns the manifest schema. Appends one JSON object per post. |
| `harvest.py` | `harvest(*, source, store, manifest, downloader, target, limit, all_, concurrency, dry_run, confirm) -> HarvestSummary` | Orchestrator: stream posts (bounded by `limit` unless `all_`), `ThreadPoolExecutor` download fan-out, skip-by-presence, dry-run, `--all` confirm. |

### Filename convention
`{taken_at:%Y-%m-%d}_{shortcode}_{index:02d}.{ext}` — flat under `output/<username>/`. Index is the
zero-padded carousel position (`01` for single images). `ext` from response `Content-Type`
(`image/jpeg`→`jpg`, `image/png`→`png`, `image/webp`→`webp`).

### Manifest schema (`manifest.jsonl`, one object per post)
```json
{
  "shortcode": "CxQwZ0gOIFp",
  "post_url": "https://www.instagram.com/p/CxQwZ0gOIFp/",
  "taken_at": "2023-09-16T...Z",
  "caption": "...", "like_count": 16200, "comment_count": 279, "owner": "madtev",
  "images": [
    {"index": 1, "url": "https://...cdninstagram.com/...jpg", "local_path": "2023-09-16_CxQwZ0gOIFp_01.jpg",
     "width": 1440, "height": 1711, "bytes": 184600, "sha256": "..."}
  ],
  "skipped_videos": 1, "fetched_at": "2026-06-03T...Z", "source": "ig:feed"
}
```

### Instagram enumeration (verified working live, logged-out)
- **Resolve id**: `GET i.instagram.com/api/v1/users/web_profile_info/?username=<u>` with
  `x-ig-app-id: 936619743392459`, via ScrapFly (`asp=true`, `render_js=false`, `country=us`,
  `format=json`) → `data.user.id`.
- **Enumerate + paginate**: `GET i.instagram.com/api/v1/feed/user/{id}/?count=12[&max_id=<next_max_id>]`
  (same headers/ScrapFly opts). Returns `items[]` + `more_available` + `next_max_id`. Follow
  `next_max_id` while `more_available` is true (default run takes only the first page; `--all` paginates).
  `count` is clamped to 12 logged-out (so the full profile ≈ N/12 feed pages = that many ScrapFly credits).
  **Fail loud** (persist what we got, exit non-zero, actionable message) on any non-`ok` status.
- **Item shape**: `code` (shortcode), `pk`, `taken_at` (unix), `like_count`, `caption.text`,
  `user.username`, `media_type` (1=image, 2=video, 8=carousel). Images via
  `image_versions2.candidates[0]` (largest ≈1440px); carousel children under `carousel_media[]` with
  per-child `media_type`.
- **Images only**: skip `media_type==2` posts and video carousel children; count as `skipped_videos`.
- The GraphQL `doc_id` pagination path was tried and **removed** — it returned HTTP 400 logged-out.
  The feed endpoint is the single media source.

## Development
```bash
cd tools/image-harvester
uv venv && uv pip install -e ".[dev]"   # or: uv run --extra dev pytest
uv run --extra dev pytest
export SCRAPFLY_KEY=scp-live-xxxx        # only for a live run
image-harvester madtev --dry-run
```

## Decisions & Gotchas
- **ScrapFly for enumeration, direct download for binaries.** IG's *API/HTML* layer is anti-bot
  (needs ScrapFly ASP); its *CDN* (`cdninstagram.com`) serves self-signed URLs to any client, so
  image bytes download free with a plain GET. Verified: `200 image/jpeg 1440x1711`, no auth.
- **CDN URLs expire fast** (`oe` param ≈ days). So we never persist+reuse URLs: every run
  re-enumerates (fresh URLs) and skips by file presence. `oe` is a hex Unix timestamp — pre-check it.
- **One post fetch = all carousel images.** The `?img_index=N` query param is client-side only;
  never fetch per-index.
- **Resolution**: the feed API returns `image_versions2.candidates[0]` ≈ **1440px** (largest), used
  directly — no extra fetch. (Supersedes the earlier "use 1080 `display_url`" call, which the feed
  endpoint made unnecessary while also unlocking logged-out pagination.)
- **Logged-out only.** No IG login (no account ban risk). Private profiles are out of reach.
- **TDD**, network mocked (`respx` for httpx; `ScrapflyClient` faked). Fixture
  `tests/fixtures/feed_user_madtev.json` is a trimmed **real** feed capture: a 4-image carousel, an
  8-child carousel with **1 video child** (→ 7 images), and a video-only post (→ 0 images).
- **Deferred seam**: keep `Downloader` behind a small interface so a ScrapFly download-fallback can
  be added later without touching callers.
- **Enumeration is the throttle point, not downloads.** Image downloads (`--concurrency`, direct to the
  CDN) aren't rate-limited; the *sequential ScrapFly feed-page calls* are. On a deep `--all` run IG can
  transiently throttle a page (it stalls ~minutes, then usually recovers — a full madtev run saw one
  such stall and still finished with 0 failures). Mitigation: **`--page-delay`** (default 2.0s + jitter)
  spaces out feed pages. Gotcha: the orchestrator blocks the main thread on each page, so a slow page
  idles the download workers — fix later by running enumeration in a producer thread feeding a queue.
- **Downloads: global pool.** `harvest` uses ONE `ThreadPoolExecutor` with bounded back-pressure across
  all posts (not a pool per post), so single/few-image posts parallelize. This took the full run from a
  ~4h pace to ~12 min of active work at `--concurrency 16`.
- **Known limitation — partial-resume manifest gap**: `harvest` calls `manifest.record(post, results)`
  with only the images *downloaded this run*. A post that straddles an interruption (some images saved
  in run 1, the rest in run 2) gets a manifest line in run 2 listing only the run-2 images; the run-1
  images are on disk but missing from that line. Clean single runs are complete. Fix later by having
  the manifest include already-on-disk images for the post (re-hash from disk or carry their metadata).
- **Minor**: `403` is currently treated as retriable (3 backoff retries before failing); `httpx.Client`
  instances aren't explicitly closed (fine for a one-shot CLI); `DownloadResult.local_path` is set as a
  dynamic attribute by `harvest`. None affect correctness for v1.

## Ideas & Future
- ScrapFly download-fallback on CDN 403/throttle.
- Resolution-max mode (per-post detail fetch).
- Other media (reel covers, video files).
- (Explicitly out of v1: multi-source genericity — see the modularity audit; it was a deliberate no.)
