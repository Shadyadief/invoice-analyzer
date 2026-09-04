"""
sample_data_generator.py
--------------------------
Generates a small set of synthetic invoice images to use as test data for
the OCR pipeline, in the same spirit as public OCR benchmark datasets
(e.g. ICDAR-SROIE): plain receipts with a vendor header, invoice number,
date, line items, and a total.

Why synthetic instead of downloading SROIE/Kaggle directly:
This build environment only has network access to a fixed allow-list of
package registries (PyPI, npm, GitHub, etc.) and does NOT have access to
kaggle.com or most dataset hosts, so a live download isn't possible here.
To keep the MVP testable end-to-end today, this script produces clean,
varied invoice images locally. Swapping in a real dataset later (SROIE,
your own scanned invoices, etc.) requires no code changes -- just drop the
images into sample_invoices/ or upload them through the app.
"""

import os
import random
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = "sample_invoices"

VENDORS = [
    "Nile Office Supplies", "Cairo Tech Distributors", "Delta Print & Paper Co",
    "Alexandria Hardware Ltd", "Giza Electronics Wholesale",
]

PRODUCTS = [
    ("A4 Paper Ream", 12.50), ("Laser Toner Cartridge", 45.00),
    ("Wireless Mouse", 15.75), ("USB-C Cable 2m", 6.20),
    ("Office Chair", 89.99), ("LED Desk Lamp", 22.30),
    ("External HDD 1TB", 55.00), ("Whiteboard Marker Pack", 4.10),
]


def _font(size=18):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _make_invoice_image(idx: int) -> str:
    width, height = 700, 900
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    vendor = random.choice(VENDORS)
    inv_date = date.today() - timedelta(days=random.randint(0, 240))
    inv_number = f"INV-{2000 + idx}"

    y = 30
    draw.text((30, y), vendor, fill="black", font=_font(24)); y += 40
    draw.text((30, y), f"Invoice Number: {inv_number}", fill="black", font=_font(16)); y += 26
    draw.text((30, y), f"Date: {inv_date.strftime('%d/%m/%Y')}", fill="black", font=_font(16)); y += 40

    draw.line((30, y, width - 30, y), fill="black", width=1); y += 15
    draw.text((30, y), "Product", fill="black", font=_font(16))
    draw.text((330, y), "Qty", fill="black", font=_font(16))
    draw.text((420, y), "Unit Price", fill="black", font=_font(16))
    draw.text((560, y), "Total", fill="black", font=_font(16))
    y += 24
    draw.line((30, y, width - 30, y), fill="black", width=1); y += 15

    n_items = random.randint(2, 5)
    chosen = random.sample(PRODUCTS, n_items)
    grand_total = 0.0
    for name, price in chosen:
        qty = random.randint(1, 6)
        line_total = round(price * qty, 2)
        grand_total += line_total
        draw.text((30, y), name, fill="black", font=_font(15))
        draw.text((330, y), str(qty), fill="black", font=_font(15))
        draw.text((420, y), f"{price:.2f}", fill="black", font=_font(15))
        draw.text((560, y), f"{line_total:.2f}", fill="black", font=_font(15))
        y += 28

    y += 20
    draw.line((30, y, width - 30, y), fill="black", width=1); y += 15
    draw.text((400, y), f"Total Amount: {grand_total:.2f}", fill="black", font=_font(20))

    path = os.path.join(OUT_DIR, f"sample_invoice_{idx}.png")
    img.save(path)
    return path


def generate_samples(n: int = 6):
    os.makedirs(OUT_DIR, exist_ok=True)
    paths = []
    for i in range(1, n + 1):
        paths.append(_make_invoice_image(i))
    return paths


if __name__ == "__main__":
    random.seed(42)
    files = generate_samples(6)
    print(f"Generated {len(files)} sample invoices in '{OUT_DIR}/':")
    for f in files:
        print(" -", f)
