# vsc-truyen-co-dan-gian-viet-nam

Scanned books of folk tales and epics of Vietnam's ethnic minorities (Chăm,
Raglai, Ba Na, Mơ Nông, Hrê).

- `master_pdf/`: the complete scanned books.
- `truyen_nguoi_*/`: the same books split per story and per language version.
- `data/books/<book>/structure.yaml`: what each book contains (works, language
  versions, page ranges). Generated from the PDFs, then edited by hand.
- `pipeline/`: the local OCR pipeline for the Vietnamese text. See
  [pipeline/README.md](pipeline/README.md).
