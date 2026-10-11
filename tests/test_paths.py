"""Cartridge folder stays next to the program."""

import unittest
from pathlib import Path

from argonaut.paths import cart_dir, font_file, install_dir


class PathTests(unittest.TestCase):
    def test_font_is_packed(self):
        self.assertTrue(font_file().is_file())

    def test_carts_live_in_the_repo_when_not_frozen(self):
        folder = cart_dir()
        self.assertEqual(folder, install_dir() / "carts")
        self.assertTrue((folder / "ferry.alc").is_file())
        self.assertEqual(install_dir(), Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
