"""The same demo running on an NVIDIA Jetson Orin instead of the laptop, with what changes marked.

    uv run python docs/fuente/diagrama_jetson.py   ->  docs/diagramas/arquitectura-jetson.png

It reuses the laptop diagram, so both images line up side by side on a slide.
"""

from diagrama_logos import HERE, diagram, render

OUTPUT = HERE.parent / "diagramas" / "arquitectura-jetson.png"
CHANGE = "#7c3aed"  # tag for what differs from the laptop version


def badge(right: float, y: float, text: str = "CAMBIA") -> str:
    """A tag centered on height y, ending at x = right (e.g. on the top border of a box)."""
    width = 8 + len(text) * 7.4
    return (
        f'<rect x="{right - width - 10}" y="{y - 9}" width="{width}" height="18" rx="9" fill="#f3edff" stroke="{CHANGE}"/>'
        f'<text x="{right - width / 2 - 10}" y="{y + 4}" text-anchor="middle" class="badge">{text}</text>'
    )


if __name__ == "__main__":
    body = diagram(
        app_label="APLICACIÓN · NVIDIA JETSON ORIN",
        app_logos=("nvidia", "ubuntu"),
        counting="HILO DE CONTEO · ~30 FRAMES POR SEGUNDO (ESTIMADO)",
        yolo=("YOLO26n · TensorRT", "En la GPU · FP16", ["ultralytics", "nvidia"]),
        extra=(
            '<style>.badge { font-family: "IBM Plex Mono", monospace; font-size: 10.5px; font-weight: 600;'
            f" letter-spacing: 0.06em; fill: {CHANGE}; }}</style>",
            badge(620, 42),  # next to the Jetson zone title
            badge(584, 90),  # on the YOLO box
            badge(1040, 96),
            '<text x="976" y="128" class="s">Distinto a la versión de la laptop</text>',
        ),
    )
    render(body, OUTPUT)
