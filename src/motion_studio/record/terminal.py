"""`record terminal`: run a vhs tape against a real shell and add the take to raw/.

The agent's tape is wrapped in a generated one: the recorder's own Output and settings, then a
hidden preamble (a clean environment and prompt, the `Launch` command started through a short
wrapper, Claude Code's folder-trust prompt accepted), then the agent's commands. vhs writes the
terminal's frames to a directory; this module pads them to the take's size at 1:1, encodes a
constant-frame-rate clip and writes the markers sidecar from the tape's `Mark` lines.
"""

import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from motion_studio.analysis.models import NAME_PATTERN, Marker, ScreenMarkers
from motion_studio.errors import InternalError, UserError
from motion_studio.media.ffmpeg import binary, run_ffmpeg
from motion_studio.record.install import terminal_tools
from motion_studio.record.take import (
    Take,
    log_take,
    place_take,
    product_project,
    refuse_existing,
    refuse_while_heavy,
    scratch_take,
    take_stem,
)

DEFAULT_SIZE = (1600, 900)
FPS = 30
TAPE_TIMEOUT_S = 3600
PROMPT = "\u276f "
CLAUDE = "claude"
# Claude Code needs a few seconds to draw its trust prompt, and a few more after it.
LAUNCH_WAIT = {CLAUDE: ("7s", "5s")}
GENERIC_LAUNCH_WAIT = "2s"
SETTINGS_OWNED = {"shell": None, "framerate": None, "width": "--size", "height": "--size"}
HEAD_COMMANDS = {"set", "require"}


@dataclass
class Tape:
    head: list[str] = field(default_factory=lambda: list[str]())
    # A body entry is a tape line, or the index of a Mark in `marks`.
    body: list[str | int] = field(default_factory=lambda: list[str | int]())
    marks: list[tuple[str, int]] = field(default_factory=lambda: list[tuple[str, int]]())
    launch: list[str] | None = None
    launch_line: int = 0


def record_terminal(
    workspace: Path,
    slug: str,
    tape_path: Path,
    *,
    name: str | None = None,
    size: tuple[int, int] = DEFAULT_SIZE,
    cwd: Path | None = None,
    on_step: Callable[[str], None] | None = None,
) -> Take:
    step = on_step or (lambda _msg: None)
    project = product_project(workspace, slug, "record terminal")
    tape_path = tape_path.expanduser().resolve()
    if not tape_path.is_file():
        raise UserError(f"no tape at {tape_path}", hint="pass the path of a vhs .tape file")
    workdir = (cwd or tape_path.parent).expanduser().resolve()
    if not workdir.is_dir():
        raise UserError(f"--cwd {workdir} is not a directory")
    tape = parse_tape(tape_path.read_text(encoding="utf-8"), tape_path.parent)
    stem = take_stem(name, tape_path)
    refuse_existing(project, stem)
    tools = terminal_tools()
    ffmpeg = binary("ffmpeg")
    launch = _resolve_launch(tape)
    refuse_while_heavy(project)

    with scratch_take(project, stem) as scratch:
        _validate(tools["vhs"], tape_path, scratch)
        bin_dir = scratch / "bin"
        bin_dir.mkdir()
        frames = scratch / "frames"
        marks = scratch / "marks"
        marks.mkdir()
        log = scratch / "marks.log"
        _write_ffmpeg_shim(bin_dir / "ffmpeg", ffmpeg, marks, log)
        launch_name = _write_wrapper(bin_dir, launch) if launch else None
        generated = scratch / "take.tape"
        generated.write_text(_generate(tape, frames, marks, size, launch_name), encoding="utf-8")
        step(f"running {tape_path.name} with vhs")
        _run_vhs(tools["vhs"], generated, workdir, _clean_env(bin_dir))
        step("encoding the frames")
        return log_take(project, stem, _encode(tape, frames, log, size, scratch, project.raw, stem))


def parse_tape(text: str, base: Path) -> Tape:
    """Split the agent's tape into its settings, its commands and the recorder's directives."""
    tape = Tape()
    in_head = True
    hidden = False
    seen: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            (tape.head if in_head else tape.body).append(raw)
            continue
        command, _, rest = line.partition(" ")
        rest = rest.strip()
        key = command.lower()
        if key == "output":
            raise UserError(
                f"line {number}: the recorder sets the Output",
                hint="remove the Output line; the clip goes to raw/<name>.mp4",
            )
        if key == "set":
            setting = rest.split(" ", 1)[0].lower()
            if setting in SETTINGS_OWNED:
                option = SETTINGS_OWNED[setting]
                hint = f"pass {option} WIDTHxHEIGHT instead" if option else "remove the line"
                raise UserError(
                    f"line {number}: the recorder sets {rest.split(' ', 1)[0]}", hint=hint
                )
        if command == "Launch":
            if tape.launch is not None:
                raise UserError(f"line {number}: only one Launch per tape")
            if not in_head:
                raise UserError(
                    f"line {number}: Launch must come before every command but Set and Require",
                    hint="move it to the top; the recorder starts it in the hidden preamble",
                )
            argv = shlex.split(rest)
            if not argv:
                raise UserError(f"line {number}: Launch needs a command, e.g. `Launch claude`")
            tape.launch = _absolute_args(argv, base, number)
            tape.launch_line = number
            continue
        if command == "Mark":
            if not rest:
                raise UserError(f"line {number}: Mark needs a name, e.g. `Mark ready`")
            if not re.fullmatch(NAME_PATTERN, rest):
                raise UserError(
                    f"line {number}: marker name {rest!r} must be letters, digits, _ and -"
                )
            if rest in seen:
                raise UserError(f"line {number}: marker {rest} is already placed")
            if hidden:
                # vhs would take the screenshot from the first frame after Show, a wrong time.
                raise UserError(
                    f"line {number}: Mark {rest} is in a hidden part of the tape",
                    hint="place it after Show",
                )
            seen.add(rest)
            tape.marks.append((rest, number))
            tape.body.append(len(tape.marks) - 1)
            in_head = False
            continue
        if in_head and key in HEAD_COMMANDS:
            tape.head.append(raw)
            continue
        in_head = False
        if key in ("hide", "show"):
            hidden = key == "hide"
        tape.body.append(raw)
    return tape


def _absolute_args(argv: list[str], base: Path, number: int) -> list[str]:
    """Paths relative to the tape's folder become absolute; they never reach the screen."""
    command = argv[0]
    if "/" in command:
        path = (base / command).expanduser().resolve()
        if not (path.is_file() and os.access(path, os.X_OK)):
            raise UserError(
                f"line {number}: Launch command {command} is not an executable file",
                hint="paths in Launch are relative to the tape's folder",
            )
        command = str(path)
    args = [
        str((base / a).resolve()) if not a.startswith("-") and (base / a).exists() else a
        for a in argv[1:]
    ]
    return [command, *args]


def _resolve_launch(tape: Tape) -> list[str] | None:
    if tape.launch is None:
        return None
    command = tape.launch[0]
    if "/" in command:
        return tape.launch
    found = shutil.which(command)
    if found is None:
        raise UserError(
            f"line {tape.launch_line}: Launch command {command} not found on PATH",
            hint="install it, or give its path relative to the tape's folder",
        )
    return [found, *tape.launch[1:]]


def _validate(vhs: str, tape_path: Path, scratch: Path) -> None:
    """`vhs validate` the agent's tape with the directives commented out, so lines match."""
    lines = tape_path.read_text(encoding="utf-8").splitlines()
    directives = ("Mark", "Launch")
    checked = [
        f"# {line}" if line.strip().split(" ", 1)[0] in directives else line for line in lines
    ]
    check = scratch / "check.tape"
    check.write_text("\n".join(checked) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [vhs, "validate", str(check)],
        cwd=tape_path.parent,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        output = (proc.stdout + proc.stderr).splitlines()
        kept = [line for line in output if line.strip() and line.strip()[0] not in "┌│└"]
        raise UserError(
            f"{tape_path.name} does not parse:\n" + "\n".join(kept[:20]),
            hint="fix the tape; nothing was recorded",
        )


def _vhs_string(text: str) -> str:
    for quote in ('"', "'", "`"):
        if quote not in text:
            return f"{quote}{text}{quote}"
    raise UserError(f"{text!r} holds every vhs quote character", hint="rename the folder")


def _write_ffmpeg_shim(path: Path, ffmpeg: str, marks: Path, log: Path) -> None:
    # vhs renders each Screenshot from one numbered frame through ffmpeg after the take; for a
    # Mark's screenshot the shim logs that frame's path instead, which is the marker's time.
    path.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        '    */frame-text-*.png) frame="$arg" ;;\n'
        f"    {shlex.quote(str(marks) + '/')}*)\n"
        f'      printf \'%s %s\\n\' "$arg" "$frame" >> {shlex.quote(str(log))}; exit 0 ;;\n'
        "  esac\n"
        "done\n"
        f'exec {shlex.quote(ffmpeg)} "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_wrapper(bin_dir: Path, argv: list[str]) -> str:
    """A script named like the command that runs it with its arguments, so only the name shows."""
    name = Path(argv[0]).name
    wrapper = bin_dir / name
    wrapper.write_text(
        f'#!/bin/sh\nexec {" ".join(shlex.quote(a) for a in argv)} "$@"\n', encoding="utf-8"
    )
    wrapper.chmod(0o755)
    return name


def _generate(
    tape: Tape, frames: Path, marks: Path, size: tuple[int, int], launch: str | None
) -> str:
    lines = [
        f"Output {_vhs_string(str(frames) + '/')}",
        "Set Shell bash",
        f"Set Width {size[0]}",
        f"Set Height {size[1]}",
        f"Set Framerate {FPS}",
        *tape.head,
        "Hide",
        # The environment is already clean; this also catches variables a shell startup sets.
        f"Type \"unset $(compgen -v CLAUDE); export PS1='{PROMPT}'; clear\"",
        "Enter",
        "Sleep 500ms",
    ]
    if launch is not None:
        lines += [f"Type {_vhs_string(launch)}", "Enter"]
        if launch == CLAUDE:
            # The trust prompt focuses "No, exit"; when the folder is trusted the keys are no-ops.
            before, after = LAUNCH_WAIT[CLAUDE]
            lines += [f"Sleep {before}", "Down", "Enter", f"Sleep {after}"]
        else:
            lines.append(f"Sleep {GENERIC_LAUNCH_WAIT}")
    lines.append("Show")
    for entry in tape.body:
        if isinstance(entry, int):
            lines.append(f"Screenshot {_vhs_string(str(marks / f'{entry:04d}.png'))}")
        else:
            lines.append(entry)
    return "\n".join(lines) + "\n"


def _clean_env(bin_dir: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("CLAUDE") and k not in ("VIRTUAL_ENV", "PS1", "PROMPT_COMMAND")
    }
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


def _run_vhs(vhs: str, tape: Path, cwd: Path, env: dict[str, str]) -> None:
    try:
        proc = subprocess.run(
            [vhs, str(tape)],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TAPE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UserError(
            f"the tape ran for more than {TAPE_TIMEOUT_S // 60} minutes",
            hint="shorten the Sleeps; nothing was added to raw/",
        ) from exc
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-20:])
        raise UserError(
            f"vhs failed:\n{tail}", hint="fix the tape and record again; nothing was added to raw/"
        )


def _encode(
    tape: Tape,
    frames: Path,
    log: Path,
    size: tuple[int, int],
    scratch: Path,
    raw: Path,
    stem: str,
) -> Take:
    count = len(list(frames.glob("frame-text-*.png")))
    if count == 0:
        raise UserError(
            "the tape shows nothing: every command is hidden",
            hint="end the tape with visible commands after any Hide; nothing was added to raw/",
        )
    with Image.open(frames / "frame-text-00001.png") as first:
        background = first.convert("RGB").getpixel((0, 0))
    assert isinstance(background, tuple)
    colour = "0x{:02x}{:02x}{:02x}".format(*background[:3])
    width, height = size
    encoded = scratch / "take.mp4"
    run_ffmpeg(
        [
            "-framerate", str(FPS), "-start_number", "1", "-i", frames / "frame-text-%05d.png",
            "-framerate", str(FPS), "-start_number", "1", "-i", frames / "frame-cursor-%05d.png",
            "-filter_complex",
            f"[0][1]overlay,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={colour},format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-r", str(FPS),
            "-movflags", "+faststart", "-an", "-y", encoded,
        ]
    )  # fmt: skip
    duration = round(count / FPS, 3)
    at = _mark_frames(log)
    markers: list[Marker] = []
    for index, (mark, number) in enumerate(tape.marks):
        if index not in at:
            raise InternalError(f"vhs took no screenshot for Mark {mark} on line {number}")
        markers.append(Marker(name=mark, t=round(min((at[index] - 1) / FPS, duration), 3)))
    sidecar_markers = ScreenMarkers(width=width, height=height, markers=markers)
    clip, sidecar = place_take(raw, stem, encoded, sidecar_markers, scratch)
    return Take(
        clip=clip,
        sidecar=sidecar,
        duration_s=duration,
        width=width,
        height=height,
        fps=FPS,
        frames=count,
        markers=[m.name for m in markers],
    )


def _mark_frames(log: Path) -> dict[int, int]:
    """Mark index to the 1-based vhs frame its screenshot was taken from."""
    if not log.is_file():
        return {}
    found: dict[int, int] = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        match = re.search(r"/(\d+)\.png .*frame-text-(\d+)\.png$", line)
        if match:
            found[int(match[1])] = int(match[2])
    return found
