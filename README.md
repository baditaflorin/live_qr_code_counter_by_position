# Live ArUco zone counter

Counts how many people are in each zone of a camera view in real time, by detecting ArUco markers (worn on heads / hats / lanyards). Comes with an admin panel for creating people, generating printable marker sheets, drawing zones, and recording snapshots per question.

## Why ArUco and not QR

QR codes carry arbitrary text but are fragile at distance and angle. ArUco markers are fiducial markers designed for exactly this use case: small black-and-white squares that are detected reliably from far away, in real time, even with dozens in frame. Each marker carries a small integer ID (0..99 by default) that we link to a person in the database.

## Architecture

```
┌──────────────┐      WebSocket (JPEG bytes)       ┌──────────────────────┐
│  Browser     │  ──────────────────────────────▶  │  FastAPI in Docker   │
│  (webcam)    │  ◀─── JSON: detections + zones ── │  OpenCV ArUco        │
│  draws over- │                                   │  SQLite + PDF gen    │
│  lay locally │                                   └──────────────────────┘
└──────────────┘
```

Docker on macOS can't access the host webcam directly, so the **browser** captures the camera and streams JPEG frames over WebSocket to the dockerized backend. Backend runs OpenCV's ArUco detector and returns per-frame detections + zone assignments.

## Quick start

```bash
docker compose up --build
```

Then open:
- http://localhost:8000/        — Live view (counter)
- http://localhost:8000/admin   — Admin panel (people, markers, zones, questions)

The first time you click **Start**, your browser will ask for camera permission.

Data persists in `./data/app.db` on the host.

## Workflow

1. **Admin → People**: add a person, choose how many markers to assign (default 1). The system generates fresh marker IDs for them.
2. **Admin → Markers**: download a printable PDF (3×3 markers per A4 page, ID + name underneath). Print, cut, hand them out.
3. **Admin → Zones**: open the camera, optionally take a still snapshot, click points on the video to draw a polygon. Name it (e.g. `left-area`), give it a display label (e.g. `Yes`), pick a color, save. Add as many zones as you like.
4. **Admin → Questions** (optional): create a question text. Mark it active.
5. **Live view**: pick the same camera and resolution, hit **Start**. You'll see live overlay with marker boxes, zone outlines, and per-zone counts.
6. To record an answer per person for the current question, hit **Record snapshot**. View results in **Admin → Questions → Results**.

## Marker dictionary

Defaults to `DICT_4X4_100` (100 unique IDs, easy to detect at distance because the inner pattern is only 4×4 cells). Change via `ARUCO_DICTIONARY` env var in `docker-compose.yml`. Larger dictionaries (e.g. `DICT_5X5_100`, `DICT_4X4_250`) give more IDs at the cost of slightly harder detection.

If you switch dictionaries after creating markers, regenerate the printable PDF — old prints won't match the new dictionary.

## Tips for King's Hall (overhead camera)

- **Marker size**: rule of thumb, the marker on print needs to be ≥1/40th of camera frame height. From the 2nd floor, that's typically A5-sized markers (≈15×15 cm) for a 1080p camera.
- **Lighting**: avoid harsh single-point lighting that creates sharp shadows. Diffuse light is best.
- **Mounting**: stiff backing (cardboard) keeps the marker flat. Curling kills detection.
- **Resolution vs. FPS**: bumping to 1920×1080 helps with small/distant markers but raises CPU. Start at 1280×720 / 10 fps.
- **Quiet zone**: the printable PDF already pads each marker with a white border — don't crop into it.

## API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/system` | dictionary in use |
| `GET/POST/PUT/DELETE` | `/api/people` | manage people |
| `GET` | `/api/markers` | list markers |
| `POST` | `/api/markers/batch` | `{count, person_id?}` create markers |
| `PUT` | `/api/markers/{id}/assign` | assign/unassign |
| `DELETE` | `/api/markers/{id}` | delete |
| `GET` | `/api/markers/{id}/image` | PNG |
| `GET` | `/api/markers/pdf?ids=1,2,3` | printable PDF |
| `GET/POST/PUT/DELETE` | `/api/zones` | polygons in normalized 0..1 coords |
| `GET/POST/PUT/DELETE` | `/api/questions` | questions |
| `POST` | `/api/questions/{id}/snapshot/record` | record one snapshot |
| `GET` | `/api/questions/{id}/summary` | latest breakdown + history |
| `WS`  | `/ws/detect` | binary JPEG in, JSON detections out |

## Without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=./data uvicorn backend.main:app --reload
```

## Notes

- **Detection runs server-side, not in the browser.** This keeps detection consistent and works even if you ever swap the browser for a thin client. Bandwidth is fine on localhost (≈300–500 KB/s at 10 fps, 1280×720 JPEG).
- **Camera access stays in the browser** because Docker on macOS cannot reach the host webcam. If you ever deploy this to a Linux box with a directly-attached camera, you can add a parallel mode that captures via OpenCV inside the container.
- **Apple Silicon Metal**: not used currently. ArUco detection is CPU-bound on a small frame and well under 5 ms per frame on M-series — no need for GPU acceleration. If you need >50 fps with many markers, switching to Apple Vision via `pyobjc` (outside Docker) is the next step.
