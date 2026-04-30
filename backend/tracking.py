"""Tracking-mode analytics.

Given the raw stream of TrackingSamples for a session — each sample is a
single marker's normalized (x, y) position at a given timestamp — compute:

- Per-pair contact time (how long markers A and B were within the configured
  proximity threshold of each other).
- Per-person total social time (sum of pair contact times the person was in).
- Pairs of people who never met during the session.

The clustering at each snapshot is done via union-find on a proximity graph,
so a cluster of N people contributes C(N, 2) pair-co-presence events at that
timestamp — i.e. all three of (A, B, C) standing together count A-B, A-C,
B-C as having met. Co-presence is counted once per snapshot, multiplied by
sample_interval_ms to convert to seconds.

Sample intervals are chosen to be on the order of "talking distance, every
half-second" — enough to catch real interactions without flooding the DB.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .db import Marker, TrackingSample, TrackingSession


# ----- union-find (DSU) -----

def _make_dsu(items):
    parent = {x: x for x in items}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return find, union


# ----- core analysis -----

@dataclass
class _Snapshot:
    t: datetime
    positions: list[tuple[int, float, float]]  # (marker_id, x, y)


def _group_samples(rows: Iterable[TrackingSample]) -> list[_Snapshot]:
    """Group raw samples by their timestamp into per-frame snapshots.

    Two samples written within ~0 ms can have slightly different timestamps
    if they came from different DB writes; we don't try to coalesce them.
    """
    by_t: dict[datetime, list[tuple[int, float, float]]] = defaultdict(list)
    for r in rows:
        by_t[r.t].append((r.marker_aruco_id, r.x_norm, r.y_norm))
    return [_Snapshot(t=t, positions=p) for t, p in sorted(by_t.items())]


def _pairs_in_clusters(snap: _Snapshot, threshold_sq: float) -> set[tuple[int, int]]:
    """Return all (min, max) pairs that landed in the same cluster at this snapshot."""
    if len(snap.positions) < 2:
        return set()
    ids = [p[0] for p in snap.positions]
    find, union = _make_dsu(ids)
    for i in range(len(snap.positions)):
        mi, xi, yi = snap.positions[i]
        for j in range(i + 1, len(snap.positions)):
            mj, xj, yj = snap.positions[j]
            dx = xi - xj
            dy = yi - yj
            if dx * dx + dy * dy <= threshold_sq:
                union(mi, mj)
    by_root: dict[int, list[int]] = defaultdict(list)
    for mid in ids:
        by_root[find(mid)].append(mid)
    pairs: set[tuple[int, int]] = set()
    for cluster in by_root.values():
        if len(cluster) < 2:
            continue
        cs = sorted(cluster)
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                pairs.add((cs[i], cs[j]))
    return pairs


def compute_report(db: Session, session: TrackingSession) -> dict:
    rows = db.execute(
        select(TrackingSample)
        .where(TrackingSample.session_id == session.id)
        .order_by(TrackingSample.t.asc(), TrackingSample.id.asc())
    ).scalars().all()

    snaps = _group_samples(rows)
    threshold_sq = session.proximity_norm ** 2
    interval_s = session.sample_interval_ms / 1000.0

    pair_count: dict[tuple[int, int], int] = defaultdict(int)
    seen_markers: set[int] = set()

    for s in snaps:
        for mid, _, _ in s.positions:
            seen_markers.add(mid)
        for pair in _pairs_in_clusters(s, threshold_sq):
            pair_count[pair] += 1

    # Resolve marker → person names in one trip.
    people_by_aruco: dict[int, str] = {}
    if seen_markers:
        marker_rows = db.execute(
            select(Marker).options(joinedload(Marker.person)).where(
                Marker.aruco_id.in_(list(seen_markers))
            )
        ).scalars().all()
        for m in marker_rows:
            if m.person:
                people_by_aruco[m.aruco_id] = m.person.name

    # Pair contact time (sorted by descending duration).
    pair_contact_seconds = []
    met_pairs: set[tuple[int, int]] = set()
    for (a, b), n in sorted(pair_count.items(), key=lambda kv: -kv[1]):
        met_pairs.add((a, b))
        pair_contact_seconds.append({
            "a": a, "a_name": people_by_aruco.get(a),
            "b": b, "b_name": people_by_aruco.get(b),
            "seconds": round(n * interval_s, 2),
            "snapshots": n,
        })

    # All possible pairs from markers that appeared in this session.
    seen_sorted = sorted(seen_markers)
    all_pairs: set[tuple[int, int]] = set()
    for i in range(len(seen_sorted)):
        for j in range(i + 1, len(seen_sorted)):
            all_pairs.add((seen_sorted[i], seen_sorted[j]))
    never_met_pairs_raw = sorted(all_pairs - met_pairs)
    never_met_pairs = [
        {
            "a": a, "a_name": people_by_aruco.get(a),
            "b": b, "b_name": people_by_aruco.get(b),
        }
        for (a, b) in never_met_pairs_raw
    ]

    # Per-person total contact seconds (each pair contact counts twice — once
    # per participant — since both people experience the social time).
    per_person_seconds: dict[int, float] = {m: 0.0 for m in seen_markers}
    for pc in pair_contact_seconds:
        per_person_seconds[pc["a"]] += pc["seconds"]
        per_person_seconds[pc["b"]] += pc["seconds"]
    per_person_contact_seconds = sorted(
        [
            {
                "aruco_id": mid,
                "person_name": people_by_aruco.get(mid),
                "seconds": round(secs, 2),
            }
            for mid, secs in per_person_seconds.items()
        ],
        key=lambda r: -r["seconds"],
    )

    end = session.stopped_at or datetime.utcnow()
    duration_s = max(0.0, (end - session.started_at).total_seconds())

    return {
        "duration_s": round(duration_s, 2),
        "sample_count": len(rows),
        "snapshot_count": len(snaps),
        "markers_seen": seen_sorted,
        "pair_contact_seconds": pair_contact_seconds,
        "never_met_pairs": never_met_pairs,
        "per_person_contact_seconds": per_person_contact_seconds,
    }
