import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from okura_web.server import Handler, HttpError, web_build


class StaticBuildTest(unittest.TestCase):
    """画面（Vite でビルドした frontend/dist の形）の配り方。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        web = Path(self.tmp.name)
        (web / "assets").mkdir()
        (web / "index.html").write_text('<script type="module" src="/assets/index-abc123.js"></script>', encoding="utf-8")
        (web / "assets" / "index-abc123.js").write_text("export {};", encoding="utf-8")
        (web / "icon.svg").write_text("<svg/>", encoding="utf-8")
        self.web = web
        self.app = SimpleNamespace(cfg=SimpleNamespace(web_dir=web))

    def tearDown(self):
        self.tmp.cleanup()

    def static(self, path):
        return Handler._static(None, self.app, path)

    def test_index_is_never_cached(self):
        r = self.static("/")
        self.assertIn("/assets/index-abc123.js", r.body.decode())
        self.assertIn("no-store", r.headers["Cache-Control"])

    def test_hashed_asset_is_cached_on_the_device_only(self):
        r = self.static("/assets/index-abc123.js")
        self.assertEqual(r.body, b"export {};")
        self.assertIn("immutable", r.headers["Cache-Control"])
        self.assertIn("private", r.headers["Cache-Control"])

    def test_other_file_is_not_cached(self):
        r = self.static("/icon.svg")
        self.assertIn("no-store", r.headers["Cache-Control"])

    def test_screen_route_falls_back_to_index(self):
        r = self.static("/tax/2026/p-1/result")
        self.assertIn("/assets/index-abc123.js", r.body.decode())
        self.assertIn("no-store", r.headers["Cache-Control"])

    def test_missing_asset_is_404_not_index(self):
        # 古い版の部品を頼まれたとき、HTML を JS として返さない
        with self.assertRaises(HttpError) as c:
            self.static("/assets/index-old999.js")
        self.assertEqual(c.exception.status, 404)
        with self.assertRaises(HttpError):
            self.static("/missing.js")

    def test_path_cannot_escape(self):
        with self.assertRaises(HttpError):
            self.static("/assets/../../secret")

    def test_not_built_is_reported(self):
        (self.web / "index.html").unlink()
        with self.assertRaises(HttpError) as c:
            self.static("/")
        self.assertEqual(c.exception.status, 503)

    def test_build_changes_with_index(self):
        a = web_build(self.web)
        (self.web / "index.html").write_text('<script type="module" src="/assets/index-def456.js"></script>', encoding="utf-8")
        self.assertNotEqual(a, web_build(self.web))


if __name__ == "__main__":
    unittest.main()
