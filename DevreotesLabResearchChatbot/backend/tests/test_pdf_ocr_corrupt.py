"""
Heuristics for when native PDF text should trigger OCR despite high character count.

Run: PYTHONPATH=. python -m unittest backend.tests.test_pdf_ocr_corrupt -v
"""

import unittest

from backend.app.pdf_ocr import native_pdf_text_looks_corrupted


class NativeCorruptionTests(unittest.TestCase):
    def test_short_text_not_corrupted(self):
        self.assertFalse(native_pdf_text_looks_corrupted("Hello world " * 10))

    def test_normal_article_not_corrupted(self):
        s = "Abstract. " + ("The Dictyostelium cells migrate toward cAMP. " * 50)
        self.assertFalse(native_pdf_text_looks_corrupted(s))

    def test_control_garbage_is_corrupted(self):
        junk = "".join(chr(i % 28 + 1) for i in range(2000))
        self.assertTrue(native_pdf_text_looks_corrupted(junk))

    def test_low_letter_ratio_long_string(self):
        s = " !@#$% " * 500
        self.assertTrue(native_pdf_text_looks_corrupted(s))


if __name__ == "__main__":
    unittest.main()
