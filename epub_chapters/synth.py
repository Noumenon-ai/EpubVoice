from __future__ import annotations

import array
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import wave
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from .models import Chapter
from .normalizer import normalize_text


class SynthError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatterboxParameter:
    name: str
    type: str
    required: bool
    default: object | None = None


@dataclass(frozen=True)
class ChatterboxParameterSchema:
    parameters: tuple[ChatterboxParameter, ...]

    def names(self) -> set[str]:
        return {parameter.name for parameter in self.parameters}

    def to_json_schema(self) -> dict[str, object]:
        properties: dict[str, object] = {}
        required: list[str] = []
        for parameter in self.parameters:
            properties[parameter.name] = {"type": parameter.type}
            if not parameter.required:
                properties[parameter.name]["default"] = parameter.default
            if parameter.required:
                required.append(parameter.name)
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        }


@dataclass(frozen=True)
class SynthOptions:
    exaggeration: float | None = None
    cfg_weight: float | None = None
    pace_weight: float | None = None
    temperature: float | None = None
    seed: int | None = None
    reference_voice_path: str | Path | None = None
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ChapterAudio:
    chapter: Chapter
    path: Path
    duration_ms: int


@dataclass(frozen=True)
class AudiobookBuild:
    output_path: Path
    chapter_wavs: tuple[ChapterAudio, ...]
    metadata_path: Path
    concat_path: Path


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class ChatterboxSynthesizer:
    def __init__(
        self,
        model: object | None = None,
        *,
        ffmpeg_path: str = "ffmpeg",
        runner: Runner | None = None,
    ) -> None:
        self._model = model if model is not None else load_chatterbox_model()
        self._ffmpeg_path = ffmpeg_path
        self._runner = runner or self._run_command
        self._uses_default_runner = runner is None
        self.parameter_schema = chatterbox_parameter_schema(self._model)
        # The engine (and its underlying model) is shared as a singleton across
        # the API's render worker pool and preview request threads. Most TTS
        # model instances are not safe for concurrent inference, so serialize
        # generation per utterance to avoid corrupted audio or crashes.
        self._generate_lock = threading.Lock()

    def synthesize_chapters(
        self,
        chapters: Iterable[Chapter],
        output_dir: str | Path,
        *,
        options: SynthOptions | None = None,
    ) -> tuple[ChapterAudio, ...]:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        selected = tuple(chapter for chapter in chapters if not chapter.excluded)
        if not selected:
            raise ValueError("at least one included chapter is required")

        rendered: list[ChapterAudio] = []
        for index, chapter in enumerate(selected, start=1):
            text = normalize_text(chapter.text)
            if not text:
                raise ValueError(f"chapter {chapter.id} has no synthesizable text")
            wav_path = destination / f"{index:04d}-{_safe_stem(chapter.title)}.wav"
            self._write_generated_audio(text, wav_path, options or SynthOptions())
            rendered.append(ChapterAudio(chapter=chapter, path=wav_path, duration_ms=_wav_duration_ms(wav_path)))
        return tuple(rendered)

    def build_m4b(
        self,
        chapters: Iterable[Chapter],
        output_path: str | Path,
        *,
        work_dir: str | Path,
        cover_path: str | Path | None = None,
        options: SynthOptions | None = None,
    ) -> AudiobookBuild:
        chapter_wavs = self.synthesize_chapters(chapters, Path(work_dir) / "chapters", options=options)
        return self.mux_m4b(chapter_wavs, output_path, work_dir=work_dir, cover_path=cover_path)

    def mux_m4b(
        self,
        chapter_wavs: Sequence[ChapterAudio],
        output_path: str | Path,
        *,
        work_dir: str | Path,
        cover_path: str | Path | None = None,
    ) -> AudiobookBuild:
        if not chapter_wavs:
            raise ValueError("chapter_wavs cannot be empty")
        if self._uses_default_runner and not shutil.which(self._ffmpeg_path):
            raise SynthError(f"ffmpeg executable not found: {self._ffmpeg_path}")

        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        concat_path = work / "chapters.concat.txt"
        metadata_path = work / "chapters.ffmetadata"
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        concat_path.write_text(_concat_demuxer(chapter_wavs), encoding="utf-8")
        metadata_path.write_text(_ffmetadata(chapter_wavs), encoding="utf-8")

        command = [
            self._ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-i",
            str(metadata_path),
        ]
        if cover_path is not None:
            cover = Path(cover_path)
            if not cover.is_file():
                raise FileNotFoundError(cover)
            command.extend(["-i", str(cover)])
        command.extend(["-map", "0:a", "-map_metadata", "1"])
        if cover_path is not None:
            command.extend(["-map", "2:v", "-disposition:v", "attached_pic", "-c:v", "copy"])
        command.extend(["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)])
        self._runner(command)
        return AudiobookBuild(
            output_path=out,
            chapter_wavs=tuple(chapter_wavs),
            metadata_path=metadata_path,
            concat_path=concat_path,
        )

    def synthesize_preview(
        self,
        output_path: str | Path,
        *,
        sample_line: str = "This is a short voice preview.",
        options: SynthOptions | None = None,
    ) -> bytes:
        text = normalize_text(sample_line)
        if not text:
            raise ValueError("sample_line cannot be empty")
        if len(text) > 500:
            raise ValueError("sample_line must be 500 characters or fewer")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._write_generated_audio(text, out, options or SynthOptions())
        return out.read_bytes()

    def _write_generated_audio(self, text: str, output_path: Path, options: SynthOptions) -> None:
        kwargs = _chatterbox_kwargs(self.parameter_schema, options)
        with self._generate_lock:
            generated = _call_model(self._model, text, kwargs)
            _write_audio_result(generated, output_path, _model_sample_rate(self._model))
        _validate_wav(output_path)

    def _run_command(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip() or "ffmpeg failed"
            raise SynthError(details)
        return completed


def load_chatterbox_model() -> object:
    try:
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise SynthError("chatterbox.tts is not installed") from exc

    if hasattr(ChatterboxTTS, "from_pretrained"):
        return ChatterboxTTS.from_pretrained()
    if hasattr(ChatterboxTTS, "load_model"):
        return ChatterboxTTS.load_model()
    return ChatterboxTTS()


def chatterbox_parameter_schema(model: object) -> ChatterboxParameterSchema:
    callable_obj = _model_generate_callable(model)
    signature = inspect.signature(callable_obj)
    parameters: list[ChatterboxParameter] = []
    for name, parameter in signature.parameters.items():
        if name in {"self", "text", "prompt", "input_text"}:
            continue
        if parameter.kind in {
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.POSITIONAL_ONLY,
        }:
            continue
        default = None if parameter.default is inspect.Parameter.empty else parameter.default
        parameters.append(
            ChatterboxParameter(
                name=name,
                type=_schema_type(parameter.annotation, default),
                required=parameter.default is inspect.Parameter.empty,
                default=_jsonable_default(default),
            )
        )
    return ChatterboxParameterSchema(tuple(parameters))


def _call_model(model: object, text: str, kwargs: Mapping[str, object]) -> object:
    callable_obj = _model_generate_callable(model)
    signature = inspect.signature(callable_obj)
    if "text" in signature.parameters:
        return callable_obj(text=text, **kwargs)
    if "input_text" in signature.parameters:
        return callable_obj(input_text=text, **kwargs)
    if "prompt" in signature.parameters:
        return callable_obj(prompt=text, **kwargs)
    return callable_obj(text, **kwargs)


def _model_sample_rate(model: object, fallback: int = 24000) -> int:
    """Resolve the model's output sample rate.

    Chatterbox's ``generate`` returns a bare audio tensor with no embedded
    rate, so when we fall back to writing raw PCM we must take the rate from
    the model (exposed as ``sr``/``sample_rate``) rather than assume 24000 and
    risk pitch/speed-shifted audio on a model that differs.
    """
    for attribute in ("sr", "sample_rate"):
        rate = getattr(model, attribute, None)
        try:
            rate = int(rate)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            return rate
    return fallback


def _model_generate_callable(model: object) -> Callable[..., object]:
    for name in ("generate", "synthesize", "tts"):
        candidate = getattr(model, name, None)
        if callable(candidate):
            return candidate
    if callable(model):
        return model
    raise TypeError("model must expose generate, synthesize, tts, or be callable")


def _chatterbox_kwargs(schema: ChatterboxParameterSchema, options: SynthOptions) -> dict[str, object]:
    values: dict[str, object] = dict(options.extra)
    aliases = {
        "exaggeration": options.exaggeration,
        "cfg_weight": options.cfg_weight,
        "cfg": options.cfg_weight,
        "pace_weight": options.pace_weight,
        "temperature": options.temperature,
        "seed": options.seed,
        "audio_prompt_path": options.reference_voice_path,
        "reference_voice_path": options.reference_voice_path,
        "voice_path": options.reference_voice_path,
    }
    allowed = schema.names()
    for name, value in aliases.items():
        if value is not None:
            if name not in allowed:
                continue
            values.setdefault(name, value)

    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unsupported Chatterbox parameters: {', '.join(sorted(unknown))}")

    if "reference_voice_path" in values:
        values["reference_voice_path"] = _existing_path(values["reference_voice_path"])
    if "audio_prompt_path" in values:
        values["audio_prompt_path"] = _existing_path(values["audio_prompt_path"])
    if "voice_path" in values:
        values["voice_path"] = _existing_path(values["voice_path"])

    _validate_numeric(values, "exaggeration", minimum=0.0, maximum=2.0)
    _validate_numeric(values, "cfg_weight", minimum=0.0, maximum=2.0)
    _validate_numeric(values, "cfg", minimum=0.0, maximum=2.0)
    _validate_numeric(values, "pace_weight", minimum=0.0, maximum=2.0)
    _validate_numeric(values, "temperature", minimum=0.0, maximum=5.0)
    if "seed" in values and (not isinstance(values["seed"], int) or values["seed"] < 0):
        raise ValueError("seed must be a non-negative integer")

    return values


def _write_audio_result(generated: object, output_path: Path, default_sample_rate: int = 24000) -> None:
    if isinstance(generated, (bytes, bytearray, memoryview)):
        output_path.write_bytes(bytes(generated))
        return
    if isinstance(generated, (str, os.PathLike)):
        source = Path(generated)
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.resolve() != output_path.resolve():
            shutil.copyfile(source, output_path)
        return
    if isinstance(generated, Mapping):
        if "wav" in generated:
            _write_audio_result(generated["wav"], output_path, default_sample_rate)
            return
        if "audio" in generated:
            sample_rate = int(generated.get("sample_rate", generated.get("sr", default_sample_rate)))
            _write_pcm_wave(generated["audio"], sample_rate, output_path)
            return
    if isinstance(generated, tuple) and len(generated) == 2:
        first, second = generated
        if isinstance(first, int):
            _write_pcm_wave(second, first, output_path)
            return
        if isinstance(second, int):
            _write_pcm_wave(first, second, output_path)
            return
    _write_pcm_wave(generated, default_sample_rate, output_path)


def _write_pcm_wave(samples: object, sample_rate: int, output_path: Path) -> None:
    if sample_rate <= 0:
        raise SynthError(f"invalid sample rate for generated audio: {sample_rate}")
    values = _flatten_samples(samples)
    if not values:
        raise SynthError("model returned no audio samples")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array.array("h", (_to_int16(sample) for sample in values))
    # array uses native byte order; the WAV PCM container is little-endian.
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def _to_int16(sample: object) -> int:
    if isinstance(sample, float):
        clamped = max(-1.0, min(1.0, sample))
        return int(clamped * 32767)
    integer = int(sample)
    return max(-32768, min(32767, integer))


def _flatten_samples(samples: object) -> list[float | int]:
    if hasattr(samples, "detach"):
        samples = samples.detach()
    if hasattr(samples, "cpu"):
        samples = samples.cpu()
    if hasattr(samples, "numpy"):
        samples = samples.numpy()
    if hasattr(samples, "tolist"):
        samples = samples.tolist()
    if not isinstance(samples, Iterable) or isinstance(samples, (str, bytes, bytearray)):
        raise SynthError("model returned unsupported audio data")
    flattened: list[float | int] = []
    for item in samples:
        if isinstance(item, Iterable) and not isinstance(item, (str, bytes, bytearray)):
            flattened.extend(_flatten_samples(item))
        else:
            flattened.append(item)
    return flattened


def _concat_demuxer(chapter_wavs: Sequence[ChapterAudio]) -> str:
    lines = []
    for chapter_audio in chapter_wavs:
        escaped = str(chapter_audio.path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def _ffmetadata(chapter_wavs: Sequence[ChapterAudio]) -> str:
    lines = [";FFMETADATA1"]
    start = 0
    for chapter_audio in chapter_wavs:
        end = start + chapter_audio.duration_ms
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start}",
                f"END={end}",
                f"title={_escape_metadata(chapter_audio.chapter.title)}",
            ]
        )
        start = end
    return "\n".join(lines) + "\n"


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    if rate <= 0:
        raise SynthError(f"invalid WAV sample rate: {path}")
    return int(math.ceil(frames / rate * 1000))


def _validate_wav(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise SynthError(f"model did not write audio: {path}")
    _wav_duration_ms(path)


def _escape_metadata(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("=", "\\=")


def _schema_type(annotation: object, default: object) -> str:
    annotation = _unwrap_optional(annotation)
    # bool is a subclass of int, so it must be checked before integer.
    if annotation in {bool, "bool"} or (isinstance(default, bool)):
        return "boolean"
    if annotation in {int, "int"} or (isinstance(default, int) and not isinstance(default, bool)):
        return "integer"
    if annotation in {float, "float"} or isinstance(default, float):
        return "number"
    if annotation in {str, Path, "str", "Path", "PathLike"} or isinstance(default, (str, Path)):
        return "string"
    return "string"


def _unwrap_optional(annotation: object) -> object:
    """Reduce an Optional/Union annotation to its single meaningful member.

    Handles both runtime types (``int | None``, ``typing.Optional[int]``) and the
    string annotations produced by ``from __future__ import annotations`` (e.g.
    ``"int | None"`` or ``"Optional[int]"``), which is how the live Chatterbox
    ``generate`` signature declares parameters such as ``seed`` and
    ``audio_prompt_path``.
    """
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if args:
        return args[0]

    if isinstance(annotation, str):
        text = annotation.strip()
        optional = re.fullmatch(r"(?:typing\.)?Optional\[(.+)\]", text)
        if optional:
            text = optional.group(1).strip()
        members = [
            member.strip()
            for member in re.split(r"\|", text)
            if member.strip() and member.strip() not in {"None", "NoneType"}
        ]
        if members:
            # Strip a leading module qualifier (e.g. "os.PathLike" -> "PathLike").
            return members[0].rsplit(".", 1)[-1]
    return annotation


def _jsonable_default(default: object) -> object | None:
    if default is None or isinstance(default, (str, int, float, bool)):
        return default
    if isinstance(default, Path):
        return str(default)
    try:
        json.dumps(default)
    except TypeError:
        return str(default)
    return default


def _existing_path(value: object) -> str:
    path = Path(value) if isinstance(value, (str, os.PathLike)) else None
    if path is None or not path.is_file():
        raise FileNotFoundError(value)
    return str(path)


def _validate_numeric(values: Mapping[str, object], key: str, *, minimum: float, maximum: float) -> None:
    if key not in values:
        return
    value = values[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    if not minimum <= float(value) <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")


def _safe_stem(value: str) -> str:
    normalized = normalize_text(value).lower()
    stem = "".join(character if character.isalnum() else "-" for character in normalized)
    stem = "-".join(part for part in stem.split("-") if part)
    return stem[:80] or "chapter"
