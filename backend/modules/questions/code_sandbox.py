from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.config import settings


CODE_BLOCK_PATTERN = re.compile(
    r"```(?:c|cc|cpp|c\+\+)?\s*\n([\s\S]*?)```",
    flags=re.IGNORECASE,
)
FORBIDDEN_CODE_PATTERNS = {
    "PROCESS_EXECUTION": r"\b(?:system|popen|fork|exec[lvpe]*|CreateProcess)\s*\(",
    "NETWORK_ACCESS": r"\b(?:socket|connect|bind|listen|accept)\s*\(",
    "FILESYSTEM_ACCESS": r"#\s*include\s*[<\"]filesystem[>\"]|\b(?:fopen|freopen|remove|rename)\s*\(",
    "INLINE_ASSEMBLY": r"\b(?:asm|__asm__)\b",
}
ALLOWED_CPP_HEADERS = {
    "algorithm",
    "array",
    "cmath",
    "cstddef",
    "cstdint",
    "iostream",
    "limits",
    "map",
    "memory",
    "queue",
    "set",
    "stack",
    "string",
    "unordered_map",
    "unordered_set",
    "utility",
    "vector",
}


def validate_code_question(content: str) -> dict:
    blocks = [block.strip() for block in CODE_BLOCK_PATTERN.findall(content or "") if block.strip()]
    if not blocks:
        return {"applied": False, "passed": True, "status": "NOT_APPLICABLE", "issues": []}
    source = "\n\n".join(blocks)
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    issues = [
        code
        for code, pattern in FORBIDDEN_CODE_PATTERNS.items()
        if re.search(pattern, source, flags=re.IGNORECASE)
    ]
    includes = re.findall(r"^\s*#\s*include\s*([<\"][^>\"]+[>\"])", source, flags=re.MULTILINE)
    if any(
        include.startswith('"')
        or include[1:-1].strip() not in ALLOWED_CPP_HEADERS
        for include in includes
    ):
        issues.append("UNSAFE_INCLUDE")
    snapshot = {
        "contract_version": "cpp-syntax-sandbox-v1",
        "source_hash": source_hash,
        "source_bytes": len(source.encode("utf-8")),
        "limits": {"timeout_seconds": settings.code_sandbox_timeout_seconds, "memory_mb": 256},
        "execution": "SYNTAX_ONLY",
    }
    if len(source.encode("utf-8")) > settings.code_sandbox_max_source_bytes:
        issues.append("SOURCE_TOO_LARGE")
    if issues:
        return {
            "applied": True,
            "passed": False,
            "status": "BLOCKED",
            "issues": issues,
            "toolchain": snapshot,
        }
    if not settings.code_sandbox_enabled:
        return {
            "applied": True,
            "passed": False,
            "status": "DISABLED",
            "issues": ["SANDBOX_DISABLED"],
            "toolchain": snapshot,
        }
    compiler = shutil.which(settings.code_sandbox_cpp_compiler)
    if not compiler:
        return {
            "applied": True,
            "passed": False,
            "status": "UNAVAILABLE",
            "issues": ["CPP_COMPILER_UNAVAILABLE"],
            "toolchain": snapshot,
        }
    resource_limiter = shutil.which("prlimit")
    if not resource_limiter:
        return {
            "applied": True,
            "passed": False,
            "status": "UNAVAILABLE",
            "issues": ["RESOURCE_LIMITER_UNAVAILABLE"],
            "toolchain": snapshot,
        }
    version = subprocess.run(
        [compiler, "--version"],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    ).stdout.splitlines()[0][:240]
    snapshot.update(
        {
            "compiler_path": compiler,
            "compiler_version": version,
            "arguments": ["-std=c++17", "-fsyntax-only"],
            "resource_limiter": resource_limiter,
        }
    )
    with tempfile.TemporaryDirectory(prefix="qbank-code-check-") as temporary_dir:
        source_path = Path(temporary_dir) / "question.cpp"
        source_path.write_text(source, encoding="utf-8")
        command = [
            resource_limiter,
            "--cpu=2",
            f"--as={256 * 1024 * 1024}",
            f"--fsize={2 * 1024 * 1024}",
            "--nproc=8",
            "--",
            compiler,
            "-std=c++17",
            "-fsyntax-only",
            str(source_path),
        ]
        kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": settings.code_sandbox_timeout_seconds,
            "check": False,
            "cwd": temporary_dir,
            "env": {"PATH": str(Path(compiler).parent)},
        }
        try:
            completed = subprocess.run(command, **kwargs)
        except subprocess.TimeoutExpired:
            return {
                "applied": True,
                "passed": False,
                "status": "TIMEOUT",
                "issues": ["COMPILER_TIMEOUT"],
                "toolchain": snapshot,
            }
    diagnostics = (completed.stderr or completed.stdout or "").strip()[:2000]
    return {
        "applied": True,
        "passed": completed.returncode == 0,
        "status": "PASSED" if completed.returncode == 0 else "FAILED",
        "issues": [] if completed.returncode == 0 else ["CPP_SYNTAX_INVALID"],
        "diagnostics": diagnostics,
        "toolchain": snapshot,
    }
