#!/usr/bin/env python3
"""vedit: simple video edits with ffmpeg and ImageMagick.
Needs Python 3 and ffmpeg. The commands title and sheet also need ImageMagick."""
import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

__version__ = "0.1.0"

# The flag --dry-run sets this to True. Then vedit prints each command and does not run it.
dry_run = False


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


def resolve_out(a, src, tag, ext=None):
    """Return the output path: the value of -o, or <name>_<tag>.<ext> next to the input file."""
    if a.output:
        return Path(a.output)
    return src.with_name(f"{src.stem}_{tag}{ext or src.suffix}")


def check_input(path):
    path = Path(path)
    if not path.is_file():
        fail(f"input file not found: {path}")
    return path


def check_output(out, force):
    """Stop if the output file exists and the user did not give --force."""
    if out.exists() and not force:
        fail(f"output exists: {out} (use --force to overwrite)")


def run_tool(cmd, out, name):
    """Run a program with an argument list. Never use a shell.
    If the program fails or the user presses Ctrl+C, delete the output file that this run made."""
    if dry_run:
        print(shlex.join(cmd))
        return
    existed = out.exists()
    done = False
    try:
        done = subprocess.run(cmd).returncode == 0
    finally:
        if not done and not existed:
            out.unlink(missing_ok=True)
    if not done:
        fail(f"{name} failed")


def run_ffmpeg(args, out, force, pattern=False):
    """Run ffmpeg with an argument list.
    If pattern is true, out is a file name pattern for many files, for example %03d.png.
    Then vedit does not look for one output file and prints no message."""
    if shutil.which("ffmpeg") is None:
        fail("ffmpeg is not installed or not in PATH")
    # Each value that follows -i is an input path. The prefix file: is not part of the path.
    inputs = [a[5:] if a.startswith("file:") else a for prev, a in zip(args, args[1:]) if prev == "-i"]
    if any(Path(i).resolve() == out.resolve() for i in inputs):
        fail(f"the output and the input are the same file: {out}")
    check_output(out, force)
    # The progress lines use carriage returns. They are hard to read in a log file or a pipe.
    stats = ["-stats"] if sys.stderr.isatty() else []
    run_tool(["ffmpeg", "-hide_banner", "-loglevel", "error", *stats, "-y", *args, ff(out)],
             out, "ffmpeg")
    if not pattern and not dry_run:
        # ffmpeg can exit with code 0 and write nothing, for example for a time after the end.
        if not out.exists():
            fail(f"ffmpeg wrote no output: {out}")
        print(f"wrote {out}")


def magick_command(tool):
    """Return the start of an ImageMagick command. Use ImageMagick 7 (`magick`) or 6 (`convert`, `montage`).
    The tool is convert or montage."""
    if shutil.which("magick"):
        return ["magick"] + ([] if tool == "convert" else [tool])
    if shutil.which(tool):
        return [tool]
    fail("ImageMagick is not installed or not in PATH")


def check_magick(args, message):
    """Run a small ImageMagick job. Stop with the message if it fails or prints a warning.
    For an unknown color, ImageMagick prints a warning, uses another color, and exits with the code 0."""
    run = subprocess.run([*magick_command("convert"), *args, "null:"], capture_output=True, text=True)
    if run.returncode != 0 or run.stderr.strip():
        fail(message)


def check_color(value):
    check_magick(["-size", "1x1", f"xc:{value}"], f"ImageMagick does not know the color: {value}")


def check_font(value):
    check_magick(["-font", value, "-size", "100x30", "label:x"], f"ImageMagick does not know the font: {value}")


def run_magick(tool, args, out, force):
    """Run ImageMagick with an argument list. The tool is convert or montage."""
    check_output(out, force)
    cmd = magick_command(tool)
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
    """Return the shown width, the shown height, and the average frame rate (for example 25/1) of a video."""
    entries = "stream=width,height,r_frame_rate,avg_frame_rate:stream_side_data=rotation"
    try:
        stream = json.loads(ffprobe(src, entries, "json"))["streams"][0]
        width, height = stream["width"], stream["height"]
        # A clip with a turn of 90 or 270 degrees shows with the width and the height swapped.
        for side in stream.get("side_data_list", []):
            if abs(side.get("rotation", 0)) % 180 == 90:
                width, height = height, width
        # The base rate can be far from the real rate in a clip with a variable frame rate.
        fps = stream["avg_frame_rate"]
        return width, height, stream["r_frame_rate"] if fps == "0/0" else fps
    except (ValueError, KeyError, IndexError):
        fail(f"cannot read the video stream of {src}")


def require_filter(name, library):
    """Stop if this ffmpeg has no filter with this name. The library is the build option that adds it."""
    if shutil.which("ffmpeg") is None:
        fail("ffmpeg is not installed or not in PATH")
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    if not re.search(rf"\s{name}\s", filters):
        fail(f"this ffmpeg has no {name} filter. It needs the library {library}")


def has_sound(src):
    return bool(ffprobe(src, "stream=codec_type", "csv=p=0", "a:0"))


def cmd_trim(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "trim")
    # Both times come before -i, so ffmpeg jumps to the start and does not decode the clip before it.
    args = ["-ss", a.start]
    if a.end:
        args += ["-to", a.end]
    if a.fast:
        # A stream copy does not encode. The cut moves to the nearest keyframe before the start time.
        run_ffmpeg([*args, "-i", ff(src), "-c", "copy"], out, a.force)
    else:
        # The cut is exact, because ffmpeg encodes the clip again.
        run_ffmpeg([*args, "-i", ff(src), "-vf", EVEN, *PIX_FMT], out, a.force)


def cmd_join(a):
    srcs = [check_input(p) for p in a.inputs]
    out = resolve_out(a, srcs[0], "joined")
    # Every clip gets the size and the frame rate of the first clip. Black bars keep the aspect ratio.
    w, h, fps = video_format(srcs[0])
    w, h = w - w % 2, h - h % 2
    fit = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")
    # ponytail: the output has no sound if one clip has no sound
    with_audio = all(has_sound(s) for s in srcs)
    inputs, parts, labels = [], [], ""
    for i, src in enumerate(srcs):
        inputs += ["-i", ff(src)]
        parts.append(f"[{i}:v]{fit}[v{i}]")
        labels += f"[v{i}]"
        if with_audio:
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
            labels += f"[a{i}]"
    if a.crossfade and len(srcs) > 1:
        fade = a.crossfade
        durations = [video_duration(src) for src in srcs]
        if fade >= min(durations):
            fail("the crossfade must be shorter than each clip")
        # Each clip starts one crossfade before the end of the clips before it.
        offset = 0
        for i in range(1, len(srcs)):
            offset += durations[i - 1] - fade
            last = i == len(srcs) - 1
            before_v, before_a = ("v0", "a0") if i == 1 else (f"x{i - 1}", f"y{i - 1}")
            parts.append(f"[{before_v}][v{i}]xfade=transition=fade:duration={fade}:offset={offset}"
                         f"[{'v' if last else f'x{i}'}]")
            if with_audio:
                parts.append(f"[{before_a}][a{i}]acrossfade=d={fade}[{'a' if last else f'y{i}'}]")
    else:
        parts.append(f"{labels}concat=n={len(srcs)}:v=1:a={int(with_audio)}[v]" + ("[a]" if with_audio else ""))
    maps = ["-map", "[v]"] + (["-map", "[a]"] if with_audio else [])
    run_ffmpeg([*inputs, "-filter_complex", ";".join(parts), *maps, *PIX_FMT], out, a.force)


def atempo_chain(factor):
    """Return the atempo filters for a factor. One atempo filter takes a factor from 0.5 to 100,
    so a factor below 0.5 needs more than one filter. For example, 0.25 is atempo=0.5,atempo=0.5."""
    filters = []
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append(f"atempo={factor:.6g}")
    return ",".join(filters)


def cmd_speed(a):
    if not 0.1 <= a.factor <= 100:
        fail("factor must be from 0.1 to 100")
    src = check_input(a.input)
    out = resolve_out(a, src, f"x{a.factor:g}")
    run_ffmpeg(
        ["-i", ff(src), "-vf", f"setpts=PTS/{a.factor},{EVEN}", *PIX_FMT, "-af", atempo_chain(a.factor)],
        out, a.force,
    )


def cmd_gif(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "gif", ".gif")
    graph = (
        f"fps={a.fps},scale='min({a.width},iw)':-1:flags=lanczos,"
        "split[a][b];[a]palettegen[p];[b][p]paletteuse"
    )
    run_ffmpeg(["-i", ff(src), "-vf", graph, "-loop", "0"], out, a.force)


def cmd_compress(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "small", ".mp4")
    run_ffmpeg(
        ["-i", ff(src), "-vf", EVEN, *PIX_FMT, "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        out, a.force,
    )


def cmd_fade(a):
    if a.fade_in is None and a.fade_out is None:
        fail("give --fade-in or --fade-out")
    src = check_input(a.input)
    out = resolve_out(a, src, "fade")
    length = video_duration(src)
    fade_in, fade_out = a.fade_in or 0, a.fade_out or 0
    if fade_in + fade_out > length:
        fail("the fades are longer than the clip")
    video, sound = [EVEN], []
    if fade_in:
        video.append(f"fade=t=in:st=0:d={fade_in}")
        sound.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out:
        video.append(f"fade=t=out:st={length - fade_out}:d={fade_out}")
        sound.append(f"afade=t=out:st={length - fade_out}:d={fade_out}")
    args = ["-i", ff(src), "-vf", ",".join(video), *PIX_FMT]
    if sound:
        args += ["-af", ",".join(sound)]
    run_ffmpeg(args, out, a.force)


def cmd_crop(a):
    if a.width % 2 or a.height % 2:
        fail("width and height must be even numbers")
    src = check_input(a.input)
    out = resolve_out(a, src, "crop")
    full_width, full_height, _ = video_format(src)
    # Without --x and --y, the cut is in the center of the picture.
    x = (full_width - a.width) // 2 if a.x is None else a.x
    y = (full_height - a.height) // 2 if a.y is None else a.y
    if x + a.width > full_width or y + a.height > full_height:
        fail(f"the cut of {a.width}x{a.height} at {x},{y} is outside the video of {full_width}x{full_height}")
    run_ffmpeg(["-i", ff(src), "-vf", f"crop={a.width}:{a.height}:{x}:{y}", *PIX_FMT, "-c:a", "copy"],
               out, a.force)


def cmd_reverse(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "reverse")
    # The filters reverse and areverse hold the whole clip in memory. Use them for short clips.
    run_ffmpeg(["-i", ff(src), "-vf", f"reverse,{EVEN}", *PIX_FMT, "-af", "areverse"], out, a.force)


def cmd_loop(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "loop")
    # The option -stream_loop gives the number of extra plays. A stream copy does not encode.
    run_ffmpeg(["-stream_loop", str(a.count - 1), "-i", ff(src), "-c", "copy"], out, a.force)


def cmd_subtitles(a):
    src = check_input(a.input)
    subs = check_input(a.subtitles)
    out = resolve_out(a, src, "subs")
    require_filter("subtitles", "libass")
    with tempfile.TemporaryDirectory() as tmp:
        # A copy with a plain name avoids the escape rules of ffmpeg for a path in a filter.
        copy = Path(tmp) / "subs.srt"
        shutil.copyfile(subs, copy)
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", str(copy)):
            fail(f"the name of the temporary folder has a character that a filter cannot read: {tmp}")
        run_ffmpeg(["-i", ff(src), "-vf", f"{EVEN},subtitles='{copy}'", *PIX_FMT, "-c:a", "copy"],
                   out, a.force)


def cmd_audio(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "audio", ".mp3")
    # ffmpeg picks the audio format from the output extension: .mp3, .wav, .m4a, .flac
    run_ffmpeg(["-i", ff(src), "-vn"], out, a.force)


def cmd_volume(a):
    src = check_input(a.input)
    if not has_sound(src):
        fail(f"the clip has no sound: {src}")
    out = resolve_out(a, src, "volume")
    run_ffmpeg(["-i", ff(src), "-af", f"volume={a.factor}", "-c:v", "copy"], out, a.force)


def cmd_normalize(a):
    src = check_input(a.input)
    if not has_sound(src):
        fail(f"the clip has no sound: {src}")
    out = resolve_out(a, src, "norm")
    # One pass of loudnorm aims at -16 LUFS. The filter makes a sample rate of 192 kHz, so aresample resets it.
    run_ffmpeg(["-i", ff(src), "-af", "loudnorm=I=-16:LRA=11:TP=-1.5,aresample=48000", "-c:v", "copy"],
               out, a.force)


def cmd_mute(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "mute")
    run_ffmpeg(["-i", ff(src), "-an", "-c:v", "copy"], out, a.force)


def cmd_frame(a):
    src = check_input(a.input)
    out = resolve_out(a, src, "frame", ".png")
    run_ffmpeg(["-ss", a.time, "-i", ff(src), "-frames:v", "1"], out, a.force)


def cmd_resize(a):
    if a.width is None and a.height is None:
        fail("give --width or --height")
    for value in (a.width, a.height):
        # H.264 needs even sizes. The value -2 makes ffmpeg pick an even size for the other side.
        if value is not None and (value <= 0 or value % 2):
            fail("width and height must be even numbers above 0")
    src = check_input(a.input)
    out = resolve_out(a, src, "resized")
    scale = f"scale={a.width or -2}:{a.height or -2}"
    run_ffmpeg(["-i", ff(src), "-vf", scale, "-c:a", "copy"], out, a.force)


ROTATE_FILTERS = {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}


def cmd_rotate(a):
    src = check_input(a.input)
    out = resolve_out(a, src, f"rot{a.degrees}")
    run_ffmpeg(["-i", ff(src), "-vf", f"{ROTATE_FILTERS[a.degrees]},{EVEN}", *PIX_FMT, "-c:a", "copy"], out, a.force)


# ffmpeg overlay positions. W and H are the video size, w and h the logo size, {m} the margin.
POSITIONS = {
    "top-left": "{m}:{m}",
    "top-right": "W-w-{m}:{m}",
    "bottom-left": "{m}:H-h-{m}",
    "bottom-right": "W-w-{m}:H-h-{m}",
    "center": "(W-w)/2:(H-h)/2",
}


def cmd_watermark(a):
    if a.margin < 0:
        fail("margin must be 0 or more")
    src = check_input(a.input)
    logo = check_input(a.image)
    if a.scale:
        # The width of the logo is a share of the width that a player shows.
        width = max(1, round(a.scale * video_format(src)[0]))
    else:
        width = a.width or 100
    out = resolve_out(a, src, "mark")
    pos = POSITIONS[a.position].format(m=a.margin)
    # The filter colorchannelmixer makes the logo transparent. It needs a format with an alpha channel.
    fade = f",format=rgba,colorchannelmixer=aa={a.opacity}" if a.opacity < 1 else ""
    graph = f"[0:v]{EVEN}[base];[1:v]scale={width}:-1{fade}[wm];[base][wm]overlay={pos}[v]"
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
    if not a.text.strip():
        fail("title text must not be empty")
    check_color(a.bg)
    check_color(a.fg)
    font = ["-font", a.font] if a.font else []
    if a.font:
        check_font(a.font)
    # ImageMagick reads a file for text that starts with @ and expands %w style codes.
    text = a.text.replace("%", "%%")
    if text.startswith("@"):
        text = "\\" + text
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "title.png"
        run_magick(
            "convert",
            [*font, "-background", a.bg, "-fill", a.fg, "-gravity", "center",
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
    src = check_input(a.input)
    out = resolve_out(a, src, "sheet", ".jpg")
    check_output(out, a.force)
    count = a.cols * a.rows
    length = video_duration(src)
    with tempfile.TemporaryDirectory() as tmp:
        # Take one frame from the middle of each equal part of the clip.
        run_ffmpeg(
            ["-ss", str(length / (2 * count)), "-i", ff(src),
             "-vf", f"fps={count}/{length},scale='min({a.width},iw)':-1", "-frames:v", str(count)],
            Path(tmp) / "%03d.png", True, pattern=True,
        )
        frames = sorted(Path(tmp).glob("*.png"))
        run_magick(
            "montage",
            [*map(str, frames), "-tile", f"{a.cols}x{a.rows}", "-geometry", "+4+4",
             "-background", "black"],
            out, a.force,
        )
    print(f"wrote {out}")


def positive_int(text):
    """An argparse type for a whole number of 1 or more."""
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def non_negative_int(text):
    """An argparse type for a whole number of 0 or more."""
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return value


def positive_number(text):
    """An argparse type for a number above 0."""
    value = float(text)
    if not value > 0:  # This also stops nan.
        raise argparse.ArgumentTypeError("must be above 0")
    return value


def crf_value(text):
    """An argparse type for the quality of libx264, from 0 to 51."""
    value = int(text)
    if not 0 <= value <= 51:
        raise argparse.ArgumentTypeError("must be from 0 to 51")
    return value


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Show the default value of an option. Keep the line breaks of the example."""

    def _get_help_string(self, action):
        # An option without a value, and an option with no default, have nothing to show.
        if action.default is None or action.default is False or action.default is argparse.SUPPRESS:
            return action.help
        return super()._get_help_string(action)


def fraction(text):
    """An argparse type for a number above 0 and up to 1."""
    value = float(text)
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError("must be above 0 and at most 1")
    return value


def build_parser():
    p = argparse.ArgumentParser(prog="vedit", description="Simple video edits with ffmpeg and ImageMagick.",
                                formatter_class=HelpFormatter)
    p.add_argument("-f", "--force", action="store_true", help="overwrite the output file")
    p.add_argument("--version", action="version", version=f"vedit {__version__}")
    p.add_argument("--dry-run", action="store_true", help="print the commands and do not run them")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, func, help_text, example):
        sp = sub.add_parser(name, help=help_text, description=help_text, formatter_class=HelpFormatter,
                            epilog=f"example:\n  {example}")
        sp.add_argument("-o", "--output", help="output file (default: next to the input)")
        # SUPPRESS keeps the value that -f before the command name set.
        sp.add_argument("-f", "--force", action="store_true", default=argparse.SUPPRESS,
                        help="overwrite the output file")
        sp.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                        help="print the commands and do not run them")
        sp.set_defaults(func=func)
        return sp

    sp = add("trim", cmd_trim, "cut a clip between two times",
            "vedit trim clip.mp4 10 25")
    sp.add_argument("input", help="the video file")
    sp.add_argument("start", help="start time, for example 10 or 0:01:30.5")
    sp.add_argument("end", nargs="?", help="end time (default: end of the clip)")
    sp.add_argument("--fast", action="store_true",
                    help="copy the streams and do not encode, the cut starts at the keyframe before the start time")

    sp = add("join", cmd_join, "join clips one after the other",
            "vedit join intro.mp4 main.mp4 outro.mp4")
    sp.add_argument("inputs", nargs="+", metavar="input", help="the video files, in the order to join them")
    sp.add_argument("--crossfade", type=positive_number, metavar="SECONDS",
                    help="fade from each clip to the next clip in this time, the fade overlaps the clips")

    sp = add("speed", cmd_speed, "make a clip faster or slower",
            "vedit speed clip.mp4 2")
    sp.add_argument("input", help="the video file")
    sp.add_argument("factor", type=float, help="2 is twice as fast, 0.5 is half speed, from 0.1 to 100")

    sp = add("gif", cmd_gif, "make a GIF from a clip",
            "vedit gif clip.mp4 --fps 12 --width 480")
    sp.add_argument("input", help="the video file")
    sp.add_argument("--fps", type=positive_int, default=12, help="frames per second of the GIF")
    sp.add_argument("--width", type=positive_int, default=480, help="largest width in pixels, vedit does not enlarge a clip")

    sp = add("compress", cmd_compress, "make the file smaller (H.264)",
            "vedit compress clip.mp4 --crf 28")
    sp.add_argument("input", help="the video file")
    sp.add_argument("--crf", type=crf_value, default=28, help="quality, 18 is high, 35 is low")

    sp = add("resize", cmd_resize, "change the size of a clip",
            "vedit resize clip.mp4 --width 1280")
    sp.add_argument("input", help="the video file")
    sp.add_argument("--width", type=int, help="width in pixels, an even number")
    sp.add_argument("--height", type=int, help="height in pixels, an even number")

    sp = add("rotate", cmd_rotate, "turn a clip clockwise",
            "vedit rotate clip.mp4 90")
    sp.add_argument("input", help="the video file")
    sp.add_argument("degrees", type=int, choices=sorted(ROTATE_FILTERS), help="the turn, clockwise")

    sp = add("watermark", cmd_watermark, "put a logo or image on a clip",
            "vedit watermark clip.mp4 logo.png --position bottom-right --width 100")
    sp.add_argument("input", help="the video file")
    sp.add_argument("image", help="logo file, for example a PNG with a clear background")
    sp.add_argument("--position", choices=sorted(POSITIONS), default="bottom-right",
                    help="place of the logo")
    size = sp.add_mutually_exclusive_group()
    size.add_argument("--width", type=positive_int, help="width of the logo in pixels, 100 if you give no size")
    size.add_argument("--scale", type=fraction, help="width of the logo as a share of the video width, for example 0.15")
    sp.add_argument("--margin", type=int, default=10, help="space to the edge in pixels")
    sp.add_argument("--opacity", type=fraction, default=1,
                    help="how solid the logo is, above 0 and at most 1, 1 is solid")

    sp = add("crop", cmd_crop, "cut away the edges of the picture", "vedit crop clip.mp4 640 360 --x 0 --y 0")
    sp.add_argument("input", help="the video file")
    sp.add_argument("width", type=positive_int, help="width of the cut in pixels, an even number")
    sp.add_argument("height", type=positive_int, help="height of the cut in pixels, an even number")
    sp.add_argument("--x", type=non_negative_int, help="left edge of the cut in pixels, the center if you give none")
    sp.add_argument("--y", type=non_negative_int, help="top edge of the cut in pixels, the center if you give none")

    sp = add("subtitles", cmd_subtitles, "burn subtitles from an .srt file into the picture",
             "vedit subtitles clip.mp4 clip.srt")
    sp.add_argument("input", help="the video file")
    sp.add_argument("subtitles", help="the subtitle file in the SRT format")

    sp = add("loop", cmd_loop, "play a clip again and again, the number of times you give", "vedit loop clip.mp4 3")
    sp.add_argument("input", help="the video file")
    sp.add_argument("count", type=positive_int, help="how many times the clip plays, in total")

    sp = add("reverse", cmd_reverse, "play a clip backward, use it for short clips only",
             "vedit reverse clip.mp4")
    sp.add_argument("input", help="the video file")

    sp = add("fade", cmd_fade, "fade a clip in from black, or out to black, with the sound",
             "vedit fade clip.mp4 --fade-in 1 --fade-out 2")
    sp.add_argument("input", help="the video file")
    sp.add_argument("--fade-in", type=positive_number, metavar="SECONDS", help="length of the fade in from black")
    sp.add_argument("--fade-out", type=positive_number, metavar="SECONDS", help="length of the fade out to black")

    sp = add("audio", cmd_audio, "save the sound of a clip as an audio file",
            "vedit audio clip.mp4 -o sound.wav")
    sp.add_argument("input", help="the video file")

    sp = add("mute", cmd_mute, "remove the sound from a clip",
            "vedit mute clip.mp4")
    sp.add_argument("input", help="the video file")

    sp = add("volume", cmd_volume, "make the sound louder or quieter", "vedit volume clip.mp4 1.5")
    sp.add_argument("input", help="the video file")
    sp.add_argument("factor", type=positive_number, help="2 is twice the volume, 0.5 is half the volume")

    sp = add("normalize", cmd_normalize, "set the loudness of the sound to -16 LUFS", "vedit normalize clip.mp4")
    sp.add_argument("input", help="the video file")

    sp = add("frame", cmd_frame, "save one frame of a clip as an image",
            "vedit frame clip.mp4 5")
    sp.add_argument("input", help="the video file")
    sp.add_argument("time", help="time of the frame, for example 5 or 0:01:30")

    sp = add("title", cmd_title, "make a title card video (needs ImageMagick)",
            'vedit title "My Holiday" --seconds 3')
    sp.add_argument("text", help="the text of the card, it must not be empty")
    sp.add_argument("--seconds", type=positive_number, default=3, help="length of the card in seconds")
    sp.add_argument("--size", default="1280x720", help="WIDTHxHEIGHT, even numbers")
    sp.add_argument("--fps", type=positive_int, default=25, help="frames per second of the card")
    sp.add_argument("--bg", default="black", help="background color")
    sp.add_argument("--fg", default="white", help="text color")
    sp.add_argument("--font", help="font name from `magick -list font`, or the path of a font file")

    sp = add("sheet", cmd_sheet, "make a contact sheet of frames (needs ImageMagick)",
            "vedit sheet clip.mp4 --cols 4 --rows 3")
    sp.add_argument("input", help="the video file")
    sp.add_argument("--cols", type=positive_int, default=4, help="number of columns")
    sp.add_argument("--rows", type=positive_int, default=3, help="number of rows")
    sp.add_argument("--width", type=positive_int, default=320, help="largest width of each frame in pixels, vedit does not enlarge a clip")
    return p


def main(argv=None):
    global dry_run
    a = build_parser().parse_args(argv)
    dry_run = a.dry_run
    try:
        a.func(a)
    except KeyboardInterrupt:
        print("vedit: interrupted", file=sys.stderr)
        sys.exit(130)
    finally:
        dry_run = False


if __name__ == "__main__":
    main()
