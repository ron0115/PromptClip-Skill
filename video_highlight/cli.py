from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze_run
from .agent_pipeline import apply_agent_decisions, apply_storyboard_decisions, build_batches
from .export import export_run
from .indexing import create_run
from .prefilter import apply_face_prefilter
from .review import serve_review
from .storage import load_run, save_json
from .storyboards import build_detail_storyboard_batches, build_storyboard_batches


def _add_common_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", type=Path, required=True, help="Path to a scan run")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-highlight",
        description="PromptClip-Skill prompt-driven local video highlight extraction",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="Scan videos and generate a frame index")
    scan.add_argument("--input", type=Path, required=True)
    scan.add_argument("--output", type=Path, default=Path("work/runs"))
    scan.add_argument("--interval", type=float, default=1.0)
    scan.add_argument("--width", type=int, default=640)
    scan.add_argument("--workers", type=int, default=2)
    scan.add_argument("--hwaccel", choices=["auto", "none", "videotoolbox"], default="auto")

    analyze = commands.add_parser("analyze", help="Analyze indexed windows with a Prompt")
    _add_common_run_argument(analyze)
    analyze.add_argument("--prompt", required=True)
    analyze.add_argument("--provider", choices=["mock", "openai"], default="mock")
    analyze.add_argument("--max-windows", type=int)

    prefilter = commands.add_parser("prefilter", help="Run prompt-specific local quality prefilters")
    _add_common_run_argument(prefilter)
    prefilter.add_argument("--prompt", required=True)

    batches = commands.add_parser("batches", help="Prepare timestamped image batches for Agent analysis")
    _add_common_run_argument(batches)
    batches.add_argument("--mode", choices=["storyboard", "detail-storyboard", "frames"], default="storyboard")
    batches.add_argument("--size", type=int, default=5)
    batches.add_argument("--only-candidates", action="store_true")
    batches.add_argument("--output", type=Path)

    apply = commands.add_parser("apply-decisions", help="Apply validated Agent window decisions")
    _add_common_run_argument(apply)
    apply.add_argument("--prompt", required=True)
    apply.add_argument("--decisions", type=Path, required=True)

    apply_storyboard = commands.add_parser("apply-storyboard-decisions", help="Apply coarse storyboard cell decisions")
    _add_common_run_argument(apply_storyboard)
    apply_storyboard.add_argument("--prompt", required=True)
    apply_storyboard.add_argument("--decisions", type=Path, required=True)
    apply_storyboard.add_argument("--merge-existing", action="store_true")

    review = commands.add_parser("review", help="Start the local review page")
    _add_common_run_argument(review)
    review.add_argument("--host", default="127.0.0.1")
    review.add_argument("--port", type=int, default=8765)

    export = commands.add_parser("export", help="Export confirmed candidates")
    _add_common_run_argument(export)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--include-pending", action="store_true")
    export.add_argument("--limit", type=int)
    export.add_argument("--no-transcode", action="store_true")
    export.add_argument("--workers", type=int, default=2)

    process = commands.add_parser("process", help="Run scan and analysis in one command")
    process.add_argument("--input", type=Path, required=True)
    process.add_argument("--output", type=Path, default=Path("work/runs"))
    process.add_argument("--prompt", required=True)
    process.add_argument("--provider", choices=["mock", "openai"], default="mock")
    process.add_argument("--interval", type=float, default=1.0)
    process.add_argument("--width", type=int, default=640)
    process.add_argument("--workers", type=int, default=2)
    process.add_argument("--hwaccel", choices=["auto", "none", "videotoolbox"], default="auto")
    process.add_argument("--max-windows", type=int)
    process.add_argument("--export-output", type=Path)
    process.add_argument("--include-pending", action="store_true")
    process.add_argument("--limit", type=int)
    process.add_argument("--export-workers", type=int, default=2)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        run_dir = create_run(
            args.input.resolve(), args.output.resolve(), args.interval, args.width, args.workers, args.hwaccel
        )
        print(run_dir)
        return 0
    if args.command == "analyze":
        run = analyze_run(args.run.resolve(), args.prompt, args.provider, args.max_windows)
        print(json.dumps({"run": str(args.run.resolve()), "candidates": len(run["candidates"])}, ensure_ascii=False))
        return 0
    if args.command == "prefilter":
        run = apply_face_prefilter(args.run.resolve(), args.prompt)
        prefilter_result = run.get("prefilter", {})
        print(json.dumps({"run": str(args.run.resolve()), **prefilter_result}, ensure_ascii=False))
        return 0
    if args.command == "batches":
        if args.mode == "storyboard":
            batches = build_storyboard_batches(args.run.resolve(), args.size)
        elif args.mode == "detail-storyboard":
            batches = build_detail_storyboard_batches(args.run.resolve(), args.size)
        else:
            batches = build_batches(args.run.resolve(), args.size, args.only_candidates)
        if args.output:
            save_json(args.output.resolve(), batches)
            print(args.output.resolve())
        else:
            print(json.dumps(batches, ensure_ascii=False))
        return 0
    if args.command == "apply-decisions":
        run = apply_agent_decisions(args.run.resolve(), args.prompt, args.decisions.resolve())
        print(json.dumps({"run": str(args.run.resolve()), "candidates": len(run["candidates"])}, ensure_ascii=False))
        return 0
    if args.command == "apply-storyboard-decisions":
        run = apply_storyboard_decisions(
            args.run.resolve(),
            args.prompt,
            args.decisions.resolve(),
            merge_existing=args.merge_existing,
        )
        print(json.dumps({"run": str(args.run.resolve()), "candidates": len(run["candidates"])}, ensure_ascii=False))
        return 0
    if args.command == "review":
        serve_review(args.run.resolve(), args.host, args.port)
        return 0
    if args.command == "export":
        run = load_run(args.run.resolve())
        manifest = export_run(
            run,
            args.output.resolve(),
            args.include_pending,
            args.limit,
            not args.no_transcode,
            args.workers,
        )
        print(json.dumps({"output": str(args.output.resolve()), "segments": len(manifest["segments"]), "merged": manifest["merged_path"]}, ensure_ascii=False))
        return 0
    if args.command == "process":
        run_dir = create_run(
            args.input.resolve(), args.output.resolve(), args.interval, args.width, args.workers, args.hwaccel
        )
        run = analyze_run(run_dir, args.prompt, args.provider, args.max_windows)
        result: dict[str, object] = {"run": str(run_dir), "candidates": len(run["candidates"])}
        if args.export_output:
            manifest = export_run(
                run,
                args.export_output.resolve(),
                args.include_pending,
                args.limit,
                workers=args.export_workers,
            )
            result.update({"export": str(args.export_output.resolve()), "segments": len(manifest["segments"])})
        print(json.dumps(result, ensure_ascii=False))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
