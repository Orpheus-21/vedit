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
| `crop` | Cuts away the edges of the picture. |
| `silence` | Cuts out the silent parts of a clip. |
| `text` | Writes text on a clip, for the whole clip or for a time. |
| `subtitles` | Burns subtitles from an `.srt` file into the picture. |
| `loop` | Plays a clip again and again, the number of times you give. |
| `reverse` | Plays a clip backward. |
| `fade` | Fades a clip in from black, or out to black, with the sound. |
| `audio` | Saves the sound of a clip as an audio file. |
| `mute` | Removes the sound from a clip. |
| `volume` | Makes the sound louder or quieter. |
| `normalize` | Sets the loudness of the sound to -16 LUFS. |
| `frame` | Saves one frame of a clip as an image. |
| `title` | Makes a title card video from text. |
| `sheet` | Makes a contact sheet: a grid of frames from a clip. |

## Requirements

* Python 3.9 or later. The tests pass on Python 3.9, 3.10, 3.11, 3.12, 3.13, and 3.14. The tests also pass on Python 3.8, and `python3 vedit.py` runs there. The install as a command needs Python 3.9, because the build needs `setuptools` 77. I could not test Python 3.7.
* `ffmpeg` and `ffprobe`. The `ffmpeg` build must include the encoders `libx264`, `aac`, and `libmp3lame`. The command `subtitles` needs the filter `subtitles`. The command `text` needs the filter `drawtext`. The tests ran on `ffmpeg` 9.0.1 and on `ffmpeg` 6.1.
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

Use `python3 vedit.py --version` to see the version of vedit. Add `--dry-run` to see the `ffmpeg` and ImageMagick commands without a run. vedit then writes no output file.

Times are in seconds (`90`) or in the form `H:MM:SS` (`0:01:30.5`).

### trim

Cuts from a start time to an end time. If you give no end time, the cut goes to the end of the clip.

```
python3 vedit.py trim clip.mp4 10 25
```

Add `--fast` to copy the streams and not encode them. This is much faster. The cut then starts at the keyframe before the start time, so it is not exact.

```
python3 vedit.py trim clip.mp4 10 25 --fast
```

### join

Joins two or more clips in the order you give them.

```
python3 vedit.py join intro.mp4 main.mp4 outro.mp4
```

Add `--crossfade` to fade from each clip to the next clip. The fade overlaps the clips. Three clips of 4 seconds with `--crossfade 1` give a video of 10 seconds. The fade must be shorter than each clip.

```
python3 vedit.py join intro.mp4 main.mp4 outro.mp4 --crossfade 1
```

### speed

Changes the speed. The factor 2 is twice as fast. The factor 0.5 is half speed. The factor must be from 0.1 to 100.

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

Give the size of the logo with `--width` in pixels, or with `--scale` as a share of the video width. You cannot give both. Without a size, the logo is 100 pixels wide.

```
python3 vedit.py watermark clip.mp4 logo.png --scale 0.15
```

Use `--opacity` to make the logo transparent. The value 1 is solid. The value 0.5 is half transparent.

```
python3 vedit.py watermark clip.mp4 logo.png --opacity 0.5
```

### crop

Gives the width and the height of the part to keep. Both numbers must be even. Without `--x` and `--y`, the part is in the center of the picture. `--x` and `--y` are the left edge and the top edge of the part, in pixels. The part must be inside the video.

```
python3 vedit.py crop clip.mp4 640 360
python3 vedit.py crop clip.mp4 640 360 --x 0 --y 0
```

### silence

Finds the parts of the clip that are quieter than `--threshold` for at least `--min-length` seconds. It cuts these parts out and joins the rest. The command stops with an error if it finds no silence. It also stops for a clip with no sound.

```
python3 vedit.py silence clip.mp4 --threshold -30 --min-length 0.5
```

### text

Writes a text on the picture. `--position` is `top-left`, `top-center`, `top-right`, `center`, `bottom-left`, `bottom-center`, or `bottom-right`. `--from` and `--to` set the times in seconds when the text shows. The command needs an `ffmpeg` build with the filter `drawtext`. The text uses the default font of `ffmpeg`.

```
python3 vedit.py text clip.mp4 "Hello" --position top-left --from 1 --to 3
```

### subtitles

Draws the text of an `.srt` file into the picture. The command needs an `ffmpeg` build with the filter `subtitles`, which uses the library `libass`. The text has the default style and the default font of `libass`.

```
python3 vedit.py subtitles clip.mp4 clip.srt
```

### loop

Gives the number of times that the clip plays in total. The count 3 gives a clip that is three times as long. The command copies the streams and does not encode them.

```
python3 vedit.py loop clip.mp4 3
```

### reverse

Plays a clip backward, the picture and the sound. The `ffmpeg` filters hold the whole clip in memory, so use this command for short clips only.

```
python3 vedit.py reverse clip.mp4
```

### fade

Give `--fade-in`, `--fade-out`, or both. Each value is a time in seconds. The fades must fit in the length of the clip. The sound fades with the picture.

```
python3 vedit.py fade clip.mp4 --fade-in 1 --fade-out 2
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

### volume

Multiplies the sound by a factor. The factor 2 is twice the volume. The factor 0.5 is half the volume. The command copies the video stream. It stops with an error for a clip with no sound.

```
python3 vedit.py volume clip.mp4 1.5
```

### normalize

Sets the loudness of the sound to -16 LUFS. The command runs one pass of the `ffmpeg` filter `loudnorm`, and sets the sample rate to 48000 Hz. It copies the video stream. It stops with an error for a clip with no sound.

```
python3 vedit.py normalize clip.mp4
```

### frame

```
python3 vedit.py frame clip.mp4 5
```

### title

Makes a video with centered text. The text must not be empty. The video has a silent audio track, so you can join it with clips that have sound.

```
python3 vedit.py title "My Holiday" --seconds 3
python3 vedit.py join title.mp4 clip.mp4 -o holiday.mp4
```

Use `--fade` to fade the card in from black and out to black. The value is the time of each fade in seconds. The two fades must fit in the length of the card.

```
python3 vedit.py title "My Holiday" --seconds 4 --fade 1
```

Use `--font` to choose the font. Give a font name from the command `magick -list font`, or the path of a font file. Without `--font`, ImageMagick uses its default font.

```
python3 vedit.py title "My Holiday" --font /path/to/font.ttf
```

### sheet

Takes one frame from the middle of each equal part of the clip. Then it puts the frames in a grid.

```
python3 vedit.py sheet clip.mp4 --cols 4 --rows 3
```

## Batch use

vedit works on one file for each run. To change many files, use a loop of the shell.

This example compresses each `.mp4` file in the current folder. It saves the results in the folder `small`:

```
mkdir small
for f in *.mp4; do python3 vedit.py compress "$f" -o "small/$f"; done
```

The loop does not read the folder `small`, so you can run it again. If a result file exists, vedit stops with an error for that file. The loop then goes on with the next file. Add `-f` to overwrite the results of an earlier run:

```
for f in *.mp4; do python3 vedit.py -f compress "$f" -o "small/$f"; done
```

Save the results in another folder. Without `-o`, vedit writes `clip_small.mp4` next to `clip.mp4`. The next run of the loop then also compresses `clip_small.mp4`.

## Configuration

vedit has no configuration file. All settings are command-line options.

| Option | Commands | Default | Effect |
|---|---|---|---|
| `-o`, `--output` | all | see below | The path of the output file. |
| `-f`, `--force` | all | off | Overwrites an output file that exists. You can write it before or after the command name. |
| `--dry-run` | all | off | Prints each `ffmpeg` and ImageMagick command and does not run it. You can write it before or after the command name. |
| `--crossfade` | `join` | none | Fade time in seconds between clips. Use a number above 0. |
| `--fast` | `trim` | off | Copies the streams and does not encode. The cut starts at the keyframe before the start time. |
| `--fps` | `gif` | 12 | Frames per second of the GIF. Use 1 or more. |
| `--width` | `gif` | 480 | Largest width of the GIF in pixels. vedit does not enlarge a clip. |
| `--crf` | `compress` | 28 | Quality, from 0 to 51. A lower value gives higher quality. |
| `--width`, `--height` | `resize` | none | New size in pixels. Give at least one. |
| `--position` | `watermark` | `bottom-right` | Place of the logo. |
| `--width` | `watermark` | 100 | Width of the logo in pixels. Use 1 or more. You cannot use it with `--scale`. |
| `--scale` | `watermark` | none | Width of the logo as a share of the video width. Use a number above 0 and at most 1. |
| `--margin` | `watermark` | 10 | Space between the logo and the edge in pixels. Use 0 or more. |
| `--opacity` | `watermark` | 1 | How solid the logo is. Use a number above 0 and at most 1. |
| `--x` | `crop` | the center | Left edge of the part to keep, in pixels. Use 0 or more. |
| `--y` | `crop` | the center | Top edge of the part to keep, in pixels. Use 0 or more. |
| `--fade-in` | `fade` | none | Length of the fade in from black, in seconds. Use a number above 0. |
| `--fade-out` | `fade` | none | Length of the fade out to black, in seconds. Use a number above 0. |
| `--threshold` | `silence` | -30 | Level in dB. Sound quieter than this level is silence. Use a number below 0. |
| `--min-length` | `silence` | 0.5 | Shortest silence in seconds that vedit cuts out. Use a number above 0. |
| `--position` | `text` | `bottom-center` | Place of the text. |
| `--size` | `text` | 36 | Height of the letters in pixels. |
| `--color` | `text` | `white` | Color of the text. Use an `ffmpeg` color name or `0xRRGGBB`. This is not an ImageMagick color. |
| `--from` | `text` | the start | Time in seconds when the text appears. Use 0 or more. |
| `--to` | `text` | the end | Time in seconds when the text goes away. Use 0 or more. |
| `--seconds` | `title` | 3 | Length of the title card in seconds. Use a number above 0. |
| `--size` | `title` | `1280x720` | Size of the title card. Both numbers must be even. |
| `--fade` | `title` | none | Time in seconds of the fade in and of the fade out. Use a number above 0. |
| `--fps` | `title` | 25 | Frames per second of the title card. Use 1 or more. |
| `--font` | `title` | the ImageMagick default | Font name or path of a font file. vedit stops with an error for a font that ImageMagick cannot use. |
| `--bg` | `title` | `black` | Background color. Any ImageMagick color works, for example `black` or `#336699`. vedit stops with an error for an unknown color. |
| `--fg` | `title` | `white` | Text color. The rule for an unknown color is the same as for `--bg`. |
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
| `crop` | `clip_crop.mp4` |
| `silence` | `clip_nosilence.mp4` |
| `text` | `clip_text.mp4` |
| `subtitles` | `clip_subs.mp4` |
| `loop` | `clip_loop.mp4` |
| `reverse` | `clip_reverse.mp4` |
| `fade` | `clip_fade.mp4` |
| `audio` | `clip_audio.mp3` |
| `mute` | `clip_mute.mp4` |
| `volume` | `clip_volume.mp4` |
| `normalize` | `clip_norm.mp4` |
| `frame` | `clip_frame.png` |
| `sheet` | `clip_sheet.jpg` |
| `title` | `title.mp4` in the current folder |

If the output file exists, vedit stops with an error. Use `-f` to overwrite the file. vedit also stops with an error if the output file and the input file are the same file.

If a run fails, or you press Ctrl+C, vedit deletes the output file that the run made. vedit does not delete an output file that existed before the run. After Ctrl+C, vedit prints `vedit: interrupted` and exits with the code 130.

## Limits

* `trim` encodes the video again. The cut is exact, but the command is slower than a stream copy. Use `--fast` for a stream copy.
* The commands that encode the video write H.264 with the pixel format `yuv420p`. These commands are `trim`, `join`, `speed`, `compress`, `rotate`, and `watermark`.
* H.264 needs an even width and an even height. The commands that encode cut off one pixel of an odd width or an odd height.
* `join` gives every clip the size and the average frame rate of the first clip. The size is the size that a player shows, after the turn that the metadata gives. `join` adds black bars to keep the aspect ratio. If one clip has no sound, the output has no sound.
* `speed` accepts a factor from 0.1 to 100.
* `silence` builds one command line with a cut for each part to keep. A clip with several hundred pauses can make the command line too long.
* `reverse` holds the whole clip in memory. A long clip can use all the memory of the computer.

## How it works

The whole program is the file `vedit.py`. It uses only the Python standard library.

Each command is a function named `cmd_NAME`. The function reads the options, checks the input file, and builds a list of arguments. Two helpers run the programs:

* `run_ffmpeg` runs `ffmpeg`. It stops with an error if the output file exists and `-f` is not set. It also stops if the output file is the input file, or if `ffmpeg` writes no file.
* `run_magick` runs ImageMagick 7 (`magick`) or ImageMagick 6 (`convert`, `montage`).
* Both helpers call `run_tool`. If the program fails or you press Ctrl+C, `run_tool` deletes the output file that the run made.

vedit passes the arguments as a list and never starts a shell. A file name with spaces, quotes, or a colon is safe. vedit gives `ffmpeg` and `ffprobe` each path with the prefix `file:`, because `ffmpeg` reads the text before a colon as a protocol name.

Some commands use more than one step:

* `join` probes the first clip with `ffprobe`. It reads the size, the turn in the metadata, and the average frame rate. Then it runs the `ffmpeg` concat filter, or the filters `xfade` and `acrossfade` for `--crossfade`, with one scale and pad chain for each clip.
* `title` checks the two colors and the font with ImageMagick, because ImageMagick only prints a warning for an unknown color. Then it draws the text into a PNG file. Then `ffmpeg` loops the PNG for the chosen time and adds silent audio. vedit escapes the characters `@` and `%` in the text, because ImageMagick gives them a special meaning.
* `sheet` finds the length of the clip with `ffprobe`. Then `ffmpeg` saves the frames in a temporary folder. Then `montage` puts the frames in a grid.

### Tests

The file `test_vedit.py` makes a short clip with `ffmpeg`. It runs each command on the clip and checks the output with `ffprobe` and `ffmpeg`. A test skips with a message if `ffmpeg`, `ffprobe`, or ImageMagick is missing. The tests for `title` and `sheet` need ImageMagick. To run the tests, use this command in the repository folder:

```
python3 -m unittest
```

A GitHub Actions workflow runs the same command on every push and pull request. The workflow file is `.github/workflows/test.yml`.

## Contributing

Open an issue or a pull request at https://github.com/Orpheus-21/vedit. Before you send a pull request, run the tests:

```
python3 -m unittest
```

Follow these rules:

* Add one test for each new command and for each fix.
* Make one commit for each change.
* Write the subject of a commit in the imperative, for example `Add the crop command`.
* Change the README if the change changes the behavior.

The GitHub Actions workflow runs the tests on every pull request.

## License

GPL version 3 or any later version. See the file `LICENSE`.
