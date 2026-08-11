# PromptClip-Skill

PromptClip-Skill is a local-first, prompt-driven tool for finding and exporting the best moments from any video collection. It never modifies the input media. A run creates a low-resolution frame index, lets a Codex sub-agent inspect bounded timestamped frame batches, supports local review, and exports selected clips plus JSON and FCPXML.

Repository: https://github.com/ron0115/PromptClip-Skill

The repository is named `PromptClip-Skill`; `video-highlight-extractor` remains the stable Codex Skill and Python package name for compatibility.

## Codex Skill mode

Use `/video-highlight-extractor` in Codex and provide a local folder plus a natural-language Prompt. Baby videos are only one example: the same workflow can select travel, pets, sports, events, or any other subject described by the Prompt. The Skill uses hardware-accelerated proxy extraction when available, runs the optional local face prefilter for face-specific Prompts, sends one bounded storyboard/refinement batch per Agent, validates `window_id` decisions, opens the review page, and exports accepted clips. This path does not require an API key or model environment variable.

## Quick start

```bash
python3 -m video_highlight process \
  --input "/Users/ron0115/Documents/手机视频素材" \
  --output work/runs \
  --prompt "保留宝宝表情清晰、动作完整、和家人互动的片段" \
  --provider mock \
  --export-output work/exports \
  --include-pending \
  --limit 3
```

The `mock` provider is deterministic and exists only to validate the local pipeline in automated tests. It does not understand video content and should not be used for a user-facing result.

Start the review page for a run:

```bash
python3 -m video_highlight review --run work/runs/<run-id>
```

The first scan creates `run.json` and `frames/` under the run directory. Re-running the same run reuses existing extracted frames when the expected sample set is present. Scanning and independent export work use at most two workers by default; lower or raise this with `--workers` when the machine and storage can support it.
