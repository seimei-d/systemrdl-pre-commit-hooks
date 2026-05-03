from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Optional, Sequence

from systemrdl import RDLCompiler, RDLCompileError
from systemrdl.node import AddrmapNode, Node
from peakrdl_ipxact import IPXACTImporter
from peakrdl_systemrdl import SystemRDLExporter


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ipxact-to-systemrdl",
        description="Convert an IP-XACT XML file into a SystemRDL (.rdl) source file.",
    )
    p.add_argument("--input", "-i", required=True, type=pathlib.Path,
                   help="Path to the source IP-XACT XML file.")
    p.add_argument("--output", "-o", required=True, type=pathlib.Path,
                   help="Path to the target SystemRDL file. Parent directories are created.")
    p.add_argument("--flatten", action="store_true",
                   help="If the top imported addrmap wraps exactly one addrmap child "
                        "(the typical IP-XACT component/memoryMap/addressBlock layering), "
                        "export that child directly. Strips the foo__foo_mmap suffix.")
    return p


def unwrap_to_inner(node: Node) -> Node:
    """If `node` is an IP-XACT wrapper with a single addrmap child, return that child.
    Repeats until no more single-child addrmap nesting remains."""
    current = node
    while True:
        children = [c for c in current.children() if isinstance(c, AddrmapNode)]
        if len(children) == 1:
            current = children[0]
            continue
        return current


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.is_file():
        print(f"ipxact-to-systemrdl: error: input file not found: {args.input}", file=sys.stderr)
        return 1

    rdlc = RDLCompiler()
    try:
        IPXACTImporter(rdlc).import_file(str(args.input))
        root = rdlc.elaborate()
    except (RDLCompileError, ValueError, IndexError, KeyError) as exc:
        print(f"ipxact-to-systemrdl: error: failed to import {args.input}: {exc}", file=sys.stderr)
        return 1

    target_node: Node = root.top if args.flatten else root
    if args.flatten:
        target_node = unwrap_to_inner(target_node)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    SystemRDLExporter().export(target_node, str(args.output))

    if args.flatten:
        # peakrdl-systemrdl derives the top type name from scope_path, so even
        # after structural unwrapping it emits 'foo__foo_mmap__foo'. Trim to
        # the last '__'-segment in the first addrmap declaration of the file.
        text = args.output.read_text()
        new_text = re.sub(
            r'^(addrmap\s+)\S*__([A-Za-z_]\w*)(\s*\{)',
            r'\1\2\3',
            text, count=1, flags=re.MULTILINE,
        )
        if new_text != text:
            args.output.write_text(new_text)
    print(f"ipxact-to-systemrdl: {args.input} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
