---
name: video-highlight-extractor
description: Use when a user asks to find memorable, useful, or Prompt-matching segments from local video files or folders and export selected clips.
---

# PromptClip-Skill Video Highlight Extractor

Use a generic, Agent-in-the-loop workflow. The user supplies a local video path and a natural-language Prompt at runtime. Baby videos, travel, pets, sports, and other themes are only Prompt examples; never hard-code a domain into the pipeline.

## Core Model

The pipeline is coverage-first:

1. **Local pre-cleaning** removes or marks only content that is proven unusable, such as an unreadable interval, black/empty output, or an exact duplicate. Blur, darkness, silence, no face, and “not interesting” are evidence or tags, not automatic rejection rules.
2. **AI storyboard coverage** analyzes every remaining time range. A storyboard is a cheap semantic coverage pass, not a final edit decision. The default MVP uses 30-second 4×3 sheets with 320×180 cells; the legacy one 10×6 contact sheet per minute remains available as a compatibility mode.
3. **AI refinement** analyzes only storyboard hits with timestamped frame windows and makes the final keep/reject decision.

Prompt-specific conditions remain AI conditions unless a local detector proves them with high recall. Never discard a low-confidence interval merely because a heuristic did not detect the subject. Preserve the original files and all timestamp mappings.

## Workflow

1. Extract `input_dir`, `prompt`, and output preferences from the request.
2. Reuse a prior run when its asset fingerprints match. Otherwise scan and create the low-resolution frame index:

```bash
python3 -m video_highlight scan \
  --input "$INPUT_DIR" \
  --output work/video-highlight/runs \
  --hwaccel auto
```

The scan, frames, quality flags, and storyboards are reusable across Prompt changes. Never send multi-GB source files to an Agent.

3. Run available local pre-cleaning. Keep a reversible record of every flag. A hard reject is allowed only when the media is unreadable, empty/black for the whole interval, or an exact duplicate whose source mapping is retained. If no deterministic pre-cleaner is available, keep the indexed interval; do not invent a rejection.
   When the Prompt explicitly requires visible faces, run the optional high-recall Apple Vision prefilter:

```bash
python3 -m video_highlight prefilter \
  --run "$RUN_DIR" \
  --prompt "$PROMPT"
```

   The prefilter detects face presence only; it cannot identify a person or judge whether a moment is interesting. If Apple Vision is unavailable, the run keeps full storyboard coverage. For a completed face prefilter, detail storyboards contain only face-positive samples within positive 30-second blocks, while the final Agent still makes the semantic decision.
4. Generate storyboard batches for all non-hard-rejected time ranges:

```bash
python3 -m video_highlight batches \
  --run "$RUN_DIR" --mode detail-storyboard --size 5 \
  --output "$RUN_DIR/agent-batches.json"
```

5. Start read-only visual children for every storyboard batch. The batch is the dispatch unit: each child receives exactly one batch, never multiple batches merged into one large request. Maintain a bounded queue with at most two active children by default; dispatch the next queued batch as soon as a child completes. Use a bounded wait (normally 120 seconds) and one retry with a smaller payload. Pass compact storyboard metadata and each contact sheet as a `local_image`; do not pass original videos. A failed batch is `failed`, never an implicit rejection. Do not create one child per cell; the batch is the unit of parallel work.

Require exactly:

```json
{"storyboards":[{"storyboard_id":"asset-minute-0000","keep_cells":[12,13],"score":0.9,"tags":["event"],"reason":"..."}]}
```

The child may return only supplied storyboard IDs and valid cell indexes. It must not invent timecodes or return Markdown. Require one result for every storyboard in the batch, including an explicit unavailable result when it cannot judge.

6. Separate coarse `no_match` from `analysis_unavailable` and low-resolution uncertainty. An empty `keep_cells` result is a valid rejection only when the Agent explicitly judged the supplied storyboard; an unavailable or “face too small to tell” result is not a rejection. For every unavailable or uncertain range, run a rescue storyboard pass before refinement. The default detail pass is already the balanced 30-second 4×3 pass; use the legacy minute storyboard first only when throughput is more important than small-subject visibility:

```bash
python3 -m video_highlight batches \
  --run "$RUN_DIR" --mode detail-storyboard --size 5 \
  --output "$RUN_DIR/detail-storyboard-batches.json"
```

Use only rescue sheets intersecting the unavailable/uncertain ranges when dispatching. The rescue child must use the same JSON contract. Apply rescue decisions with `--merge-existing` so a retry cannot erase candidates already found in another pass:

```bash
python3 -m video_highlight apply-storyboard-decisions \
  --run "$RUN_DIR" --prompt "$PROMPT" \
  --decisions "$RUN_DIR/detail-storyboard-decisions.json" \
  --merge-existing
```

7. Apply valid storyboard decisions locally. This creates padded approximate candidates, not final clips:

```bash
python3 -m video_highlight apply-storyboard-decisions \
  --run "$RUN_DIR" --prompt "$PROMPT" \
  --decisions "$RUN_DIR/storyboard-decisions.json"
```

8. Refine only approximate candidates:

```bash
python3 -m video_highlight batches \
  --run "$RUN_DIR" --mode frames --only-candidates --size 8 \
  --output "$RUN_DIR/refinement-batches.json"
```

Send each refinement batch to one read-only visual child, with no more than two active children and the remaining batches queued. Require one validated `decisions` item per known `window_id`; this is the semantic final decision. For a strict “every frame” Prompt, use dense samples in the candidate window and run a local per-frame verifier; one-second samples alone are not literal every-frame proof.

Before export, compare the set of supplied refinement `window_id`s with the returned valid unique decision IDs. Retry missing or malformed decisions. If any remain missing, report `partial` and do not describe the output as a complete folder result.

9. Start review and export accepted segments:

```bash
python3 -m video_highlight review --run "$RUN_DIR"
python3 -m video_highlight export --run "$RUN_DIR" --output "$RUN_DIR/export"
```

## Quality and Speed Rules

- The AI storyboard pass covers all non-hard-rejected time ranges; local pre-cleaning does not replace semantic coverage.
- Low-resolution empty hits and unavailable batches trigger the detail rescue pass; they never silently remove an asset from the result.
- Cache fingerprints, proxy frames, quality flags, face-prefilter results, and storyboards. A new Prompt should not rescan unchanged media.
- Dispatch independent storyboard and refinement batches through a bounded queue. Keep concurrency bounded by the observed model gateway capacity; unbounded fan-out can cause throttling and make the run slower, while merging multiple batches into one child creates oversized visual contexts.
- Use compact metadata, deduplicate repeated refinement frames, and keep Agent batches bounded. Do not wait indefinitely for a child.
- Merge adjacent candidates, add bounded padding, clamp to source duration, and let local code assign final timecodes.
- Export one primary `highlight-reel.mp4` even when candidates come from multiple source files. Its duration is the sum of accepted segments, with no fixed 30-second cap. Keep individual segment MP4s as supporting artifacts and report segment counts by source asset.
- If any batch fails, report `partial`, list failed batch IDs, and never claim the whole folder was analyzed.
- Never require `HIGHLIGHT_API_KEY` or `HIGHLIGHT_MODEL` for the normal Skill path. The visual child Agent is the analysis engine.
- Do not use the deterministic `mock` provider for user-facing results.
- Do not create a private Jianying draft in the first output. Export MP4, JSON, and FCPXML first.

## Output Contract

Report:

- `status`: `success`, `partial`, or `failure`;
- Prompt, coverage count, candidate count, accepted count, and failed batch IDs;
- next action: review URL or missing batch/configuration;
- artifacts: run directory, decisions, primary `highlight-reel.mp4`, individual clips, `segments.json`, and `timeline.fcpxml`.
