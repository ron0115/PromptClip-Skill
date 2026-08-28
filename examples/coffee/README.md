# Public Demo: Coffee Highlights

This demo uses openly licensed footage downloaded from Wikimedia Commons. It is designed to show semantic filtering without using private family videos or identifiable personal recordings.

## Showcase

![Coffee highlights showcase](../../assets/coffee-demo.gif)

The [full MP4](showcase/coffee-highlights.mp4) is the output of a real `fast`-mode Skill run. It scanned both input videos, selected two candidate segments from storyboard frames, and exported a 28-second reel. The decision file, `segments.json`, `run-report.json`, and FCPXML timeline are included in [`real-run/`](real-run/) for inspection.

The original OGV download is archived in `source-original/`; the WebM copy in `input/` contains the same footage and is the file used by the Skill run because it is more broadly supported by the local media scanner.

## Files

- `input/latte-art-leaf-01.webm` - CC0 latte-art footage, normalized from the original OGV for Skill compatibility
- `input/making-cappuccino-coffee.webm` - CC BY-SA 4.0 coffee-making footage
- `source-original/latte-art-leaf-01.ogv` - original Wikimedia download
- [`prompt.txt`](prompt.txt) - reusable filtering Prompt
- [`SOURCES.md`](SOURCES.md) - attribution and license records
- [`showcase/coffee-highlights.mp4`](showcase/coffee-highlights.mp4) - short reference edit

## Prompt

```text
Keep the meaningful coffee-making moments: coffee or milk being poured,
the latte pattern forming, the finished drink, and stable close-ups of
the completed result. Remove waiting, preparation with no visible change,
repeated takes, severe camera shake, blocked views, and empty shots.
Preserve the original order and keep the final reel under 30 seconds.
```

This is a small showcase dataset, not a benchmark. The selected moments should be reviewed before being described as a final edit, especially when using the `fast` mode.
