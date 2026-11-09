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

UNPLAYABLE_FPS = 5

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


# 9 Nov (Ray: "we're no longer seeing the players on the shard, and On your server often shows -"): a banner or the
# mission tracker across the overlay's Server line hides the player counts on many readings (his session: read on 33%
# of them). They change slowly, so the last good counts on this same server stint stand in for up to HOLD_S, with
# their age, instead of a dash. The game server's number is held the same way.
HOLD_S = 180


def _held(recent, key, now):
    """The newest value of key in this server stint's readings no older than HOLD_S: (value, its reading's time)."""
    for s in reversed(recent):
        if now - s["ts"] > HOLD_S:
            break
        if s.get(key) is not None:
            return s[key], s["ts"]
    return None, None


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
    last = dict(recent[-1])
    pop_ts = None
    for k in ("pop_shard", "pop_srv", "server_name"):
        if last.get(k) is None:
            v, t = _held(recent, k, now)
            if v is not None:
                last[k] = v
                if k != "server_name":
                    pop_ts = min(pop_ts or t, t)
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
    # Unplayable: the last minute's typical server rate under 5 fps. The game can't keep up at that rate, so it
    # shows the alarm the design gives a crash. Needs 3 readings so one misread can't set it off.
    last_min = _vals([s for s in recent if now - s["ts"] <= 60], "server_fps")
    fps_now = st.median(last_min) if len(last_min) >= 3 else None
    unplayable = fps_now is not None and fps_now < UNPLAYABLE_FPS

    return {
        "score": score, "label": label, "cls": cls, "readings": len(recent), "ts": last["ts"],
        "unplayable": unplayable, "server_fps_now": round(fps_now, 1) if fps_now is not None else None,
        "server_fps": round(med_fps, 1) if med_fps is not None else None,
        "server_fps_low": round(sfps_low, 1) if sfps_low is not None else None,
        "ping_ms": round(ping) if ping is not None else None, "loss_pct": loss,
        "hitches": hitches, "restarts": restarts,
        "pop_shard": last.get("pop_shard"), "pop_srv": last.get("pop_srv"),
        # seconds since the player counts were last read, when they're held from an earlier reading (None: read now)
        "pop_age": round(now - pop_ts) if pop_ts is not None else None,
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
    # Since server meshing these numbers are your game server's (one part of the shard), not the whole shard's
    from .overlay import node_of
    node = node_of(last.get("server_name"))
    you = f"Your game server ({node})" if node else "Your game server"
    head = {"Healthy": f"{you} is healthy.", "OK": f"{you} is OK.", "Struggling": f"{you} is struggling.",
            "Bad": f"{you} is in a bad way."}.get(label, "")
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
                   "missions that don't update. Each area of the verse runs on its own game server, so flying to "
                   "another area can help as much as a server hop. Do one or the other before starting anything important.")
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
        mt, gpu = last.get("render_mt_ms"), last.get("render_gpu_ms")
        if mt is not None and gpu is not None and gpu > mt * 1.15:
            out.append(f"Your own frame rate is {cfps:.0f} fps while the server is fine, and your graphics card is "
                       f"the limit (GPU {gpu:.1f} ms a frame, CPU {mt:.1f} ms): lower resolution, upscaling quality or "
                       "shadows to help.")
        elif mt is not None and gpu is not None and mt > gpu * 1.15:
            out.append(f"Your own frame rate is {cfps:.0f} fps while the server is fine, and your CPU is the limit "
                       f"(main thread {mt:.1f} ms a frame, GPU {gpu:.1f} ms): graphics settings won't help much; busy "
                       "areas and background apps cost CPU time.")
        else:
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


SESSION_MIN_READINGS = 5


def session_score(snaps):
    """One score for a whole session (every server it was on), from the same curves as the live score.
    None with too few readings: the app wasn't reading the overlay, which isn't the same as a bad session."""
    snaps = [s for s in snaps if s.get("server_fps") is not None]
    if len(snaps) < SESSION_MIN_READINGS:
        return None
    sfps = _vals(snaps, "server_fps")
    med, p10 = st.median(sfps), _pct(sfps, 10)
    server = 0.7 * _curve(SERVER_FPS_CURVE, med) + 0.3 * _curve(SERVER_FPS_CURVE, p10)
    pings = _vals(snaps, "ping_ms")
    losses = [v for v in clean.settle([s.get("loss_pct") for s in snaps]) if v is not None]
    net_parts = [v for v in (_curve(PING_CURVE, st.median(pings) if pings else None),
                             _curve(LOSS_CURVE, st.median(losses) if losses else None)) if v is not None]
    if net_parts:
        return round(0.6 / 0.9 * server + 0.3 / 0.9 * min(net_parts))
    return round(server)
