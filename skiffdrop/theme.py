"""Harbor Edition: the two palettes (Harbor Ink at night, Sail Ivory by day) and the
type stack for each language. Everything the PC window paints takes its colors from here."""

from __future__ import annotations

from dataclasses import dataclass, field

# Brand colors (see the brand sheet): Harbor Ink, Deep Hull, Brass, Sea Glass, Signal Coral, Sail Ivory.
INK, HULL, BRASS, SEA, CORAL, IVORY = "#0A0F1A", "#111A2B", "#D8B46A", "#5CC8B0", "#F08A6C", "#F4EFE6"


@dataclass(frozen=True)
class Palette:
    name: str
    ground: str        # window background
    panel: str         # cards
    raised: str        # secondary buttons, selected rows
    raised_hi: str     # their hover
    well: str          # inset areas: activity list, keycaps
    field: str         # text inputs
    text: str
    text2: str         # secondary
    text3: str         # muted
    line: str          # hairlines
    line2: str         # stronger hairlines, dashed drop area
    brass_text: str    # brass used as text (darker on ivory for contrast)
    sea: str           # "connected"
    coral: str         # warnings
    banner: str        # background of the warning bar
    banner_line: str
    scroll: str
    mark: dict = field(default_factory=dict)     # left sail, right sail, hull, wave
    muted_mark: dict = field(default_factory=dict)
    tile: str = ""
    tile_line: str = ""
    qr_bg: str = IVORY
    dark: bool = True


DARK = Palette(
    "dark", ground=INK, panel=HULL, raised="#16213A", raised_hi="#1C2945", well="#0D1422", field=INK,
    text=IVORY, text2="rgba(244,239,230,0.68)", text3="rgba(244,239,230,0.46)",
    line="rgba(244,239,230,0.08)", line2="rgba(244,239,230,0.18)", brass_text=BRASS, sea=SEA, coral=CORAL,
    banner="#1A1513", banner_line="rgba(240,138,108,0.30)", scroll="rgba(244,239,230,0.16)",
    mark={"left": "#8E7B55", "right": BRASS, "hull": IVORY, "wave": BRASS},
    muted_mark={"left": "#4A4434", "right": "#6B5D40", "hull": "#2C3547", "wave": "#2C3547"},
    tile=HULL, tile_line="rgba(216,180,106,0.30)", qr_bg=IVORY, dark=True)

LIGHT = Palette(
    "light", ground=IVORY, panel="#FBF8F2", raised="#EEE7DA", raised_hi="#E7DECD", well="#F1EBE0", field="#FFFFFF",
    text=INK, text2="rgba(10,15,26,0.68)", text3="rgba(10,15,26,0.48)",
    line="rgba(10,15,26,0.09)", line2="rgba(10,15,26,0.20)", brass_text="#8A6A2E", sea="#23806C", coral="#B5482B",
    banner="#FBEBE4", banner_line="rgba(181,72,43,0.28)", scroll="rgba(10,15,26,0.18)",
    mark={"left": "#D2B784", "right": "#A9813D", "hull": INK, "wave": "#B08A45"},
    muted_mark={"left": "#E3D7C0", "right": "#D5C3A0", "hull": "#D3CABA", "wave": "#D3CABA"},
    tile="#FBF8F2", tile_line="rgba(10,15,26,0.12)", qr_bg="#FFFFFF", dark=False)

# Type: Instrument Serif for the wordmark and titles, Manrope for the interface, JetBrains Mono for
# codes, addresses and paths. None of them has Arabic or CJK, so each
# language gets the Windows font that draws its script well, put first among the fallbacks.
SCRIPT_UI = {"ar": "Segoe UI", "ja": "Yu Gothic UI", "zh": "Microsoft YaHei UI"}
SCRIPT_DISPLAY = {"ar": "Segoe UI", "ja": "Yu Gothic UI", "zh": "Microsoft YaHei UI"}
FALLBACKS = ["Segoe UI", "Yu Gothic UI", "Microsoft YaHei UI", "Malgun Gothic", "Nirmala UI", "Segoe UI Emoji"]


def _stack(first: str, lang: str, table: dict) -> str:
    names = [first] + ([table[lang]] if lang in table else []) + FALLBACKS
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return ", ".join(f"'{n}'" for n in seen)


def ui_family(lang: str) -> str:
    return _stack("Manrope", lang, SCRIPT_UI)


def display_family(lang: str) -> str:
    return _stack("Instrument Serif", lang, SCRIPT_DISPLAY)


def mono_family(lang: str) -> str:
    return _stack("JetBrains Mono", lang, SCRIPT_UI)


def display_size(lang: str, size: int) -> int:
    """The serif runs small for its size; script fallbacks don't, so they get a step down."""
    return size if lang not in SCRIPT_DISPLAY else round(size * 0.78)
