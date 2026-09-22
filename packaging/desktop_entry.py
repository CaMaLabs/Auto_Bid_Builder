from __future__ import annotations

import sys

from auto_bid_builder import __version__
from auto_bid_builder.gui import main


def _smoke_test_requested() -> bool:
    return "--smoke-test" in sys.argv


if __name__ == "__main__":
    if _smoke_test_requested():
        # Used by the Windows release workflow to prove the frozen executable can
        # actually import the packaged application before publishing an installer.
        raise SystemExit(0)
    main()
