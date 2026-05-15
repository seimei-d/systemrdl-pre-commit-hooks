from __future__ import annotations

import pathlib
import shutil

import pytest

from pre_commit_scripts.systemrdl_to_uvm.cli import (
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    main,
    output_file_for,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample.rdl"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shutil.copy(FIXTURE, tmp_path / "sample.rdl")
    return tmp_path


def test_default_export_writes_package(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    out = repo / DEFAULT_OUTPUT_DIR / "sample_uvm.sv"
    assert out.is_file()
    text = out.read_text()
    assert "package sample_uvm" in text
    assert "uvm_reg" in text
    assert "uvm_reg_block" in text


def test_register_classes_emitted(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample_uvm.sv").read_text()
    # CTRL and STATUS regs from the fixture
    assert "sample__CTRL" in text
    assert "sample__STATUS" in text
    # field names from the fixture
    assert "enable" in text
    assert "mode" in text
    assert "ready" in text


def test_default_no_factory(repo):
    rc = main(["sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample_uvm.sv").read_text()
    assert "uvm_object_utils" not in text
    assert "type_id::create" not in text


def test_use_factory_emits_object_utils(repo):
    rc = main(["--use-factory", "sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample_uvm.sv").read_text()
    assert "uvm_object_utils" in text
    assert "type_id::create" in text


def test_as_include_drops_package_wrapper(repo):
    rc = main(["--as-include", "sample.rdl"])
    assert rc == 0
    text = (repo / DEFAULT_OUTPUT_DIR / "sample_uvm.sv").read_text()
    assert "package sample_uvm" not in text
    assert "endpackage" not in text
    # but the register classes are still there
    assert "sample__CTRL" in text


def test_custom_file_name_template(repo):
    rc = main(["--file-name", "{name}_ral", "sample.rdl"])
    assert rc == 0
    out = repo / DEFAULT_OUTPUT_DIR / "sample_ral.sv"
    assert out.is_file()
    assert "package sample_ral" in out.read_text()


def test_explicit_output_dir(repo, tmp_path):
    out_dir = tmp_path / "elsewhere"
    rc = main(["--output-dir", str(out_dir), "sample.rdl"])
    assert rc == 0
    assert (out_dir / "sample_uvm.sv").is_file()


def test_default_input_dir_scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / DEFAULT_INPUT_DIR / "block"
    src.mkdir(parents=True)
    shutil.copy(FIXTURE, src / "sample.rdl")

    rc = main([])
    assert rc == 0
    assert (tmp_path / DEFAULT_OUTPUT_DIR / "block" / "sample_uvm.sv").is_file()


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
    assert (repo / DEFAULT_OUTPUT_DIR / "keep_uvm.sv").is_file()
    assert not (repo / DEFAULT_OUTPUT_DIR / "skip_pkg_uvm.sv").exists()


def test_output_file_for_mirrors_input_dir(tmp_path):
    repo_root = tmp_path
    input_dir = repo_root / "regmap"
    nested = input_dir / "blocks" / "core"
    nested.mkdir(parents=True)
    rdl = nested / "core.rdl"
    rdl.write_text("")
    out = output_file_for(rdl, pathlib.Path("dv/uvm_regmodel"), repo_root, input_dir, "{name}_uvm")
    assert out == pathlib.Path("dv/uvm_regmodel") / "blocks" / "core" / "core_uvm.sv"
