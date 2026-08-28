# Public Demo: Skatepark Highlights

This example is designed for a privacy-safe demo. It uses public-domain or appropriately licensed skatepark footage instead of personal family videos. The repository does not include third-party media; add clips locally after checking their license.

## Recording recipe

Collect 8-12 short clips containing a mixture of:

- a clearly completed trick or landing
- a failed attempt
- the preparation before a trick
- repeated takes
- camera shake or a subject leaving the frame
- an empty establishing shot

Keep the original clips in `input/` and record the source URLs and licenses in `SOURCES.md`.

## Prompt

The reusable prompt is in [`prompt.txt`](prompt.txt).

## Expected review result

The expected result is a short list of high-signal moments, not a claim that every frame in the exported `fast` reel satisfies the Prompt. Use `precise` when exact boundaries matter.

```text
input/                  # locally added, licensed clips
prompt.txt              # the Prompt above
expected-segments.json  # manually maintained reference for the demo
SOURCES.md              # creator, URL, and license for every clip
```

The demo is intentionally about filtering. It should make the transformation obvious:

```text
10 mixed clips -> Prompt -> 3 completed tricks -> reviewable highlight reel
```
