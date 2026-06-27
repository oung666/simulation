# simulation

`simulation` is a lightweight pure-Qt prototype. It does not use
`QWebEngineView`, Vite, Node.js, or any frontend map renderer.

The first version focuses on:

- offline map layer data from `data/layers/offline_map.json`
- optional local raster tiles from `map_assets/taiwan_fujian/tiles`
- deterministic WGS84 longitude/latitude coordinates
- Qt `QPainter` rendering
- mouse pan, wheel zoom, and live lon/lat display
- simple red/blue units moving along JSON-defined routes

Run:

```powershell
D:\software\Anaconda\envs\python3.11\python.exe simulation\main.py
```

This version intentionally keeps the map data simple. The map file can later be
replaced by a higher-detail generated JSON or a tile-backed renderer without
bringing the frontend stack back.

Download offline tiles:

```powershell
D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\download_tiles.py --zoom-min 6 --zoom-max 10 --workers 8
```

Use a higher `--zoom-max` only for a smaller region. Street-level tiles for the
full Taiwan-Fujian range are large.

