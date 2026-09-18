#!/usr/bin/env python3
"""Assemble reviewed slide PNG exports into a portable seven-page PDF.

Run with bundled artifact Python (Pillow). The PPTX remains editable; the PDF
uses the exact inspected slide renders, at their original aspect ratio.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
images = [Image.open(ROOT/'scripts/.deck-build'/f'slide-{n}.png').convert('RGB') for n in range(1,8)]
images[0].save(ROOT/'submission/deck.pdf',save_all=True,append_images=images[1:],resolution=96)
