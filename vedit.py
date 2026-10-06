#!/usr/bin/env python3
"""vedit: simple video edits with ffmpeg and ImageMagick. Needs Python 3 and ffmpeg."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# H.264 needs an even width and an even height. This filter cuts off one pixel of an odd side.
EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
# Many players cannot play H.264 with other pixel formats, for example yuv444p.
PIX_FMT = ["-pix_fmt", "yuv420p"]


def ff(path):
    """Return a path in the form that ffmpeg and ffprobe read as a file.
    Without the prefix, ffmpeg reads "a:" in "a:b.mp4" as a protocol name."""
    return f"file:{path}"


def fail(message):
    sys.exit(f"vedit: error: {message}")


def default_out(src, tag, ext=None):
    """Return the output path: <name>_<tag>.<ext> next to the input file."""
    return src.with_name(f"{src.stem}_{tag}{ext or src.suffix}")


def check_input(path):
    path = Path(path)
    if not path.is_file():
        fail(f"input file not found: {path}")
    return path


def run_tool(cmd, out, name):
    """Run a program with an argument list. Never use a shell.
    If the program fails, delete the output file that this run made, then stop."""
    existed = out.exists()
    if subprocess.run(cmd).returncode != 0:
        if not existed:
            out.unlink(missing_ok=True)
        fail(f"{name} failed")


def run_ffmpeg(args, out, force, quiet=False):
    """Run ffmpeg with an argument list."""
    if shutil.which("ffmpeg") is None:
        fail("ffmpeg is not installed or not in PATH")
    if out.exists() and not force:
        fail(f"output exists: {out} (use --force to overwrite)")
    run_tool(["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y", *args, ff(out)],
             out, "ffmpeg")
    if not quiet:
        # ffmpeg can exit with code 0 and write nothing, for example for a time after the end.
        if not out.exists():
            fail(f"ffmpeg wrote no output: {out}")
        print(f"wrote {out}")


def run_magick(tool, args, out, force):
    """Run ImageMagick 7 (`magick`) or 6 (`convert`, `montage`). tool is convert or montage."""
    if out.exists() and not force:
        fail(f"output exists: {out} (use --force to overwrite)")
    if shutil.which("magick"):
        cmd = ["magick"] + ([] if tool == "convert" else [tool])
    elif shutil.which(tool):
        cmd = [tool]
    else:
        fail("ImageMagick is not installed or not in PATH")
    # An absolute path keeps ImageMagick from reading "a:" in "a:b.jpg" as a format name.
    run_tool([*cmd, *args, str(out.absolute())], out, "ImageMagick")


def ffprobe(src, entries, fmt, stream="v:0"):
    """Return the text that ffprobe prints for the entries of the first video or audio stream."""
    if shutil.which("ffprobe") is None:
        fail("ffprobe is not installed or not in PATH")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries,
         "-of", fmt, ff(src)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def video_duration(src):
    """Return the length of a video in seconds."""
    try:
        return float(ffprobe(src, "format=duration", "default=nw=1:nk=1"))
    except ValueError:
        fail(f"cannot read the length of {src}")


def video_format(src):
    """Return the shown width, the shown height, and the frame rate (for example 25/1) of a video."""
    entries = "stream=width,height,r_frame_rate:stream_side_data=rotation"
    try:
        stream = json.loads(ffprobe(src, entries, "json"))["streams"][0]
        width, height = stream["width"], stream["height"]
        # A clip with a turn of 90 or 270 degrees shows with the width and the height swapped.
        for side in stream.get("side_data_list", []):
            if abs(side.get("rotation", 0)) % 180 == 90:
                width, height = height, width
        return width, height, stream["r_frame_rate"]
    except (ValueError, KeyError, IndexError):
        fail(f"cannot read the video stream of {src}")


def cmd_trim(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "trim")
    # ponytail: re-encodes for exact cuts, add a --fast stream copy mode if speed matters
    # Both times come before -i, so ffmpeg jumps to the start and does not decode the clip before it.
    # The cut stays exact, because ffmpeg encodes the clip again.
    args = ["-ss", a.start]
    if a.end:
        args += ["-to", a.end]
    run_ffmpeg([*args, "-i", ff(src), "-vf", EVEN, *PIX_FMT], out, a.force)


def cmd_join(a):
    srcs = [check_input(p) for p in a.inputs]
    out = Path(a.output) if a.output else default_out(srcs[0], "joined")
    # Every clip gets the size and the frame rate of the first clip. Black bars keep the aspect ratio.
    w, h, fps = video_format(srcs[0])
    w, h = w - w % 2, h - h % 2
    fit = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
    # ponytail: no crossfade, and the output has no sound if one clip has no sound
    with_audio = all(ffprobe(s, "stream=codec_type", "csv=p=0", "a:0") for s in srcs)
    inputs, parts, labels = [], [], ""
    for i, src in enumerate(srcs):
        inputs += ["-i", ff(src)]
        parts.append(f"[{i}:v]{fit}[v{i}]")
        labels += f"[v{i}]"
        if with_audio:
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
            labels += f"[a{i}]"
    parts.append(f"{labels}concat=n={len(srcs)}:v=1:a={int(with_audio)}[v]" + ("[a]" if with_audio else ""))
    maps = ["-map", "[v]"] + (["-map", "[a]"] if with_audio else [])
    run_ffmpeg([*inputs, "-filter_complex", ";".join(parts), *maps, *PIX_FMT], out, a.force)


def cmd_speed(a):
    if not 0.5 <= a.factor <= 100:
        fail("factor must be from 0.5 to 100")
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, f"x{a.factor:g}")
    run_ffmpeg(
        ["-i", ff(src), "-vf", f"setpts=PTS/{a.factor},{EVEN}", *PIX_FMT, "-af", f"atempo={a.factor}"],
        out, a.force,
    )


def cmd_gif(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "gif", ".gif")
    graph = (
        f"fps={a.fps},scale='min({a.width},iw)':-1:flags=lanczos,"
        "split[a][b];[a]palettegen[p];[b][p]paletteuse"
    )
    run_ffmpeg(["-i", ff(src), "-vf", graph, "-loop", "0"], out, a.force)


def cmd_compress(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "small", ".mp4")
    run_ffmpeg(
        ["-i", ff(src), "-vf", EVEN, *PIX_FMT, "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        out, a.force,
    )


def cmd_audio(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "audio", ".mp3")
    # ffmpeg picks the audio format from the output extension: .mp3, .wav, .m4a, .flac
    run_ffmpeg(["-i", ff(src), "-vn"], out, a.force)


def cmd_mute(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "mute")
    run_ffmpeg(["-i", ff(src), "-an", "-c:v", "copy"], out, a.force)


def cmd_frame(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "frame", ".png")
    run_ffmpeg(["-ss", a.time, "-i", ff(src), "-frames:v", "1"], out, a.force)


def cmd_resize(a):
    if a.width is None and a.height is None:
        fail("give --width or --height")
    for value in (a.width, a.height):
        # H.264 needs even sizes. The value -2 makes ffmpeg pick an even size for the other side.
        if value is not None and (value <= 0 or value % 2):
            fail("width and height must be even numbers above 0")
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "resized")
    scale = f"scale={a.width or -2}:{a.height or -2}"
    run_ffmpeg(["-i", ff(src), "-vf", scale, "-c:a", "copy"], out, a.force)


ROTATE_FILTERS = {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}


def cmd_rotate(a):
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, f"rot{a.degrees}")
    run_ffmpeg(["-i", ff(src), "-vf", f"{ROTATE_FILTERS[a.degrees]},{EVEN}", *PIX_FMT, "-c:a", "copy"], out, a.force)


# ffmpeg overlay positions. W and H are the video size, w and h the logo size, M the margin.
POSITIONS = {
    "top-left": "M:M",
    "top-right": "W-w-M:M",
    "bottom-left": "M:H-h-M",
    "bottom-right": "W-w-M:H-h-M",
    "center": "(W-w)/2:(H-h)/2",
}


def cmd_watermark(a):
    if a.width < 1 or a.margin < 0:
        fail("width must be 1 or more and margin must be 0 or more")
    src = check_input(a.input)
    logo = check_input(a.image)
    out = Path(a.output) if a.output else default_out(src, "mark")
    pos = POSITIONS[a.position].replace("M", str(a.margin))
    graph = f"[0:v]{EVEN}[base];[1:v]scale={a.width}:-1[wm];[base][wm]overlay={pos}[v]"
    run_ffmpeg(
        ["-i", ff(src), "-i", ff(logo), "-filter_complex", graph,
         "-map", "[v]", "-map", "0:a?", *PIX_FMT, "-c:a", "copy"],
        out, a.force,
    )


def cmd_title(a):
    m = re.fullmatch(r"(\d+)x(\d+)", a.size)
    if not m or int(m[1]) % 2 or int(m[2]) % 2 or 0 in (int(m[1]), int(m[2])):
        fail("size must be WIDTHxHEIGHT with even numbers, for example 1280x720")
    w, h = int(m[1]), int(m[2])
    out = Path(a.output) if a.output else Path("title.mp4")
    # ImageMagick reads a file for text that starts with @ and expands %w style codes.
    text = a.text.replace("%", "%%")
    if text.startswith("@"):
        text = "\\" + text
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "title.png"
        run_magick(
            "convert",
            ["-background", a.bg, "-fill", a.fg, "-gravity", "center",
             "-size", f"{w * 8 // 10}x{h * 8 // 10}", f"caption:{text}",
             "-extent", f"{w}x{h}"],
            png, True,
        )
        # The silent audio track lets the title card join with clips that have sound.
        run_ffmpeg(
            ["-loop", "1", "-framerate", str(a.fps), "-i", ff(png),
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
             "-t", str(a.seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
            out, a.force,
        )


def cmd_sheet(a):
    if a.cols < 1 or a.rows < 1:
        fail("cols and rows must be 1 or more")
    src = check_input(a.input)
    out = Path(a.output) if a.output else default_out(src, "sheet", ".jpg")
    if out.exists() and not a.force:
        fail(f"output exists: {out} (use --force to overwrite)")
    count = a.cols * a.rows
    length = video_duration(src)
    with tempfile.TemporaryDirectory() as tmp:
        # Take one frame from the middle of each equal part of the clip.
        run_ffmpeg(
            ["-ss", str(length / (2 * count)), "-i", ff(src),
             "-vf", f"fps={count}/{length},scale='min({a.width},iw)':-1", "-frames:v", str(count)],
            Path(tmp) / "%03d.png", True, quiet=True,
        )
        frames = sorted(Path(tmp).glob("*.png"))
        run_magick(
            "montage",
            [*map(str, frames), "-tile", f"{a.cols}x{a.rows}", "-geometry", "+4+4",
             "-background", "black"],
            out, a.force,
        )
    print(f"wrote {out}")


def build_parser():
    p = argparse.ArgumentParser(prog="vedit", description="Simple video edits with ffmpeg.")
    p.add_argument("-f", "--force", action="store_true", help="overwrite the output file")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        sp = sub.add_parser(name, help=help_text, description=help_text)
        sp.add_argument("-o", "--output", help="output file (default: next to the input)")
        # SUPPRESS keeps the value that -f before the command name set.
        sp.add_argument("-f", "--force", action="store_true", default=argparse.SUPPRESS,
                        help="overwrite the output file")
        sp.set_defaults(func=func)
        return sp

    sp = add("trim", cmd_trim, "cut a clip between two times")
    sp.add_argument("input")
    sp.add_argument("start", help="start time, for example 10 or 0:01:30.5")
    sp.add_argument("end", nargs="?", help="end time (default: end of the clip)")

    sp = add("join", cmd_join, "join clips one after the other")
    sp.add_argument("inputs", nargs="+", metavar="input")

    sp = add("speed", cmd_speed, "make a clip faster or slower")
    sp.add_argument("input")
    sp.add_argument("factor", type=float, help="2 is twice as fast, 0.5 is half speed")

    sp = add("gif", cmd_gif, "make a GIF from a clip")
    sp.add_argument("input")
    sp.add_argument("--fps", type=int, default=12)
    sp.add_argument("--width", type=int, default=480, help="largest width in pixels, vedit does not enlarge a clip")

    sp = add("compress", cmd_compress, "make the file smaller (H.264)")
    sp.add_argument("input")
    sp.add_argument("--crf", type=int, default=28, help="quality, 18 is high, 35 is low")

    sp = add("title", cmd_title, "make a title card video (needs ImageMagick)")
    sp.add_argument("text")
    sp.add_argument("--seconds", type=float, default=3)
    sp.add_argument("--size", default="1280x720", help="WIDTHxHEIGHT, even numbers")
    sp.add_argument("--fps", type=int, default=25)
    sp.add_argument("--bg", default="black", help="background color")
    sp.add_argument("--fg", default="white", help="text color")

    sp = add("sheet", cmd_sheet, "make a contact sheet of frames (needs ImageMagick)")
    sp.add_argument("input")
    sp.add_argument("--cols", type=int, default=4)
    sp.add_argument("--rows", type=int, default=3)
    sp.add_argument("--width", type=int, default=320, help="largest width of each frame in pixels, vedit does not enlarge a clip")

    sp = add("audio", cmd_audio, "save the sound of a clip as an audio file")
    sp.add_argument("input")

    sp = add("mute", cmd_mute, "remove the sound from a clip")
    sp.add_argument("input")

    sp = add("frame", cmd_frame, "save one frame of a clip as an image")
    sp.add_argument("input")
    sp.add_argument("time", help="time of the frame, for example 5 or 0:01:30")

    sp = add("resize", cmd_resize, "change the size of a clip")
    sp.add_argument("input")
    sp.add_argument("--width", type=int, help="width in pixels, an even number")
    sp.add_argument("--height", type=int, help="height in pixels, an even number")

    sp = add("rotate", cmd_rotate, "turn a clip clockwise")
    sp.add_argument("input")
    sp.add_argument("degrees", type=int, choices=sorted(ROTATE_FILTERS))

    sp = add("watermark", cmd_watermark, "put a logo or image on a clip")
    sp.add_argument("input")
    sp.add_argument("image", help="logo file, for example a PNG with a clear background")
    sp.add_argument("--position", choices=sorted(POSITIONS), default="bottom-right")
    sp.add_argument("--width", type=int, default=100, help="width of the logo in pixels")
    sp.add_argument("--margin", type=int, default=10, help="space to the edge in pixels")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
