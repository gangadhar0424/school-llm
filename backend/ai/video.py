"""
AI Video Generation Module

Produces real animated slideshow-style MP4 videos from a script.
Pipeline:
    1. LLM generates narration script (from summary or from a user query + RAG context)
    2. LLM splits the script into scenes: [{title, bullets[], narration}]
    3. Each scene is rendered as a PNG slide (PIL) + a narration WAV (pyttsx3)
    4. MoviePy stitches the slides + narration with fade transitions into an MP4
"""
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from config import settings
from ai.ollama_client import ollama_client
from ai.llm_client import get_llm_client

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

logger = logging.getLogger(__name__)


VIDEO_WIDTH = 960
VIDEO_HEIGHT = 540
VIDEO_FPS = 12
MAX_SCENES = 4
BG_COLOR_TOP = (26, 16, 64)       # deep purple
BG_COLOR_BOTTOM = (13, 27, 62)    # deep blue
ACCENT_COLOR = (168, 156, 255)    # light purple
TITLE_COLOR = (255, 255, 255)
BULLET_COLOR = (220, 220, 240)
FOOTER_COLOR = (130, 130, 170)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try common Windows fonts first, then fall back to PIL default."""
    candidates_bold = [
        "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in (candidates_bold if bold else candidates):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Wrap a single string into lines that fit `max_width` pixels."""
    if not text:
        return []
    words = text.split()
    lines: List[str] = []
    current = ""
    for w in words:
        trial = (current + " " + w).strip()
        bbox = font.getbbox(trial)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _render_slide(title: str, bullets: List[str], footer: str, out_path: Path,
                  reveal_count: Optional[int] = None) -> None:
    """Draw a slide PNG: gradient background, title, bullet list, footer.

    `reveal_count` (if given) limits how many bullets are drawn — used to render
    progressive build-up frames for the animated-slides pipeline.
    """
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR_BOTTOM)
    draw = ImageDraw.Draw(img)

    # Vertical gradient
    for y in range(VIDEO_HEIGHT):
        t = y / VIDEO_HEIGHT
        r = int(BG_COLOR_TOP[0] * (1 - t) + BG_COLOR_BOTTOM[0] * t)
        g = int(BG_COLOR_TOP[1] * (1 - t) + BG_COLOR_BOTTOM[1] * t)
        b = int(BG_COLOR_TOP[2] * (1 - t) + BG_COLOR_BOTTOM[2] * t)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    # Accent bar on the left
    draw.rectangle([(0, 0), (12, VIDEO_HEIGHT)], fill=ACCENT_COLOR)

    title_font = _load_font(44, bold=True)
    bullet_font = _load_font(28)
    footer_font = _load_font(16)

    # Title (wrapped to two lines if needed)
    left_margin = 80
    right_margin = 80
    max_text_width = VIDEO_WIDTH - left_margin - right_margin
    title_lines = _wrap_text(title or "", title_font, max_text_width)[:2]
    y = 80
    for line in title_lines:
        draw.text((left_margin, y), line, font=title_font, fill=TITLE_COLOR)
        bbox = title_font.getbbox(line)
        y += (bbox[3] - bbox[1]) + 12

    # Underline accent
    y += 12
    draw.rectangle([(left_margin, y), (left_margin + 120, y + 4)], fill=ACCENT_COLOR)
    y += 40

    # Bullets (optionally truncated for progressive reveal)
    visible_bullets = (bullets or [])[:5]
    if reveal_count is not None:
        visible_bullets = visible_bullets[: max(0, reveal_count)]
    for b in visible_bullets:
        bullet_text = f"•  {b.strip()}"
        wrapped = _wrap_text(bullet_text, bullet_font, max_text_width)
        for wline in wrapped[:3]:
            draw.text((left_margin, y), wline, font=bullet_font, fill=BULLET_COLOR)
            bbox = bullet_font.getbbox(wline)
            y += (bbox[3] - bbox[1]) + 14
        y += 8

    # Footer
    if footer:
        draw.text((left_margin, VIDEO_HEIGHT - 50), footer, font=footer_font, fill=FOOTER_COLOR)

    img.save(out_path, format="PNG")


def _tts_to_wav(text: str, out_path: Path) -> None:
    """Blocking pyttsx3 synthesis (call via asyncio.to_thread)."""
    if pyttsx3 is None:
        raise Exception("pyttsx3 not installed. Run: pip install pyttsx3")
    engine = pyttsx3.init()
    if settings.AUDIO_VOICE:
        engine.setProperty("voice", settings.AUDIO_VOICE)
    if settings.AUDIO_RATE:
        engine.setProperty("rate", settings.AUDIO_RATE)
    engine.save_to_file(text, str(out_path))
    engine.runAndWait()


def _parse_scenes_json(raw: str) -> List[Dict]:
    """Extract a JSON list of scenes from model output, with tolerant fallbacks."""
    if not raw:
        return []
    # Try direct JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "scenes" in data:
            return data["scenes"]
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Extract the first [...]+ or {...}+ block
    m = re.search(r'\{[\s\S]*"scenes"[\s\S]*\}', raw)
    if m:
        try:
            d = json.loads(m.group(0))
            return d.get("scenes", [])
        except Exception:
            pass
    m = re.search(r'\[[\s\S]+\]', raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return []


class VideoGenerator:
    """Generate real slideshow-style educational videos."""

    def __init__(self):
        self.video_dir = Path(settings.VIDEO_DIR)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = self.video_dir / "_tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.model = settings.OLLAMA_CHAT_MODEL

    async def generate_script(self, source_text: str, focus_query: Optional[str] = None) -> str:
        """Turn source text (summary or RAG chunks) into a narrated teacher-style script."""
        focus_line = (
            f"Focus the video on this query: {focus_query.strip()}\n\n"
            if focus_query and focus_query.strip()
            else ""
        )
        prompt = (
            "You are a friendly classroom teacher recording the narration for a short educational video. "
            "Rewrite the source material below as if you are explaining it out loud to a curious student. "
            "Total length: 120-200 words spoken in roughly 60-90 seconds.\n\n"
            "STRICT STYLE RULES (very important — the text will be read aloud verbatim by a TTS engine):\n"
            "- Write ONLY flowing conversational prose. No bullet points. No numbered lists. No headings.\n"
            "- DO NOT use any of these characters: # * _ ` > [] {} — at all.\n"
            "- DO NOT write 'Step 1', 'Step 2', '1.', '2.', '(a)', '(i)' or any list markers. Use words instead: 'first', 'next', 'then', 'after that', 'finally'.\n"
            "- DO NOT include citations like [S1], (p.23), or 'see chapter 4'.\n"
            "- DO NOT include stage directions, timestamps, speaker labels, or 'Welcome to' / 'In conclusion' filler.\n"
            "- Use natural teacher transitions to connect ideas: 'Let's start with...', 'Now imagine...', 'You might be wondering...', 'So why does this matter?'.\n"
            "- Keep sentences short and clear. Pretend the audience is a 14-year-old student.\n\n"
            f"{focus_line}"
            "Source material:\n"
            f"{source_text.strip()[:4000]}\n\n"
            "Now write the narration as one continuous block of plain conversational text:"
        )
        _llm = get_llm_client()
        script = await _llm.chat(
            messages=[
                {"role": "system",
                 "content": "You produce ONLY plain conversational narration text. Never use markdown, lists, or citations."},
                {"role": "user", "content": prompt},
            ],
            model=_llm.generation_model or self.model,
            temperature=0.45,
            max_tokens=500,
        )
        return (script or "").strip()

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Strip markdown artifacts and list markers from script/slide text."""
        if not text:
            return ""
        out = text.replace("\r\n", "\n")

        # Drop ATX headers (#, ##, ### …) at line start
        out = re.sub(r'^\s*#{1,6}\s+', '', out, flags=re.MULTILINE)
        # Drop stray hash sequences anywhere
        out = re.sub(r'#{1,6}', '', out)
        # Bold / italic / code markers
        out = re.sub(r'\*\*(.*?)\*\*', r'\1', out)
        out = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'\1', out)
        out = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', out)
        out = re.sub(r'`([^`]+)`', r'\1', out)
        out = re.sub(r'[*_`~]', '', out)
        # Blockquotes / bullets / hyphens at line start
        out = re.sub(r'^\s*[>\-•·*]+\s*', '', out, flags=re.MULTILINE)
        # Numbered list markers at line start: "1. " / "1) " / "(1)" / "a) "
        out = re.sub(r'^\s*\(?\s*[0-9]{1,2}\s*[.)\-:]\s+', '', out, flags=re.MULTILINE)
        out = re.sub(r'^\s*\(?[A-Za-z]\)\s+', '', out, flags=re.MULTILINE)
        # "Step 1:", "Point 2 -" etc. anywhere
        out = re.sub(r'\b(?:Step|Point|Part|Section)\s+[0-9]+[:\-.]?\s*', '', out, flags=re.I)
        # Source citations like [S1], [S12], (S2), (p. 23), (chapter 4)
        out = re.sub(r'\[(?:S|s)\d+\]', '', out)
        out = re.sub(r'\((?:S|s)\d+\)', '', out)
        out = re.sub(r'\(p\.?\s*\d+\)', '', out, flags=re.I)
        out = re.sub(r'\((?:chapter|ch\.?)\s*\d+\)', '', out, flags=re.I)
        # Collapse whitespace
        out = re.sub(r'[ \t]+', ' ', out)
        out = re.sub(r'\n{2,}', '\n\n', out)
        return out.strip()

    @staticmethod
    def _clean_title(text: str) -> str:
        """Tidy a derived slide title: strip stray punctuation and dashes."""
        t = re.sub(r'^[\s\-–—:*#>"\']+', '', text or '')
        t = re.sub(r'[\s\-–—:*#>"\']+$', '', t).strip()
        t = re.sub(r'\s+', ' ', t)
        return t

    @staticmethod
    def _clean_for_narration(text: str) -> str:
        """Final pass before TTS: ensure no characters that the speech engine
        would pronounce literally (numbers, slashes, dashes, parens, etc.).
        Keeps natural sentences intact."""
        if not text:
            return ""
        out = text
        # Remove any lingering markdown / bracket noise
        out = re.sub(r'[#*_`~>\[\]{}]', '', out)
        # Replace slashes & pipes with words for cleaner speech
        out = out.replace('&', ' and ')
        out = re.sub(r'\s*/\s*', ' or ', out)
        out = re.sub(r'\s*\|\s*', ', ', out)
        # Convert remaining em/en dashes to commas (TTS reads "—" awkwardly)
        out = re.sub(r'\s*[–—]\s*', ', ', out)
        # Strip leading list markers if any survived
        out = re.sub(r'^\s*\(?\s*[0-9]{1,2}\s*[.)\-:]\s+', '', out, flags=re.MULTILINE)
        out = re.sub(r'^\s*\(?[A-Za-z]\)\s+', '', out, flags=re.MULTILINE)
        # Strip trailing parenthetical refs that survived
        out = re.sub(r'\s*\([^)]{0,40}?(?:S\d+|p\.?\s*\d+|chapter\s*\d+)[^)]*\)', '', out, flags=re.I)
        # Collapse whitespace and stray double punctuation
        out = re.sub(r'[ \t]+', ' ', out)
        out = re.sub(r'\s+([,.;:!?])', r'\1', out)
        out = re.sub(r'\.{2,}', '.', out)
        out = re.sub(r',{2,}', ',', out)
        return out.strip()

    def split_into_scenes(self, script: str, topic_hint: str = "") -> List[Dict]:
        """Heuristic scene splitter — fast, deterministic, no LLM call.

        Splits the script into `MAX_SCENES` scenes by sentence boundary, then
        derives a title and full-sentence bullets per scene.
        """
        script = self._clean_markdown(script or "")
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', script) if s.strip()]
        if not sentences:
            return []

        total = len(sentences)
        n_scenes = min(MAX_SCENES, max(2, min(total, MAX_SCENES if total >= MAX_SCENES else total)))
        chunk_size = max(1, (total + n_scenes - 1) // n_scenes)

        scenes: List[Dict] = []
        hint_title = self._clean_title(topic_hint or "").title() or "Overview"
        intro_titles = [
            hint_title,
            "Key Ideas",
            "Details & Examples",
            "Why It Matters",
            "Summary",
            "Takeaways",
        ]

        for idx, i in enumerate(range(0, total, chunk_size)):
            chunk = sentences[i:i + chunk_size]
            if not chunk:
                continue

            # Title: fixed sequence for scene 0/last, derived for middle scenes
            derived_title = self._clean_title(" ".join(chunk[0].split()[:6]))
            derived_title = re.sub(r'^(The|A|An|This|These|Those|In|On|At)\s+', '', derived_title, flags=re.I)
            title = intro_titles[idx] if idx < len(intro_titles) else f"Part {idx + 1}"
            if idx > 0 and len(derived_title) > 4:
                title = self._clean_title(derived_title.title())[:45]

            # Bullets: full sentences (slide renderer wraps long text to 3 lines)
            bullets: List[str] = []
            for s in chunk[:3]:
                cleaned = self._clean_markdown(re.sub(r'\s+', ' ', s))
                cleaned = self._clean_title(cleaned.rstrip('.'))
                if cleaned:
                    bullets.append(cleaned)

            narration_raw = " ".join(chunk)
            narration_clean = self._clean_for_narration(self._clean_markdown(narration_raw))

            scenes.append({
                "title": title,
                "bullets": bullets,
                "narration": narration_clean or narration_raw,
            })
            if len(scenes) >= MAX_SCENES:
                break

        return scenes

    def _render_single_scene(self, scene: Dict, footer: str, idx: int) -> Dict:
        """Blocking: render N progressive build-up PNGs + narration WAV for one scene.

        Frames produced:
          - frame 0: title only (no bullets)
          - frame k for k=1..len(bullets): title + first k bullets visible

        These get composited into an animated build-up by `_compose_video`.
        """
        title = scene.get("title", "")
        bullets = scene.get("bullets", []) or []
        wav_path = self.tmp_dir / f"scene_{idx:02d}.wav"
        _tts_to_wav(scene.get("narration", ""), wav_path)

        frames: List[Path] = []
        # Title-only frame
        f0 = self.tmp_dir / f"scene_{idx:02d}_f0.png"
        _render_slide(title, bullets, footer, f0, reveal_count=0)
        frames.append(f0)
        # Build-up frames: one per bullet
        for k in range(1, min(len(bullets), 5) + 1):
            fp = self.tmp_dir / f"scene_{idx:02d}_f{k}.png"
            _render_slide(title, bullets, footer, fp, reveal_count=k)
            frames.append(fp)
        return {"frames": frames, "audio": wav_path, **scene}

    def _compose_video(self, rendered_scenes: List[Dict], out_path: Path) -> float:
        """Blocking: stitch animated slides + audio into an MP4.

        For each scene:
          - 0.5s build-up: cycles through frame_0 → frame_N (title appears, then
            bullets reveal one by one)
          - rest of audio duration: holds the final frame
          - subtle Ken-Burns zoom (1.00 → 1.04 across the scene)
          - cross-fade with neighboring scenes
        """
        try:
            from moviepy.video.fx import FadeIn, FadeOut
        except Exception:
            FadeIn = FadeOut = None

        clips = []
        total_duration = 0.0
        cross_fade = 0.5
        build_total = 0.8  # seconds spent on the build-up sequence per scene

        for r in rendered_scenes:
            audio = AudioFileClip(str(r["audio"]))
            # MoviePy can seek slightly past audio EOF due to fps boundary rounding
            # (Error: Accessing time t=27.24-27.29 with clip duration=27.20).
            # Trim a 50ms safety margin so reads always land inside the audio.
            safe_dur = max(0.0, audio.duration - 0.05)
            if safe_dur <= 0.05:
                continue
            try:
                audio = audio.subclipped(0, safe_dur)
            except AttributeError:
                # MoviePy < 2.0 used .subclip — keep compatibility
                audio = audio.subclip(0, safe_dur)
            scene_dur = audio.duration
            frames: List[Path] = r["frames"]

            # Build-up: equal slice per build frame (excluding the final hold frame)
            build_frames = frames[:-1] if len(frames) > 1 else frames
            hold_frame = frames[-1]
            # Cap build phase at 40% of scene length so very short scenes still hold the final frame
            actual_build = min(build_total, max(0.2, scene_dur * 0.4))
            per_build = actual_build / max(1, len(build_frames))
            hold_duration = max(0.05, scene_dur - actual_build)

            sub_clips = []
            for fp in build_frames:
                sub_clips.append(ImageClip(str(fp)).with_duration(per_build))
            sub_clips.append(ImageClip(str(hold_frame)).with_duration(hold_duration))

            scene_video = concatenate_videoclips(sub_clips, method="compose")

            # Subtle Ken-Burns zoom on the full scene
            try:
                scene_video = scene_video.resized(
                    lambda t, sd=scene_dur: 1.00 + 0.04 * (t / max(0.1, sd))
                )
            except Exception:
                pass

            scene_video = scene_video.with_audio(audio).with_duration(scene_dur)

            if FadeIn is not None and FadeOut is not None:
                scene_video = scene_video.with_effects([FadeIn(cross_fade), FadeOut(cross_fade)])

            clips.append(scene_video)
            total_duration += scene_dur

        final = concatenate_videoclips(clips, method="compose")
        ffmpeg_params = ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        temp_audiofile = str(self.tmp_dir / f"{out_path.stem}_audio.m4a")
        final.write_videofile(
            str(out_path),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=4,
            logger=None,
            ffmpeg_params=ffmpeg_params,
            temp_audiofile=temp_audiofile,
        )
        final.close()
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        return total_duration

    # ---------------------------------------------------------------------
    # MANIM PATH (Option B) — generates a single Manim Scene from template
    # and renders it. We control the structure; the LLM only supplied scene
    # titles/bullets/narration via split_into_scenes — so the generated
    # Python is always valid.
    # ---------------------------------------------------------------------

    @staticmethod
    def _wrap_for_manim(text: str, max_chars: int) -> str:
        """Word-wrap a string into '\\n'-separated lines no longer than
        max_chars. Manim's Text class respects embedded newlines but does
        NOT auto-wrap — long sentences would otherwise extend off-screen."""
        text = (text or "").strip()
        if not text:
            return ""
        words = text.split()
        lines: List[str] = []
        current = ""
        for w in words:
            trial = (current + " " + w).strip()
            if len(trial) <= max_chars:
                current = trial
            else:
                if current:
                    lines.append(current)
                # Break a single word that's already too long
                while len(w) > max_chars:
                    lines.append(w[:max_chars])
                    w = w[max_chars:]
                current = w
        if current:
            lines.append(current)
        return "\n".join(lines)

    def _build_manim_code(self, scenes: List[Dict], audio_durations: List[float]) -> str:
        """Build a self-contained Manim Python file from scene data.

        Layout per scene:
          - Left half (≈55% of frame): accent bar + title (Write) + underline +
            bullets (Write, drawn stroke-by-stroke)
          - Right half: an animated diagram that varies per scene
              0: concentric circles + an orbiting dot (planetary motion)
              1: animated coordinate axes with a dot tracing a sine curve
              2: a shape morphing triangle → square → pentagon
              3: a network graph with edges pulsing in a wave
        Long text is pre-wrapped (Manim's Text doesn't auto-wrap), and any
        residual overflow is caught by scale_to_fit_width.
        """
        body: List[str] = []
        for i, sc in enumerate(scenes):
            raw_title = sc.get("title", "") or f"Part {i+1}"
            title_wrapped = self._wrap_for_manim(raw_title, max_chars=28)
            bullets = (sc.get("bullets", []) or [])[:3]
            audio_d = audio_durations[i] if i < len(audio_durations) else 4.0

            # Pre-wait animation budget:
            #   accent_bar(0.4) + title Write(0.8) + underline(0.4)
            #   + visual_intro(0.7) + bullets(0.6 each)
            reserved = 0.4 + 0.8 + 0.4 + 0.7 + 0.6 * len(bullets)
            # wait_t includes both the visual motion-during-hold AND the still tail
            wait_t = max(0.5, audio_d - reserved + 0.3)
            motion_budget = max(0.0, wait_t - 0.4)  # leave ≥0.4s still wait
            include_motion = motion_budget >= 0.5

            body.append(f"        # === Scene {i+1} ===")
            # ── Decorative left accent bar
            body.append(f"        accent_bar = Rectangle(width=0.18, height=6.5, "
                        f"fill_color='#A89CFF', fill_opacity=1, stroke_width=0)")
            body.append(f"        accent_bar.to_edge(LEFT, buff=0.4)")
            body.append(f"        self.play(GrowFromEdge(accent_bar, DOWN), run_time=0.4)")

            # ── Title (Write — drawn stroke-by-stroke)
            body.append(
                f"        title = Text({json.dumps(title_wrapped)}, font_size=38, "
                f"weight=BOLD, color=WHITE, line_spacing=0.8)"
            )
            body.append(f"        title.to_edge(UP, buff=0.7).to_edge(LEFT, buff=1.0)")
            body.append(f"        if title.width > 7.5:\n"
                        f"            title.scale_to_fit_width(7.5)")
            body.append(f"        self.play(Write(title), run_time=0.8)")
            body.append(f"        underline = Line(title.get_corner(DL)+DOWN*0.15, "
                        f"title.get_corner(DL)+DOWN*0.15+RIGHT*min(title.width, 6), "
                        f"color='#A89CFF', stroke_width=6)")
            body.append(f"        self.play(Create(underline), run_time=0.4)")

            # ── Right-side animated diagram (varies per scene)
            visual_idx = i % 4
            if visual_idx == 0:
                # Planetary motion: concentric circles + orbiting dot
                body.append(f"        v_center = np.array([4.0, -0.5, 0])")
                body.append(f"        c1 = Circle(radius=1.7, color='#A89CFF', stroke_width=4).move_to(v_center)")
                body.append(f"        c2 = Circle(radius=1.05, color='#7B6BFF', stroke_width=3).move_to(v_center)")
                body.append(f"        c3 = Circle(radius=0.4, color='#DCDCF0', stroke_width=2, "
                            f"fill_opacity=0.3, fill_color='#DCDCF0').move_to(v_center)")
                body.append(f"        orbit_dot = Dot(color='#FFD96B', radius=0.14).move_to(v_center + RIGHT*1.7)")
                body.append(f"        self.play(Create(c1), Create(c2), Create(c3), "
                            f"FadeIn(orbit_dot), run_time=0.7)")
                visual_group = "VGroup(c1, c2, c3, orbit_dot)"
                motion_dur = min(2.5, motion_budget)
                visual_motion = (
                    f"        self.play(Rotate(orbit_dot, angle=2*PI, about_point=v_center), "
                    f"run_time={motion_dur:.2f}, rate_func=linear)"
                )
                motion_total = motion_dur
            elif visual_idx == 1:
                # Coordinate axes with a dot tracing a sine curve
                body.append(
                    f"        axes = Axes(x_range=[-3,3,1], y_range=[-1.5,1.5,1], "
                    f"x_length=3.6, y_length=2.6, "
                    f"axis_config={{'color': '#A89CFF', 'stroke_width': 3}}, "
                    f"tips=False).move_to([4.0, -0.5, 0])"
                )
                body.append(f"        curve = axes.plot(lambda x: np.sin(x*1.5), "
                            f"color='#FFD96B', stroke_width=4)")
                body.append(f"        moving_dot = Dot(color='#FFD96B', radius=0.13)")
                body.append(f"        self.play(Create(axes), run_time=0.4)")
                body.append(f"        moving_dot.move_to(curve.get_start())")
                body.append(f"        self.play(Create(curve), FadeIn(moving_dot), run_time=0.5)")
                visual_group = "VGroup(axes, curve, moving_dot)"
                motion_dur = min(2.0, motion_budget)
                visual_motion = (
                    f"        self.play(MoveAlongPath(moving_dot, curve, "
                    f"rate_func=there_and_back), run_time={motion_dur:.2f})"
                )
                motion_total = motion_dur
            elif visual_idx == 2:
                # Polygon morph: triangle → square → pentagon
                body.append(f"        v_center = np.array([4.0, -0.5, 0])")
                body.append(f"        tri = RegularPolygon(n=3, color='#A89CFF', stroke_width=4, "
                            f"fill_opacity=0.3, fill_color='#7B6BFF').scale(1.4).move_to(v_center)")
                body.append(f"        sq = RegularPolygon(n=4, color='#A89CFF', stroke_width=4, "
                            f"fill_opacity=0.3, fill_color='#7B6BFF').scale(1.4).move_to(v_center)")
                body.append(f"        pent = RegularPolygon(n=5, color='#A89CFF', stroke_width=4, "
                            f"fill_opacity=0.3, fill_color='#7B6BFF').scale(1.4).move_to(v_center)")
                body.append(f"        self.play(Create(tri), run_time=0.6)")
                visual_group = "tri"
                step = min(0.8, motion_budget / 2) if include_motion else 0.0
                visual_motion = (
                    f"        self.play(Transform(tri, sq), run_time={step:.2f})\n"
                    f"        self.play(Transform(tri, pent), run_time={step:.2f})"
                )
                motion_total = step * 2
            else:
                # Network graph: center node with 6 satellites + pulsing edges
                body.append(f"        v_center = np.array([4.0, -0.5, 0])")
                body.append(
                    f"        nodes = VGroup(*[Dot(color='#FFD96B', radius=0.14).move_to("
                    f"v_center + np.array([np.cos(a)*1.55, np.sin(a)*1.55, 0])) "
                    f"for a in np.linspace(0, 2*PI, 6, endpoint=False)])"
                )
                body.append(f"        center_node = Dot(color='#A89CFF', radius=0.18).move_to(v_center)")
                body.append(
                    f"        edges = VGroup(*[Line(center_node.get_center(), n.get_center(), "
                    f"color='#7B6BFF', stroke_width=2.5) for n in nodes])"
                )
                body.append(f"        self.play(FadeIn(center_node), Create(edges), "
                            f"FadeIn(nodes, lag_ratio=0.1), run_time=0.8)")
                visual_group = "VGroup(center_node, edges, nodes)"
                motion_dur = min(2.0, motion_budget)
                visual_motion = (
                    f"        self.play(LaggedStart(*[Indicate(e, color='#FFD96B', "
                    f"scale_factor=1.05) for e in edges], lag_ratio=0.15), "
                    f"run_time={motion_dur:.2f})"
                )
                motion_total = motion_dur

            # ── Bullets (Write — drawn stroke-by-stroke; on the LEFT half)
            bullet_text_vars: List[str] = []
            all_bullet_objs: List[str] = []
            for j, b in enumerate(bullets):
                bv = f"b_{i}_{j}"
                dot = f"d_{i}_{j}"
                bw = self._wrap_for_manim(b, max_chars=38)
                body.append(f"        {dot} = Dot(color='#FFD96B', radius=0.09)")
                body.append(
                    f"        {bv} = Text({json.dumps(bw)}, font_size=22, "
                    f"color='#DCDCF0', line_spacing=0.7)"
                )
                body.append(f"        if {bv}.width > 6.3:\n"
                            f"            {bv}.scale_to_fit_width(6.3)")
                if j == 0:
                    body.append(f"        {bv}.next_to(underline, DOWN, buff=0.55).align_to(title, LEFT)")
                else:
                    body.append(f"        {bv}.next_to({bullet_text_vars[-1]}, DOWN, "
                                f"buff=0.4).align_to(title, LEFT)")
                body.append(f"        {dot}.move_to({bv}.get_corner(UL) + LEFT*0.18 + DOWN*0.18)")
                body.append(f"        self.play(FadeIn({dot}, scale=0.5), Write({bv}), "
                            f"run_time=0.6)")
                bullet_text_vars.append(bv)
                all_bullet_objs.append(bv)
                all_bullet_objs.append(dot)

            # ── Hold (animate visual during the hold, then still wait)
            if include_motion:
                body.append(visual_motion)
                still_wait = max(0.2, wait_t - motion_total)
            else:
                still_wait = wait_t
            body.append(f"        self.wait({still_wait:.2f})")

            group_members = ["accent_bar", "title", "underline"] + all_bullet_objs + [visual_group]
            body.append(
                f"        self.play(FadeOut(VGroup({', '.join(group_members)}), "
                f"scale=0.95), run_time=0.4)"
            )

        code = (
            "from manim import *\n"
            "import numpy as np\n\n"
            "class GeneratedLesson(Scene):\n"
            "    def construct(self):\n"
            "        self.camera.background_color = '#1A1040'\n"
            + "\n".join(body)
            + "\n"
        )
        return code

    def _render_manim_video(self, scenes: List[Dict], rendered_audio: List[Path],
                           out_path: Path) -> float:
        """Render a Manim video and mux per-scene narration audio.

        Returns total duration. Raises on Manim CLI failure (caller may fall back).
        """
        import subprocess
        import sys
        if not MOVIEPY_AVAILABLE:
            raise Exception("moviepy not installed. Run: pip install moviepy imageio-ffmpeg")
        from moviepy import VideoFileClip, CompositeAudioClip

        # 1. Get audio durations
        audio_durations: List[float] = []
        for ap in rendered_audio:
            ac = AudioFileClip(str(ap))
            audio_durations.append(ac.duration)
            ac.close()

        # 2. Generate Manim code
        manim_dir = self.tmp_dir / "manim_run"
        manim_dir.mkdir(parents=True, exist_ok=True)
        # Clean any prior run
        for child in manim_dir.iterdir():
            try:
                if child.is_file():
                    child.unlink()
                else:
                    import shutil
                    shutil.rmtree(child, ignore_errors=True)
            except Exception:
                pass

        code = self._build_manim_code(scenes, audio_durations)
        code_path = manim_dir / "lesson.py"
        code_path.write_text(code, encoding="utf-8")

        # 3. Run Manim CLI: -ql = 480p15 (fastest)
        cmd = [
            sys.executable, "-m", "manim",
            "-ql",
            "--media_dir", str(manim_dir),
            "--output_file", "lesson",
            str(code_path), "GeneratedLesson",
        ]
        logger.info("Running Manim: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd, capture_output=True, timeout=900,
            cwd=str(manim_dir), text=True,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "")[-500:]
            raise Exception(f"Manim render failed: {stderr}")

        # 4. Locate the generated MP4
        # Manim outputs to <media_dir>/videos/<file_stem>/<quality>/<output_file>.mp4
        candidates = list(manim_dir.glob("videos/lesson/*/lesson.mp4"))
        if not candidates:
            candidates = list(manim_dir.glob("**/lesson.mp4"))
        if not candidates:
            raise Exception("Manim ran but produced no MP4 output")
        silent_mp4 = candidates[0]

        # 5. Build a CompositeAudioClip with each scene's narration at the right
        # offset. Each Manim scene runs roughly: 0.6 + 0.4*bullets + wait + 0.4
        # = audio_duration + 0.3 — matching how _build_manim_code spaced things.
        offset = 0.0
        audio_clips = []
        for i, ap in enumerate(rendered_audio):
            ac = AudioFileClip(str(ap))
            # 50ms safety trim so MoviePy never seeks past EOF
            safe_d = max(0.0, ac.duration - 0.05)
            if safe_d <= 0.05:
                ac.close()
                continue
            try:
                ac = ac.subclipped(0, safe_d)
            except AttributeError:
                ac = ac.subclip(0, safe_d)
            ac = ac.with_start(offset)
            audio_clips.append(ac)
            # Move offset by this scene's intended length (must match Manim timing)
            audio_d = audio_durations[i]
            scene_animation_time = audio_d + 0.3 + 0.4  # wait + fadeout
            offset += scene_animation_time

        composite_audio = CompositeAudioClip(audio_clips)

        # 6. Mux audio onto Manim video
        video = VideoFileClip(str(silent_mp4))
        video = video.with_audio(composite_audio)
        ffmpeg_params = ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        temp_audiofile = str(self.tmp_dir / f"{out_path.stem}_audio.m4a")
        video.write_videofile(
            str(out_path),
            fps=15,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=4,
            logger=None,
            ffmpeg_params=ffmpeg_params,
            temp_audiofile=temp_audiofile,
        )
        duration = video.duration
        video.close()
        for ac in audio_clips:
            try:
                ac.close()
            except Exception:
                pass
        # Cleanup manim_dir
        try:
            import shutil
            shutil.rmtree(manim_dir, ignore_errors=True)
        except Exception:
            pass
        return duration

    def _cache_key(self, source_text: str, query: Optional[str], style: str) -> str:
        raw = f"{style}|{query or ''}|" + (source_text or "")[:2000]
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    async def generate_video(
        self,
        source_text: str,
        pdf_identifier: Optional[str] = None,
        query: Optional[str] = None,
        style: str = "slides",
    ) -> Dict:
        """Produce an MP4 video.

        style:
            - "slides" (default): animated slideshow with build-up reveal,
              ken-burns zoom and cross-fade transitions.
            - "manim":  Manim-rendered animations (text fade-in, line drawing,
              bullets sliding in). Falls back to slides on render failure.
        """
        if not MOVIEPY_AVAILABLE:
            raise Exception("moviepy not installed. Run: pip install moviepy imageio-ffmpeg")

        source_text = (source_text or "").strip()
        if not source_text:
            raise Exception("No source text supplied for video generation")

        style = (style or "slides").strip().lower()
        if style not in {"slides", "manim"}:
            style = "slides"

        key = self._cache_key(source_text, query, style)
        pdf_stub = re.sub(r'[^A-Za-z0-9]+', "_", (pdf_identifier or "video"))[:40]
        filename = f"video_{style}_{pdf_stub}_{key}.mp4"
        out_path = self.video_dir / filename

        if out_path.exists() and out_path.stat().st_size > 1024:
            logger.info(f"Video cache hit: {filename}")
            return {
                "filename": filename,
                "video_url": f"/api/video/{filename}",
                "cached": True,
                "style": style,
                "duration_estimate": 0.0,
                "scenes_count": 0,
                "script": "",
            }

        logger.info("Generating video script…")
        script = await self.generate_script(source_text, focus_query=query)
        logger.info("Splitting into scenes (heuristic)…")
        scenes = self.split_into_scenes(script, topic_hint=(query or "")[:60])
        if not scenes:
            raise Exception("Could not break the script into scenes. Try again with a richer source.")

        scenes = scenes[:MAX_SCENES]

        # Render TTS + slide build frames per scene (always — used by both paths)
        logger.info(f"Rendering {len(scenes)} scenes (audio + frames)…")
        rendered: List[Dict] = []
        for i, scene in enumerate(scenes):
            r = await asyncio.to_thread(self._render_single_scene, scene, "", i)
            rendered.append(r)

        used_style = style
        if style == "manim":
            try:
                logger.info("Rendering with Manim…")
                audio_paths = [r["audio"] for r in rendered]
                duration = await asyncio.to_thread(
                    self._render_manim_video, scenes, audio_paths, out_path,
                )
            except Exception as me:
                logger.warning("Manim render failed (%s) — falling back to slides", me)
                used_style = "slides"
                duration = await asyncio.to_thread(self._compose_video, rendered, out_path)
        else:
            logger.info("Composing animated slides MP4…")
            duration = await asyncio.to_thread(self._compose_video, rendered, out_path)

        logger.info(f"Video written: {out_path} ({duration:.1f}s) [style={used_style}]")

        # Cleanup scene artifacts (keep final MP4)
        for r in rendered:
            paths_to_clean = []
            if r.get("frames"):
                paths_to_clean.extend(r["frames"])
            if r.get("audio"):
                paths_to_clean.append(r["audio"])
            for p in paths_to_clean:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass

        return {
            "filename": filename,
            "video_url": f"/api/video/{filename}",
            "cached": False,
            "style": used_style,
            "duration_estimate": duration,
            "scenes_count": len(scenes),
            "script": script,
            "scenes": [{"title": s.get("title"), "bullets": s.get("bullets", [])} for s in scenes],
        }


# Global singleton
video_generator = VideoGenerator()
