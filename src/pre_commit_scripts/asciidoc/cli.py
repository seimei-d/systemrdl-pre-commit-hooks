from __future__ import annotations

import argparse
import fnmatch
import pathlib
import sys
from typing import Iterable, Iterator, List, Optional, Sequence

from systemrdl import RDLCompiler, RDLCompileError
from systemrdl.node import AddrmapNode, MemNode, Node

DEFAULT_INPUT_DIR = "regmap"
DEFAULT_OUTPUT_DIR_NAME = "asciidoc"


def _fmt_size(n: int) -> str:
    """Power-of-2 size in KiB / MiB / GiB; bytes for anything below 1 KiB."""
    GB = 1 << 30
    MB = 1 << 20
    KB = 1 << 10
    if n >= GB and n % GB == 0:
        return f"{n // GB} GiB"
    if n >= MB and n % MB == 0:
        return f"{n // MB} MiB"
    if n >= KB and n % KB == 0:
        return f"{n // KB} KiB"
    return f"{n} B"


def _fmt_params(node: Node) -> str:
    params = node.inst.parameters
    if not params:
        return "—"
    return ", ".join(f"{p.name}={p.get_value()}" for p in params)


def _block_type(node: Node) -> str:
    if isinstance(node, MemNode):
        return "mem"
    if isinstance(node, AddrmapNode):
        return node.inst.original_def.type_name or "(anonymous)"
    return type(node).__name__


def first_level_blocks(top: AddrmapNode) -> Iterator[Node]:
    for child in top.children():
        if isinstance(child, (AddrmapNode, MemNode)):
            yield child


def render_asciidoc(top: AddrmapNode) -> Optional[str]:
    children: List[Node] = list(first_level_blocks(top))
    if not children:
        return None

    headers = [
        "Block name", "Block type",
        "Start address", "End address",
        "Region size", "Parameters",
    ]
    table: List[List[str]] = [headers]
    for ch in children:
        start = ch.absolute_address
        end = start + ch.size - 1
        table.append([
            ch.inst_name,
            _block_type(ch),
            f"0x{start:08X}",
            f"0x{end:08X}",
            _fmt_size(ch.size),
            _fmt_params(ch),
        ])

    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]

    def fmt_row(cells: List[str]) -> str:
        padded = [c.ljust(w) for c, w in zip(cells[:-1], widths[:-1])]
        padded.append(cells[-1])
        return "| " + " | ".join(padded)

    lines = [
        f"= Address map: {top.inst_name}",
        "",
        '[cols="1,1,1,1,1,2",options="header"]',
        "|===",
        fmt_row(table[0]),
    ]
    lines.extend(fmt_row(row) for row in table[1:])
    lines += ["|===", ""]
    return "\n".join(lines)


def output_path(
    rdl: pathlib.Path,
    out_dir: Optional[pathlib.Path],
    repo_root: pathlib.Path,
    input_dir: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    base = out_dir if out_dir is not None else repo_root / DEFAULT_OUTPUT_DIR_NAME
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
            return base / rel.with_suffix(".adoc")
        except ValueError:
            continue
    return base / pathlib.Path(rdl.name).with_suffix(".adoc")


def convert_one(rdl: pathlib.Path, args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    rdlc = RDLCompiler()
    incdirs = [str(p) for p in (args.incdir or [])]
    try:
        rdlc.compile_file(str(rdl), incl_search_paths=incdirs)
        root = rdlc.elaborate()
    except RDLCompileError:
        print(f"asciidoc-addrmap: failed to compile {rdl}", file=sys.stderr)
        return 1

    target = output_path(rdl, args.output_dir, repo_root, args.input_dir)
    rendered = render_asciidoc(root.top)

    if rendered is None:
        # No top-level subsystems — no table to render.
        # Drop any previously generated .adoc so it doesn't go stale.
        if target.is_file():
            target.unlink()
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    print(f"asciidoc-addrmap: {rdl} -> {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="asciidoc-addrmap",
        description="Render the first-level address-map table from a SystemRDL file as AsciiDoc.",
    )
    p.add_argument(
        "files", nargs="*", type=pathlib.Path,
        help=f"Files to process. If omitted, scan ./{DEFAULT_INPUT_DIR}/**/*.rdl.",
    )
    p.add_argument(
        "--input-dir", type=pathlib.Path, default=pathlib.Path(DEFAULT_INPUT_DIR),
        help=f"Directory scanned for *.rdl when no files are passed (default: {DEFAULT_INPUT_DIR}).",
    )
    p.add_argument(
        "--output-dir", type=pathlib.Path, default=None,
        help=f"Root directory for generated .adoc. Defaults to <repo-root>/{DEFAULT_OUTPUT_DIR_NAME}.",
    )
    p.add_argument(
        "-I", "--incdir", type=pathlib.Path, action="append", default=[],
        help="Add a search path for `include directives. May be repeated.",
    )
    p.add_argument(
        "--exclude", action="append", default=[], metavar="PATTERN",
        help="Skip files whose path or basename matches the fnmatch pattern "
             "(e.g. 'lib/*', '*_pkg.rdl'). May be repeated.",
    )
    return p


def collect_files(args: argparse.Namespace) -> List[pathlib.Path]:
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
    rc = 0
    for f in collect_files(args):
        if f.suffix != ".rdl":
            continue
        if is_excluded(f, args.exclude):
            continue
        if not f.is_file():
            print(f"asciidoc-addrmap: skipping missing file {f}", file=sys.stderr)
            rc = 1
            continue
        rc |= convert_one(f, args, repo_root)
    return rc


if __name__ == "__main__":
    sys.exit(main())
