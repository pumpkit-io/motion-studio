# Music library

Put your own licensed tracks here and list them in `tags.json`. An EDL with `"music": {"mode": "library"}` picks from this list by mood and BPM.

motion-studio only uses a track whose entry has a `licence`; entries without one are refused. When a track needs attribution, motion-studio writes it to `final/<slug>_credits.txt`. Only list music you have the right to publish: a track you bought for personal listening, or one ripped from a video, usually does not allow it.

`tags.json` is a list of entries like this one (`file` is relative to this folder; `energy` runs from 1 to 5):

```json
[
  {
    "file": "warm-synths.mp3",
    "title": "Warm Synths",
    "mood": ["confident", "optimistic"],
    "bpm": 104,
    "energy": 3,
    "licence": "CC BY 4.0",
    "source_url": "https://example.com/warm-synths",
    "attribution": "Warm Synths by Example Artist (CC BY 4.0)"
  }
]
```

The default music mode, `generate`, needs nothing here: motion-studio generates an instrumental bed locally and records the model's licence in each project's `build/music.json`.
