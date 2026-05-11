# Avatar input

Place a single file at `assets/avatars/default.mp4`. MuseTalk uses this as
the source face that will be lip-synced to your text. The path is configurable
via the `AVATAR_INPUT` environment variable (see `.env.example`).

Recommended specs for the best result:

- 5–10 second MP4 video (or a high-quality still PNG/JPG)
- person facing the camera straight-on (no severe profile)
- professional lighting (soft, even, no harsh shadows on the face)
- neutral expression with mouth mostly closed in idle state
- minimal head movement (the avatar should look natural while still)
- 1080p preferred (MuseTalk works at 256x256 on the face crop, so resolution above that is mostly for surrounding pixels)
- non-distracting background — a plain office wall, brand backdrop, or studio gradient

Avoid:

- talking, smiling broadly, or blinking heavily during the clip — MuseTalk
  preserves the source mouth shape and any motion in the original frames.
- fast camera motion, parallax, or zoom.
- heavy compression artefacts.

If `assets/avatars/default.mp4` is missing, real-mode jobs will fail fast
with an actionable error message; mock mode keeps working.
