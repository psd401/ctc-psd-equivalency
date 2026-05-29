"""Inspect column geometry of a sample courses page in the TCC catalog PDF."""
import pdfplumber
import sys

PDF = "tcc-2025-2026-catalog.pdf"

# Sample known course-description pages from the earlier text scan:
#   Math department starts around p. 340 → first MATH courses ~ p. 345-347
#   Accounting "Courses" header at text-line 3220 → page ~ 47-48
SAMPLE_PAGES = [47, 343, 408]  # ACCT, MATH, PHYS

with pdfplumber.open(PDF) as pdf:
    for pno in SAMPLE_PAGES:
        page = pdf.pages[pno - 1]  # 0-indexed
        print(f"\n=== Page {pno} | width={page.width:.0f} height={page.height:.0f} ===")
        words = page.extract_words(x_tolerance=2, y_tolerance=3)
        # Histogram of word starting x-positions to find column boundaries
        xs = [w["x0"] for w in words]
        if xs:
            buckets = {}
            for x in xs:
                b = int(x // 20) * 20
                buckets[b] = buckets.get(b, 0) + 1
            print("x0 histogram (bucket→count):")
            for b in sorted(buckets):
                print(f"  {b:>4}: {'#' * min(buckets[b], 60)} ({buckets[b]})")
        # Show first 30 words with positions
        print("\nFirst 25 words:")
        for w in words[:25]:
            print(f"  x0={w['x0']:>6.1f} top={w['top']:>6.1f}  {w['text']}")
