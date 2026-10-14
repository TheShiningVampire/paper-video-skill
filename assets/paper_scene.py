"""Shared base for paper-video Manim scenes. Copy next to scenes.py; do not edit per paper.

Each scene class is named after its narration entry (e.g. S03_Method). PaperScene then:
  * attaches audio/<SceneName>.wav at t=0 and pads the end so video length == narration + tail,
  * gives pacing helpers (self.until(t), self.remaining()),
  * renders paper equations with the paper's own macros (macros.tex),
  * logs off-frame / overlapping elements to layout_warnings.txt after every animation.
"""
import json, re, sys
from pathlib import Path

from manim import *

WORK = Path(__file__).resolve().parent
TAIL = 0.6  # seconds of breathing room after narration ends

# One colour per recurring concept; keep the mapping fixed for the whole video.
PALETTE = [BLUE_C, YELLOW_C, GREEN_C, RED_C, PURPLE_B, TEAL_C, ORANGE, PINK]
BG = "#0f1117"
config.background_color = BG

_template = TexTemplate()
_template.add_to_preamble(r"\usepackage{amsmath,amssymb,bm,mathtools}")
_macros = WORK / "macros.tex"
if _macros.exists():
    _template.add_to_preamble(_macros.read_text())


def Eq(*tex, **kw):
    """MathTex with the paper's macros. Split terms into separate strings to colour/point at them."""
    kw.setdefault("tex_template", _template)
    return MathTex(*tex, **kw)


_eq_file = WORK / "equations.json"
EQS = {e["n"]: e["latex"] for e in json.loads(_eq_file.read_text())} if _eq_file.exists() else {}


def _norm(s):
    return re.sub(r"\s+", "", s).rstrip(".,")


def PEq(n, *parts, **kw):
    """Paper equation n from equations.json, split into parts you can colour/point at.

    Fails the render if the parts don't join to exactly the paper's LaTeX (whitespace ignored).
    """
    assert _norm("".join(parts)) == _norm(EQS[n]), f"Eq {n} differs from the paper:\n{''.join(parts)}\n{EQS[n]}"
    return Eq(*parts, **kw)


def E(n, **kw):
    """Paper equation n from equations.json, unsplit."""
    return Eq(EQS[n].strip().rstrip(".,"), **kw)


def Label(text, size=30, **kw):
    return Text(text, font_size=size, **kw)


class PaperScene(Scene):
    def setup(self):
        name = type(self).__name__
        durs_file = WORK / "audio" / "durations.json"
        durs = json.loads(durs_file.read_text()) if durs_file.exists() else {}
        self.narration = durs.get(name)
        wav = WORK / "audio" / f"{name}.wav"
        if self.narration and wav.exists():
            self.add_sound(str(wav))
        else:
            print(f"[paper_scene] no narration for {name}; rendering silent", file=sys.stderr)
        self._warned = set()

    # ---- pacing -------------------------------------------------------
    def until(self, t):
        """Wait until absolute scene time t (seconds). Use to sync visuals with narration cues."""
        if t > self.time:
            self.wait(t - self.time)

    def at(self, phrase, lead=0.3):
        """Wait until the narration reaches `phrase` (estimated by character position in the text).

        Start an animation right after this so it lands as the words are spoken.
        """
        text = self._text()
        i = text.lower().find(phrase.lower())
        if i < 0 or not self.narration:
            print(f"[paper_scene] cue {phrase!r} not found in {type(self).__name__}", file=sys.stderr)
            return
        self.until(max(0.0, self.narration * i / len(text) - lead))

    def _text(self):
        if not hasattr(self, "_narr_text"):
            f = WORK / "narration.json"
            items = json.loads(f.read_text()) if f.exists() else []
            self._narr_text = next((s["text"] for s in items if s["scene"] == type(self).__name__), "")
        return self._narr_text

    def remaining(self):
        return max(0.0, (self.narration or 0) - self.time)

    def tear_down(self):
        if self.narration:
            self.until(self.narration + TAIL)

    # ---- layout checks -----------------------------------------------
    def play(self, *args, **kwargs):
        super().play(*args, **kwargs)
        self._check_layout()

    def _check_layout(self):
        w, h = config.frame_width / 2 - 0.1, config.frame_height / 2 - 0.1
        items = [m for m in self.mobjects if m.get_family() and not m.is_off_screen()
                 and m.width > 0 and m.width < config.frame_width * 1.5]
        msgs = []
        for m in items:
            l, r = m.get_left()[0], m.get_right()[0]
            b, t = m.get_bottom()[1], m.get_top()[1]
            if l < -w or r > w or b < -h or t > h:
                msgs.append(f"OFF-FRAME {type(m).__name__} at t={self.time:.1f}s "
                            f"x[{l:.2f},{r:.2f}] y[{b:.2f},{t:.2f}]")
        kinds = (Text, MathTex, MarkupText)
        texts = [f for m in items for f in m.get_family() if isinstance(f, kinds)]
        texts = [t for t in dict.fromkeys(texts)  # outermost text objects only
                 if not any(o is not t and t in o.get_family() for o in texts)]
        for i, a in enumerate(texts):
            for b in texts[i + 1:]:
                if _overlap(a, b) > 0.15:
                    msgs.append(f"OVERLAP {_short(a)} <> {_short(b)} at t={self.time:.1f}s")
        new = [m for m in msgs if m.split(" at ")[0] not in self._warned]
        if new:
            with open(WORK / "layout_warnings.txt", "a") as f:
                for m in new:
                    self._warned.add(m.split(" at ")[0])
                    f.write(f"{type(self).__name__}: {m}\n")

    # ---- building blocks ---------------------------------------------
    def title_card(self, title, subtitle=""):
        t = Label(title, size=48, weight=BOLD)
        fit_width(t, 12)
        grp = VGroup(t)
        if subtitle:
            s = Label(subtitle, size=28, color=GREY_B)
            fit_width(s, 12)
            grp.add(s)
        grp.arrange(DOWN, buff=0.4)
        self.play(FadeIn(grp, shift=UP * 0.3))
        return grp

    def show_figure(self, path, caption="", height=5.2):
        """Show a figure cropped from the paper, with a 'Figure from the paper' caption."""
        img = ImageMobject(str(WORK / path))
        img.height = height
        if img.width > 12.5:
            img.width = 12.5
        grp = Group(img)
        if caption:
            cap = Label(caption, size=22, color=GREY_B)
            fit_width(cap, 12)
            grp.add(cap)
            grp.arrange(DOWN, buff=0.25)
        self.play(FadeIn(grp))
        return grp

    def callout(self, eq, index, note, color=YELLOW_C, direction=DOWN):
        """Box one term of a multi-part Eq and label it in plain words."""
        part = eq[index]
        box = SurroundingRectangle(part, color=color, buff=0.08)
        lab = Label(note, size=26, color=color).next_to(box, direction, buff=0.25)
        fit_width(lab, 12)
        self.play(Create(box), FadeIn(lab, shift=direction * 0.2), part.animate.set_color(color))
        return VGroup(box, lab)


def fit_width(m, max_w):
    if m.width > max_w:
        m.width = max_w
    return m


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = a.get_left()[0], a.get_bottom()[1], a.get_right()[0], a.get_top()[1]
    bx0, by0, bx1, by1 = b.get_left()[0], b.get_bottom()[1], b.get_right()[0], b.get_top()[1]
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    small = min(a.width * a.height, b.width * b.height) or 1
    return ix * iy / small


def _short(m):
    s = getattr(m, "original_text", None) or getattr(m, "tex_string", "") or type(m).__name__
    return repr(s[:25])
