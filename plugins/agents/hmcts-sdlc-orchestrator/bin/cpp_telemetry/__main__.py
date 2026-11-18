"""Entry point: python3 "$CLAUDE_PLUGIN_ROOT/bin/cpp_telemetry" <command>.

Run as a directory there is no package context, so the package's parent
directory goes first on sys.path. Bytecode is not written: nothing persistent
may land under the plugin root.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cpp_telemetry import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))
