def player_detector(g=None):
    """Rank which object is most likely the agent-controlled sprite.

    Heuristic: a small (<=16 cells) component whose colour occurs exactly once
    on the grid; falls back to the smallest components. Returns up to 3 objects
    (same fields as objects()), most likely first, each with "unique_colour".
    """
    objs = objects(g)
    if not objs:
        return []
    by_colour = {}
    for o in objs:
        by_colour.setdefault(o["colour"], []).append(o)
    cands = [os_[0] for os_ in by_colour.values() if len(os_) == 1 and os_[0]["size"] <= 16]
    if not cands:
        cands = sorted(objs, key=lambda o: o["size"])[:3]
    cands = sorted(cands, key=lambda o: o["size"])[:3]
    out = []
    for o in cands:
        item = dict(o)
        item["unique_colour"] = len(by_colour[o["colour"]]) == 1
        out.append(item)
    return out
