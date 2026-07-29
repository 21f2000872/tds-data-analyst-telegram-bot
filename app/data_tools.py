from __future__ import annotations

import ast
import ipaddress
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import pandas as pd


class ToolError(RuntimeError):
    pass


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ToolError("Only public HTTP(S) dataset URLs are allowed.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, None)}
    except socket.gaierror as exc:
        raise ToolError("The dataset hostname could not be resolved.") from exc
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global:
            raise ToolError("Private, loopback, and link-local dataset hosts are blocked.")


def download_dataset(url: str, run_dir: Path, max_bytes: int) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    current_url = url
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        for _ in range(6):
            _assert_public_url(current_url)
            with client.stream("GET", current_url, headers={"User-Agent": "tds-data-analyst-bot/1.0"}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ToolError("Dataset redirect had no destination.")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", "0") or "0")
                if content_length > max_bytes:
                    raise ToolError("Dataset exceeds the configured download limit.")
                suffix = Path(urlparse(current_url).path).suffix.lower() or ".data"
                destination = run_dir / f"dataset{suffix}"
                total = 0
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            output.close()
                            destination.unlink(missing_ok=True)
                            raise ToolError("Dataset exceeds the configured download limit.")
                        output.write(chunk)
                return {
                    "path": str(destination),
                    "bytes": total,
                    "source_url": current_url,
                }
    raise ToolError("Dataset redirected too many times.")


def _load_frame(path: Path) -> pd.DataFrame:
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
        tables = pd.read_html(path)
        if not tables:
            raise ToolError("No table was found in the HTML dataset.")
        return tables[0]
    raise ToolError(f"Unsupported dataset type: {suffix or 'unknown'}")


def inspect_dataset(path: str) -> dict[str, Any]:
    frame = _load_frame(Path(path))
    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "dtypes": {str(key): str(value) for key, value in frame.dtypes.items()},
        "sample": json.loads(frame.head(5).to_json(orient="records", date_format="iso")),
        "missing": {str(key): int(value) for key, value in frame.isna().sum().items()},
    }


_BLOCKED_NAMES = {
    "__import__", "breakpoint", "compile", "eval", "exec", "globals", "help",
    "input", "locals", "open", "quit", "exit", "memoryview",
}
_BLOCKED_ROOTS = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil", "requests",
    "httpx", "urllib", "builtins", "importlib",
}


def _validate_analysis_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ToolError(f"Analysis code is invalid: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise ToolError("Imports and global declarations are not allowed.")
        if isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES | _BLOCKED_ROOTS:
            raise ToolError(f"Blocked name in analysis: {node.id}")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_")
            or isinstance(node.value, ast.Name) and node.value.id in _BLOCKED_ROOTS
        ):
            raise ToolError("Private or system attributes are not allowed.")


def run_python_analysis(path: str, code: str, run_dir: Path) -> dict[str, Any]:
    """Run model-produced pandas code in an isolated child process with guardrails."""
    _validate_analysis_code(code)
    runner = Path(__file__).with_name("analysis_worker.py")
    result = subprocess.run(
        [sys.executable, "-I", str(runner)],
        input=json.dumps({"path": path, "code": code, "run_dir": str(run_dir)}),
        text=True,
        capture_output=True,
        timeout=20,
        cwd=run_dir,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Analysis failed."
        raise ToolError(message[-2000:])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError("Analysis did not return valid JSON.") from exc

