"""Draws the architecture diagram with technology logos and renders it as a PNG with a white background.

    uv run python docs/fuente/diagrama_logos.py   ->  docs/diagramas/arquitectura-logos.png

Logos: Simple Icons (CC0), https://simpleicons.org, in each brand's own color.
"""

import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
OUTPUT = HERE.parent / "diagramas" / "arquitectura-logos.png"
WIDTH, HEIGHT = 1240, 740

BRAND = {  # Simple Icons hex colors
    "python": "#3776AB",
    "fastapi": "#009688",
    "opencv": "#5C3EE8",
    "pytorch": "#EE4C2C",
    "ultralytics": "#111F68",
    "claude": "#D97757",
    "cloudflare": "#F38020",
    "googlegemini": "#8E75B2",
    "nvidia": "#76B900",
    "docker": "#2496ED",
    "ubuntu": "#E95420",
}
INK, MUTED, LINE, ACCENT, PRIVACY, DETECT = "#17212b", "#5a6774", "#c3ccd5", "#2455d4", "#a86200", "#1d8a50"


def logo(slug: str, x: float, y: float, size: float = 30) -> str:
    path = re.search(r' d="([^"]+)"', (HERE / "logos" / f"{slug}.svg").read_text()).group(1)
    return (
        f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 24 24">'
        f'<path fill="{BRAND[slug]}" d="{path}"/></svg>'
    )


def generic_icon(kind: str, cx: float, y: float) -> str:
    """Brand-free drawings for the room's devices."""
    s = f'fill="none" stroke="{MUTED}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "camera":
        return (
            f'<rect x="{cx - 15}" y="{y + 7}" width="30" height="20" rx="4" {s}/>'
            f'<circle cx="{cx}" cy="{y + 17}" r="6" {s}/><path d="M{cx - 6} {y + 7} l3 -4 h6 l3 4" {s}/>'
        )
    if kind == "screen":
        return (
            f'<rect x="{cx - 17}" y="{y + 3}" width="34" height="22" rx="3" {s}/>'
            f'<path d="M{cx} {y + 25} v5 M{cx - 8} {y + 30} h16" {s}/>'
        )
    return (  # phone
        f'<rect x="{cx - 10}" y="{y + 1}" width="20" height="30" rx="4" {s}/><path d="M{cx - 3} {y + 26} h6" {s}/>'
    )


def node(x, y, w, h, title, sub, logos=(), icon=None, stroke=LINE, width=1.5, dashed=False, mono_sub=False):
    cx = x + w / 2
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#ffffff" stroke="{stroke}" '
        f'stroke-width="{width}"{' stroke-dasharray="6 4"' if dashed else ""}/>'
    ]
    size, gap = 30, 10
    if logos:
        total = len(logos) * size + (len(logos) - 1) * gap
        for i, slug in enumerate(logos):
            parts.append(logo(slug, cx - total / 2 + i * (size + gap), y + 12, size))
    if icon:
        parts.append(generic_icon(icon, cx, y + 10))
    parts.append(f'<text x="{cx}" y="{y + 64}" text-anchor="middle" class="t">{title}</text>')
    for i, line in enumerate(sub if isinstance(sub, list | tuple) else [sub]):
        parts.append(
            f'<text x="{cx}" y="{y + 82 + i * 17}" text-anchor="middle" class="{"m" if mono_sub else "s"}">{line}</text>'
        )
    return "\n".join(parts)


def arrow(x1, y1, x2, y2, color=INK, both=False, dash=False):
    marker = "ai" if color == ACCENT else "ink"
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{2 if color == ACCENT else 1.7}"'
        f'{' stroke-dasharray="6 4"' if dash else ""} marker-end="url(#{marker})"'
        f"{f' marker-start="url(#{marker})"' if both else ''}/>"
    )


def label(x, y, text, anchor="middle", color=MUTED, weight=400):
    # style, not the fill attribute: the page's CSS for <text> would win over an attribute
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="al" style="fill:{color};font-weight:{weight}">{text}</text>'


def diagram(
    app_label: str = "APLICACIÓN",
    app_logos: tuple[str, ...] = (),
    counting: str = "HILO DE CONTEO · ~10 FRAMES POR SEGUNDO",
    yolo: tuple[str, str, list[str]] = ("YOLO26n", "Detecta personas", ["ultralytics", "pytorch"]),
    extra: tuple[str, ...] = (),
) -> str:
    """The demo's architecture. The arguments are what changes when it runs on other hardware."""
    body = []
    # Zones
    body += [
        f'<rect x="16" y="16" width="220" height="660" rx="16" fill="none" stroke="{LINE}" stroke-width="1.5"/>',
        '<text x="36" y="46" class="zl">HARDWARE</text>',
        f'<rect x="256" y="16" width="680" height="660" rx="16" fill="none" stroke="{PRIVACY}" stroke-width="2" stroke-dasharray="8 6"/>',
        f'<text x="276" y="46" class="zl">{app_label}</text>',
        *(logo(slug, 864 + i * 28 - 28 * (len(app_logos) - 2), 32, 24) for i, slug in enumerate(app_logos)),
        f'<rect x="956" y="16" width="268" height="660" rx="16" fill="none" stroke="{LINE}" stroke-width="1.5"/>',
        '<text x="976" y="46" class="zl">CLOUD</text>',
    ]
    # The room
    body += [
        node(36, 90, 180, 92, "Cámara C920", "USB · 1080p", icon="camera"),
        node(36, 330, 180, 92, "Proyector", "Video en vivo · solo local", icon="screen"),
        node(36, 560, 180, 92, "Celulares", "QR → página /m", icon="phone"),
    ]
    # Counting thread
    body.append(f'<text x="276" y="70" class="cap">{counting}</text>')
    xs = [276, 442, 608, 774]
    body += [
        node(xs[0], 90, 142, 92, "Lector", "Frame más nuevo", logos=["opencv"]),
        node(xs[1], 90, 142, 92, yolo[0], yolo[1], logos=yolo[2], stroke=DETECT, width=2),
        node(xs[2], 90, 142, 92, "Contador", "Mediana de 15 frames", logos=["python"]),
        node(xs[3], 90, 142, 92, "Último frame", "JPEG + imagen limpia", logos=["opencv"]),
    ]
    body += [arrow(216, 136, 276, 136)] + [arrow(xs[i] + 142, 136, xs[i + 1], 136) for i in range(3)]
    # Web server
    body += [
        arrow(805, 182, 805, 238),
        label(797, 214, "Frame + conteo", anchor="end"),
        f'<rect x="276" y="238" width="560" height="218" rx="12" fill="none" stroke="{LINE}" stroke-width="1.5"/>',
        logo("fastapi", 292, 250, 26),
        logo("python", 324, 250, 26),
        '<text x="360" y="269" class="t">Servidor web · FastAPI</text>',
        f'<rect x="292" y="292" width="256" height="58" rx="8" fill="#ffffff" stroke="{LINE}" stroke-width="1.5"/>',
        '<text x="420" y="316" text-anchor="middle" class="t">Lista de eventos</text>',
        '<text x="420" y="336" text-anchor="middle" class="s">Decisiones · preguntas · análisis</text>',
        f'<rect x="572" y="292" width="248" height="58" rx="8" fill="#ffffff" stroke="{LINE}" stroke-width="1.5"/>',
        '<text x="696" y="316" text-anchor="middle" class="t">Monitor de aforo</text>',
        '<text x="696" y="336" text-anchor="middle" class="s">Cada 0.5 s · ¿se rebasó el aforo?</text>',
        arrow(572, 321, 548, 321),
    ]
    chips = [
        ["/video · solo local", "/api/occupancy", "/api/feed?rol="],
        ["/api/analyze · local", "/api/ask · con límite", "/api/capacity · local"],
    ]
    for row, y in zip(chips, (366, 408), strict=True):
        for text, x in zip(row, (292, 471, 650), strict=True):
            body += [
                f'<rect x="{x}" y="{y}" width="170" height="32" rx="6" fill="#f4f6f8" stroke="{LINE}"/>',
                f'<text x="{x + 85}" y="{y + 20}" text-anchor="middle" class="m">{text}</text>',
            ]
    body.append(arrow(276, 376, 216, 376))
    # AI
    body += [
        arrow(836, 322, 976, 322, color=ACCENT),
        label(886, 312, "1 imagen", color=ACCENT, weight=600),
        arrow(976, 356, 836, 356, color=ACCENT, dash=True),
        label(886, 374, "Texto", color=ACCENT, weight=600),
        node(
            976,
            276,
            228,
            112,
            "Claude API",
            ["Opus 5 · visión", "~5–9 s · ~2 centavos"],
            logos=["claude"],
            stroke=ACCENT,
            width=2,
        ),
        node(976, 404, 228, 92, "Gemini · respaldo", "--ai gemini", logos=["googlegemini"], dashed=True, mono_sub=True),
    ]
    # Tunnel
    body += [
        arrow(380, 456, 380, 540, both=True),
        label(390, 502, "HTTP local", anchor="start"),
        node(276, 540, 200, 92, "cloudflared", "Túnel de salida", logos=["cloudflare"]),
        arrow(476, 586, 976, 586, both=True),
        node(976, 540, 228, 92, "Cloudflare", "URL pública https + QR", logos=["cloudflare"]),
        f'<polyline points="1090,632 1090,712 126,712 126,652" fill="none" stroke="{INK}" stroke-width="1.7" '
        'marker-end="url(#ink)" marker-start="url(#ink)"/>',
        label(608, 704, "HTTPS · conteo, avisos y preguntas, nunca el video"),
        '<text x="596" y="660" text-anchor="middle" class="priv">El video no sale de este entorno: a la nube solo va 1 imagen por pregunta o evento</text>',
    ]
    body += extra
    return "\n".join(body)


def page(body: str) -> str:
    marker = (
        '<marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
  body {{ margin: 0; padding: 24px; background: #ffffff; }}
  svg.d {{ width: {WIDTH}px; height: {HEIGHT}px; display: block; }}
  text {{ font-family: "IBM Plex Sans", "Segoe UI", sans-serif; fill: {INK}; }}
  .t {{ font-size: 14px; font-weight: 600; }}
  .s {{ font-size: 12px; fill: {MUTED}; }}
  .m {{ font-family: "IBM Plex Mono", monospace; font-size: 12px; }}
  .al {{ font-size: 12px; }}
  .zl {{ font-family: "IBM Plex Mono", monospace; font-size: 12px; letter-spacing: 0.08em; fill: {MUTED}; }}
  .cap {{ font-family: "IBM Plex Mono", monospace; font-size: 11px; letter-spacing: 0.06em; fill: {MUTED}; }}
  .priv {{ font-size: 13px; font-weight: 600; fill: {PRIVACY}; }}
</style></head><body>
<svg class="d" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">
<defs>{marker.format(id="ink", color=INK)}{marker.format(id="ai", color=ACCENT)}</defs>
{body}
</svg></body></html>"""


def render(body: str, output: Path) -> None:
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "diagrama.html"
        source.write_text(page(body))
        subprocess.run(
            [
                "google-chrome",
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--user-data-dir={tmp}/chrome",
                "--force-device-scale-factor=2",
                f"--window-size={WIDTH + 48},{HEIGHT + 48}",
                "--virtual-time-budget=5000",
                f"--screenshot={output.resolve()}",
                source.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=90,
        )
    print(output)


def main() -> None:
    render(diagram(), OUTPUT)


if __name__ == "__main__":
    main()
