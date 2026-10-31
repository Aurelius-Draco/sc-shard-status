"""Shard health score (0-100) and a plain-English summary from overlay readings.

Thresholds are set from real 4.10 readings, where a healthy server runs at about
20-22 fps. Older patches ran far lower, so the "normal" figure lives in one place
(HEALTHY_SERVER_FPS) and can be tuned as patches change.
"""

import statistics as st
import time

from . import clean

HEALTHY_SERVER_FPS = 20.0

# (value, score) points; scores in between are interpolated
SERVER_FPS_CURVE = [(0, 0), (3, 5), (6, 25), (10, 50), (15, 80), (18, 95), (20, 100)]
PING_CURVE = [(0, 100), (80, 100), (150, 75), (250, 40), (400, 10), (1000, 0)]
LOSS_CURVE = [(0, 100), (0.5, 90), (2, 50), (5, 15), (10, 0)]

BANDS = [(80, "Healthy", "good"), (60, "OK", "ok"), (40, "Struggling", "poor"), (0, "Bad", "bad")]


def _curve(points, x):
    if x is None:
        return None
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _vals(snaps, key):
    return [s[key] for s in snaps if s.get(key) is not None]


def _pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]


def band(score):
    for lo, label, cls in BANDS:
        if score >= lo:
            return label, cls
    return BANDS[-1][1:]


def assess(snaps, now=None, window_s=300):
    """Score the most recent readings. snaps: overlay snapshots, oldest first."""
    now = now or time.time()
    # Only your current stint on this server: a hop or relog starts afresh (see clean.py)
    run = clean.current_run(snaps)
    recent = [s for s in run if now - s["ts"] <= window_s]
    if not recent:
        return {"score": None, "label": "No readings", "cls": "none",
                "summary": "No overlay readings yet. In game, open the console (~) and type r_displayinfo 3.",
                "points": [], "readings": 0}
    last = recent[-1]
    sfps = _vals(recent, "server_fps")
    med_fps = st.median(sfps) if sfps else None
    p10_fps = _pct(sfps, 10)
    # "Low" is the slowest tenth of readings, not the single worst one, which is often a misread
    sfps_low = p10_fps
    ping = st.median(_vals(recent, "ping_ms")) if _vals(recent, "ping_ms") else None
    # Loss and hitches only count once a value repeats; a lone 9.0% or 519 is the overlay being misread
    losses = [v for v in clean.settle([s.get("loss_pct") for s in recent]) if v is not None]
    loss = st.median(losses) if losses else None
    hitch_vals = [v for v in clean.settle([s.get("hitches") for s in recent]) if v is not None]
    hitches = max(hitch_vals) if hitch_vals else 0
    # The overlay's count covers the server node's whole life; only a confirmed rise while you're on it is news
    rs = [s.get("restarts") for s in run]
    restarts = clean.restart_rises(rs)
    restarted_before = (clean.first_settled(rs) or 0) > 0

    server = None
    if med_fps is not None:
        # Mostly the typical rate, with a nudge for dips inside the window
        server = 0.7 * _curve(SERVER_FPS_CURVE, med_fps) + 0.3 * _curve(SERVER_FPS_CURVE, p10_fps)
    net_parts = [v for v in (_curve(PING_CURVE, ping), _curve(LOSS_CURVE, loss)) if v is not None]
    net = min(net_parts) if net_parts else None
    stab = 100 - min(60, hitches * 10) - (50 if restarts else 0)

    parts = [(server, 0.6), (net, 0.3), (max(0, stab), 0.1)]
    have = [(v, w) for v, w in parts if v is not None]
    score = round(sum(v * w for v, w in have) / sum(w for _, w in have)) if have else None
    label, cls = band(score) if score is not None else ("No readings", "none")

    return {
        "score": score, "label": label, "cls": cls, "readings": len(recent), "ts": last["ts"],
        "server_fps": round(med_fps, 1) if med_fps is not None else None,
        "server_fps_low": round(sfps_low, 1) if sfps_low is not None else None,
        "ping_ms": round(ping) if ping is not None else None, "loss_pct": loss,
        "hitches": hitches, "restarts": restarts,
        "pop_shard": last.get("pop_shard"), "pop_srv": last.get("pop_srv"),
        "client_fps": last.get("client_fps"), "shard_id": last.get("shard_id"),
        "server_name": last.get("server_name"), "location": last.get("location"),
        "parts": {"server": _r(server), "network": _r(net), "stability": _r(stab)},
        "summary": summarise(label, med_fps, p10_fps, ping, loss, hitches, restarts, last),
        "points": tips(med_fps, p10_fps, ping, loss, hitches, restarts, last, restarted_before),
    }


def _r(v):
    return round(v) if v is not None else None


def summarise(label, fps, low, ping, loss, hitches, restarts, last):
    bits = []
    pop, srv = last.get("pop_shard"), last.get("pop_srv")
    head = {"Healthy": "Healthy shard.", "OK": "Shard is OK.", "Struggling": "Shard is struggling.",
            "Bad": "Shard is in a bad way."}.get(label, "")
    bits.append(head)
    if pop is not None:
        bits.append(f"{pop} players" + (f", {srv} on your server." if srv is not None else "."))
    if fps is not None:
        s = f"Server running at {fps:.0f} fps"
        s += " with no hitches." if not hitches else f" with {hitches} hitch{'es' if hitches != 1 else ''}."
        bits.append(s)
    if ping is not None:
        bits.append(f"Ping {ping:.0f} ms" + (", no packet loss." if not loss else f", {loss:g}% packet loss."))
    return " ".join(bits)


def tips(fps, low, ping, loss, hitches, restarts, last, restarted_before=False):
    out = []
    if restarts:
        out.append("The server node you're on restarted while you were on it. Expect things to reset or "
                   "go missing nearby; a server hop is worth it.")
    elif restarted_before:
        out.append("The overlay shows this server node has restarted at some point, though not while you've been "
                   "watching. Nothing to do unless things start going missing.")
    if fps is not None and fps < 10:
        out.append("Server fps this low means slow elevators, frozen or laggy AI, rubber-banding and "
                   "missions that don't update. Consider a server hop before starting anything important.")
    elif fps is not None and fps < 15:
        out.append("Server fps is below normal. Expect some lag on elevators, kiosks and AI.")
    elif low is not None and fps is not None and low < fps * 0.6:
        out.append("Server fps is dipping hard at times. Short lag spikes are likely.")
    if ping is not None and ping > 250:
        out.append("High ping. You may be on a server in another region; check the region in the launcher.")
    if loss:
        if loss >= 2:
            out.append("Packet loss this high causes rubber-banding and failed interactions. Check your own "
                       "connection (Wi-Fi, other downloads) before blaming the server.")
    cfps = last.get("client_fps")
    if cfps is not None and cfps < 30 and (fps is None or fps >= 15):
        out.append(f"Your own frame rate is {cfps:.0f} fps while the server is fine, so the slowdown is on "
                   "your PC (settings, background apps, or a busy area).")
    return out


def compare(current_fps, history_fps):
    """How this shard compares with the player's own history for the same build."""
    if current_fps is None or not history_fps:
        return None
    avg = st.median(history_fps)
    if avg <= 0:
        return None
    diff = (current_fps - avg) / avg * 100
    return {"your_median": round(avg, 1), "diff_pct": round(diff)}
