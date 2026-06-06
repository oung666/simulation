from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


def lon_to_tile_x(lon: float, zoom: int) -> int:
    return int((lon + 180.0) / 360.0 * (2**zoom))


def lat_to_tile_y(lat: float, zoom: int) -> int:
    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))
    return int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * (2**zoom))


def iter_tiles(bounds: list[float], zoom_min: int, zoom_max: int):
    west, south, east, north = bounds
    for zoom in range(zoom_min, zoom_max + 1):
        min_x = lon_to_tile_x(west, zoom)
        max_x = lon_to_tile_x(east, zoom)
        min_y = lat_to_tile_y(north, zoom)
        max_y = lat_to_tile_y(south, zoom)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                yield zoom, x, y


def download_one(url_template: str, output_root: Path, tile: tuple[int, int, int], retries: int, delay: float) -> str:
    zoom, x, y = tile
    output_path = output_root / str(zoom) / str(x) / f"{y}.png"
    if output_path.exists() and output_path.stat().st_size > 0:
        return "skipped"

    url = url_template.format(z=zoom, x=x, y=y)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt in range(retries + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "qt_frontend_v6_offline_tile_prepare/0.1",
                    "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
                },
            )
            with urlopen(request, timeout=30) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                body = response.read()
                if "image" not in content_type or body.lstrip().startswith(b"<"):
                    raise RuntimeError(f"non-image response: {content_type or 'unknown'}")
                output_path.write_bytes(body)
            return "downloaded"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < retries:
                time.sleep(delay)
    return f"failed: {last_error}"


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    default_map = root / "data" / "layers" / "offline_map.json"
    return argparse.ArgumentParser(description="Download offline XYZ raster tiles for qt_frontend_v6.").parse_args()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download offline XYZ raster tiles for qt_frontend_v6.")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--map", type=Path, default=root / "data" / "layers" / "offline_map.json")
    parser.add_argument("--zoom-min", type=int, default=6)
    parser.add_argument("--zoom-max", type=int, default=10)
    parser.add_argument(
        "--bounds",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Override map bounds with WGS84 lon/lat values.",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=0.8)
    args = parser.parse_args()

    payload = json.loads(args.map.read_text(encoding="utf-8"))
    bounds = args.bounds if args.bounds is not None else payload["bounds"]
    url_template = payload["tile_source"]
    output_root = (args.map.parent / payload.get("tile_root", "tiles")).resolve()
    tiles = list(iter_tiles(bounds, args.zoom_min, args.zoom_max))

    downloaded = 0
    skipped = 0
    failed = 0
    print(f"tiles={len(tiles)} zoom={args.zoom_min}-{args.zoom_max} output={output_root}")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(download_one, url_template, output_root, tile, args.retries, args.retry_delay)
            for tile in tiles
        ]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result == "downloaded":
                downloaded += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1
            if index % 50 == 0 or index == len(futures):
                print(f"[{index}/{len(futures)}] downloaded={downloaded} skipped={skipped} failed={failed}")

    print(f"done downloaded={downloaded} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
