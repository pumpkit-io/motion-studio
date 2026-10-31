# motion-studio

motion-studio edits video with a coding agent: talking-head footage into short videos for Instagram Reels and X, and screen recordings into product videos such as launch videos. The agent makes every editorial choice. motion-studio turns footage into text and stills the agent can read, and renders the edit the agent describes.

## Roles

**Host agent**:
The coding agent (Claude Code, Codex, Gemini CLI, Cursor) that a creator opens in a workspace and that makes every editorial decision.
_Avoid_: AI, LLM, the model, editor bot

**Creator**:
The person whose footage is being edited and who asks the host agent for a video.
_Avoid_: User (ambiguous with the agent's user), customer

## Places

**Workspace**:
A directory created by `reelcut init` that holds the creator's config, library and projects, and in which the host agent is opened.
_Avoid_: Repo, folder, project root

**Project**:
One video job inside a workspace: its raw files, derived files, EDL and deliverables, identified by a slug.
_Avoid_: Job, edit, video

**Project kind**:
What a project makes, set when the project is created: `talk` (a talking-head video, the default) or `product` (a product video).
_Avoid_: Type, mode, template

**Product video**:
A project made from recordings of a product's screens instead of a speaker: a launch video, a feature demo or a changelog video. It shares the workspace, music, render and check with talking-head projects.
_Avoid_: Promo, demo reel, motion graphics

**Library**:
Workspace-level reusable material: licensed music tracks and brand assets.
_Avoid_: Assets folder

## Source material

**Clip**:
One file in a project's `raw/` directory, given a stable short ID at ingest.
_Avoid_: File, take, source

**Role**:
What a clip is used for: A-roll, B-roll or image.
_Avoid_: Type, kind, category

**A-roll**:
A clip of the speaker talking; its speech is what the edit cuts. IDs start with `c`.
_Avoid_: Main footage, talking head clip

**B-roll**:
A video clip without significant speech, used only as an overlay. IDs start with `b`.
_Avoid_: Cutaway footage, stock

**Image**:
A still picture used only as an overlay. IDs start with `i`.
_Avoid_: Photo, still

**Asset**:
A B-roll clip or an image; anything that can appear as an overlay.
_Avoid_: Media, resource

**Take**:
One attempt by the speaker at delivering some lines. A clip can hold several takes.
_Avoid_: Clip (a clip is a file; a take is a performance), Screen recording

**Screen recording**:
A clip made by running a recording script against a browser or a terminal, carrying the markers the script wrote.
_Avoid_: Take (a take is a speaker's performance), capture, screencast

**Recording script**:
The script the host agent writes to drive a product through one screen recording: what to click, type and wait for, and where to place markers.
_Avoid_: Take script, tape (a tape is one kind of terminal recording script)

**Marker**:
A named moment in a screen recording (`brief_sent`, `v1_shown`), written by the recording script on the same clock as the frames.
_Avoid_: Timestamp, cue, bookmark

**Element**:
A named on-screen region whose box the recording script captured at a marker, such as the post text when version 2 appears. Camera moves and highlights target elements.
_Avoid_: Selector (a selector is how the script finds it), bounding box, region

**Shot list**:
The recordings a product video needs, each with what it shows and every side effect it causes outside the isolated instance, agreed with the creator before anything is recorded.
_Avoid_: Storyboard (a storyboard is the edit), script

**Demo kit**:
A document in a product's own repository that says how to film that product safely: the isolated instance, demo accounts, how to sign in, and how to undo every side effect a recording causes.
_Avoid_: Demo guide, test setup

**Mezzanine**:
The normalised copy of a clip (constant frame rate, SDR) that every later stage reads instead of the raw file.
_Avoid_: Proxy, intermediate, transcode

## Analysis

**Word**:
One transcribed word with source times and a stable ID such as `c1.w127`.
_Avoid_: Token

**Utterance**:
A run of words split at a long pause or at sentence-final punctuation, with an ID such as `c1.s4`.
_Avoid_: Sentence, line, phrase

**Incomplete utterance**:
An utterance that stops mid-sentence before a long pause or the clip end, usually an abandoned take. Marked `✗`.
_Avoid_: Broken sentence, false start

**Filler**:
A word that carries no content. A **hard filler** (`ehm`, `um`) is removed by default. A **soft filler** (`tipo`, `like`, `allora` at utterance start) is only marked, and the host agent decides.
_Avoid_: Disfluency, tic

**Unaligned voice**:
A stretch the voice-activity detector hears as speech but where no word was transcribed: likely a mumble, breath or skipped filler.
_Avoid_: Noise, gap

**Pause**:
Silence between two consecutive words.
_Avoid_: Gap, dead air (dead air is a pause worth cutting)

**Retake cluster**:
A group of utterances, within or across clips, that say the same thing. The draft keeps one winner per cluster.
_Avoid_: Duplicates, repeats

**Static stretch**:
At least 2 seconds with no speech and almost no motion on screen.
_Avoid_: Dead footage, idle

**Packed index**:
The compact text view of a whole project (`analysis/packed.md`): one line per utterance with fillers, pauses, retakes and static stretches marked. It is the host agent's primary view of the footage.
_Avoid_: Transcript, summary

**Contact sheet**:
One PNG showing frames, waveform, word labels and face boxes for a time range or an asset, made on demand by `look`.
_Avoid_: Thumbnail, screenshot, storyboard

**Look budget**:
The number of contact sheets the host agent may request per project before it is warned.
_Avoid_: Quota, limit

## The edit

**EDL**:
The edit decision list (`edl.json`): the single file in which the host agent records every creative decision, referencing words and utterances by ID.
_Avoid_: Plan, script, cut list

**Draft**:
The deterministic baseline EDL that reelcut writes from the analysis, before the host agent refines it.
_Avoid_: Auto-edit, first cut

**Segment**:
An entry in the EDL that keeps a range of words from one clip. The order of segments in the EDL is their order in the output.
_Avoid_: Clip, section, part

**Scene**:
An entry in a product video's EDL: one title card, footage shot, proof shot or outro, with its own duration. The order of scenes is their order in the output.
_Avoid_: Segment (a segment keeps a range of words), slide, shot

**Title card**:
A short full-frame scene with a headline, and optionally a step number and a subline, that introduces what comes next.
_Avoid_: Title (a title is text over footage), slate, intertitle

**Device frame**:
The drawn browser, terminal or phone window that footage plays inside in a product video.
_Avoid_: Mockup, chrome, window

**Proof shot**:
A still of a real result produced by the product, such as a published post, shown in a product video as evidence that it works.
_Avoid_: Screenshot, social proof

**Highlight**:
A box with an optional label drawn around a region of footage to direct the viewer's eye.
_Avoid_: Callout, annotation

**Mask**:
A rectangle drawn over part of the footage in the frame's background colour to hide something that must not be seen.
_Avoid_: Blur, redaction, crop

**Hook**:
The opening of the video, roughly the first 2 to 3 seconds, chosen to make a viewer stay.
_Avoid_: Intro

**Event**:
An EDL instruction layered on top of segments or scenes: in a talk project a zoom, push, B-roll, image, title or emphasis; in a product video a camera move, highlight, mask or caption pill.
_Avoid_: Effect, overlay (an overlay is one kind of event)

**Anchor**:
The word, utterance or segment ID an event is attached to. It resolves to a time in the output.
_Avoid_: Timestamp, Marker (a marker is a moment in a screen recording; an anchor can point at one)

**Policy**:
The trimming rules applied while resolving an EDL: padding, maximum pause, minimum run length, filler dropping, jump-cut punch.
_Avoid_: Settings, options

**Run**:
A continuous stretch of source footage that survives resolving. One segment becomes one or more runs.
_Avoid_: Segment (a segment is what the agent asks for; a run is what is actually cut), shot, piece

**Jump cut**:
A cut between two runs from the same clip with source time skipped between them.

**Jump-cut punch**:
Alternating the base zoom between consecutive runs at a jump cut so the cut reads as deliberate.
_Avoid_: Auto-zoom

**Timeline**:
The frame-accurate result of resolving the EDL (`build/timeline.json`): runs, words and events in output time. The renderer reads only this.
_Avoid_: Project file, sequence

**Source time / output time**:
Source time is a position in a clip's mezzanine. Output time is a position in the finished video.

**Reframing**:
Choosing a crop per run that keeps the speaker's face in the right place for the target format.
_Avoid_: Auto-crop, tracking

## Output

**Format**:
One output aspect ratio and size: `9x16` (1080×1920), `16x9` (1920×1080) or `4x5` (1080×1350).
_Avoid_: Platform, resolution, preset

**Preview**:
A half-resolution, fast-encoded render for checking an edit.
_Avoid_: Draft render, proxy

**Final**:
A full-resolution render delivered to the creator.
_Avoid_: Export, master

**Share copy**:
A full-resolution copy of a final, re-encoded to stay under 30 MiB so it can be sent through chat tools and to phones.
_Avoid_: Preview (a preview is half-resolution and checks an edit), small copy, compressed version

**Check**:
The automated quality pass on a render: re-transcribe and diff, cut stills, loudness, black and frozen frames, duration.
_Avoid_: QA run, validation (validation is of the EDL, not of a render)

**Clipped cut**:
A cut that removes part of a word that should have been kept. A check that finds one blocks delivery.
_Avoid_: Bad cut

**Review gate**:
A stop where the host agent waits for the creator's go-ahead: optional after the plan and after the preview, and required after the shot list of a product video.
_Avoid_: Approval step, checkpoint

## Music

**Music bed**:
The instrumental track mixed under the voice, either generated locally or picked from the library.
_Avoid_: Soundtrack, background music, BGM

**Section hit**:
The moment a music bed changes section (intro end, build, drop, ending), on a bar line and given a time in the bed.
_Avoid_: Drop (a drop is one kind of section hit), beat, cue

**Small-speaker check**:
Comparing the energy of a render's high frequencies with its sub-bass, so that music which disappears on laptop and phone speakers is caught before delivery.
_Avoid_: Bass check, EQ check

**Beat grid**:
The bars and beats of the music bed laid over output time. Product video scenes are timed on it.
_Avoid_: Tempo map, click track

**Ducking**:
Lowering the music bed automatically while the voice is speaking.
_Avoid_: Sidechain (that is the mechanism)
