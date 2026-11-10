"""ATHEX -> MetaStock txt.

Χωρίς ορίσματα ανοίγει το παράθυρο.  Με ορίσματα δουλεύει από γραμμή εντολών:
  python athex_to_metastock.py 06/11/2026
  python athex_to_metastock.py --from 20/10/2026 --to 06/11/2026
  python athex_to_metastock.py --update
"""

import sys


def main():
    if len(sys.argv) > 1:
        from athex.cli import main as cli_main
        sys.exit(cli_main())
    from athex.gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
