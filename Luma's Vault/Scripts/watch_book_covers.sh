#!/bin/zsh
cd "$(dirname "$0")/.."
python3 Scripts/fetch_book_covers.py --watch
