from __future__ import annotations

import csv

import pytest

from app.data_tools import ToolError, inspect_dataset, run_python_analysis


def test_inspect_and_analyze_csv(tmp_path) -> None:
    dataset = tmp_path / "sample.csv"
    with dataset.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group", "value"])
        writer.writerow(["a", 10])
        writer.writerow(["a", 20])
        writer.writerow(["b", 7])

    details = inspect_dataset(str(dataset))
    assert details["rows"] == 3
    assert details["columns"] == ["group", "value"]

    result = run_python_analysis(
        str(dataset),
        'result = {"total": int(df["value"].sum())}',
        tmp_path,
    )
    assert result == {"result": {"total": 37}}


def test_analysis_blocks_imports(tmp_path) -> None:
    dataset = tmp_path / "sample.csv"
    dataset.write_text("value\n1\n", encoding="utf-8")
    with pytest.raises(ToolError, match="Imports"):
        run_python_analysis(str(dataset), "import os\nresult = 1", tmp_path)

