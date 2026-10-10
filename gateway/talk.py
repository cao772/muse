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
from integrations.attention import AttentionObserver
from integrations.cao import CAOClient, CAOError
from integrations.chatgpt_plan import ChatGPTPlanProvider
from integrations.execution_agent import ExecutionClient, PersonalAgentRouter
from integrations.llm import CompatibleProvider, MockProvider
from integrations.local_tts import RUNTIME
from integrations.personal_provider import PersonalAgentProvider
from integrations.resident import ResidentModel
from integrations.stt import MockSTT, stereo_wav_to_mono
from integrations.tts import MockTTS, TTSOutputTooLong, decode_playback_wav
from integrations.wechat_notifications import WeChatNotifications, unavailable_frame
from scripts.capture_audio import CaptureCancelled, CaptureTimeout, receive_pcm
from scripts.play_audio import upload


def input_wav(pcm):
    if not 0 < len(pcm) <= 1280000 or len(pcm) % 4:
        raise ValueError("Expected verified stereo PCM, at most 20 seconds")
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


def pack_playback(buffers):
    # TTS phrase boundaries need not become USB upload pauses. Preserve every sample.
    joined = b"".join(buffers)
    return [joined[i : i + 160000] for i in range(0, len(joined), 160000)]


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
    timeout = (
        provider.timeout_seconds(text, provider_timeout)
        if hasattr(provider, "timeout_seconds")
        else provider_timeout
    )
    answer = await asyncio.wait_for(provider.reply(text), timeout)
    answer_source = getattr(provider, "last_source", "llm")
    timings["llm_seconds"] = round(perf_counter() - started, 3)
    status("Synthesizing")
    started = perf_counter()
    # Generate and validate the entire answer before any playback. No partial reply on TTS failure.
    buffers = []
    for chunk in speech_chunks(answer):
        buffers.extend(await synthesize_bounded(tts, chunk))
    timings["tts_seconds"] = round(perf_counter() - started, 3)
    buffers = pack_playback(buffers)
    status("Playing")
    timings["before_play_seconds"] = round(perf_counter() - turn_started, 3)
    started = perf_counter()
    for pcm in buffers:
        await play(pcm)
    timings["play_seconds"] = round(perf_counter() - started, 3)
    result = {"segments": len(buffers), "answer_source": answer_source, **timings}
    if isinstance(provider, PersonalAgentRouter):
        result.update(intent=provider.last_intent, route_result=provider.last_route_result)
    brain = provider.fallback if isinstance(provider, PersonalAgentRouter) else provider
    if answer_source == "chatgpt" and getattr(brain, "last_route", {}).get("model"):
        route = brain.last_route
        result["research"] = {
            key: route[key]
            for key in ("model", "actual_used_web", "reasoning_effort", "reflection")
        }
    return result


async def serve(args):
    settings = Settings()
    cao_client = None
    if args.mock:

        class OfflineSTT:
            async def transcribe(self, wav):
                return await MockSTT().transcribe(stereo_wav_to_mono(wav))

        stt, provider, tts = OfflineSTT(), MockProvider(), MockTTS()
    else:
        if settings.stt_provider != "mlx-whisper" or settings.provider == "mock":
            raise ValueError("Configure local Whisper and a real LLM in .env, or use --mock")
        stt = ResidentWhisper(settings.stt_model)
        fallback = CompatibleProvider(settings, voice_mode=True)
        cao_client = (
            CAOClient(
                settings.cao_base_url,
                settings.cao_timeout_seconds,
                muse_token=settings.cao_muse_token.get_secret_value(),
            )
            if settings.cao_enabled
            else None
        )
        chatgpt = (
            ChatGPTPlanProvider(
                settings.chatgpt_credentials_path,
                preferred_model=settings.chatgpt_model,
                timeout_seconds=settings.chatgpt_timeout_seconds,
                web_context=settings.chatgpt_web_context,
                voice_mode=True,
            )
            if settings.chatgpt_enabled
            else None
        )
        brain = PersonalAgentProvider(
            fallback,
            cao=cao_client,
            chatgpt=chatgpt,
            chatgpt_auto_enabled=settings.chatgpt_auto_enabled,
        )
        provider = (
            PersonalAgentRouter(
                brain,
                cao_client,
                ExecutionClient(settings.cao_base_url, settings.cao_muse_token.get_secret_value()),
            )
            if settings.cao_enabled and settings.cao_execution_enabled
            else brain
        )
        tts = ResidentSerena()
    if getattr(args, "execution_id", None):
        if not isinstance(provider, PersonalAgentRouter):
            raise ValueError("Explicit execution recovery requires P2 configuration")
        await provider.restore(args.execution_id)
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

        if isinstance(provider, PersonalAgentRouter):
            last_execution_state = [None]

            def report_execution(value):
                marker = (value.get("id"), value.get("status"), value.get("model_profile"))
                if marker != last_execution_state[0]:
                    last_execution_state[0] = marker
                    print(
                        "CODEX "
                        + json.dumps({"id": marker[0], "state": marker[1], "profile": marker[2]}),
                        flush=True,
                    )

            provider.on_execution = report_execution

        state = ["Thinking"]
        attention = {"count": None}
        attention_observer = AttentionObserver()
        wechat = (
            WeChatNotifications(
                CAOClient(
                    settings.wechat_base_url or settings.cao_base_url,
                    settings.cao_timeout_seconds,
                    muse_token=settings.wechat_token.get_secret_value(),
                ),
                settings.wechat_scope_id,
                Path(settings.wechat_cursor_path).expanduser(),
            )
            if settings.wechat_enabled and cao_client is not None and not args.mock
            else None
        )
        device.device._muse_on_inbox = wechat.acknowledge if wechat else None

        def send_state(value=None):
            with device.lock:
                if value is not None:
                    state[0] = value
                frame = {"voice_state": state[0], "attention_count": attention["count"]}
                frame["wechat"] = wechat.frame if wechat else unavailable_frame()
                execution = getattr(provider, "snapshot", None)
                if execution:
                    frame["codex"] = {
                        "state": execution.get("status", "unknown"),
                        "profile": execution.get("model_profile", "balanced"),
                        "needs_user": bool(execution.get("needs_user")),
                        "title": execution.get("project_id", "Task")[:24],
                    }
                device.device.write(json.dumps(frame).encode() + b"\n")

        async def heartbeat():
            while True:
                await asyncio.to_thread(send_state)
                await asyncio.sleep(2)

        async def poll_execution():
            while True:
                if isinstance(provider, PersonalAgentRouter) and provider.active_id:
                    try:
                        await provider.refresh()
                    except Exception:
                        provider.publish({"id": provider.active_id, "status": "unknown"})
                await asyncio.sleep(3)

        async def poll_attention():
            while True:
                if not args.mock and cao_client is not None:
                    try:
                        snapshot = await cao_client.attention()
                        attention_observer.observe(snapshot, focus=state[0] != "Ready")
                        count = snapshot.get("count")
                        attention["count"] = (
                            count if type(count) is int and 0 <= count <= 999 else None
                        )
                    except CAOError:
                        attention["count"] = None
                await asyncio.sleep(15)

        async def poll_wechat():
            while True:
                if wechat:
                    await wechat.refresh()
                await asyncio.sleep(60)

        wechat_task = asyncio.create_task(poll_wechat())
        attention_task = asyncio.create_task(poll_attention())
        task = asyncio.create_task(heartbeat())
        poll_task = asyncio.create_task(poll_execution())
        try:
            send_state("Thinking")
            if not args.mock:
                print("Preloading Whisper / Serena", flush=True)
                await stt.worker.start()
                await tts.worker.start()
            await conversation(args, device, stt, provider, tts, play, settings, send_state)
        finally:
            wechat_task.cancel()
            attention_task.cancel()
            task.cancel()
            poll_task.cancel()
            await asyncio.gather(
                task, poll_task, attention_task, wechat_task, return_exceptions=True
            )
            if wechat:
                wechat.close()
            if not args.mock:
                await stt.worker.close()
                await tts.worker.close()


async def conversation(args, device, stt, provider, tts, play, settings, send_state):
    turn = 0
    while True:
        send_state("Ready")
        print(
            "Ready: tap Audio Input → Speak, speak; wait until Ready before pressing again",
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
        except CaptureCancelled as error:
            status("Synthesizing")
            message = (
                "没听到说话，请重试。"
                if error.reason == "no_speech"
                else "录音到达二十秒上限，请分成短句重说。"
            )
            try:
                for chunk in speech_chunks(message):
                    for audio in await synthesize_bounded(tts, chunk):
                        status("Playing")
                        await play(audio)
            except (ValueError, RuntimeError, TimeoutError, OSError, serial.SerialException):
                print("Capture guidance unavailable; return to Ready without execution", flush=True)
            print("Capture cancelled: " + error.reason + "; no STT or task execution", flush=True)
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
    parser.add_argument(
        "--execution-id", help="Explicitly inspect an existing authorized P2 UUID; never replay"
    )
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
