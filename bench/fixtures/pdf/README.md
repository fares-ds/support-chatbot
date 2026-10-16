# Parser sample

`parser-sample.pdf` is written for the PDF parser bake-off (#16). It is not taken from a business. Real documents are still required before a parser is chosen.

Rebuild it from the repository root:

```sh
uv run --with reportlab --with arabic-reshaper python bench/fixtures/pdf/generate.py
```

reportlab and arabic-reshaper are not project dependencies. PyMuPDF is not used.

## Pages

Each page number is printed at the bottom as `Page N`.

1. **Listes en français.** A heading, a hyphen list, and a numbered list.
2. **Tableau avec en-tête.** A table whose first row is Service, Frais, Délai, then three rows: Virement 50 DA Immédiat, Carte 500 DA 3 jours, Recharge 0 DA Immédiat.
3. **Deux colonnes.** The left column begins "Colonne gauche" and the right column begins "Colonne droite".
4. **صفحة عربية: عنوان وقائمة وفقرة.** A heading, a hyphen list of three lines, and a two-line paragraph, in Arabic, read from the right. The letters are placed one at a time so the text layer stays in reading order.

## Font

Arabic is set in Noto Naskh Arabic Regular, embedded in the PDF. The file is `fonts/NotoNaskhArabic-Regular.ttf`, the hinted Regular face from [googlefonts/noto-fonts](https://github.com/googlefonts/noto-fonts) (`hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf`). The font's name table says Copyright 2019-2021 Google LLC. All Rights Reserved. The face is licensed under the SIL Open Font License 1.1; the text shipped with that repository is `fonts/OFL.txt` (Copyright 2018 The Noto Project Authors).
