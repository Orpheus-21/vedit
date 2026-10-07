"""Check each vedit command on a short generated clip. Run: python3 -m unittest"""
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import vedit

needs_ffmpeg = unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe are not installed")
needs_imagemagick = unittest.skipUnless(
    shutil.which("magick") or (shutil.which("convert") and shutil.which("montage")),
    "ImageMagick is not installed")


def probe(path, entries, fmt="csv=p=0", select=None):
    """Return the text that ffprobe prints for the entries of a file."""
    cmd = ["ffprobe", "-v", "error"]
    if select:
        cmd += ["-select_streams", select]
    cmd += ["-show_entries", entries, "-of", fmt, str(path)]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def duration(path):
    return float(probe(path, "format=duration"))


def streams(path):
    """Return the stream types of a file, for example ['video', 'audio']."""
    return probe(path, "stream=codec_type").split()


def video_size(path):
    """Return the size of the first video stream, for example '320x240'."""
    return probe(path, "stream=width,height", "csv=p=0:s=x", "v:0")


@needs_ffmpeg
class VeditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One clip for all tests. The tests do not change it. The clip has video and audio,
        # it is 4 seconds long, and its name has a space and a quote.
        cls.clip_folder = tempfile.TemporaryDirectory()
        cls.clip = Path(cls.clip_folder.name) / "my 'clip'.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
             "-f", "lavfi", "-i", "sine=duration=4", "-shortest", str(cls.clip)],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.clip_folder.cleanup()

    def setUp(self):
        # A new folder for the output files of each test.
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_trim(self):
        out = self.dir / "t.mp4"
        vedit.main(["trim", str(self.clip), "1", "3", "-o", str(out)])
        self.assertAlmostEqual(duration(out), 2, delta=0.2)

    def test_trim_is_exact_between_keyframes(self):
        # This clip has only one keyframe, at the start. A cut at 1.5 s is not on a keyframe.
        sparse = self.dir / "sparse.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
             "-c:v", "libx264", "-g", "1000", str(sparse)],
            check=True,
        )
        out = self.dir / "ts.mp4"
        vedit.main(["trim", str(sparse), "1.5", "3", "-o", str(out)])
        self.assertAlmostEqual(duration(out), 1.5, delta=0.1)
        to_end = self.dir / "te.mp4"
        vedit.main(["trim", str(sparse), "3", "-o", str(to_end)])
        self.assertAlmostEqual(duration(to_end), 1, delta=0.1)

    def test_trim_fast_copies_the_streams(self):
        # A yuv444p clip keeps its pixel format only if ffmpeg does not encode it again.
        wide = self.dir / "wide_fast.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
             "-f", "lavfi", "-i", "sine=duration=4", "-pix_fmt", "yuv444p", "-c:v", "libx264", "-g", "25",
             "-shortest", str(wide)],
            check=True,
        )
        fast = self.dir / "fast.mp4"
        vedit.main(["trim", str(wide), "1", "3", "--fast", "-o", str(fast)])
        self.assertEqual(probe(fast, "stream=pix_fmt", select="v:0"), "yuv444p")
        # The keyframes are 1 second apart and the cut is on a keyframe.
        self.assertAlmostEqual(duration(fast), 2, delta=0.3)
        exact = self.dir / "exact.mp4"
        vedit.main(["trim", str(wide), "1", "3", "-o", str(exact)])
        self.assertEqual(probe(exact, "stream=pix_fmt", select="v:0"), "yuv420p")

    def test_trim_without_an_end_time_goes_to_the_end(self):
        out = self.dir / "te2.mp4"
        vedit.main(["trim", str(self.clip), "1", "-o", str(out)])
        self.assertAlmostEqual(duration(out), 3, delta=0.2)

    def test_speed_factor_out_of_range(self):
        for factor in ("0.25", "101"):
            with self.subTest(factor=factor), self.assertRaises(SystemExit) as caught:
                vedit.main(["speed", str(self.clip), factor, "-o", str(self.dir / "never.mp4")])
            self.assertIn("from 0.5 to 100", str(caught.exception.code))
            self.assertFalse((self.dir / "never.mp4").exists())

    def test_speed_on_a_clip_with_no_sound(self):
        silent = self.dir / "quiet.mp4"
        vedit.main(["mute", str(self.clip), "-o", str(silent)])
        out = self.dir / "qs.mp4"
        vedit.main(["speed", str(silent), "2", "-o", str(out)])
        self.assertEqual(streams(out), ["video"])
        self.assertAlmostEqual(duration(out), 2, delta=0.3)

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
        self.assertEqual(video_size(out), "240x320")
        self.assertAlmostEqual(duration(out), 8, delta=0.3)

    def test_join_uses_the_average_frame_rate(self):
        # This clip keeps 4 of 10 frames at random times. The base rate is 25 and the average is about 10.
        vfr = self.dir / "vfr.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=8",
             "-vf", "select='gt(random(1),0.6)'", "-fps_mode", "vfr", "-c:v", "libx264", str(vfr)],
            check=True,
        )
        self.assertTrue(8 < Fraction(vedit.video_format(vfr)[2]) < 13)
        out = self.dir / "jv.mp4"
        vedit.main(["join", str(vfr), str(self.clip), "-o", str(out)])
        self.assertTrue(8 < Fraction(vedit.video_format(out)[2]) < 13)

    def test_video_format_falls_back_to_the_base_frame_rate(self):
        probe = json.dumps({"streams": [
            {"width": 320, "height": 240, "r_frame_rate": "25/1", "avg_frame_rate": "0/0"}]})
        with mock.patch("vedit.ffprobe", return_value=probe):
            self.assertEqual(vedit.video_format("clip.mp4"), (320, 240, "25/1"))

    def test_join_with_a_crossfade(self):
        out = self.dir / "jx.mp4"
        vedit.main(["join", str(self.clip), str(self.clip), "--crossfade", "1", "-o", str(out)])
        # Two clips of 4 seconds with a crossfade of 1 second are 7 seconds long.
        self.assertAlmostEqual(duration(out), 7, delta=0.3)
        self.assertAlmostEqual(float(probe(out, "stream=duration", select="v:0")), 7, delta=0.3)
        self.assertEqual(streams(out), ["video", "audio"])
        three = self.dir / "jx3.mp4"
        vedit.main(["join", str(self.clip), str(self.clip), str(self.clip), "--crossfade", "1.5", "-o", str(three)])
        self.assertAlmostEqual(duration(three), 9, delta=0.4)

    def test_join_with_a_crossfade_and_no_sound(self):
        silent = self.dir / "quiet_x.mp4"
        vedit.main(["mute", str(self.clip), "-o", str(silent)])
        out = self.dir / "jxs.mp4"
        vedit.main(["join", str(silent), str(silent), "--crossfade", "1", "-o", str(out)])
        self.assertEqual(streams(out), ["video"])
        self.assertAlmostEqual(duration(out), 7, delta=0.3)

    def test_crossfade_must_be_shorter_than_the_clips(self):
        with self.assertRaises(SystemExit) as caught:
            vedit.main(["join", str(self.clip), str(self.clip), "--crossfade", "4",
                        "-o", str(self.dir / "never_x.mp4")])
        self.assertIn("shorter than each clip", str(caught.exception.code))

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

    @needs_imagemagick
    def test_gif_and_sheet_do_not_enlarge_a_small_clip(self):
        # The clip is 320 pixels wide. The default GIF width is 480.
        gif = self.dir / "small.gif"
        vedit.main(["gif", str(self.clip), "-o", str(gif)])
        self.assertEqual(video_size(gif), "320x240")
        narrow = self.dir / "narrow.gif"
        vedit.main(["gif", str(self.clip), "--width", "100", "-o", str(narrow)])
        self.assertEqual(video_size(narrow), "100x75")
        sheet = self.dir / "wide_sheet.png"
        vedit.main(["sheet", str(self.clip), "--cols", "2", "--rows", "1", "--width", "500",
                    "-o", str(sheet)])
        # Each frame is 320x240 plus 4 pixels of border on every side.
        self.assertEqual(video_size(sheet), "656x248")

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
        self.assertEqual(video_size(out), "320x240")

    def test_frame_after_the_end(self):
        with self.assertRaises(SystemExit):
            vedit.main(["frame", str(self.clip), "99", "-o", str(self.dir / "late.png")])

    def test_resize_width_only(self):
        out = self.dir / "r.mp4"
        vedit.main(["resize", str(self.clip), "--width", "160", "-o", str(out)])
        self.assertEqual(video_size(out), "160x120")

    def test_resize_odd_width(self):
        with self.assertRaises(SystemExit):
            vedit.main(["resize", str(self.clip), "--width", "161"])

    def test_resize_needs_a_size(self):
        with self.assertRaises(SystemExit):
            vedit.main(["resize", str(self.clip)])

    def test_rotate(self):
        out = self.dir / "rot.mp4"
        vedit.main(["rotate", str(self.clip), "90", "-o", str(out)])
        self.assertEqual(video_size(out), "240x320")

    def is_red(self, video, x, y):
        """Return True if the pixel at x, y in the first frame is red."""
        pixel = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(video), "-frames:v", "1",
             "-vf", f"format=rgb24,crop=1:1:{x}:{y}", "-f", "rawvideo", "-"],
            capture_output=True, check=True,
        ).stdout
        red, green, blue = pixel
        return red > 204 and green < 77 and blue < 77

    def make_logo(self, name):
        """Make a red square PNG file of 40x40 pixels and return its path."""
        logo = self.dir / name
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=red:s=40x40",
             "-frames:v", "1", str(logo)],
            check=True,
        )
        return logo

    def test_watermark(self):
        logo = self.make_logo("logo.png")
        top = self.dir / "wt.mp4"
        vedit.main(["watermark", str(self.clip), str(logo), "--width", "40",
                    "--position", "top-left", "-o", str(top)])
        self.assertTrue(self.is_red(top, 20, 20))
        self.assertEqual(streams(top), ["video", "audio"])
        bottom = self.dir / "wb.mp4"
        vedit.main(["watermark", str(self.clip), str(logo), "--width", "40", "-o", str(bottom)])
        self.assertTrue(self.is_red(bottom, 290, 210))
        self.assertFalse(self.is_red(bottom, 20, 20))

    def test_watermark_positions(self):
        # The clip is 320x240, the logo is 40x40, and the margin is 10.
        logo = self.make_logo("logo_pos.png")
        for position, (x, y) in {
            "top-left": (30, 30),
            "top-right": (290, 30),
            "bottom-left": (30, 210),
            "bottom-right": (290, 210),
            "center": (160, 120),
        }.items():
            with self.subTest(position=position):
                out = self.dir / f"pos_{position}.mp4"
                vedit.main(["watermark", str(self.clip), str(logo), "--width", "40",
                            "--position", position, "-o", str(out)])
                self.assertTrue(self.is_red(out, x, y))

    @needs_imagemagick
    def test_title_joins_with_clip(self):
        card = self.dir / "card.mp4"
        vedit.main(["title", "Hello 100%", "--seconds", "2", "--size", "320x240", "-o", str(card)])
        self.assertAlmostEqual(duration(card), 2, delta=0.2)
        out = self.dir / "tj.mp4"
        vedit.main(["join", str(card), str(self.clip), "-o", str(out)])
        self.assertAlmostEqual(duration(out), 6, delta=0.3)

    @needs_imagemagick
    def test_title_text_is_not_read_as_a_file(self):
        # ImageMagick would try to open this path if the text were not escaped.
        card = self.dir / "at.mp4"
        vedit.main(["title", "@/no/such/file", "--size", "320x240", "-o", str(card)])
        self.assertTrue(card.stat().st_size > 0)

    def test_title_odd_size(self):
        with self.assertRaises(SystemExit):
            vedit.main(["title", "x", "--size", "321x240"])

    def test_title_empty_text(self):
        with self.assertRaises(SystemExit):
            vedit.main(["title", "", "--size", "320x240"])

    def test_title_text_with_only_spaces_writes_no_file(self):
        for text in ("", "   ", "\t"):
            out = self.dir / "empty.mp4"
            with self.subTest(text=text), self.assertRaises(SystemExit) as caught:
                vedit.main(["title", text, "--size", "320x240", "-o", str(out)])
            self.assertIn("title text must not be empty", str(caught.exception.code))
            self.assertFalse(out.exists())

    @needs_imagemagick
    def test_sheet(self):
        out = self.dir / "sheet.png"
        vedit.main(["sheet", str(self.clip), "--cols", "3", "--rows", "2", "--width", "100", "-o", str(out)])
        # Each tile is 100x75 plus 4 pixels of border on every side.
        self.assertEqual(video_size(out), f"{3 * 108}x{2 * 83}")

    def test_commands_that_encode_accept_an_odd_size(self):
        odd = self.dir / "odd.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=321x241:rate=25:duration=2",
             "-f", "lavfi", "-i", "sine=duration=2", "-pix_fmt", "yuv420p", "-c:v", "mpeg4",
             "-shortest", str(odd)],
            check=True,
        )
        logo = self.make_logo("logo_odd.png")
        cases = {
            "trim": (["trim", str(odd), "0", "1"], "320x240"),
            "speed": (["speed", str(odd), "2"], "320x240"),
            "rotate": (["rotate", str(odd), "90"], "240x320"),
            "compress": (["compress", str(odd)], "320x240"),
            "watermark": (["watermark", str(odd), str(logo)], "320x240"),
            "join": (["join", str(odd), str(odd)], "320x240"),
        }
        for name, (args, size) in cases.items():
            with self.subTest(command=name):
                out = self.dir / f"odd_{name}.mp4"
                vedit.main([*args, "-o", str(out)])
                self.assertEqual(video_size(out), size)

    def test_commands_that_encode_write_yuv420p(self):
        # A yuv444p clip makes libx264 write the profile High 4:4:4, which many players cannot play.
        wide = self.dir / "wide.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
             "-f", "lavfi", "-i", "sine=duration=2", "-pix_fmt", "yuv444p", "-c:v", "libx264",
             "-shortest", str(wide)],
            check=True,
        )
        logo = self.make_logo("logo_wide.png")
        cases = {
            "trim": ["trim", str(wide), "0", "1"],
            "speed": ["speed", str(wide), "2"],
            "rotate": ["rotate", str(wide), "90"],
            "compress": ["compress", str(wide)],
            "watermark": ["watermark", str(wide), str(logo)],
            "join": ["join", str(wide), str(wide)],
        }
        for name, args in cases.items():
            with self.subTest(command=name):
                out = self.dir / f"wide_{name}.mp4"
                vedit.main([*args, "-o", str(out)])
                self.assertEqual(vedit.ffprobe(out, "stream=pix_fmt", "csv=p=0"), "yuv420p")

    @needs_imagemagick
    def test_file_names_with_a_colon(self):
        # ffmpeg reads "a:" as a protocol name. ImageMagick reads it as a format name.
        # The bug shows only with relative paths, so the test runs in the temporary folder.
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.dir)
        Path("a:b.mp4").write_bytes(self.clip.read_bytes())
        for args, name in [
            (["mute", "a:b.mp4"], "a:b_mute.mp4"),
            (["frame", "a:b.mp4", "1"], "a:b_frame.png"),
            (["sheet", "a:b.mp4", "--cols", "2", "--rows", "1"], "a:b_sheet.jpg"),
            (["join", "a:b.mp4", "a:b.mp4"], "a:b_joined.mp4"),
            (["title", "x", "--size", "320x240", "-o", "t:1.mp4"], "t:1.mp4"),
        ]:
            with self.subTest(command=args[0]):
                vedit.main(args)
                self.assertTrue(Path(name).stat().st_size > 0)

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

    def test_force_before_and_after_the_command_name(self):
        out = self.dir / "f.mp4"
        out.write_text("x")
        for args in (["-f", "mute", str(self.clip)], ["mute", str(self.clip), "-f"]):
            with self.subTest(args=args):
                out.write_text("x")
                vedit.main([*args, "-o", str(out)])
                self.assertEqual(streams(out), ["video"])

    def test_output_must_not_be_the_input(self):
        before = self.clip.read_bytes()
        with self.assertRaises(SystemExit) as caught:
            vedit.main(["-f", "mute", str(self.clip), "-o", str(self.clip)])
        self.assertIn("same file", str(caught.exception.code))
        self.assertEqual(self.clip.read_bytes(), before)

    def test_ctrl_c_deletes_the_new_output_and_exits_with_130(self):
        out = self.dir / "i.mp4"

        def interrupt(cmd, *args, **kwargs):
            # ffmpeg has written a part of the output when the user presses Ctrl+C.
            Path(cmd[-1][len("file:"):]).write_text("part")
            raise KeyboardInterrupt

        stderr = io.StringIO()
        with mock.patch("vedit.subprocess.run", side_effect=interrupt), \
                contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            vedit.main(["mute", str(self.clip), "-o", str(out)])
        self.assertEqual(caught.exception.code, 130)
        self.assertEqual(stderr.getvalue(), "vedit: interrupted\n")
        self.assertFalse(out.exists())

    def test_bad_numbers_stop_with_a_usage_error(self):
        clip = str(self.clip)
        for args in (
            ["compress", clip, "--crf", "99"],
            ["compress", clip, "--crf", "-1"],
            ["gif", clip, "--fps", "0"],
            ["gif", clip, "--width", "0"],
            ["title", "x", "--fps", "0"],
            ["title", "x", "--seconds", "0"],
            ["title", "x", "--seconds", "nan"],
            ["sheet", clip, "--width", "0"],
            ["sheet", clip, "--cols", "0"],
            ["sheet", clip, "--rows", "0"],
        ):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as caught:
                vedit.main(args)
            # The code 2 is the usage error of argparse. ffmpeg errors give the code 1.
            self.assertEqual(caught.exception.code, 2)

    def run_in_temporary_folder(self):
        """Go into the temporary folder with a copy of the clip named clip.mp4 and a logo."""
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.dir)
        Path("clip.mp4").write_bytes(self.clip.read_bytes())
        Path("logo.png").write_bytes(self.make_logo("logo_names.png").read_bytes())

    def test_default_output_names(self):
        # The names must match the table in the README.
        self.run_in_temporary_folder()
        for args, name in [
            (["trim", "clip.mp4", "0", "1"], "clip_trim.mp4"),
            (["join", "clip.mp4", "clip.mp4"], "clip_joined.mp4"),
            (["speed", "clip.mp4", "2"], "clip_x2.mp4"),
            (["gif", "clip.mp4"], "clip_gif.gif"),
            (["compress", "clip.mp4"], "clip_small.mp4"),
            (["resize", "clip.mp4", "--width", "160"], "clip_resized.mp4"),
            (["rotate", "clip.mp4", "90"], "clip_rot90.mp4"),
            (["watermark", "clip.mp4", "logo.png"], "clip_mark.mp4"),
            (["audio", "clip.mp4"], "clip_audio.mp3"),
            (["mute", "clip.mp4"], "clip_mute.mp4"),
            (["frame", "clip.mp4", "1"], "clip_frame.png"),
        ]:
            with self.subTest(command=args[0]):
                vedit.main(args)
                self.assertTrue(Path(name).stat().st_size > 0)

    @needs_imagemagick
    def test_default_output_names_with_imagemagick(self):
        self.run_in_temporary_folder()
        for args, name in [
            (["sheet", "clip.mp4", "--cols", "2", "--rows", "1"], "clip_sheet.jpg"),
            (["title", "x", "--size", "320x240", "--seconds", "1"], "title.mp4"),
        ]:
            with self.subTest(command=args[0]):
                vedit.main(args)
                self.assertTrue(Path(name).stat().st_size > 0)

    def test_a_missing_tool_gives_a_clear_error(self):
        out = str(self.dir / "never.mp4")
        for missing, args in [
            ("ffmpeg", ["mute", str(self.clip), "-o", out]),
            ("ffprobe", ["join", str(self.clip), str(self.clip), "-o", out]),
            ("ImageMagick", ["title", "x", "-o", out]),
        ]:
            hidden = {"ffmpeg", "ffprobe"} if missing == "ImageMagick" else {missing}
            hidden = {"magick", "convert", "montage"} if missing == "ImageMagick" else hidden

            def which(name, hidden=hidden):
                return None if name in hidden else "/usr/bin/" + name

            with self.subTest(missing=missing), mock.patch("vedit.shutil.which", side_effect=which), \
                    self.assertRaises(SystemExit) as caught:
                vedit.main(args)
            self.assertIn(f"{missing} is not installed", str(caught.exception.code))
            self.assertFalse(Path(out).exists())

    @needs_imagemagick
    def test_title_with_an_unknown_color(self):
        # ImageMagick only prints a warning for an unknown color and exits with the code 0.
        for option in ("--bg", "--fg"):
            out = self.dir / f"bad{option}.mp4"
            with self.subTest(option=option), self.assertRaises(SystemExit) as caught:
                vedit.main(["title", "x", option, "notacolor", "--size", "320x240", "-o", str(out)])
            self.assertIn("does not know the color: notacolor", str(caught.exception.code))
            self.assertFalse(out.exists())

    @needs_imagemagick
    def test_title_with_a_hex_color(self):
        out = self.dir / "hex.mp4"
        vedit.main(["title", "x", "--bg", "#336699", "--size", "320x240", "-o", str(out)])
        self.assertTrue(out.stat().st_size > 0)

    def test_join_with_one_input(self):
        out = self.dir / "one.mp4"
        vedit.main(["join", str(self.clip), "-o", str(out)])
        self.assertAlmostEqual(duration(out), 4, delta=0.2)

    def test_progress_lines_only_in_a_terminal(self):
        class Stream(io.StringIO):
            def __init__(self, tty):
                super().__init__()
                self.tty = tty

            def isatty(self):
                return self.tty

        for tty in (True, False):
            with self.subTest(tty=tty), \
                    mock.patch("vedit.subprocess.run", return_value=mock.Mock(returncode=0)) as run, \
                    mock.patch("vedit.sys.stderr", Stream(tty)):
                vedit.run_ffmpeg(["-i", str(self.clip)], self.dir / "x.mp4", False, pattern=True)
            self.assertEqual("-stats" in run.call_args[0][0], tty)

    def two_fonts(self):
        """Return the names of two different installed fonts, or None."""
        tool = ["magick"] if shutil.which("magick") else ["convert"]
        listing = subprocess.run([*tool, "-list", "font"], capture_output=True, text=True).stdout
        names = re.findall(r"^\s*Font:\s*(\S+)", listing, re.M)

        def works(name):
            # ImageMagick can list a font that is not installed. Such a font gives an error.
            run = subprocess.run([*tool, "-font", name, "-size", "100x30", "label:x", "null:"],
                                 capture_output=True, text=True)
            return run.returncode == 0 and not run.stderr.strip()

        first = next((name for name in names[:30] if works(name)), None)
        last = next((name for name in reversed(names[-30:]) if works(name)), None)
        return (first, last) if first and last and first != last else None

    @needs_imagemagick
    def test_title_with_a_font(self):
        fonts = self.two_fonts()
        if fonts is None:
            self.skipTest("ImageMagick has fewer than two fonts")
        frames = []
        for number, font in enumerate(fonts):
            video = self.dir / f"font{number}.mp4"
            vedit.main(["title", "Hello", "--size", "320x240", "--font", font, "-o", str(video)])
            frames.append(subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-i", str(video), "-frames:v", "1", "-vf", "format=gray",
                 "-f", "rawvideo", "-"], capture_output=True, check=True).stdout)
        # Two fonts draw different pixels. Both cards must also show text, not only a black frame.
        self.assertNotEqual(frames[0], frames[1])
        self.assertTrue(all(max(frame) > 200 for frame in frames))

    @needs_imagemagick
    def test_title_with_an_unknown_font(self):
        out = self.dir / "bad_font.mp4"
        with self.assertRaises(SystemExit) as caught:
            vedit.main(["title", "x", "--font", "notafont", "--size", "320x240", "-o", str(out)])
        self.assertIn("does not know the font: notafont", str(caught.exception.code))
        self.assertFalse(out.exists())

    def test_help_text_names_imagemagick(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as caught:
            vedit.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("ImageMagick", stdout.getvalue())

    def test_every_option_has_help_text(self):
        subparsers = vedit.build_parser()._subparsers._group_actions[0].choices
        self.assertEqual(len(subparsers), 13)
        for name, parser in subparsers.items():
            for action in parser._actions:
                with self.subTest(command=name, option=action.dest):
                    self.assertTrue(action.help, f"{name} {action.dest} has no help text")

    def test_help_shows_defaults_and_a_working_example(self):
        gif_help = vedit.build_parser()._subparsers._group_actions[0].choices["gif"].format_help()
        self.assertIn("(default: 12)", gif_help)
        self.assertIn("example:\n  vedit gif clip.mp4", gif_help)
        subparsers = vedit.build_parser()._subparsers._group_actions[0].choices
        for name, parser in subparsers.items():
            with self.subTest(command=name):
                text = parser.format_help()
                self.assertNotIn("(default: None)", text)
                self.assertNotIn("(default: False)", text)
                # The example in the help text must be a valid command line.
                example = shlex.split(parser.epilog.splitlines()[-1])
                self.assertEqual(example[:2], ["vedit", name])
                self.assertEqual(vedit.build_parser().parse_args(example[1:]).command, name)

    def test_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as caught:
            vedit.main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"vedit {vedit.__version__}")

    def test_dry_run_prints_the_command_and_writes_no_file(self):
        out = self.dir / "dry.mp4"
        for args in (["--dry-run", "trim", str(self.clip), "1", "2"],
                     ["trim", str(self.clip), "1", "2", "--dry-run"]):
            with self.subTest(args=args[:2]):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    vedit.main([*args, "-o", str(out)])
                lines = stdout.getvalue().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(shlex.split(lines[0])[0], "ffmpeg")
                self.assertIn("-ss", lines[0])
                self.assertFalse(out.exists())
        self.assertFalse(vedit.dry_run)

    @needs_imagemagick
    def test_dry_run_of_title_prints_two_commands(self):
        out = self.dir / "dry_title.mp4"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            vedit.main(["--dry-run", "title", "x", "--size", "320x240", "-o", str(out)])
        tools = [shlex.split(line)[0] for line in stdout.getvalue().splitlines()]
        self.assertIn(tools[0], ("magick", "convert"))
        self.assertEqual(tools[1:], ["ffmpeg"])
        self.assertFalse(out.exists())

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
