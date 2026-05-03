from __future__ import annotations

import argparse
import fnmatch
import pathlib
import re
import sys
from typing import Iterable, Optional, Sequence

from systemrdl import RDLCompiler, RDLCompileError
from peakrdl_ipxact import IPXACTExporter, Standard

DEFAULT_INPUT_DIR = "regmap"

_STD_BY_VERSION = {
    "2009": Standard.IEEE_1685_2009,
    "2014": Standard.IEEE_1685_2014,
}

_NS_RE = re.compile(r'xmlns(?::[\w-]+)?\s*=\s*"[^"]*?(1685-20\d\d)')


def detect_standard(xml_path: pathlib.Path) -> Optional[Standard]:
    """Sniff the IP-XACT version from an existing target file's xmlns."""
    if not xml_path.is_file():
        return None
    head = xml_path.read_text(errors="ignore")[:2048]
    match = _NS_RE.search(head)
    if not match:
        return None
    return _STD_BY_VERSION.get(match.group(1).split("-")[1])


def output_path(
    rdl: pathlib.Path,
    out_dir: Optional[pathlib.Path],
    repo_root: pathlib.Path,
    input_dir: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    base = out_dir if out_dir is not None else repo_root / "ipxact"
    rdl_abs = rdl.resolve()

    anchors = []
    if input_dir is not None:
        anchors.append(
            (input_dir if input_dir.is_absolute() else (repo_root / input_dir)).resolve()
        )
    anchors.append(repo_root.resolve())

    for anchor in anchors:
        try:
            rel = rdl_abs.relative_to(anchor)
            return base / rel.with_suffix(".xml")
        except ValueError:
            continue
    return base / pathlib.Path(rdl.name).with_suffix(".xml")


def resolve_standard(arg: str, target: pathlib.Path) -> Standard:
    if arg in _STD_BY_VERSION:
        return _STD_BY_VERSION[arg]
    return detect_standard(target) or Standard.IEEE_1685_2014


def convert_one(rdl: pathlib.Path, args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    rdlc = RDLCompiler()
    incdirs = [str(p) for p in (args.incdir or [])]
    try:
        rdlc.compile_file(str(rdl), incl_search_paths=incdirs)
        root = rdlc.elaborate()
    except RDLCompileError:
        print(f"systemrdl-to-ipxact: failed to compile {rdl}", file=sys.stderr)
        return 1

    target = output_path(rdl, args.output_dir, repo_root, args.input_dir)
    target.parent.mkdir(parents=True, exist_ok=True)

    standard = resolve_standard(args.standard, target)

    exporter = IPXACTExporter(
        vendor=args.vendor,
        library=args.library,
        version=args.version,
        standard=standard,
    )
    exporter.export(root.top, str(target))
    print(f"systemrdl-to-ipxact: {rdl} -> {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="systemrdl-to-ipxact",
        description="Convert SystemRDL (.rdl) files to IP-XACT XML for use as a pre-commit hook.",
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
                   help="Skip files whose path or basename matches the fnmatch "
                        "pattern (e.g. 'lib/*', '*_pkg.rdl'). May be repeated.")
    p.add_argument("--output-dir", type=pathlib.Path, default=None,
                   help="Root directory for generated XML. Defaults to <repo-root>/ipxact.")
    p.add_argument("--vendor", default="example.org", help="IP-XACT vendor (default: example.org).")
    p.add_argument("--library", default="mylibrary", help="IP-XACT library (default: mylibrary).")
    p.add_argument("--version", default="1.0", help="IP-XACT component version (default: 1.0).")
    p.add_argument("--standard", choices=["auto", "2009", "2014"], default="auto",
                   help="IP-XACT standard. 'auto' reuses the existing target file's "
                        "namespace if present, otherwise IEEE 1685-2014.")
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
            print(f"systemrdl-to-ipxact: skipping missing file {f}", file=sys.stderr)
            rc = 1
            continue
        rc |= convert_one(f, args, repo_root)
    return rc


if __name__ == "__main__":
    sys.exit(main())
