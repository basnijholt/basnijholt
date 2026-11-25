from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeroPalette:
    mode: str
    bg: str
    card: str
    border: str
    fg: str
    muted: str
    accent: str
    green: str
    kw: str
    str_col: str
    num: str
    attr: str
    cmt: str
    mesh_stroke: str
    mesh_node: str


LIGHT = HeroPalette(
    mode="light",
    bg="#ffffff",
    card="#f6f8fa",
    border="#d0d7de",
    fg="#1f2328",
    muted="#656d76",
    accent="#0969da",
    green="#1a7f37",
    kw="#cf222e",
    str_col="#0a3069",
    num="#0550ae",
    attr="#8250df",
    cmt="#6e7781",
    mesh_stroke="#0969da",
    mesh_node="#0969da",
)

DARK = HeroPalette(
    mode="dark",
    bg="#0d1117",
    card="#161b22",
    border="#30363d",
    fg="#e6edf3",
    muted="#8b949e",
    accent="#58a6ff",
    green="#3fb950",
    kw="#ff7b72",
    str_col="#a5d6ff",
    num="#79c0ff",
    attr="#d2a8ff",
    cmt="#8b949e",
    mesh_stroke="#58a6ff",
    mesh_node="#79c0ff",
)

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"


def _adaptive_mesh_svg(
    p: HeroPalette,
    total_stars: int,
    total_blog_posts: int,
) -> str:
    pts = [
        (520, 22), (610, 14), (710, 26), (820, 16), (886, 42),
        (495, 78), (580, 68), (668, 84), (760, 64), (848, 92),
        (530, 136), (620, 126), (708, 144), (796, 122), (878, 152),
        (575, 186), (675, 188), (766, 182), (854, 192),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (0, 6), (1, 6), (1, 7),
        (2, 7), (2, 8), (3, 8), (3, 9), (4, 9), (5, 6), (6, 7), (7, 8),
        (8, 9), (5, 10), (6, 10), (6, 11), (7, 11), (7, 12), (8, 12),
        (8, 13), (9, 13), (9, 14), (10, 11), (11, 12), (12, 13), (13, 14),
        (10, 15), (11, 15), (11, 16), (12, 16), (12, 17), (13, 17),
        (13, 18), (14, 18), (15, 16), (16, 17), (17, 18),
    ]
    dense = [(682, 92), (714, 78), (736, 104), (698, 118), (720, 98)]
    dense_edges = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)]

    base_lines = "\n    ".join(
        f'<line x1="{pts[a][0]}" y1="{pts[a][1]}" x2="{pts[b][0]}" y2="{pts[b][1]}" />'
        for a, b in edges
    )
    fine_lines = "\n    ".join(
        f'<line x1="{dense[a][0]}" y1="{dense[a][1]}" x2="{dense[b][0]}" y2="{dense[b][1]}" />'
        for a, b in dense_edges
    )
    base_nodes = "\n    ".join(
        f'<circle cx="{x}" cy="{y}" r="2.2" fill-opacity="0.45" />'
        for x, y in pts
    )
    fine_nodes = "\n    ".join(
        f'<circle cx="{x}" cy="{y}" r="{3.6 if i == 4 else 2.5}" fill-opacity="{0.95 if i == 4 else 0.7}" />'
        for i, (x, y) in enumerate(dense)
    )
    glow_op = "0.18" if p.mode == "dark" else "0.11"
    edge_op = "0.24" if p.mode == "dark" else "0.18"
    fine_op = "0.55" if p.mode == "dark" else "0.42"

    return f"""<svg viewBox="0 0 900 205" width="900" height="205" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="meshBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{p.card}" />
      <stop offset="100%" stop-color="{p.bg}" />
    </linearGradient>
    <radialGradient id="meshGlow" cx="78%" cy="48%" r="36%">
      <stop offset="0%" stop-color="{p.accent}" stop-opacity="{glow_op}" />
      <stop offset="100%" stop-color="{p.accent}" stop-opacity="0" />
    </radialGradient>
  </defs>
  <rect x="0.5" y="0.5" width="899" height="204" rx="10" fill="url(#meshBg)" stroke="{p.border}" />
  <rect x="1" y="1" width="898" height="203" rx="10" fill="url(#meshGlow)" />

  <g stroke="{p.mesh_stroke}" stroke-opacity="{edge_op}" stroke-width="1">
    {base_lines}
  </g>
  <g stroke="{p.mesh_stroke}" stroke-opacity="{fine_op}" stroke-width="1.1">
    {fine_lines}
    <line x1="668" y1="84" x2="682" y2="92" />
    <line x1="760" y1="64" x2="714" y2="78" />
    <line x1="760" y1="64" x2="736" y2="104" />
    <line x1="708" y1="144" x2="698" y2="118" />
    <line x1="708" y1="144" x2="736" y2="104" />
  </g>
  <g fill="{p.mesh_node}">
    {base_nodes}
    {fine_nodes}
  </g>

  <text x="34" y="42" fill="{p.accent}" font-size="11" font-weight="700" letter-spacing="1" font-family="{MONO}">BAS NIJHOLT · SEATTLE, WA</text>
  <text x="34" y="84" fill="{p.fg}" font-size="34" font-weight="700" letter-spacing="-0.8" font-family="{SANS}">Physicist turned builder.</text>
  <text x="34" y="114" fill="{p.muted}" font-size="15" font-family="{SANS}">Co-founder at a stealth AI company, working on MindRoom.</text>
  <text x="34" y="136" fill="{p.muted}" font-size="14" font-family="{SANS}">Previously IonQ · Microsoft Quantum · TU Delft PhD</text>

  <g font-family="{MONO}" font-size="11.5">
    <rect x="34" y="156" width="128" height="26" rx="6" fill="{p.bg}" stroke="{p.border}" />
    <text x="46" y="173" fill="{p.fg}" font-weight="600">★ {total_stars:,}</text>
    <text x="118" y="173" fill="{p.muted}">stars</text>

    <rect x="172" y="156" width="164" height="26" rx="6" fill="{p.bg}" stroke="{p.border}" />
    <text x="184" y="173" fill="{p.fg}" font-weight="600">15+ NixOS</text>
    <text x="256" y="173" fill="{p.muted}">~150 apps</text>

    <rect x="346" y="156" width="118" height="26" rx="6" fill="{p.bg}" stroke="{p.border}" />
    <text x="358" y="173" fill="{p.fg}" font-weight="600">{total_blog_posts} posts</text>
    <text x="422" y="173" fill="{p.muted}">blog</text>
  </g>
</svg>
"""


def _bas_nix_svg(
    p: HeroPalette,
    total_stars: int,
    stars_last_year: int,
) -> str:
    return f"""<svg viewBox="0 0 900 250" width="900" height="250" xmlns="http://www.w3.org/2000/svg">
  <rect x="0.5" y="0.5" width="899" height="249" rx="10" fill="{p.card}" stroke="{p.border}" />
  <rect x="1" y="1" width="898" height="34" rx="10" fill="{p.bg}" />
  <rect x="1" y="20" width="898" height="15" fill="{p.bg}" />
  <line x1="1" y1="35" x2="899" y2="35" stroke="{p.border}" />
  <circle cx="22" cy="18" r="5" fill="#ff5f56" />
  <circle cx="38" cy="18" r="5" fill="#ffbd2e" />
  <circle cx="54" cy="18" r="5" fill="#27c93f" />
  <text x="74" y="22" fill="{p.muted}" font-size="12" font-family="{MONO}">~/dotfiles/bas.nix</text>
  <text x="876" y="22" fill="{p.green}" font-size="11.5" text-anchor="end" font-family="{MONO}">● flake clean · {total_stars:,} ★</text>

  <g font-family="{MONO}" font-size="13.5" xml:space="preserve">
    <text x="26" y="64" fill="{p.muted}">1</text>
    <text x="52" y="64" fill="{p.fg}">{{ <tspan fill="{p.cmt}"># Dutch physicist turned builder, living near Seattle</tspan></text>

    <text x="26" y="88" fill="{p.muted}">2</text>
    <text x="68" y="88"><tspan fill="{p.attr}">now</tspan><tspan fill="{p.fg}">       = </tspan><tspan fill="{p.str_col}">"co-founder @ stealth AI (building MindRoom)"</tspan><tspan fill="{p.fg}">;</tspan></text>

    <text x="26" y="112" fill="{p.muted}">3</text>
    <text x="68" y="112"><tspan fill="{p.attr}">before</tspan><tspan fill="{p.fg}">    = [ </tspan><tspan fill="{p.str_col}">"IonQ"</tspan><tspan fill="{p.fg}"> </tspan><tspan fill="{p.str_col}">"Microsoft Quantum"</tspan><tspan fill="{p.fg}"> </tspan><tspan fill="{p.str_col}">"TU Delft (PhD)"</tspan><tspan fill="{p.fg}"> ];</tspan></text>

    <text x="26" y="136" fill="{p.muted}">4</text>
    <text x="68" y="136"><tspan fill="{p.attr}">homelab</tspan><tspan fill="{p.fg}">   = {{ </tspan><tspan fill="{p.attr}">os</tspan><tspan fill="{p.fg}"> = </tspan><tspan fill="{p.str_col}">"NixOS"</tspan><tspan fill="{p.fg}">; </tspan><tspan fill="{p.attr}">hosts</tspan><tspan fill="{p.fg}"> = </tspan><tspan fill="{p.num}">16</tspan><tspan fill="{p.fg}">; </tspan><tspan fill="{p.attr}">containers</tspan><tspan fill="{p.fg}"> = </tspan><tspan fill="{p.num}">150</tspan><tspan fill="{p.fg}">; </tspan><tspan fill="{p.attr}">kubernetes</tspan><tspan fill="{p.fg}"> = </tspan><tspan fill="{p.kw}">false</tspan><tspan fill="{p.fg}">; }};</tspan></text>

    <text x="26" y="160" fill="{p.muted}">5</text>
    <text x="68" y="160"><tspan fill="{p.attr}">rules</tspan><tspan fill="{p.fg}">     = [ </tspan><tspan fill="{p.str_col}">"plain text in git"</tspan><tspan fill="{p.fg}"> </tspan><tspan fill="{p.str_col}">"roll your own, fork the rest"</tspan><tspan fill="{p.fg}"> ];</tspan></text>

    <text x="26" y="184" fill="{p.muted}">6</text>
    <text x="68" y="184"><tspan fill="{p.attr}">languages</tspan><tspan fill="{p.fg}"> = [ </tspan><tspan fill="{p.str_col}">"Python"</tspan><tspan fill="{p.fg}"> </tspan><tspan fill="{p.str_col}">"TypeScript"</tspan><tspan fill="{p.fg}"> </tspan><tspan fill="{p.str_col}">"Nix"</tspan><tspan fill="{p.fg}"> ];</tspan></text>

    <text x="26" y="208" fill="{p.muted}">7</text>
    <text x="68" y="208"><tspan fill="{p.attr}">stars</tspan><tspan fill="{p.fg}">     = </tspan><tspan fill="{p.num}">{total_stars}</tspan><tspan fill="{p.fg}">; </tspan><tspan fill="{p.cmt}"># +{stars_last_year:,} in the last 12 months · updated daily</tspan></text>

    <text x="26" y="232" fill="{p.muted}">8</text>
    <text x="52" y="232" fill="{p.fg}">}}</text>
  </g>
</svg>
"""


def render_adaptive_mesh_heroes(
    total_stars: int,
    total_blog_posts: int,
    light_path: str = "hero_light.svg",
    dark_path: str = "hero_dark.svg",
) -> None:
    with open(light_path, "w") as f:
        f.write(_adaptive_mesh_svg(LIGHT, total_stars, total_blog_posts))
    with open(dark_path, "w") as f:
        f.write(_adaptive_mesh_svg(DARK, total_stars, total_blog_posts))


def render_bas_nix_heroes(
    total_stars: int,
    stars_last_year: int,
    light_path: str = "hero_light.svg",
    dark_path: str = "hero_dark.svg",
) -> None:
    with open(light_path, "w") as f:
        f.write(_bas_nix_svg(LIGHT, total_stars, stars_last_year))
    with open(dark_path, "w") as f:
        f.write(_bas_nix_svg(DARK, total_stars, stars_last_year))
