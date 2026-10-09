"""Truyện cổ dân gian Chăm, `truyen-co-dan-gian-cham`: the code that parses
this book only. Rules that are data (pages, the mục lục, the intro) are in
data/books/truyen-co-dan-gian-cham/assemble.yaml.

  clean.py     shared clean + footnotes under the rule, scene breaks, drop caps
  dropcap.py   the ornamental capital opening every section
  toc.py       the mục lục, one row per entry -> toc.generated.yaml
  booktoc.py   mục lục + page headings + structure.yaml -> toc.json
  notes.py     each page's footnotes and their calls -> notes.json
  assemble.py  book.md
"""

from .assemble import assemble
from .clean import clean_book
from .toc import build_toc

__all__ = ["assemble", "build_toc", "clean_book"]
