"""Press-to-talk MVP: screen recording → local STT → LLM → offline Serena → USB speaker."""

import argparse
import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
import threading
import wave
from array import array
from pathlib import Path
from time import perf_counter

import serial

from gateway.config import Settings
from integrations.cao import CAOClient, ProjectAwareProvider
from integrations.llm import CompatibleProvider, MockProvider
from integrations.local_tts import RUNTIME
from integrations.resident import ResidentModel
from integrations.stt import MockSTT, stereo_wav_to_mono
from integrations.tts import MockTTS, TTSOutputTooLong, decode_playback_wav
from scripts.capture_audio import CaptureTimeout, receive_pcm
from scripts.play_audio import upload


def input_wav(pcm):
    if len(pcm) != 320000:
        raise ValueError("Expected a verified 5-second stereo recording")
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(pcm)
    return stream.getvalue()


class ProcessWhisper:
    def __init__(self, model):
        self.model = model

    def _transcribe(self, wav):
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "gateway.talk_stt_worker", self.model],
                cwd=Path(__file__).resolve().parents[1],
                input=wav,
                capture_output=True,
                timeout=90,
                check=True,
                env=env,
            )
            # Third-party progress may precede the final JSON; never log it.
            text = json.loads(result.stdout.decode().strip().splitlines()[-1])["text"]
            if not isinstance(text, str) or not text.strip() or len(text) > 500:
                raise ValueError("Invalid transcript")
            return text.strip()
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
            raise RuntimeError("Local STT failed or exceeded 90 seconds") from None

    async def transcribe(self, wav):
        return await asyncio.to_thread(self._transcribe, wav)


class ResidentWhisper:
    def __init__(self, model):
        self.worker = ResidentModel(
            [sys.executable, "-m", "gateway.talk_stt_worker", model, "--resident"]
        )

    async def transcribe(self, wav):
        response = await self.worker.request({"wav": base64.b64encode(wav).decode()})
        text = response.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise RuntimeError("Invalid transcript")
        return text.strip()


class ResidentSerena:
    def __init__(self):
        self.worker = ResidentModel(
            [str(RUNTIME), "-m", "integrations.local_tts_worker", "--resident"], 180
        )

    async def synthesize(self, text):
        response = await self.worker.request({"text": text, "voice": "Serena"})
        data = base64.b64decode(response["wav"], validate=True)
        decode_playback_wav(data)
        return data


class SharedUSB:
    def __init__(self, device):
        self.device = device
        self.lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.device, name)

    def write(self, data):
        with self.lock:
            return self.device.write(data)


def speech_chunks(answer):
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 120:
        raise ValueError("Voice reply must contain 1–120 characters")
    text = answer.strip()
    # Preserve every character; prefer punctuation boundaries, otherwise 20 chars.
    chunks = []
    while text:
        window = text[:20]
        ends = list(re.finditer(r"[，。！？；、,.!?;]", window))
        end = ends[-1].end() if ends else len(window)
        chunks.append(text[:end])
        text = text[end:]
    return chunks


async def synthesize_bounded(tts, text):
    """Retry smaller text segments if a voice exceeds 5s; never truncate PCM."""
    try:
        return [decode_playback_wav(await tts.synthesize(text))]
    except TTSOutputTooLong:
        if len(text) <= 4:
            raise
        mid = len(text) // 2
        return await synthesize_bounded(tts, text[:mid]) + await synthesize_bounded(tts, text[mid:])


async def respond(wav, stt, provider, tts, play, provider_timeout=15, status=print):
    timings = {}
    turn_started = perf_counter()
    status("Transcribing")
    started = perf_counter()
    # Deterministic quiet-input gate before STT to reduce silence hallucinations.
    audio = stereo_wav_to_mono(wav)
    samples = array("h", audio.pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or sum(int(v) * int(v) for v in samples) / len(samples) < 30**2:
        raise ValueError("No audible speech; please try again")
    text = await stt.transcribe(wav)
    timings["stt_seconds"] = round(perf_counter() - started, 3)
    status("Thinking")
    started = perf_counter()
    answer = await asyncio.wait_for(provider.reply(text), provider_timeout)
    answer_source = getattr(provider, "last_source", "llm")
    timings["llm_seconds"] = round(perf_counter() - started, 3)
    status("Synthesizing")
    started = perf_counter()
    # Generate and validate the entire answer before any playback. No partial reply on TTS failure.
    buffers = []
    for chunk in speech_chunks(answer):
        buffers.extend(await synthesize_bounded(tts, chunk))
    timings["tts_seconds"] = round(perf_counter() - started, 3)
    status("Playing")
    timings["before_play_seconds"] = round(perf_counter() - turn_started, 3)
    started = perf_counter()
    for pcm in buffers:
        await play(pcm)
    timings["play_seconds"] = round(perf_counter() - started, 3)
    return {"segments": len(buffers), "answer_source": answer_source, **timings}


async def serve(args):
    settings = Settings()
    if args.mock:

        class OfflineSTT:
            async def transcribe(self, wav):
                return await MockSTT().transcribe(stereo_wav_to_mono(wav))

        stt, provider, tts = OfflineSTT(), MockProvider(), MockTTS()
    else:
        if settings.stt_provider != "mlx-whisper" or settings.provider == "mock":
            raise ValueError("Configure local Whisper and a real LLM in .env, or use --mock")
        stt = ResidentWhisper(settings.stt_model)
        provider = CompatibleProvider(settings, voice_mode=True)
        if settings.cao_enabled:
            provider = ProjectAwareProvider(
                provider,
                CAOClient(settings.cao_base_url, settings.cao_timeout_seconds),
            )
        tts = ResidentSerena()
    # Own one USB handle across capture, processing and playback; no competing reader.
    with serial.Serial(
        args.port, 115200, timeout=0.5, write_timeout=5, exclusive=True
    ) as raw_device:
        device = SharedUSB(raw_device)
        device.reset_input_buffer()

        async def play(pcm):
            try:
                return await asyncio.to_thread(
                    upload,
                    device,
                    pcm,
                    80,
                    lambda: (
                        setattr(device, "_muse_first_audio", perf_counter())
                        if not getattr(device, "_muse_first_audio", None)
                        else None
                    ),
                )
            except ValueError as error:
                message = str(error)
                rejected = re.fullmatch(r"Device rejected playback \(([a-z_]{1,24})\)", message)
                code = (
                    rejected[1]
                    if rejected
                    else (
                        "timeout"
                        if message.startswith("Playback response timed out:")
                        else "validation"
                    )
                )
                print(f"USB playback failed: {code}", flush=True)
                raise

        state = ["Thinking"]

        def send_state(value=None):
            with device.lock:
                if value is not None:
                    state[0] = value
                device.device.write(json.dumps({"voice_state": state[0]}).encode() + b"\n")

        async def heartbeat():
            while True:
                await asyncio.to_thread(send_state)
                await asyncio.sleep(2)

        task = asyncio.create_task(heartbeat())
        try:
            send_state("Thinking")
            if not args.mock:
                print("Preloading Whisper / Serena", flush=True)
                await stt.worker.start()
                await tts.worker.start()
            await conversation(args, device, stt, provider, tts, play, settings, send_state)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if not args.mock:
                await stt.worker.close()
                await tts.worker.close()


async def conversation(args, device, stt, provider, tts, play, settings, send_state):
    turn = 0
    while True:
        send_state("Ready")
        print(
            "Ready: tap Audio Input → Record 5s, speak; wait until Ready before pressing again",
            flush=True,
        )
        phase = "Receiving"

        def status(state):
            nonlocal phase
            phase = state
            send_state("Speaking" if state == "Playing" else "Thinking")
            print(state, flush=True)

        try:
            device._muse_first_audio = None
            device._muse_capture_started = None
            pcm = await asyncio.to_thread(receive_pcm, device, 5, True)
            recorded = perf_counter()
            result = await respond(
                input_wav(pcm),
                stt,
                provider,
                tts,
                play,
                settings.provider_timeout_seconds,
                status=status,
            )
            turn += 1
            result["turn"] = turn
            result["after_receive_seconds"] = round(perf_counter() - recorded, 3)
            capture_started = getattr(device, "_muse_capture_started", None)
            first_audio = getattr(device, "_muse_first_audio", None)
            if first_audio:
                result["first_audio_after_receive_seconds"] = round(first_audio - recorded, 3)
            if capture_started:
                result["turn_seconds"] = round(perf_counter() - capture_started, 3)
                result["capture_export_seconds"] = round(recorded - capture_started, 3)
                if first_audio:
                    result["first_audio_from_button_seconds"] = round(
                        first_audio - capture_started, 3
                    )
            print("Done: " + json.dumps(result), flush=True)
        except CaptureTimeout:
            if args.once:
                raise
            continue
        except (ValueError, RuntimeError, TimeoutError, OSError, serial.SerialException):
            # Never print upstream bodies, arbitrary serial logs, transcript or reply.
            print(
                f"Turn failed during {phase}: "
                "check speech, USB, local models or LLM; no automatic replay",
                flush=True,
            )
            if args.once:
                raise RuntimeError("Voice MVP turn failed") from None
        send_state("Ready")
        if args.once:
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--mock", action="store_true", help="No API call; mock TTS is silence")
    args = parser.parse_args()
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        print("Stopped")
    except Exception:
        raise SystemExit(
            "Voice MVP stopped; check exclusive USB access and local configuration"
        ) from None


if __name__ == "__main__":
    main()
