# Public Glorb media search notebook

Research snapshot: September 9, 2026 PDT (query timestamps are September 10 UTC).
**Zero visually confirmed public Glorb 2026 media matches.** This is a discovery
and screening notebook, not proof of absence and not a gallery of sightings.
The [owner-supplied photo collection](../gallery-2026/) is separate evidence;
its collection label does not independently establish event attendance or capture date.

Follow-up: [widened photographer, video and social search](widened/README.md).
The original snapshot and totals below are preserved; the follow-up is not a cumulative replacement.

## Scope and audit

The completed social and video research reports are consolidated here as a
sanitized ledger rather than copied with raw search responses or local paths.
Search covered Glorb/crew/Beignet names, broom/mop/bristles/LED-tube aliases,
Instagram, Facebook, TikTok, Reddit, Flickr, YouTube, Vimeo, photographer galleries,
drones, night footage, walkthroughs and art-car roundups. Exact-name operators
were noisy; empty results do not establish absence.

- **65 distinct query strings:** 44 social and 21 video queries.
- **415 result URL occurrences; 357 exact unique result URLs.** These are search
  returns, not screened media or canonicalized website counts. URLs are preserved
  verbatim; only identical URLs within each query are deduplicated.
- **38 unique source records**, consolidated from 15 social and 24 video records.
  The shared Forbes preview appears once, with the more specific video status
  `preview_not_sighting` rather than the social lane's broad `candidate` status.
- The video research report records **108 sampled frames across four RGJ clips**
  at approximately two-second intervals, and **142 gallery image entries / 116
  unique photos** after Gannett cross-domain/path deduplication. These were
  contact-sheet inspections, not exhaustive full-resolution or continuous-playback
  reviews. No Glorb was recognized in those samples. The 116 figure is the
  research report's deduplicated inspection count, not a new independent recount.
  Social-lane images were not visually inspected.

Files: [source ledger](sources.json), [computed counts](summary.json),
[social queries](social-queries.json), [video queries](video-queries.json).
Query logs contain only query strings, retrieval timestamps and result URLs.
Ledger text records research findings, not a fresh verification of every publisher.
No third-party images, video, contact sheets, raw transcripts, directory contact
information, private media paths or credentials are published here.

## Status vocabulary and exact counts

| Status | Count | Meaning |
| --- | ---: | --- |
| `confirmed_named_mention` | 1 | Retrieved directory text names Glorb; **not photo proof**. |
| `candidate` | 7 | Broad social/image lead; not a positive visual identification. |
| `uninspected_lead` | 6 | Potential video/gallery source; footage/images not inspected. |
| `year_unverified` | 5 | Capture year lacks adequate evidence. |
| `sampled_no_match` | 4 | No recognition in sampled video frames; gaps/backgrounds remain. |
| `thumbnails_no_match` | 4 | No recognition in gallery contact sheets; not a full-resolution exclusion. |
| `preview_not_sighting` | 1 | Preview/roundup is not evidence of a current-event appearance. |
| `excluded` | 6 | Unrelated name collision or retrospective lacking current capture evidence. |
| `excluded_wrong_year` | 2 | Older articles/media, outside the requested year. |
| `excluded_synthetic` | 1 | Indexed title explicitly labels AI-generated content. |
| `excluded_pre_event` | 1 | Documentary published before the event according to the research report. |

No record has confirmed 2026 Glorb media, and no Glorb appearance timecode is known.
Exclusion applies to the recorded source/evidence, not all work by that creator.

## Forward screening queue

1. **Large public webcast album:** [Burning Man BMwebcast 2026](https://flickr.com/photos/flight0001/sets/72177720335406158/).
   Extraction reported 974 photos and one video; these remain unscreened. Inspect
   batches against the hanging-tube broom reference, recording exact photo URLs,
   not just the album. Check capture date and underlying BMwebcast credit per image.
2. **Night-life video:** [Breeze Offroad](https://www.youtube.com/watch?v=uMJzVmSMNCI).
   Title/creator retrieved through oEmbed, **footage not verified**. Screen in
   playback when publicly accessible and record ranges actually reviewed.
3. **Other YouTube leads:** [Truck House Life](https://www.youtube.com/watch?v=IsIEDo2EibE)
   and [moontaurus](https://www.youtube.com/watch?v=4geGfPlzOGY). oEmbed metadata is
   not visual evidence. The Truck House Life search transcript concerns a
   kayak/OneWheel car, not an identified Glorb. Also check
   [Todd Kortte's night tour](https://www.youtube.com/watch?v=dXAk98eGwd4), whose
   capture year remains unverified.
4. **Named directory lead:** [GET LOST BRC public data](https://hyperlo.ca/data/events.json),
   record `mv-a6BVI000000MpWv2AK`, names “Glorb the beignet max pro 2 too” and
   The Glorb Crew. Its description concerns a holographic/rainbow cube, not the
   broom. The linked image is uninspected. A `last_checked` date is not an image
   capture date; synthetic roaming coordinates are not a real car location.
5. **Remaining galleries/social sources:** use `candidate`, `uninspected_lead`
   and `year_unverified` records in the ledger, including SFGATE, the Business
   Insider gallery and dated Flickr sunrise photo. Follow secondary pointers to
   their original posts before making attribution or year claims. Revisit sampled
   sources at full resolution if a background object merits closer inspection.

Do not conflate [Scott London's 2010 Glorb by Brant Moore](https://www.scottlondon.com/photo/burningman2010/088.html)
with this car. GLORB the lamp, the musician, unrelated performances and synthetic
videos are also excluded. Publication/upload year, a 2026 title, footer, or search
snippet alone does not prove capture year.

## Access limits at research time

Social browser launch and image inspection failed with local disk-space errors;
the video researcher also reported a browser startup error (code 101). These are
run-specific blockers, not permanent inability to inspect public media.
YouTube's attempted Truck House Life retrieval returned a sign-in/bot check;
Vimeo returned a human check. SFGATE served a challenge page despite HTTP 200.
TikTok extraction returned a script shell; an Instagram reel timed out.
Some RGJ requests returned 403, but ordinary public page requests exposed MP4
links and four clips were successfully sampled. Matt Mullenweg's gallery was
recovered after extraction timeouts and its twelve images entered the sample.
No paid APIs, account access, contact/outreach or access-control bypass was used.
Retry normal public access when available; do not infer unseen content from a wall.

## Contribute a sighting

Submit a source link in an issue or PR, with:

- Original publisher/uploader and photographer credit if known; distinguish reposts.
- Exact photo permalink or video timecode/range, plus the portion actually reviewed.
- Capture-year evidence separately from upload/publication date, and uncertainties.
- Visible identifying features compared with the owner-supplied broom photos
  (hanging LED-tube curtain, rectangular two-story platform and upper railing).
- Retrieval date, access blockers, and whether this is metadata-only, sampled,
  thumbnail-level or full-resolution/playback inspection.

Keep leads unconfirmed until both the visible car and requested year are supported.
Link to third-party media rather than uploading it without publication permission.
Do not include personal contact details or private paths. Update the ledger and
computed counts together; run `python docs/media-hunt-2026/verify_notebook.py`
from the repository root before proposing the change.
