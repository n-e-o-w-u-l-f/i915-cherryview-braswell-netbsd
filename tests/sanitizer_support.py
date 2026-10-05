"""Run temporary ASan binaries with the NetBSD-required ELF PaX flag."""
from pathlib import Path
import platform
import subprocess
import tempfile


def run_sanitized(binary: Path, **options) -> subprocess.CompletedProcess:
    binary = binary.resolve(strict=True)
    if platform.system() == "NetBSD":
        # GCC's NetBSD ASan runtime requires a non-ASLR test executable.
        # Change only this disposable binary, never host/kernel policy.
        if not binary.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise ValueError("PaX adjustment is limited to temporary test binaries")
        subprocess.run(["/usr/sbin/paxctl", "+a", str(binary)], check=True)
    options.setdefault("check", True)
    return subprocess.run([str(binary)], **options)
