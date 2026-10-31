"""Making overlay readings trustworthy before anything is worked out from them.

The overlay is small text read off the screen, so now and then one reading comes out wrong: a restart counter of 0
reads as 10 or 435, packet loss of 0.0 reads as 9.0, a stray hitch count of 519. In real data every one of these is a
single reading with normal ones either side. So a value only counts once it repeats (settle), and everything is worked
out from the current stint on one server (current_run): a server hop, relog or long gap starts a fresh one, so one
server's numbers are never mixed with the next.
"""

from collections import Counter

GAP_S = 600          # more than 10 minutes between readings: a new stint
IDENTITY_N = 5       # readings used to decide which shard and server you're on now


def most_common(vals):
    vals = [v for v in vals if v not in (None, "")]
    if not vals:
        return None
    c = Counter(vals)
    best = max(c.values())
    # On a tie, the most recent value wins
    for v in reversed(vals):
        if c[v] == best:
            return v


def identity(snaps):
    """(shard, server) you're on now, from the latest few readings, so one misread name can't move you."""
    last = [s for s in snaps if s.get("ok")][-IDENTITY_N:]
    return most_common([s.get("shard_id") for s in last]), most_common([s.get("server_name") for s in last])


def current_run(snaps, now=None, window_s=None):
    """The readings from your current stint: same shard, same server (a blank server name doesn't break it), no gap
    over 10 minutes, newest last. window_s keeps only the last so many seconds of it."""
    ok = [s for s in snaps if s.get("ok")]
    if not ok:
        return []
    shard, server = identity(ok)
    run = []
    prev_ts = None
    for s in reversed(ok):
        if prev_ts is not None and prev_ts - s["ts"] > GAP_S:
            break
        if shard and s.get("shard_id") and s["shard_id"] != shard:
            break
        if server and s.get("server_name") and s["server_name"] != server:
            break
        run.append(s)
        prev_ts = s["ts"]
    run.reverse()
    if window_s is not None:
        end = now if now is not None else run[-1]["ts"]
        run = [s for s in run if end - s["ts"] <= window_s]
    return run


def settle(values, k=2):
    """Each reading's value, but a new value only replaces the old one once it has shown up k times in a row
    (blanks don't count either way). Single misreads simply disappear."""
    out, current, cand, n = [], None, None, 0
    for v in values:
        if v is None:
            out.append(current)
            continue
        if current is None:
            # The very first value is taken once confirmed too, so a misread first reading can't become the baseline
            if v == cand:
                n += 1
            else:
                cand, n = v, 1
            if n >= k:
                current = v
            out.append(current)
            continue
        if v == current:
            cand, n = None, 0
        elif v == cand:
            n += 1
            if n >= k:
                current, cand, n = v, None, 0
        else:
            cand, n = v, 1
        out.append(current)
    return out


def restart_rises(values, k=5):
    """How many times the server's restart counter genuinely went up. The new count has to hold for k readings (about
    25 seconds), be one or two higher, and never drop back: a real counter only ever goes up, so falling back to the
    old number means it was misread (seen in real data: 9, 9, 9, 19, 10, 10, 10, then 0 again). A bigger jump is a
    misread or a different server, so it resets the baseline instead."""
    settled = [v for v in settle(values, k) if v is not None]
    rises, base = 0, None
    for i, v in enumerate(settled):
        if base is None:
            base = v
            continue
        if v > base:
            if v - base <= 2 and min(settled[i:]) >= v:
                rises += v - base
            base = v
        elif v < base:
            base = v
    return rises


def first_settled(values, k=5):
    for v in settle(values, k):
        if v is not None:
            return v
    return None


def pct(values, p):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]
