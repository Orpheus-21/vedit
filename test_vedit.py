"""Check each vedit command on a short generated clip. Run: python3 -m unittest"""
import subprocess
import tempfile
import unittest
from pathlib import Path

import vedit


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout)


def streams(path):
    """Return the stream types of a file, for example ['video', 'audio']."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.split()


class VeditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # A 4 second clip with video and audio. The name has a space and a quote.
        self.clip = self.dir / "my 'clip'.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
             "-f", "lavfi", "-i", "sine=duration=4", "-shortest", str(self.clip)],
            check=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_trim(self):
        out = self.dir / "t.mp4"
        vedit.main(["trim", str(self.clip), "1", "3", "-o", str(out)])
        self.assertAlmostEqual(duration(out), 2, delta=0.2)

    def test_join(self):
        out = self.dir / "j.mp4"
        vedit.main(["join", str(self.clip), str(self.clip), "-o", str(out)])
        self.assertAlmostEqual(duration(out), 8, delta=0.3)

    def test_join_clips_with_different_size_and_frame_rate(self):
        big = self.dir / "big.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x480:rate=30:duration=2",
             "-f", "lavfi", "-i", "sine=duration=2", "-shortest", str(big)],
            check=True,
        )
        out = self.dir / "jd.mp4"
        vedit.main(["join", str(self.clip), str(big), "-o", str(out)])
        self.assertEqual(vedit.video_format(out)[:2], (320, 240))
        # The video stream and the audio stream must both be about 6 seconds long.
        self.assertAlmostEqual(duration(out), 6, delta=0.3)
        self.assertAlmostEqual(float(vedit.ffprobe(out, "stream=duration", "csv=p=0")), 6, delta=0.3)

    def test_join_clip_with_rotation_metadata(self):
        # Phone video has a turn of 90 degrees in the metadata. This needs ffmpeg 6.0 or later.
        turned = self.dir / "turned.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-display_rotation", "90", "-i", str(self.clip),
             "-c", "copy", str(turned)],
            check=True,
        )
        self.assertEqual(vedit.video_format(turned)[:2], (240, 320))
        out = self.dir / "jr.mp4"
        vedit.main(["join", str(turned), str(self.clip), "-o", str(out)])
        self.assertEqual(self.video_size(out), "240x320")
        self.assertAlmostEqual(duration(out), 8, delta=0.3)

    def test_join_with_a_clip_that_has_no_sound(self):
        silent = self.dir / "silent.mp4"
        vedit.main(["mute", str(self.clip), "-o", str(silent)])
        out = self.dir / "js.mp4"
        vedit.main(["join", str(self.clip), str(silent), "-o", str(out)])
        self.assertEqual(streams(out), ["video"])
        self.assertAlmostEqual(duration(out), 8, delta=0.3)

    def test_speed(self):
        out = self.dir / "s.mp4"
        vedit.main(["speed", str(self.clip), "2", "-o", str(out)])
        self.assertAlmostEqual(duration(out), 2, delta=0.3)

    def test_gif(self):
        out = self.dir / "g.gif"
        vedit.main(["gif", str(self.clip), "-o", str(out)])
        self.assertTrue(out.stat().st_size > 0)

    def test_compress(self):
        out = self.dir / "c.mp4"
        vedit.main(["compress", str(self.clip), "-o", str(out)])
        self.assertTrue(out.stat().st_size > 0)

    def test_audio(self):
        out = self.dir / "a.mp3"
        vedit.main(["audio", str(self.clip), "-o", str(out)])
        self.assertEqual(streams(out), ["audio"])
        self.assertAlmostEqual(duration(out), 4, delta=0.3)

    def test_mute(self):
        out = self.dir / "m.mp4"
        vedit.main(["mute", str(self.clip), "-o", str(out)])
        self.assertEqual(streams(out), ["video"])

    def test_frame(self):
        out = self.dir / "f.png"
        vedit.main(["frame", str(self.clip), "2", "-o", str(out)])
        size = subprocess.run(
            ["magick", "identify", "-format", "%wx%h", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual(size, "320x240")

    def test_frame_after_the_end(self):
        with self.assertRaises(SystemExit):
            vedit.main(["frame", str(self.clip), "99", "-o", str(self.dir / "late.png")])

    def video_size(self, path):
        return subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    def test_resize_width_only(self):
        out = self.dir / "r.mp4"
        vedit.main(["resize", str(self.clip), "--width", "160", "-o", str(out)])
        self.assertEqual(self.video_size(out), "160x120")

    def test_resize_odd_width(self):
        with self.assertRaises(SystemExit):
            vedit.main(["resize", str(self.clip), "--width", "161"])

    def test_resize_needs_a_size(self):
        with self.assertRaises(SystemExit):
            vedit.main(["resize", str(self.clip)])

    def test_rotate(self):
        out = self.dir / "rot.mp4"
        vedit.main(["rotate", str(self.clip), "90", "-o", str(out)])
        self.assertEqual(self.video_size(out), "240x320")

    def is_red(self, video, x, y):
        """Return True if the pixel at x, y in the first frame is red."""
        frame = self.dir / "px.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-frames:v", "1", str(frame)], check=True)
        test = f"%[fx:p{{{x},{y}}}.r>0.8&&p{{{x},{y}}}.g<0.3&&p{{{x},{y}}}.b<0.3]"
        return subprocess.run(["magick", str(frame), "-format", test, "info:"],
                              capture_output=True, text=True, check=True).stdout == "1"

    def test_watermark(self):
        logo = self.dir / "logo.png"
        subprocess.run(["magick", "-size", "40x40", "xc:red", str(logo)], check=True)
        top = self.dir / "wt.mp4"
        vedit.main(["watermark", str(self.clip), str(logo), "--width", "40",
                    "--position", "top-left", "-o", str(top)])
        self.assertTrue(self.is_red(top, 20, 20))
        self.assertEqual(streams(top), ["video", "audio"])
        bottom = self.dir / "wb.mp4"
        vedit.main(["watermark", str(self.clip), str(logo), "--width", "40", "-o", str(bottom)])
        self.assertTrue(self.is_red(bottom, 290, 210))
        self.assertFalse(self.is_red(bottom, 20, 20))

    def test_title_joins_with_clip(self):
        card = self.dir / "card.mp4"
        vedit.main(["title", "Hello 100%", "--seconds", "2", "--size", "320x240", "-o", str(card)])
        self.assertAlmostEqual(duration(card), 2, delta=0.2)
        out = self.dir / "tj.mp4"
        vedit.main(["join", str(card), str(self.clip), "-o", str(out)])
        self.assertAlmostEqual(duration(out), 6, delta=0.3)

    def test_title_text_is_not_read_as_a_file(self):
        # ImageMagick would try to open this path if the text were not escaped.
        card = self.dir / "at.mp4"
        vedit.main(["title", "@/no/such/file", "--size", "320x240", "-o", str(card)])
        self.assertTrue(card.stat().st_size > 0)

    def test_title_odd_size(self):
        with self.assertRaises(SystemExit):
            vedit.main(["title", "x", "--size", "321x240"])

    def test_sheet(self):
        out = self.dir / "sheet.png"
        vedit.main(["sheet", str(self.clip), "--cols", "3", "--rows", "2", "--width", "100", "-o", str(out)])
        size = subprocess.run(
            ["magick", "identify", "-format", "%wx%h", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout
        # Each tile is 100x75 plus 4 pixels of border on every side.
        self.assertEqual(size, f"{3 * 108}x{2 * 83}")

    # The encoder libx264 cannot write a clip with an odd size. ffmpeg fails after it opens the output.
    FAILING_ARGS = ["-vf", "scale=321:241", "-c:v", "libx264", "-pix_fmt", "yuv420p"]

    def test_failed_run_deletes_the_new_output(self):
        out = self.dir / "new.mp4"
        with self.assertRaises(SystemExit):
            vedit.run_ffmpeg(["-i", str(self.clip), *self.FAILING_ARGS], out, False)
        self.assertFalse(out.exists())

    def test_failed_run_keeps_an_output_that_existed(self):
        out = self.dir / "old.mp4"
        out.write_text("x")
        with self.assertRaises(SystemExit):
            vedit.run_ffmpeg(["-i", str(self.clip), *self.FAILING_ARGS], out, True)
        self.assertTrue(out.exists())

    def test_no_overwrite_without_force(self):
        out = self.dir / "o.mp4"
        out.write_text("x")
        with self.assertRaises(SystemExit):
            vedit.main(["compress", str(self.clip), "-o", str(out)])
        self.assertEqual(out.read_text(), "x")

    def test_missing_input(self):
        with self.assertRaises(SystemExit):
            vedit.main(["trim", str(self.dir / "none.mp4"), "1"])


if __name__ == "__main__":
    unittest.main()
