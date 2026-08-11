# Historical Fast-Mode Experiment

Date: 2026-08-11

Branch: `experiment/no-refinement`

This is the historical validation run that established the behavior now exposed as `fast` mode.

Input: `/Users/ron0115/Documents/手机视频素材/`

Prompt: `每一帧必须要有宝宝的脸出现，按照精彩瞬间的标准剪辑`

## Method

This run was created from the original input directory. It did not read earlier decisions, storyboards, or exported clips.

The run used the existing local face prefilter, 30-second detail storyboards, at most two parallel visual Agents, and direct export of storyboard candidates with `--include-pending`. The refinement frame pass was intentionally skipped.

## Measurements

| Stage | Wall time |
| --- | ---: |
| Scan 3 source videos and extract 794 one-second samples | 76.57 s |
| Apple Vision face prefilter, 794 samples -> 258 positives | 8.62 s |
| Generate 26 detail storyboards / 6 Agent batches | 2.55 s |
| Storyboard Agent analysis and result orchestration | about 9 min 05 s |
| Apply 26 storyboard results -> 26 candidates | 0.51 s |
| Transcode 26 segments and merge MP4 | 398.83 s |
| End-to-end wall-clock time, run directory creation -> merged MP4 | about 18 min 20 s |

The Agent interval includes dispatch, bounded waits, and manually combining the six returned JSON results for this validation run. A fully automated skill implementation should remove most of that manual orchestration overhead.

## Output

- 26 storyboard results, 91 kept cells, 26 merged candidates.
- 26 exported segments from all 3 source videos.
- Merged duration: 216.2 s.
- Merged file: `/Users/ron0115/Desktop/Personal/PromptClip-Skill-no-refinement/work/experiments/no-refinement-20260811/exports/highlight-reel.mp4`
- Run data and decisions: `/Users/ron0115/Desktop/Personal/PromptClip-Skill-no-refinement/work/experiments/no-refinement-20260811/runs/run-20260811-062212-357707/`

Per-source exported duration:

| Source | Segments | Duration |
| --- | ---: | ---: |
| `dji_mimo_20260726_144156_0_1785076823758_video.mp4` | 1 | 17.0 s |
| `dji_mimo_20260726_145410_0_1785076817805_video.mp4` | 11 | 73.0 s |
| `dji_mimo_20260726_153834_0_1785076560884_video.mp4` | 14 | 126.0 s |

## Conclusion

The hypothesis is supported: compared with the previous complete-flow baseline of 1,984.19 s (33 min 04 s), coarse-only completed in about 1,100 s (18 min 20 s), saving about 884 s (14 min 44 s), or 44.6% wall time.

The speedup is meaningful but not close to 2x in this run because coarse-only retained more material: 216.2 s versus 105.1 s in the recent balanced run. Export alone took 398.83 s, so direct coarse export can give back part of the time saved by removing refinement.

Quality limitations observed or implied by the design:

- Storyboard cells are sparse samples, not proof that every frame contains a face.
- Candidate padding and merging can include non-matching frames and unrelated lead-in or tail material.
- Short events can be missed between storyboard cells.
- More candidates make export slower and the result longer, even though AI analysis is shorter.

Current Skill policy: default to `fast` unless the Prompt explicitly requires precise boundaries or frame-level compliance, in which case use `precise`. Fast output remains approximate and must be labeled as such.
