# vedit

vedit is a command-line tool for simple video edits. It uses `ffmpeg` and ImageMagick, so you do not need a big video editor.

## What it does

Each vedit command runs one `ffmpeg` or ImageMagick job. You give the command a file and some options. The command writes a new file. vedit has no timeline and no graphical interface.

| Command | What it does |
|---|---|
| `trim` | Cuts a clip between two times. |
| `join` | Joins clips one after the other. |
| `speed` | Makes a clip faster or slower. |
| `gif` | Makes a GIF from a clip. |
| `compress` | Makes the file smaller with H.264. |
| `resize` | Changes the width, the height, or both. |
| `rotate` | Turns a clip 90, 180, or 270 degrees clockwise. |
| `watermark` | Puts a logo on a clip. |
| `audio` | Saves the sound of a clip as an audio file. |
| `mute` | Removes the sound from a clip. |
| `frame` | Saves one frame of a clip as an image. |
| `title` | Makes a title card video from text. |
| `sheet` | Makes a contact sheet: a grid of frames from a clip. |

## Requirements

* Python 3. The tests ran on Python 3.14 and on Python 3.12.
* `ffmpeg` and `ffprobe`. The `ffmpeg` build must include the encoders `libx264`, `aac`, and `libmp3lame`. The tests ran on `ffmpeg` 9.0.1 and on `ffmpeg` 6.1.
* ImageMagick. The commands `title` and `sheet` need it. The other commands do not. The tests ran on ImageMagick 7.1.2 and on ImageMagick 6.9. If the command `magick` is missing, vedit uses the ImageMagick 6 commands `convert` and `montage`.
* Linux. The tests ran on Linux. I do not know if vedit works on other systems.

## Install

1. Install `ffmpeg` and ImageMagick with the package manager of your system. On Arch Linux, run this command:

```
sudo pacman -S ffmpeg imagemagick
```

2. Clone the repository:

```
git clone https://github.com/Orpheus-21/vedit.git
```

3. Go into the folder:

```
cd vedit
```

4. Show the help text:

```
python3 vedit.py --help
```

### Install as a command

You can install vedit as the command `vedit`. Then you do not need to be in the repository folder.

1. Install `ffmpeg` and ImageMagick, as in step 1 above.
2. Install vedit with `uv`:

```
uv tool install git+https://github.com/Orpheus-21/vedit.git
```

3. Show the help text:

```
vedit --help
```

I tested this install with `uv`. I did not test `pipx`.

## Usage

The general form is:

```
python3 vedit.py COMMAND INPUT [options]
```

Use `python3 vedit.py COMMAND --help` to see the options of one command. If you installed the command `vedit`, write `vedit` in place of `python3 vedit.py` in all examples.

Times are in seconds (`90`) or in the form `H:MM:SS` (`0:01:30.5`).

### trim

Cuts from a start time to an end time. If you give no end time, the cut goes to the end of the clip.

```
python3 vedit.py trim clip.mp4 10 25
```

### join

Joins two or more clips in the order you give them.

```
python3 vedit.py join intro.mp4 main.mp4 outro.mp4
```

### speed

Changes the speed. The factor 2 is twice as fast. The factor 0.5 is half speed. The factor must be from 0.5 to 100.

```
python3 vedit.py speed clip.mp4 2
```

### gif

```
python3 vedit.py gif clip.mp4 --fps 12 --width 480
```

### compress

A higher `--crf` value gives a smaller file and lower quality. The value 18 is high quality. The value 35 is low quality.

```
python3 vedit.py compress clip.mp4 --crf 28
```

### resize

Give `--width`, `--height`, or both. Each value must be an even number. If you give one value, vedit keeps the aspect ratio.

```
python3 vedit.py resize clip.mp4 --width 1280
```

### rotate

```
python3 vedit.py rotate clip.mp4 90
```

### watermark

The `--position` value is `top-left`, `top-right`, `bottom-left`, `bottom-right`, or `center`. A PNG file with a clear background works well as a logo.

```
python3 vedit.py watermark clip.mp4 logo.png --position bottom-right --width 100
```

### audio

The extension of the output file selects the audio format, for example `.mp3`, `.wav`, `.m4a`, or `.flac`.

```
python3 vedit.py audio clip.mp4 -o sound.wav
```

### mute

```
python3 vedit.py mute clip.mp4
```

### frame

```
python3 vedit.py frame clip.mp4 5
```

### title

Makes a video with centered text. The video has a silent audio track, so you can join it with clips that have sound.

```
python3 vedit.py title "My Holiday" --seconds 3
python3 vedit.py join title.mp4 clip.mp4 -o holiday.mp4
```

### sheet

Takes one frame from the middle of each equal part of the clip. Then it puts the frames in a grid.

```
python3 vedit.py sheet clip.mp4 --cols 4 --rows 3
```

## Configuration

vedit has no configuration file. All settings are command-line options.

| Option | Commands | Default | Effect |
|---|---|---|---|
| `-o`, `--output` | all | see below | The path of the output file. |
| `-f`, `--force` | all | off | Overwrites an output file that exists. You can write it before or after the command name. |
| `--fps` | `gif` | 12 | Frames per second of the GIF. Use 1 or more. |
| `--width` | `gif` | 480 | Largest width of the GIF in pixels. vedit does not enlarge a clip. |
| `--crf` | `compress` | 28 | Quality, from 0 to 51. A lower value gives higher quality. |
| `--width`, `--height` | `resize` | none | New size in pixels. Give at least one. |
| `--position` | `watermark` | `bottom-right` | Place of the logo. |
| `--width` | `watermark` | 100 | Width of the logo in pixels. |
| `--margin` | `watermark` | 10 | Space between the logo and the edge in pixels. |
| `--seconds` | `title` | 3 | Length of the title card in seconds. Use a number above 0. |
| `--size` | `title` | `1280x720` | Size of the title card. Both numbers must be even. |
| `--fps` | `title` | 25 | Frames per second of the title card. Use 1 or more. |
| `--bg` | `title` | `black` | Background color. Any ImageMagick color name works. |
| `--fg` | `title` | `white` | Text color. |
| `--cols` | `sheet` | 4 | Number of columns. Use 1 or more. |
| `--rows` | `sheet` | 3 | Number of rows. Use 1 or more. |
| `--width` | `sheet` | 320 | Largest width of each frame in pixels. vedit does not enlarge a clip. |

Without `-o`, vedit writes the output next to the input file. The name is the name of the input, then an underscore, then a tag:

| Command | Output name for `clip.mp4` |
|---|---|
| `trim` | `clip_trim.mp4` |
| `join` | `clip_joined.mp4` (the name of the first clip) |
| `speed` | `clip_x2.mp4` (the tag holds the factor) |
| `gif` | `clip_gif.gif` |
| `compress` | `clip_small.mp4` |
| `resize` | `clip_resized.mp4` |
| `rotate` | `clip_rot90.mp4` (the tag holds the degrees) |
| `watermark` | `clip_mark.mp4` |
| `audio` | `clip_audio.mp3` |
| `mute` | `clip_mute.mp4` |
| `frame` | `clip_frame.png` |
| `sheet` | `clip_sheet.jpg` |
| `title` | `title.mp4` in the current folder |

If the output file exists, vedit stops with an error. Use `-f` to overwrite the file.

## Limits

* `trim` encodes the video again. The cut is exact, but the command is slower than a stream copy.
* `join` gives every clip the size and the frame rate of the first clip. It adds black bars to keep the aspect ratio. It has no crossfade. If one clip has no sound, the output has no sound.
* `title` uses the default ImageMagick font. It has no option to change the font.

## How it works

The whole program is the file `vedit.py`. It uses only the Python standard library.

Each command is a function named `cmd_NAME`. The function reads the options, checks the input file, and builds a list of arguments. Two helpers run the programs:

* `run_ffmpeg` runs `ffmpeg`. It stops with an error if the output file exists and `-f` is not set. It also stops if `ffmpeg` writes no file.
* `run_magick` runs ImageMagick 7 (`magick`) or ImageMagick 6 (`convert`, `montage`).

vedit passes the arguments as a list and never starts a shell. A file name with spaces or quotes is safe.

Some commands use more than one step:

* `join` probes the first clip with `ffprobe`. Then it runs the `ffmpeg` concat filter with one scale and pad chain for each clip.
* `title` draws the text into a PNG file with ImageMagick. Then `ffmpeg` loops the PNG for the chosen time and adds silent audio. vedit escapes the characters `@` and `%` in the text, because ImageMagick gives them a special meaning.
* `sheet` finds the length of the clip with `ffprobe`. Then `ffmpeg` saves the frames in a temporary folder. Then `montage` puts the frames in a grid.

### Tests

The file `test_vedit.py` makes a short clip with `ffmpeg`. It runs each command on the clip and checks the output with `ffprobe` and ImageMagick. To run the tests, use this command in the repository folder:

```
python3 -m unittest
```

## License

GPL version 3 or any later version. See the file `LICENSE`.
