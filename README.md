# PromptClip-Skill

PromptClip-Skill is a local-first, prompt-driven tool for finding and exporting the best moments from any video collection. It never modifies the input media. A run creates a low-resolution frame index, lets Codex sub-agents inspect bounded timestamped frame batches, supports fast and precise edit modes, and exports one merged highlight reel plus JSON and FCPXML.

Repository: https://github.com/ron0115/PromptClip-Skill

The repository is named `PromptClip-Skill`; `video-highlight-extractor` remains the stable Codex Skill and Python package name for compatibility.

## Codex Skill mode

Use `/video-highlight-extractor` in Codex and provide a local folder plus a natural-language Prompt. Baby videos are only one example: the same workflow can select travel, pets, sports, events, or any other subject described by the Prompt. The Skill uses hardware-accelerated proxy extraction when available, runs the optional local face prefilter for face-specific Prompts, sends bounded storyboard/refinement batches to at most two Agents, validates decisions, opens the review page, and exports one merged reel. This path does not require an API key or model environment variable.

The default mode is `fast`: it stops after storyboard analysis and exports padded storyboard candidates with `--include-pending`. Use `precise` when the Prompt explicitly requires exact boundaries or frame-level compliance; it adds the refinement pass and exports accepted candidates only. Both modes share the same scan, storyboard, Agent result contract, and export implementation. The mode changes AI analysis depth, not output encoding or merge quality.

## Smart Export

The export stage automatically chooses the fastest compatible path for the selected timeline:

- `stream_copy`: source streams have compatible parameters and every cut is keyframe-safe. The final MP4 preserves the source video/audio streams and is created with no intermediate clip files.
- `single_transcode`: source parameters are compatible but a cut needs frame-accurate decoding. All selected ranges are decoded and encoded once into the final MP4.
- `compatibility_transcode`: source parameters differ or the normal concat path fails. Inputs are normalized to a broadly playable H.264/AAC MP4, using the first source's dimensions as the target canvas.

`segments.json` records `export_strategy`, `source_preserved`, and `reencoded`. `highlight-reel.mp4` is the primary media artifact; `timeline.fcpxml` and the JSON manifest retain the source time ranges for editing applications. Fast and precise modes use this same export decision tree.

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

The `process` command above is a compatibility/test entry point. The user-facing Agent workflow and its `fast`/`precise` mode selection are defined by `/video-highlight-extractor`.

Start the review page for a run:

```bash
python3 -m video_highlight review --run work/runs/<run-id>
```

The first scan creates `run.json` and `frames/` under the run directory. Re-running the same run reuses existing extracted frames when the expected sample set is present. Scanning and independent export work use at most two workers by default; lower or raise this with `--workers` when the machine and storage can support it.
