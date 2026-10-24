"""Command line:

  image-studio presets
  image-studio analyze PHOTOS... [--preset P] [--json]
  image-studio process PHOTOS... -o OUT [--preset P] [--set key=value ...] [--sheet]
  image-studio calibrate REFERENCE_PHOTOS... --preset P -o my-preset.json
  image-studio serve [--host 0.0.0.0] [--port 8100]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import __version__
from .analyze import consistency, resize_long, subject_stats, to_lab
from .config import list_presets, load_preset, parse_set
from .imgio import expand_paths, extension, open_image
from .mask import subject_mask
from .pipeline import analyze, process
from .sheet import contact_sheet


def _issues_line(report: dict) -> str:
    codes = [i["code"] for i in report["issues"]]
    return ", ".join(codes) if codes else "ok"


def cmd_presets(args) -> int:
    for name, desc in list_presets().items():
        print(f"{name:18} {desc}")
    return 0


def cmd_analyze(args) -> int:
    overrides = parse_set(args.set)
    reports = {}
    for path in expand_paths(args.paths):
        r = analyze(path, args.preset, overrides)
        reports[str(path)] = r
        if not args.json:
            print(f"{r['score']:3d}  {path.name:32} {_issues_line(r)}")
    if args.json:
        print(json.dumps({"images": reports, "consistency": consistency(list(reports.values()))}, indent=2))
    else:
        print("\nconsistency (std, lower = more uniform):", json.dumps(consistency(list(reports.values()))))
    return 0


def cmd_process(args) -> int:
    cfg = load_preset(args.preset, parse_set(args.set))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = cfg["output"]["format"]
    reports, pairs = {}, []
    paths = expand_paths(args.paths)
    for n, path in enumerate(paths, 1):
        try:
            res = process(path, cfg=cfg)
        except Exception as exc:  # keep going through a batch
            print(f"[{n}/{len(paths)}] {path.name}: FAILED - {exc}", file=sys.stderr)
            continue
        target = out_dir / f"{path.stem}{extension(fmt)}"
        target.write_bytes(res.encode())
        for r in res.renditions():
            (out_dir / f"{path.stem}{r['suffix']}{extension(r['format'])}").write_bytes(r["data"])
        if args.masks:
            res.mask.save(out_dir / f"{path.stem}.mask.png")
        reports[path.name] = res.report
        pairs.append((path, target))
        rep = res.report
        print(f"[{n}/{len(paths)}] {path.name:32} {rep['source']['score']:3d} -> {rep['result']['score']:3d}  fixed: {', '.join(rep['fixed']) or '-'}  remaining: {', '.join(rep['remaining']) or '-'}")

    summary = {
        "preset": cfg["name"],
        "consistency_before": consistency([r["source"] for r in reports.values()]),
        "consistency_after": consistency([r["result"] for r in reports.values()]),
        "images": reports,
    }
    (out_dir / "report.json").write_text(json.dumps(summary, indent=2))
    if args.sheet and pairs:
        sheet = contact_sheet([(p.name, [p, t]) for p, t in pairs], tile=args.tile)
        sheet.save(out_dir / "before-after.jpg", quality=88)
    print("\nconsistency before:", json.dumps(summary["consistency_before"]))
    print("consistency after: ", json.dumps(summary["consistency_after"]))
    print(f"wrote {len(pairs)} images and report.json to {out_dir}")
    return 0 if len(pairs) == len(paths) else 1


def cmd_calibrate(args) -> int:
    """Measure reference photos and write a preset whose colour targets match them."""
    base = load_preset(args.preset)
    stats = []
    for path in expand_paths(args.paths):
        img = open_image(path)
        work = resize_long(np.asarray(img)).astype("float32") / 255.0
        mask, _ = subject_mask(work, base["mask"])
        stats.append(subject_stats(to_lab(work), mask))
    keys = ("L", "L_median", "L_std", "a", "b", "chroma")
    reference = {k: round(sum(s[k] for s in stats) / len(stats), 2) for k in keys}
    name = args.name or Path(args.output).stem
    preset = {
        "name": name,
        "description": args.description or f"{base['name']} calibrated to {len(stats)} reference photo(s)",
        "extends": args.preset,
        "color": {"reference": reference},
    }
    Path(args.output).write_text(json.dumps(preset, indent=2) + "\n")
    print(json.dumps(reference))
    print(f"wrote {args.output}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("image_studio.server:app", host=args.host, port=args.port, workers=args.workers)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="image-studio", description="Analyse, enhance and unify photos.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("presets", help="list presets").set_defaults(fn=cmd_presets)

    a = sub.add_parser("analyze", help="score photos and list quality issues")
    a.add_argument("paths", nargs="+")
    a.add_argument("--preset", default="default")
    a.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_analyze)

    pr = sub.add_parser("process", help="enhance photos with a preset")
    pr.add_argument("paths", nargs="+")
    pr.add_argument("-o", "--output", required=True)
    pr.add_argument("--preset", default="default")
    pr.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a preset value, e.g. background.color=#fff")
    pr.add_argument("--sheet", action="store_true", help="also write before-after.jpg")
    pr.add_argument("--tile", type=int, default=320)
    pr.add_argument("--masks", action="store_true", help="also write the subject masks")
    pr.set_defaults(fn=cmd_process)

    c = sub.add_parser("calibrate", help="build a preset whose colour matches reference photos")
    c.add_argument("paths", nargs="+")
    c.add_argument("--preset", default="default", help="preset to extend")
    c.add_argument("-o", "--output", required=True)
    c.add_argument("--name")
    c.add_argument("--description")
    c.set_defaults(fn=cmd_calibrate)

    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8100)
    s.add_argument("--workers", type=int, default=1)
    s.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
