"""离线瓦片读取控制。

这个类只负责从本地瓦片目录按 z/x/y 读取 png，并做简单缓存。
地图如何绘制瓦片仍然在 ui/map_canvas.py 中完成。
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtGui import QPixmap


class TileStore:
    """离线瓦片仓库：管理本地瓦片读取、缓存和可用 zoom 查询。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[tuple[int, int, int], QPixmap | None] = {}
        self._available_zooms: list[int] | None = None

    def get_tile(self, zoom: int, x: int, y: int) -> QPixmap | None:
        """读取一张 z/x/y 瓦片；不存在或损坏时返回 None。"""
        key = (zoom, x, y)
        if key in self._cache:
            return self._cache[key]
        path = self.root / str(zoom) / str(x) / f"{y}.png"
        if not path.exists():
            self._cache[key] = None
            return None
        pixmap = QPixmap(str(path))
        self._cache[key] = pixmap if not pixmap.isNull() else None
        return self._cache[key]

    def has_any_tiles(self) -> bool:
        """判断瓦片目录里是否至少有一张 png。"""
        return self.root.exists() and any(self.root.rglob("*.png"))

    def available_zooms(self) -> list[int]:
        """扫描瓦片目录，返回已经下载好的 zoom 层级。"""
        if self._available_zooms is not None:
            return self._available_zooms
        if not self.root.exists():
            self._available_zooms = []
            return self._available_zooms
        zooms: list[int] = []
        for child in self.root.iterdir():
            if child.is_dir() and child.name.isdigit():
                zooms.append(int(child.name))
        self._available_zooms = sorted(zooms)
        return self._available_zooms

    def best_zoom_for(self, requested_zoom: float) -> int | None:
        """根据当前地图 zoom，选择最合适的本地瓦片 zoom。"""
        zooms = self.available_zooms()
        if not zooms:
            return None
        requested = int(round(requested_zoom))
        lower_or_equal = [zoom for zoom in zooms if zoom <= requested]
        if lower_or_equal:
            return lower_or_equal[-1]
        return zooms[0]
