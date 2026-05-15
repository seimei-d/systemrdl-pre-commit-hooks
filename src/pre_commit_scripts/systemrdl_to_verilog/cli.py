from __future__ import annotations

import argparse
import fnmatch
import importlib
import pathlib
import sys
from typing import Iterable, Optional, Sequence, Type

from systemrdl import RDLCompiler, RDLCompileError
from peakrdl_regblock import RegblockExporter
from peakrdl_regblock.cpuif.base import CpuifBase
from peakrdl_regblock.udps import ALL_UDPS

DEFAULT_INPUT_DIR = "regmap"
DEFAULT_OUTPUT_DIR = "rtl/regmap"

# choice name -> (module under peakrdl_regblock.cpuif, class name)
_CPUIF_CHOICES = {
    "apb3":              ("apb3",        "APB3_Cpuif"),
    "apb3-flat":         ("apb3",        "APB3_Cpuif_flattened"),
    "apb4":              ("apb4",        "APB4_Cpuif"),
    "apb4-flat":         ("apb4",        "APB4_Cpuif_flattened"),
    "axi4-lite":         ("axi4lite",    "AXI4Lite_Cpuif"),
    "axi4-lite-flat":    ("axi4lite",    "AXI4Lite_Cpuif_flattened"),
    "avalon":            ("avalon",      "Avalon_Cpuif"),
    "avalon-flat":       ("avalon",      "Avalon_Cpuif_flattened"),
    "obi":               ("obi",         "OBI_Cpuif"),
    "obi-flat":          ("obi",         "OBI_Cpuif_flattened"),
    "wishbone":          ("wishbone",    "Wishbone_Cpuif"),
    "wishbone-flat":     ("wishbone",    "Wishbone_Cpuif_flattened"),
    "passthrough":       ("passthrough", "PassthroughCpuif"),
}


def resolve_cpuif(name: str) -> Type[CpuifBase]:
    mod_name, cls_name = _CPUIF_CHOICES[name]
    mod = importlib.import_module(f"peakrdl_regblock.cpuif.{mod_name}")
    return getattr(mod, cls_name)


def output_dir_for(
    rdl: pathlib.Path,
    out_root: pathlib.Path,
    repo_root: pathlib.Path,
    input_dir: Optional[pathlib.Path],
) -> pathlib.Path:
    """Mirror the RDL's path under ``input_dir`` into ``out_root``.

    Each .rdl gets its own subdirectory (named after the file's stem) so that
    the .sv module and _pkg.sv files don't collide when several RDL sources
    sit side-by-side."""
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
            return out_root / rel.with_suffix("")
        except ValueError:
            continue
    return out_root / rdl.stem


def format_module_name(template: str, addrmap_name: str) -> str:
    try:
        return template.format(name=addrmap_name)
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"--module-name template {template!r} references unknown placeholder: {exc}"
        ) from exc


def convert_one(rdl: pathlib.Path, args: argparse.Namespace, repo_root: pathlib.Path) -> int:
    rdlc = RDLCompiler()
    for udp in ALL_UDPS:
        rdlc.register_udp(udp)
    incdirs = [str(p) for p in (args.incdir or [])]
    try:
        rdlc.compile_file(str(rdl), incl_search_paths=incdirs)
        root = rdlc.elaborate()
    except RDLCompileError:
        print(f"systemrdl-to-verilog: failed to compile {rdl}", file=sys.stderr)
        return 1

    target_dir = output_dir_for(rdl, args.output_dir, repo_root, args.input_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    top = root.top
    module_name = format_module_name(args.module_name, top.inst_name)
    package_name = format_module_name(args.package_name, top.inst_name)

    exporter = RegblockExporter()
    exporter.export(
        top,
        str(target_dir),
        cpuif_cls=resolve_cpuif(args.cpuif),
        module_name=module_name,
        package_name=package_name,
        default_reset_activelow=(args.reset_polarity == "active-low"),
        default_reset_async=(args.reset_sync == "async"),
        retime_read_fanin=args.retime_read_fanin,
        retime_read_response=args.retime_read_response,
        retime_external_reg=args.retime_external_reg,
        retime_external_regfile=args.retime_external_regfile,
        retime_external_mem=args.retime_external_mem,
        retime_external_addrmap=args.retime_external_addrmap,
        generate_hwif_report=args.hwif_report,
    )
    print(f"systemrdl-to-verilog: {rdl} -> {target_dir}/{module_name}.sv")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="systemrdl-to-verilog",
        description="Generate SystemVerilog register-block RTL from SystemRDL "
                    "via peakrdl-regblock, for use as a pre-commit hook.",
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
                        "Each .rdl gets its own subdirectory mirroring its location under --input-dir.")
    p.add_argument("--cpuif", choices=sorted(_CPUIF_CHOICES), default="apb4-flat",
                   help="CPU interface for the generated register block (default: apb4-flat). "
                        "Non-flat variants reference a SystemVerilog `interface` (e.g. apb4_intf) "
                        "that you must declare elsewhere in your design.")
    p.add_argument("--module-name", default="{name}",
                   help="Template for the SystemVerilog module name. "
                        "Use '{name}' as a placeholder for the top addrmap name (default: '{name}').")
    p.add_argument("--package-name", default="{name}_pkg",
                   help="Template for the SystemVerilog package name (default: '{name}_pkg').")
    p.add_argument("--reset-polarity", choices=["active-low", "active-high"], default="active-low",
                   help="Default reset polarity when the RDL does not specify one (default: active-low).")
    p.add_argument("--reset-sync", choices=["async", "sync"], default="async",
                   help="Default reset synchronicity when the RDL does not specify one (default: async).")
    p.add_argument("--retime-read-fanin", action="store_true",
                   help="Insert an extra retiming flop in the readback fan-in path (+1 read latency).")
    p.add_argument("--retime-read-response", action="store_true",
                   help="Insert an extra retiming flop between readback mux and CPU response logic (+1 read latency).")
    p.add_argument("--retime-external-reg", action="store_true",
                   help="Retime outputs to external `reg` components.")
    p.add_argument("--retime-external-regfile", action="store_true",
                   help="Retime outputs to external `regfile` components.")
    p.add_argument("--retime-external-mem", action="store_true",
                   help="Retime outputs to external `mem` components.")
    p.add_argument("--retime-external-addrmap", action="store_true",
                   help="Retime outputs to external `addrmap` components.")
    p.add_argument("--hwif-report", action="store_true",
                   help="Also emit a <module>_hwif.rpt describing hwif_in/hwif_out contents.")
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
            print(f"systemrdl-to-verilog: skipping missing file {f}", file=sys.stderr)
            rc = 1
            continue
        rc |= convert_one(f, args, repo_root)
    return rc


if __name__ == "__main__":
    sys.exit(main())
