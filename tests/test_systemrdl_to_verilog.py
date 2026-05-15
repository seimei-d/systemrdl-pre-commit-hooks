from __future__ import annotations

import pathlib
import shutil

import pytest

from pre_commit_scripts.systemrdl_to_verilog.cli import (
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    main,
    output_dir_for,
    resolve_cpuif,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample.rdl"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shutil.copy(FIXTURE, tmp_path / "sample.rdl")
    return tmp_path


def test_default_export_writes_module_and_package(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    out_dir = repo / DEFAULT_OUTPUT_DIR / "sample"
    assert (out_dir / "sample.sv").is_file()
    assert (out_dir / "sample_pkg.sv").is_file()


def test_default_apb4_cpuif_uses_interface(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample.sv").read_text()
    # Default APB4 cpuif declares a SystemVerilog interface port.
    assert "apb4_intf" in text


def test_apb4_flat_cpuif_exposes_pprot(repo):
    rc = main(["--cpuif", "apb4-flat", "sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample.sv").read_text()
    # APB4 (flat) has pprot; APB3 does not.
    assert "pprot" in text.lower()


def test_axi4lite_flat_cpuif_switch(repo):
    rc = main(["--cpuif", "axi4-lite-flat", "sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample.sv").read_text()
    assert "awvalid" in text.lower() or "awaddr" in text.lower()


def test_explicit_output_dir_and_module_name(repo, tmp_path):
    out_dir = tmp_path / "elsewhere"
    rc = main([
        "--output-dir", str(out_dir),
        "--module-name", "{name}_regs",
        "--package-name", "{name}_regs_pkg",
        "sample.rdl",
    ])
    assert rc == 0
    assert (out_dir / "sample" / "sample_regs.sv").is_file()
    assert (out_dir / "sample" / "sample_regs_pkg.sv").is_file()


def test_active_high_reset(repo):
    rc = main(["--reset-polarity", "active-high", "sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample.sv").read_text()
    # peakrdl-regblock names the async active-high reset 'arst'.
    assert "posedge arst" in text


def test_active_low_async_reset_is_default(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample.sv").read_text()
    # Default: async active-low, named 'arst_n'.
    assert "negedge arst_n" in text


def test_sync_reset(repo):
    rc = main(["--reset-sync", "sync", "sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample.sv").read_text()
    # Synchronous reset: no edge on the reset in always_ff sensitivity lists.
    assert "negedge arst_n" not in text
    assert "posedge arst" not in text


def test_default_input_dir_scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / DEFAULT_INPUT_DIR / "block"
    src.mkdir(parents=True)
    shutil.copy(FIXTURE, src / "sample.rdl")

    rc = main([])
    assert rc == 0
    assert (tmp_path / DEFAULT_OUTPUT_DIR / "block" / "sample" / "sample.sv").is_file()


def test_default_input_dir_missing_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main([])
    assert rc == 0
    assert not (tmp_path / DEFAULT_OUTPUT_DIR).exists()


def test_non_rdl_file_skipped(repo):
    (repo / "notes.txt").write_text("hello")
    rc = main(["notes.txt"])
    assert rc == 0
    assert not (repo / DEFAULT_OUTPUT_DIR).exists()


def test_missing_file_returns_error(repo):
    rc = main(["does_not_exist.rdl"])
    assert rc == 1


def test_exclude_by_basename_glob(repo):
    (repo / "keep.rdl").write_text(FIXTURE.read_text())
    (repo / "skip_pkg.rdl").write_text(
        FIXTURE.read_text().replace("addrmap sample", "addrmap skipme")
    )
    rc = main(["--exclude", "*_pkg.rdl", "keep.rdl", "skip_pkg.rdl"])
    assert rc == 0
    assert (repo / DEFAULT_OUTPUT_DIR / "keep").is_dir()
    assert not (repo / DEFAULT_OUTPUT_DIR / "skip_pkg").exists()


def test_hwif_report_generated(repo):
    rc = main(["--hwif-report", "sample.rdl"])
    assert rc == 0
    assert (repo / DEFAULT_OUTPUT_DIR / "sample" / "sample_hwif.rpt").is_file()


def test_output_dir_for_mirrors_input_dir(tmp_path):
    repo_root = tmp_path
    input_dir = repo_root / "regmap"
    nested = input_dir / "blocks" / "core"
    nested.mkdir(parents=True)
    rdl = nested / "core.rdl"
    rdl.write_text("")
    out = output_dir_for(rdl, pathlib.Path("rtl/regmap"), repo_root, input_dir)
    assert out == pathlib.Path("rtl/regmap") / "blocks" / "core" / "core"


def test_resolve_cpuif_known_choices():
    from peakrdl_regblock.cpuif.base import CpuifBase
    for name in ("apb3", "apb4", "axi4-lite", "passthrough", "wishbone-flat"):
        cls = resolve_cpuif(name)
        assert issubclass(cls, CpuifBase)
