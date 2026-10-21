import argparse
from pathlib import Path

from people_counter.adapters.display import OpenCVWindow
from people_counter.adapters.frame_source import find_camera
from people_counter.bootstrap import CountPeople, bootstrap
from people_counter.domain.model import DEFAULT_MIN_CONFIDENCE


def parse_source(value: str) -> int | str:
    """'0' means webcam 0, a name like 'C920' finds that webcam; anything else is a file path or a stream URL."""
    if value.isdigit():
        return int(value)
    if "://" in value or Path(value).exists():
        return value
    camera = find_camera(value)
    if camera is None:
        raise argparse.ArgumentTypeError(f"no video file or webcam called {value!r}")
    return camera


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--source", type=parse_source, default=0, help="webcam index or name (e.g. C920), video file or RTSP URL"
    )
    parser.add_argument("--model", default="yolo26n.pt", help="Ultralytics model weights")
    parser.add_argument("--image-size", type=int, default=960, help="bigger finds people at the back, but is slower")
    parser.add_argument(
        "--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE, help="ignore detections below this"
    )
    parser.add_argument("--window", type=int, default=15, help="frames used to smooth the count")
    return parser


def bootstrap_from(args: argparse.Namespace) -> CountPeople:
    return bootstrap(args.source, args.model, args.image_size, args.min_confidence, args.window)


def main() -> None:
    args = build_parser("Count the people in a room with YOLO.").parse_args()
    count_people = bootstrap_from(args)

    display = OpenCVWindow()
    try:
        occupancy = count_people(display)
    finally:
        display.close()

    if occupancy:
        noun = "person" if occupancy.count == 1 else "people"
        print(f"Last count: {occupancy.count} {noun} (peak: {occupancy.peak})")
