from __future__ import annotations

import sys

from setup_london_mapped_data import setup


def main() -> None:
    package_dir = setup()
    sys.path.insert(0, str(package_dir))

    from london_mapped_data.export import main as export_main

    export_main()


if __name__ == "__main__":
    main()
