# Widened public-media search

Follow-up to [merged PR #15](https://github.com/glitch003/glorb/pull/15), research snapshot September 9, 2026 Pacific. **Zero confirmed Glorb 2026 sightings; no plausible lookalike retained.** This packages the researchers' recorded visual inspections, not a new independent visual review or evidence of exhaustive absence. The [prior notebook](../README.md) and its totals remain historical; do not add source or query totals across snapshots without deduplicating.

## Computed coverage

- 16 lane source records become **15 exact-URL source records**. Jurvetson appears in both Flickr and social; retain the successful Flickr inspection plus the blocked social recheck, counting the photograph once.
- **37 distinct query strings:** 10 Flickr/photographer, 19 video, 8 social. Of these, 34 returned and 3 failed. The query manifest preserves failures, empty returns, original timestamps and URL occurrences. Flickr timestamps lack an offset in the original log; none is invented.
- **214 result URL occurrences, 191 exact unique URLs.** These are discovery returns, not inspected media or canonicalized pages.
- **1,211 still-image screenings:** 1,178 distinct BMwebcast Flickr photo IDs (also 1,178 distinct downloaded-thumbnail hashes), 32 unique SFGATE article image URLs, one Jurvetson photo. No cross-publisher perceptual-image deduplication is claimed.
- **130 sampled frames across four clips:** EDMHouseNetwork 16, The Vich's Fam 72, Borys Grabar 32, Burning Man TikTok 10. Not continuous playback, not 130 sightings, and not all established as 2026 footage.

### Photographs

[BMwebcast album](https://flickr.com/photos/flight0001/sets/72177720335406158/) — uploader goflight001 / flight0001, underlying watermark BMwebcast.online. The snapshot reports 1,178 photos and zero videos, unlike the prior ledger's 974 photos plus one video; the cause of that change is unknown. Initial HTML pagination exposed only 300 thumbnails. Public album enumeration recovered the other 878; **do not add the initial 300 again**. All 1,178 were screened in 30 contact sheets at approximately 160px-wide displayed tiles. Three lookalikes were enlarged and rejected; a fourth enlargement was downloaded but not reviewed or counted. Full-resolution backgrounds and original webcast footage remain unreviewed. Taken metadata spans August 30–September 7, 2026, but timestamps and filenames date screenshots, not independently verified underlying footage.

[Jane Hu / SFGATE gallery](https://www.sfgate.com/travel/burningman/article/photos-burning-man-2026-22414672.php), article by Dan Gentile — 32 event-captioned images screened in three contact sheets. Canonical host challenged access; the [same-publisher public version](https://cmf.s.sfgate.com/travel/burningman/article/photos-burning-man-2026-22414672.php) supplied the article. September 8 publication and individual captions support 2026. The curtain-like LED cube is captioned Apotheneum by Anthony Feldman and Mark Slee, not Glorb.

[Burning Man Sunrise](https://www.flickr.com/photos/jurvetson/55513405597/) — Steve Jurvetson uploader; caption credits a UK friend Charlie. One image inspected; no match. Primary page records taken September 4 and uploaded September 7, 2026.

[Scott London index](https://www.scottlondon.com/photography/burningman) and [Jamen Percy albums](https://www.flickr.com/photos/jamenpercy/albums/) yielded no current 2026 gallery in the retrieved indexes. Percy’s retrieved model started with 2025. Index discovery is not photo screening; footer years are not capture-year evidence.

### Video samples

| Public source / credit | Source-relative PTS, inclusive | Interval | Frames | Year limit |
|---|---|---|---|---|
| [EDMHouseNetwork](https://www.facebook.com/EDMHouseNetwork/videos/1647876596914615/) | 0–15 s | 1 s | 16 | September 6 upload, generic “Every year” caption; unverified capture year |
| [The Vich’s Fam](https://www.facebook.com/thevichfam/videos/1048034064882387/) | 0–355 s | 5 s | 72 | September 3 upload / “Day 3” suggestive, not independent dating |
| [Borys Grabar](https://www.instagram.com/reel/DdA0AwduhAx/) | 0–31 s | 1 s | 32 | Caption has no year; indexed September 7 vs downloader September 8 |
| [Burning Man](https://www.tiktok.com/@burningman/video/7673671671865232658) | 0–18 s | 2 s | 10 | Excluded: August 14 pre-event upload despite 2026 hashtag |

Intervals are discrete frame samples. Tiny objects and gaps remain unresolved. TikTok's last two samples are endcards; decoded duration is 19.611 seconds, unlike the 15-second metadata duration. Only the definitive actual-PTS ledger is included, not superseded exploratory samples. These four clips are separate from the prior RGJ sampling.

## Durable next-search queue

1. Prioritize original BMwebcast footage and camera/time anchors from [photo IDs and screenshot dates](flickr-photos.json), with closer inspection of moving art cars rather than repeating thumbnails. Match the hanging rainbow LED bristles and rectangular platform against the [owner reference](../../gallery-2026/glorb-2026-3525.jpg); a cropped-out broom handle alone is not an exclusion.
2. [Jamen Percy / @jamenpercy.burn reel](https://www.instagram.com/reel/DXz7XfSznnL/): new photographer lead, not a sighting. Signup/login modal obscured footage; stopped without login or bypass. Caption's “wild 2026 so far” dates commentary, not capture. Extractor also returned 403.
3. [Radio FG](https://www.facebook.com/radiofg/videos/2163539317838208/), [Burning Man Project](https://www.facebook.com/burningman/videos/1385434320355410/), [ABC News](https://www.facebook.com/ABCNews/videos/1604106251408913/): discovery only. Download batch was held for execution approval and **did not run**. No metadata or inspection success is inferred; approval-pending records are historical execution state, not completed downloads.
4. [YouTube short](https://www.youtube.com/shorts/WNQqpNOsDOY) and [Breeze Offroad](https://www.youtube.com/watch?v=uMJzVmSMNCI): unavailable/sign-in or bot challenge; no footage inspected. Prior notebook's other unscreened leads remain open.
5. Broader multilingual/social batch was approval-gated and **did not execute**. The initial logged batch includes failed searches; empty Reddit returns do not prove no posts exist. No exhaustive platform or photographer coverage is claimed.

## Audit and publication scope

[Sources and statuses](sources.json), [query manifest](queries.json), [computed counts](summary.json), [Flickr IDs](flickr-photos.json), [SFGATE image pointers](sfgate-images.json), [definitive frame timestamps](video-frames.json), [lookalike decisions](lookalikes.json).

Public links and creator credits are provenance, not permission to republish. No third-party media, contact sheets, raw HTML/search snippets, account metadata, credentials or host paths are included. Source URLs are preserved, not rewritten into guessed canonical forms; exact-URL deduplication does not imply distinct visual content. Local media and raw research evidence remain outside the repository. Public link syntax is checked, but no claim is made that login-blocked or dynamic sources are currently playable.

Run `python docs/media-hunt-2026/widened/verify.py` to recompute counts, validate coverage, source references, link syntax, local Markdown targets and publication scope. The prior notebook and both gallery verifiers remain applicable.
