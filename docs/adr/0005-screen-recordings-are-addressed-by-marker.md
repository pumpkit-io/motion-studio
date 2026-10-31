# Screen recordings are addressed by marker, not by seconds

ADR 0002 has the EDL name words and utterances because models pick sentences well and milliseconds badly. Screen recordings have no words, so the recording script writes named markers on the same clock as the frames, and a product EDL points into a recording with marker IDs (`c2.m.v1_shown`) plus a short offset in seconds or beats. Scene lengths are set in beats or bars on the music's beat grid, with seconds allowed. Source seconds are accepted only for clips that carry no markers, such as footage the creator brings, and validation warns on each one. This is an exception to ADR 0002 for screen recordings; talk projects keep word and utterance IDs only.

## Considered Options

- Source seconds everywhere in product EDLs. Rejected: in the Pumpkit session the agent read times off contact sheets and misplaced an in-point by 1.5 s, because a 3 s sheet hid when the terminal finished printing.
- Markers only. Rejected: it would refuse footage that was not made with the recorder.
