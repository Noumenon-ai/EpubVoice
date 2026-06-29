from __future__ import annotations

import subprocess
import wave
from pathlib import Path
from typing import Sequence

import pytest

from epub_chapters import Chapter
from epub_chapters.synth import ChapterAudio, ChatterboxSynthesizer, SynthOptions, chatterbox_parameter_schema


class FakeChatterbox:
    def __init__(self, fixture: Path) -> None:
        self.fixture = fixture
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        text: str,
        *,
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5,
        pace_weight: float = 1.0,
        temperature: float = 0.8,
        seed: int | None = None,
        audio_prompt_path: str | None = None,
    ) -> bytes:
        self.calls.append(
            {
                "text": text,
                "exaggeration": exaggeration,
                "cfg_weight": cfg_weight,
                "pace_weight": pace_weight,
                "temperature": temperature,
                "seed": seed,
                "audio_prompt_path": audio_prompt_path,
            }
        )
        return self.fixture.read_bytes()


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        return subprocess.CompletedProcess(args=list(command), returncode=0, stdout="", stderr="")


@pytest.fixture
def wav_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "voice.wav"
    _write_silent_wav(path, sample_rate=1000, frames=1500)
    return path


def test_chatterbox_schema_is_sourced_from_live_generate_signature(wav_fixture: Path) -> None:
    schema = chatterbox_parameter_schema(FakeChatterbox(wav_fixture))

    document = schema.to_json_schema()

    assert set(document["properties"]) == {
        "exaggeration",
        "cfg_weight",
        "pace_weight",
        "temperature",
        "seed",
        "audio_prompt_path",
    }
    assert document["properties"]["cfg_weight"]["type"] == "number"
    assert document["properties"]["seed"]["default"] is None


def test_schema_resolves_optional_annotations_to_their_underlying_type(wav_fixture: Path) -> None:
    document = chatterbox_parameter_schema(FakeChatterbox(wav_fixture)).to_json_schema()

    # `seed: int | None` and `audio_prompt_path: str | None` arrive as string
    # annotations under `from __future__ import annotations`; the typed schema
    # must unwrap the Optional and report the real member type, not fall back to
    # a generic string.
    assert document["properties"]["seed"]["type"] == "integer"
    assert document["properties"]["audio_prompt_path"]["type"] == "string"
    assert document["properties"]["exaggeration"]["type"] == "number"


def test_synthesizes_chapter_wavs_and_calls_chatterbox_with_validated_options(
    tmp_path: Path,
    wav_fixture: Path,
) -> None:
    reference = tmp_path / "reference.wav"
    reference.write_bytes(wav_fixture.read_bytes())
    model = FakeChatterbox(wav_fixture)
    synth = ChatterboxSynthesizer(model=model, runner=RecordingRunner())

    rendered = synth.synthesize_chapters(
        [
            Chapter(id="c1", title="Opening", text=" Hello chapter. ", reading_order=0),
            Chapter(id="c2", title="Cut", text="Excluded.", reading_order=1, excluded=True),
        ],
        tmp_path / "rendered",
        options=SynthOptions(
            exaggeration=0.7,
            cfg_weight=0.4,
            pace_weight=1.2,
            temperature=0.9,
            seed=123,
            reference_voice_path=reference,
        ),
    )

    assert len(rendered) == 1
    assert rendered[0].path.is_file()
    assert rendered[0].duration_ms == 1500
    assert model.calls == [
        {
            "text": "Hello chapter.",
            "exaggeration": 0.7,
            "cfg_weight": 0.4,
            "pace_weight": 1.2,
            "temperature": 0.9,
            "seed": 123,
            "audio_prompt_path": str(reference),
        }
    ]


def test_muxes_m4b_with_ffmpeg_concat_metadata_and_cover(tmp_path: Path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    cover = tmp_path / "cover.jpg"
    _write_silent_wav(first, sample_rate=1000, frames=1250)
    _write_silent_wav(second, sample_rate=1000, frames=750)
    cover.write_bytes(b"\xff\xd8\xff\xd9")
    runner = RecordingRunner()
    synth = ChatterboxSynthesizer(model=FakeChatterbox(first), runner=runner)

    build = synth.mux_m4b(
        [
            ChapterAudio(Chapter(id="c1", title="First = Part", text="One.", reading_order=0), first, 1250),
            ChapterAudio(Chapter(id="c2", title="Second", text="Two.", reading_order=1), second, 750),
        ],
        tmp_path / "book.m4b",
        work_dir=tmp_path / "mux",
        cover_path=cover,
    )

    assert runner.commands == [
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(build.concat_path),
            "-i",
            str(build.metadata_path),
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map_metadata",
            "1",
            "-map",
            "2:v",
            "-disposition:v",
            "attached_pic",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(tmp_path / "book.m4b"),
        ]
    ]
    assert build.metadata_path.read_text(encoding="utf-8") == (
        ";FFMETADATA1\n"
        "[CHAPTER]\n"
        "TIMEBASE=1/1000\n"
        "START=0\n"
        "END=1250\n"
        "title=First \\= Part\n"
        "[CHAPTER]\n"
        "TIMEBASE=1/1000\n"
        "START=1250\n"
        "END=2000\n"
        "title=Second\n"
    )
    assert str(first.resolve()) in build.concat_path.read_text(encoding="utf-8")
    assert str(second.resolve()) in build.concat_path.read_text(encoding="utf-8")


def test_voice_preview_returns_audio_bytes(tmp_path: Path, wav_fixture: Path) -> None:
    model = FakeChatterbox(wav_fixture)
    synth = ChatterboxSynthesizer(model=model, runner=RecordingRunner())

    audio = synth.synthesize_preview(tmp_path / "preview.wav", sample_line=" A short preview. ")

    assert audio == wav_fixture.read_bytes()
    assert model.calls[0]["text"] == "A short preview."


def test_rejects_invalid_checkout_like_generation_inputs(tmp_path: Path, wav_fixture: Path) -> None:
    synth = ChatterboxSynthesizer(model=FakeChatterbox(wav_fixture), runner=RecordingRunner())

    with pytest.raises(ValueError, match="temperature"):
        synth.synthesize_preview(
            tmp_path / "preview.wav",
            options=SynthOptions(temperature=9.0),
        )

    with pytest.raises(ValueError, match="sample_line"):
        synth.synthesize_preview(tmp_path / "preview.wav", sample_line=" ")


class PcmChatterbox:
    """Model that returns raw float samples (like a bare TTS tensor) and
    advertises its own sample rate via ``sr`` instead of writing a WAV itself."""

    sr = 16000

    def generate(self, text: str, **_: object) -> list[float]:
        return [0.0, 0.5, -0.5, 1.0, -1.0, 0.25]


def test_raw_sample_output_uses_model_sample_rate_and_encodes_int16(tmp_path: Path) -> None:
    synth = ChatterboxSynthesizer(model=PcmChatterbox(), runner=RecordingRunner())

    synth.synthesize_preview(tmp_path / "preview.wav", sample_line="Sample line.")

    with wave.open(str(tmp_path / "preview.wav"), "rb") as wav:
        # Sample rate is sourced from the model (16000), not the hardcoded 24000.
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getnframes() == 6
        frames = wav.readframes(wav.getnframes())

    decoded = [
        int.from_bytes(frames[offset : offset + 2], byteorder="little", signed=True)
        for offset in range(0, len(frames), 2)
    ]
    # Floats are clamped to [-1, 1] and scaled by 32767.
    assert decoded == [0, 16383, -16383, 32767, -32767, 8191]


def _write_silent_wav(path: Path, *, sample_rate: int, frames: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
