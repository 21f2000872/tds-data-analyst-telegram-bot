from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def load_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".html", ".htm"}:
        return pd.read_html(path)[0]
    raise ValueError(f"Unsupported dataset type: {suffix}")


def make_json_safe(value):
    if isinstance(value, pd.DataFrame):
        return json.loads(value.to_json(orient="records", date_format="iso"))
    if isinstance(value, pd.Series):
        return json.loads(value.to_json(date_format="iso"))
    if isinstance(value, np.generic):
        return value.item()
    return value


def main() -> None:
    payload = json.load(sys.stdin)
    frame = load_frame(Path(payload["path"]).resolve())
    namespace = {
        "df": frame,
        "pd": pd,
        "np": np,
        "result": None,
        "__builtins__": {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        },
    }
    exec(compile(payload["code"], "<analysis>", "exec"), namespace, namespace)
    print(json.dumps({"result": make_json_safe(namespace.get("result"))}, default=str))


if __name__ == "__main__":
    main()

