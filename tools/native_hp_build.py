"""Read-only admission and private-output guards for native HP ABI builds."""
import hashlib
import os
from pathlib import Path
import platform
import shlex
import socket
import stat


def require_hp_owner():
    """Keep native builds on the actual HP, without a historical fixed UID."""
    if (platform.system() != 'NetBSD'
            or platform.release().split('.')[0] != '11'
            or platform.machine() != 'amd64'
            or os.geteuid() == 0
            or socket.gethostname().split('.')[0] != 'hp-tpnw121'):
        raise ValueError('HP NetBSD11 amd64 non-root owner only')


def toolchain_paths(directory):
    """Resolve real executable tools; do not install, configure or run them."""
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('native toolchain directory required')
    tools = {'root': root}
    for key, name in (('make', 'nbmake-amd64'),
                      ('compiler', 'x86_64--netbsd-gcc')):
        path = (root / 'bin' / name).resolve(strict=True)
        if (not path.is_relative_to(root) or not path.is_file()
                or not os.access(path, os.X_OK)):
            raise ValueError('executable native tool outside/missing from toolchain: ' + name)
        tools[key] = path
    return tools


def configured_compiler(value, tools):
    """A selected toolchain must match the compiler in the native receipt."""
    command = shlex.split(value)
    if (len(command) != 1 or not Path(command[0]).is_absolute()
            or Path(command[0]).resolve(strict=True) != tools['compiler']):
        raise ValueError('configured compiler differs from explicit native toolchain')
    return command



def core_toolchain_receipt(core, tools):
    """Bind provider admission to the tools that produced the core ABI proof."""
    recorded_root = core.get('toolchain')
    if (not isinstance(recorded_root, str) or not recorded_root
            or not Path(recorded_root).is_absolute()):
        raise ValueError('core toolchain provenance missing; new native core receipt required')
    if Path(recorded_root).resolve(strict=True) != tools['root']:
        raise ValueError('core toolchain root differs from explicit native toolchain')
    recorded = core.get('native_tool_sha256')
    expected_paths = {str(tools[key]) for key in ('make', 'compiler')}
    if not isinstance(recorded, dict) or set(recorded) != expected_paths:
        raise ValueError('core tool hashes missing or paths differ; new native core receipt required')
    for path, expected in recorded.items():
        if (not isinstance(expected, str) or len(expected) != 64
                or any(ch not in '0123456789abcdef' for ch in expected)):
            raise ValueError('invalid native core tool digest')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('native core tool changed since ABI receipt: ' + path)
    return recorded.copy()

def private_output(path, inputs):
    """Admit a fresh output without touching any input or existing output."""
    path = Path(path)
    if path.name in ('', '.', '..'):
        raise ValueError('fresh private output name required')
    parent = path.parent.resolve(strict=True)
    output = parent / path.name
    if path.is_symlink() or output.exists():
        raise ValueError('preserve existing output or symlink')
    if any(output.is_relative_to(Path(item).resolve(strict=True)) for item in inputs):
        raise ValueError('private output overlaps protected inputs')
    info = parent.stat()
    sticky_shared = (info.st_mode & stat.S_ISVTX
                     and info.st_mode & stat.S_IWOTH
                     and info.st_mode & stat.S_IXOTH)
    if (not parent.is_dir()
            or (info.st_uid != os.geteuid() and not sticky_shared)
            or not os.access(parent, os.W_OK | os.X_OK)):
        raise ValueError('output parent must be writable owner directory or sticky shared temporary directory')
    return output


def create_private_output(output):
    """Atomic exclusive mkdir also preserves a path appearing after preflight."""
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    info = output.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise RuntimeError('new private output ownership or permissions differ')
