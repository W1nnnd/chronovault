#!/usr/bin/env python3
"""Render the ChronoVault demo video (1080p H.264, English voiceover + burned-in captions).

Pipeline: offline Piper TTS per sentence -> scripted headless Chromium session
(slides + the real dashboard on synthetic data) recorded via the DevTools
screencast -> ffmpeg assembly with an ASS caption track.

    python tools/make_video.py --out dist/media --voice /path/en_US-ljspeech-high.onnx
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.async_api import async_playwright  # noqa: E402

from chronovault.server import serve  # noqa: E402
from samples.generate_samples import generate  # noqa: E402

AS_OF = dt.date(2026, 10, 30)
MEDIA = ROOT / "tools" / "media"
W, H, DSF = 1536, 864, 1.25  # CSS viewport scaled to 1920x1080 device pixels
GAP = 0.32  # silence between sentences (s)
BLOCKING = {"click_first_scan", "wait_scan_done"}

# Each segment: (scene, [(sentence, action-before-sentence or None), ...], tail seconds)
SCRIPT = [
    ("slide:title", [
        ("Meet ChronoVault: a local-first AI steward for the UGREEN AI NAS that keeps every contract, bill and warranty deadline in view.", None),
    ], 0.8),
    ("slide:problem", [
        ("Every home and small studio keeps contracts, invoices, receipts and warranty cards on the NAS.", None),
        ("But the dates that cost money are buried inside those files.", None),
        ("An auto-renewal that needed thirty days notice. A warranty that quietly ended. A late bill.", None),
        ("Cloud AI could read them, but only if you upload your most private financial records.", None),
    ], 0.6),
    ("slide:arch", [
        ("ChronoVault is a UGOS Skill that orchestrates the NAS's own experts in three stages.", None),
        ("First, the file agent fingerprints only the folders you authorize, read-only, so unchanged files are never processed twice.", None),
        ("Second, the document and photo agents extract dates, amounts and notice periods on the device, each backed by a verbatim quote.", None),
        ("Third, the Skill computes the real action date, and saves a digest only after you approve.", None),
    ], 0.6),
    ("dash:overview", [
        ("Here is the working reference prototype, running locally on thirteen synthetic documents.", "hover_first_scan"),
    ], 0.2),
    ("scan", [
        ("One click runs the whole pipeline.", "click_first_scan"),
        ("Files are hashed, a duplicate is detected, a receipt photo is read with OCR, and a damaged PDF is set aside instead of breaking the batch.", None),
    ], 0.4),
    ("dash", [
        ("The overview ranks everything by the date you actually need to act.", "wait_scan_done"),
        ("A subscription renews in four days, and the broadband bill is due in six.", "hover_alerts"),
    ], 0.4),
    ("dash", [
        ("This cloud backup contract renews on December fifteenth.", "open_lumora"),
        ("But its thirty day notice clause makes the real deadline November fifteenth, and ChronoVault highlights the sentence that proves it.", "hover_math"),
    ], 0.6),
    ("dash", [
        ("From a photo of a paper receipt, it derives the warranty end date from the purchase date and the two year term.", "open_vantage"),
    ], 0.6),
    ("dash", [
        ("The timeline shows every obligation for the next three months, including each notice window.", "nav_timeline"),
    ], 0.5),
    ("dash", [
        ("Anything without a date or readable text goes to Needs Review. ChronoVault never guesses.", "nav_review"),
    ], 0.5),
    ("dash", [
        ("Run it again, and every file is skipped by its hash, so nightly scans cost almost nothing.", "rescan"),
    ], 0.8),
    ("dash", [
        ("The result is a plain Markdown action digest, saved back to the NAS.", "nav_digest"),
    ], 0.4),
    ("dash", [
        ("Privacy is verified, not promised.", "nav_privacy"),
        ("After every run the sources are hashed again: thirteen of thirteen unchanged, zero network calls, and writes stay inside one folder.", None),
    ], 0.6),
    ("slide:impact", [
        ("One missed renewal or warranty can cost a family hundreds of dollars.", None),
        ("ChronoVault turns a passive archive into a steward that pays for itself.", None),
        ("Next, we will validate it on the iDX6011 Pro with the NAS's own local models.", None),
    ], 0.6),
    ("slide:closing", [
        ("ChronoVault. Your deadlines, on your NAS, under your control.", None),
    ], 1.6),
]

CURSOR_JS = """
(() => {
  const init = () => {
    if (document.getElementById('__cv_cursor')) return;
    const c = document.createElement('div');
    c.id = '__cv_cursor';
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 9-6.5 1.6L9 19z" fill="#0f172a" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, {position:'fixed', left:'-60px', top:'-60px', zIndex:2147483647, pointerEvents:'none', transition:'transform .08s'});
    const r = document.createElement('div');
    Object.assign(r.style, {position:'fixed', width:'34px', height:'34px', borderRadius:'50%', border:'3px solid #10b981', left:'-80px', top:'-80px', zIndex:2147483646, pointerEvents:'none', opacity:0, transition:'opacity .35s, transform .35s'});
    document.body.appendChild(r); document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = (e.clientX - 3) + 'px'; c.style.top = (e.clientY - 2) + 'px'; }, true);
    addEventListener('mousedown', e => { r.style.left = (e.clientX - 17) + 'px'; r.style.top = (e.clientY - 17) + 'px'; r.style.transition='none'; r.style.opacity=1; r.style.transform='scale(.5)'; requestAnimationFrame(()=>{ r.style.transition='opacity .45s, transform .45s'; r.style.opacity=0; r.style.transform='scale(1.6)'; }); c.style.transform='scale(.85)'; }, true);
    addEventListener('mouseup', () => { c.style.transform='scale(1)'; }, true);
  };
  if (document.body) init(); else addEventListener('DOMContentLoaded', init);
})();
"""


def tts(text: str, voice: Path, cache: Path, length_scale: float) -> Path:
    key = hashlib.sha1(f"{voice.name}|{length_scale}|{text}".encode()).hexdigest()[:16]
    out = cache / f"{key}.wav"
    if not out.exists():
        piper = Path(sys.executable).parent / "piper"
        subprocess.run([str(piper), "-m", str(voice), "--length-scale", str(length_scale), "-f", str(out)],
                       input=text.encode(), check=True, capture_output=True)
    return out


def wav_seconds(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


class Recorder:
    def __init__(self, frames_dir: Path):
        self.dir = frames_dir
        self.frames: list[tuple[float, Path]] = []
        self.t0 = None

    async def start(self, page):
        self.cdp = await page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", lambda e: asyncio.ensure_future(self._frame(e)))
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920,
                                                     "maxHeight": 1080, "everyNthFrame": 1})
        self.t0 = time.time()

    async def _frame(self, e):
        t = time.time()
        p = self.dir / f"f{len(self.frames):06d}.jpg"
        p.write_bytes(base64.b64decode(e["data"]))
        self.frames.append((t, p))
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": e["sessionId"]})
        except Exception:  # noqa: BLE001
            pass

    async def stop(self):
        await self.cdp.send("Page.stopScreencast")

    def now(self) -> float:
        return time.time() - self.t0


async def smooth_click(page, selector: str, click: bool = True, steps: int = 28, pause: int = 260):
    el = page.locator(selector).first
    box = await el.bounding_box()
    x, y = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5
    await page.mouse.move(x, y, steps=steps)
    await page.wait_for_timeout(pause)
    if click:
        await page.mouse.down()
        await page.wait_for_timeout(70)
        await page.mouse.up()


async def record(out_frames: Path, timeline: list, durations: dict, slides_url: str, arch_png: Path):
    tmp = Path(tempfile.mkdtemp(prefix="cv-video-"))
    nas = generate(tmp / "nas")
    httpd = serve([nas / "Documents", nas / "Photos"], tmp / "vault", AS_OF, port=0, block=False)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    rec = Recorder(out_frames)
    events = []
    scan_sentences = [s for scene, sents, _ in SCRIPT if scene == "scan" for s, _ in sents]
    scan_seconds = sum(durations[s] + GAP for s in scan_sentences) + 1.2
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=DSF)
            await ctx.add_init_script(CURSOR_JS)
            page = await ctx.new_page()
            await page.goto(slides_url + "?s=blank")
            await rec.start(page)
            await page.wait_for_timeout(300)

            async def act(name):
                if name == "hover_first_scan":
                    await page.mouse.move(W * 0.62, H * 0.35)
                    await page.wait_for_timeout(1400)
                    await smooth_click(page, "#first-scan", click=False, steps=40)
                elif name == "click_first_scan":
                    pace = max(150, int((scan_seconds * 1000 - 600) / 27.6))
                    await page.evaluate(f"window.SCAN_PACE = {pace}")
                    await smooth_click(page, "#first-scan", steps=6, pause=120)
                elif name == "wait_scan_done":
                    await page.wait_for_function("!document.querySelector('#scan-modal').classList.contains('open')",
                                                 timeout=60000)
                    await page.wait_for_timeout(300)
                elif name == "hover_alerts":
                    await smooth_click(page, ".alert.critical >> nth=0", click=False)
                    await page.wait_for_timeout(1500)
                    await smooth_click(page, ".alert.critical >> nth=1", click=False, steps=18)
                elif name == "open_lumora":
                    await smooth_click(page, ".alert:has-text('Lumora')")
                elif name == "hover_math":
                    await smooth_click(page, ".math .box.result", click=False, steps=30)
                    await page.wait_for_timeout(2600)
                    await smooth_click(page, ".preview mark >> nth=1", click=False, steps=30)
                elif name == "open_vantage":
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(450)
                    await smooth_click(page, ".alert:has-text('Vantage')")
                    await page.wait_for_timeout(1600)
                    await smooth_click(page, ".preview img", click=False, steps=30)
                elif name.startswith("nav_"):
                    await page.keyboard.press("Escape")
                    route = name[4:]
                    await smooth_click(page, f"#nav a[data-route='{route}']")
                    if route == "digest":
                        await page.wait_for_timeout(1500)
                        await page.mouse.move(W * 0.55, H * 0.6, steps=20)
                        for _ in range(12):
                            await page.mouse.wheel(0, 45)
                            await page.wait_for_timeout(110)
                elif name == "rescan":
                    await page.evaluate("window.SCAN_PACE = 330")
                    await smooth_click(page, "#scan-btn")

            pending = [None]
            for scene, sentences, tail in SCRIPT:
                if scene.startswith("slide:") and pending[0] is not None:
                    await pending[0]
                    pending[0] = None
                if scene.startswith("slide:"):
                    sid = scene.split(":", 1)[1]
                    await page.goto(f"{slides_url}?s={sid}")
                elif scene == "dash:overview":
                    await page.goto(base + "/#/overview")
                    await page.wait_for_timeout(500)
                for text, action in sentences:
                    if pending[0] is not None:
                        await pending[0]
                        pending[0] = None
                    if action in BLOCKING:
                        await act(action)
                    elif action:
                        pending[0] = asyncio.ensure_future(act(action))
                        await asyncio.sleep(0.35)
                    start = rec.now()
                    events.append({"text": text, "start": start, "dur": durations[text]})
                    await asyncio.sleep(durations[text] + GAP)
                await asyncio.sleep(tail)
            await rec.stop()
            end = rec.now()
            await browser.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return rec, events, end


def build_video(rec: Recorder, end: float, work: Path) -> Path:
    lst = work / "frames.txt"
    frames = [(t - rec.t0, p) for t, p in rec.frames]
    lines = []
    for i, (t, p) in enumerate(frames):
        nxt = frames[i + 1][0] if i + 1 < len(frames) else end
        lines.append(f"file '{p}'\nduration {max(nxt - t, 0.001):.4f}")
    lines.append(f"file '{frames[-1][1]}'")
    lst.write_text("\n".join(lines))
    first_offset = frames[0][0]
    silent = work / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"tpad=start_duration={first_offset:.3f}:start_mode=clone,fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16", str(silent)], check=True)
    return silent


def build_audio(events: list, wavs: dict, end: float, work: Path) -> Path:
    sr = 22050
    track = np.zeros(int((end + 1) * sr), dtype=np.float32)
    for ev in events:
        with wave.open(str(wavs[ev["text"]])) as w:
            sr = w.getframerate()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        i = int(ev["start"] * sr)
        track[i:i + len(data)] += data[: len(track) - i]
    out = work / "voice.wav"
    with wave.open(str(out), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())
    return out


def _ts(t: float, ass: bool) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    if ass:
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def caption_chunks(events: list, max_words: int = 13) -> list[tuple[float, float, str]]:
    out = []
    for ev in events:
        parts = re.split(r"(?<=[.,:;])\s+", ev["text"])
        chunks, cur = [], ""
        for part in parts:
            if cur and len((cur + " " + part).split()) > max_words:
                chunks.append(cur)
                cur = part
            else:
                cur = (cur + " " + part).strip()
        if cur:
            chunks.append(cur)
        final = []
        for c in chunks:  # hard-split chunks that are still long
            words = c.split()
            while len(words) > max_words + 3:
                final.append(" ".join(words[:max_words]))
                words = words[max_words:]
            final.append(" ".join(words))
        total = sum(len(c) for c in final)
        t = ev["start"]
        for c in final:
            d = ev["dur"] * len(c) / total
            out.append((t, t + d, c))
            t += d
    return out


def write_captions(events: list, work: Path, out_dir: Path) -> Path:
    chunks = caption_chunks(events)
    srt = "\n".join(f"{i}\n{_ts(a, False)} --> {_ts(b, False)}\n{t}\n" for i, (a, b, t) in enumerate(chunks, 1))
    (out_dir / "ChronoVault_demo_captions_en.srt").write_text(srt, encoding="utf-8")
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 0", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
           "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
           "MarginR, MarginV, Encoding",
           "Style: Cap,Inter,46,&H00FFFFFF,&H00FFFFFF,&H90101418,&H90101418,1,0,0,0,100,100,0,0,3,14,0,2,240,240,46,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for a, b, t in chunks:
        ass.append(f"Dialogue: 0,{_ts(a, True)},{_ts(b + 0.05, True)},Cap,,0,0,0,,{t}")
    p = work / "captions.ass"
    p.write_text("\n".join(ass), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "media")
    ap.add_argument("--voice", type=Path, required=True, help="Piper .onnx voice (e.g. en_US-ljspeech-high)")
    ap.add_argument("--length-scale", type=float, default=0.92)
    ap.add_argument("--arch", type=Path, default=None, help="architecture PNG for the slide")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="cv-render-"))
    cache = ROOT / ".tts_cache"
    cache.mkdir(exist_ok=True)

    wavs, durations = {}, {}
    for _, sents, _ in SCRIPT:
        for text, _ in sents:
            wavs[text] = tts(text, args.voice, cache, args.length_scale)
            durations[text] = wav_seconds(wavs[text])
    est = sum(d + GAP for d in durations.values()) + sum(t for *_, t in SCRIPT)
    print(f"narration {sum(durations.values()):.1f}s, estimated video {est:.1f}s")

    arch = args.arch or (args.out / "gallery" / "09_architecture.png")
    slides = (MEDIA / "slides.html").read_text().replace("ARCH", arch.resolve().as_uri())
    slides_file = work / "slides.html"
    slides_file.write_text(slides)
    (work / "frames").mkdir()
    rec, events, end = asyncio.run(record(work / "frames", [], durations, slides_file.as_uri(), arch))
    print(f"recorded {len(rec.frames)} frames over {end:.1f}s")
    silent = build_video(rec, end, work)
    voice = build_audio(events, wavs, end, work)
    ass = write_captions(events, work, args.out)
    final = args.out / "ChronoVault_demo_1080p.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(voice),
                    "-vf", f"subtitles={ass}", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", "-shortest", str(final)], check=True)
    # also keep a caption-free master for YouTube CC upload
    clean = args.out / "ChronoVault_demo_1080p_no_burned_captions.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(voice),
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", "-shortest", str(clean)], check=True)
    (args.out / "ChronoVault_demo_script.json").write_text(json.dumps(events, indent=2))
    shutil.copy(voice, args.out / "ChronoVault_demo_voiceover.wav")
    print(f"video: {final} ({final.stat().st_size / 1e6:.1f} MB)")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
