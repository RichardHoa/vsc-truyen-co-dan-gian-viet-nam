"""Ariya (Trường ca Chăm), `ariya-truong-ca-cham`: the code that parses this
book only. Rules that are data (pages, version kinds, note scopes, tables)
are in data/books/ariya-truong-ca-cham/assemble.yaml.

  clean.py        shared clean + verse turnover lines, forced page modes
  toc.py          shared toc + this book's mục lục layout (rows without numbers)
  booktoc.py      the mục lục nested and located in the body -> toc.json
  notes.py        Chú thích blocks and their calls -> notes.json
  superscript.py  raised note calls found on a 600 dpi render
  tables.py       the ruled transliteration tables, read cell by cell
  assemble.py     book.md
"""

from .assemble import assemble
from .clean import clean_book
from .toc import build_toc

__all__ = ["assemble", "build_toc", "clean_book"]
