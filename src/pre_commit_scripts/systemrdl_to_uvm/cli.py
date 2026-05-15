from __future__ import annotations

import argparse
import fnmatch
import pathlib
import sys
from typing import Iterable, Optional, Sequence

from systemrdl import RDLCompiler, RDLCompileError
from peakrdl_uvm import UVMExporter

DEFAULT_INPUT_DIR = "regmap"
DEFAULT_OUTPUT_DIR = "dv/uvm_regmodel"


def output_file_for(
    rdl: pathlib.Path,
    out_root: pathlib.Path,
    repo_root: pathlib.Path,
    input_dir: Optional[pathlib.Path],
    filename_template: str,
) -> pathlib.Path:
    """Mirror the RDL's path under ``input_dir`` into ``out_root``.

    The output is a single .sv file; ``filename_template`` controls its stem
    via ``{name}`` (the RDL filename stem) — e.g. ``{name}_uvm`` yields
    ``foo_uvm.sv``. The .sv package name is derived from the file stem by
    peakrdl-uvm, so the same template effectively names the package."""
    rdl_abs = rdl.resolve()

    anchors = []
    if input_dir is not None:
        anchors.append(
            (input_dir if input_dir.is_absolute() else (repo_root / input_dir)).resolve()
        )
    anchors.append(repo_root.resolve())

    rel: Optional[pathlib.Path] = None
    for anchor in anchors:
        try:
            rel = rdl_abs.relative_to(anchor)
            break
        except ValueError:
            continue
    if rel is None:
        rel = pathlib.Path(rdl.name)

    stem = format_template(filename_template, rel.stem)
    return out_root / rel.parent / f"{stem}.sv"


def format_template(template: str, name: str) -> str:
    try:
        return template.format(name=name)
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"template {template!r} references unknown placeholder: {exc}"
        ) from exc


def convert_one(rdl: pathlib.Path, args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    rdlc = RDLCompiler()
    incdirs = [str(p) for p in (args.incdir or [])]
    try:
        rdlc.compile_file(str(rdl), incl_search_paths=incdirs)
        root = rdlc.elaborate()
    except RDLCompileError:
        print(f"systemrdl-to-uvm: failed to compile {rdl}", file=sys.stderr)
        return 1

    target = output_file_for(rdl, args.output_dir, repo_root, args.input_dir, args.file_name)
    target.parent.mkdir(parents=True, exist_ok=True)

    exporter = UVMExporter()
    exporter.export(
        root.top,
        str(target),
        export_as_package=not args.as_include,
        reuse_class_definitions=not args.no_reuse_classes,
        use_uvm_factory=args.use_factory,
    )
    print(f"systemrdl-to-uvm: {rdl} -> {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="systemrdl-to-uvm",
        description="Generate a UVM register model from SystemRDL via peakrdl-uvm, "
                    "for use as a pre-commit hook.",
    )
    p.add_argument(
        "files", nargs="*", type=pathlib.Path,
        help=f"Files to convert. If omitted, scan ./{DEFAULT_INPUT_DIR}/**/*.rdl.",
    )
    p.add_argument("--input-dir", type=pathlib.Path, default=pathlib.Path(DEFAULT_INPUT_DIR),
                   help=f"Directory scanned for *.rdl when no files are passed (default: {DEFAULT_INPUT_DIR}).")
    p.add_argument("-I", "--incdir", type=pathlib.Path, action="append", default=[],
                   help="Add a search path for `include directives. May be repeated.")
    p.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                   help="Skip files whose path or basename matches the fnmatch pattern. May be repeated.")
    p.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path(DEFAULT_OUTPUT_DIR),
                   help=f"Root directory for generated SystemVerilog (default: {DEFAULT_OUTPUT_DIR}). "
                        "Layout mirrors the source tree under --input-dir.")
    p.add_argument("--file-name", default="{name}_uvm",
                   help="Template for the output file stem. '{name}' is the RDL filename stem "
                        "(default: '{name}_uvm'). The same stem becomes the SystemVerilog package name.")
    p.add_argument("--as-include", action="store_true",
                   help="Emit an includable header instead of a SystemVerilog package "
                        "(passes export_as_package=False to peakrdl-uvm).")
    p.add_argument("--no-reuse-classes", action="store_true",
                   help="Do not reuse class definitions across structurally identical RDL nodes. "
                        "Class names then follow the instance's hierarchical path.")
    p.add_argument("--use-factory", action="store_true",
                   help="Generate UVM factory registrations and create() instantiations. "
                        "Required if you want to override generated classes via the UVM factory.")
    return p


def collect_files(args: argparse.Namespace) -> list[pathlib.Path]:
    if args.files:
        return list(args.files)
    if args.input_dir.is_dir():
        return sorted(args.input_dir.rglob("*.rdl"))
    return []


def is_excluded(path: pathlib.Path, patterns: Iterable[str]) -> bool:
    s = str(path)
    name = path.name
    for pat in patterns:
        if fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = pathlib.Path.cwd()

    files = collect_files(args)
    rc = 0
    for f in files:
        if f.suffix != ".rdl":
            continue
        if is_excluded(f, args.exclude):
            continue
        if not f.is_file():
            print(f"systemrdl-to-uvm: skipping missing file {f}", file=sys.stderr)
            rc = 1
            continue
        rc |= convert_one(f, args, repo_root)
    return rc


if __name__ == "__main__":
    sys.exit(main())
