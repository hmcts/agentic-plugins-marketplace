"""Entry point: python3 -I -B "$CLAUDE_PLUGIN_ROOT/bin/cpp_telemetry" <command>.

Run as a directory there is no package context, so the package's parent
directory goes first on sys.path, and the package directory itself (which the
interpreter put there) is removed so no module of ours can shadow the standard
library. Every caller passes -B: nothing persistent may land under the plugin
root.
"""
import os
import sys

_PACKAGE_DIR = os.path.dirname(os.path.realpath(__file__))


def _is_package_dir(entry: str) -> bool:
    try:
        return os.path.realpath(entry or os.curdir) == _PACKAGE_DIR
    except (OSError, ValueError):
        return False


sys.path[:] = [entry for entry in sys.path if not _is_package_dir(entry)]
sys.path.insert(0, os.path.dirname(_PACKAGE_DIR))

from cpp_telemetry import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))
