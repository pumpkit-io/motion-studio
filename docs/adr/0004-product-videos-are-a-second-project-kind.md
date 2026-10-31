# Product videos are a second project kind with a scene-based EDL

Product videos (launch videos, feature demos, changelog videos) become a second project kind, `product`, next to the existing `talk`. The kind is set once with `new --kind` and stored in `project.toml`, never detected from the footage, because analysis built for speech labelled a speech-only clip as B-roll. Both kinds share the workspace, music, mastering, render and check, and both write `edl.json` through the same `plan draft` and `plan validate`. A `product` EDL holds `scenes[]` (title cards, footage in device frames, proof shots, an outro) where a `talk` EDL holds `segments[]`, and the shared top-level fields stay the same.

## Considered Options

- Keep launch videos in a separate tool. Rejected: music, mastering, render and check would be built twice, and the Pumpkit launch video already needed every one of them.
- Extend the talk EDL, with title cards and outros as events. Rejected: it forces an output order made of speech onto footage that has none.
- A separate `storyboard.json` with its own commands. Rejected: the agent would have to learn two command sets for one workflow.
- A general motion-graphics editor. Rejected: free-form composition would push the agent back into writing rendering code, which coding rule 2 forbids.
