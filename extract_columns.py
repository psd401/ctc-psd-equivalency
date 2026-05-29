"""Column-aware text extraction from the TCC catalog.

Splits each page into left/right columns at the visible gutter and emits one
line per visual line, left column first, then right column. Drops the running
page header ("Tacoma Community College") and footer page-number block.
"""
import argparse
import pdfplumber

GUTTER_X = 290  # midline between the two text columns (page width 595pt)
HEADER_BOTTOM = 50  # ignore words above this (running header band)
FOOTER_TOP = 800  # ignore words below this (page-number band)


def lines_for_column(words, x_min, x_max, y_tol=2.5):
    """Group words within an x-range into lines by top-position."""
    col = [w for w in words if x_min <= w["x0"] < x_max]
    col.sort(key=lambda w: (w["top"], w["x0"]))
    lines = []
    for w in col:
        if not lines or abs(w["top"] - lines[-1]["top"]) > y_tol:
            lines.append({"top": w["top"], "words": [w]})
        else:
            lines[-1]["words"].append(w)
    out = []
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        out.append(" ".join(w["text"] for w in ln["words"]))
    return out


def extract_page(page):
    words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
    words = [w for w in words if HEADER_BOTTOM < w["top"] < FOOTER_TOP]
    left = lines_for_column(words, 0, GUTTER_X)
    right = lines_for_column(words, GUTTER_X, page.width)
    return left, right


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="tcc-2025-2026-catalog.pdf")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--out", default="tcc-columnwise.txt")
    args = ap.parse_args()

    with pdfplumber.open(args.pdf) as pdf:
        end = args.end or len(pdf.pages)
        with open(args.out, "w") as fh:
            for pno in range(args.start, end + 1):
                page = pdf.pages[pno - 1]
                left, right = extract_page(page)
                fh.write(f"\n@@@PAGE {pno}@@@\n")
                fh.write("---LEFT---\n")
                fh.write("\n".join(left))
                fh.write("\n---RIGHT---\n")
                fh.write("\n".join(right))
                fh.write("\n")
                if pno % 25 == 0:
                    print(f"  page {pno}/{end}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
