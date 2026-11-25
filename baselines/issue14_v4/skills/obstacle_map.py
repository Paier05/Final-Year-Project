def obstacle_map(g=None):
    """Classify each colour as wall-like or item-like from how its cells clump.

    Wall-like = at least 20 cells and on average 8+ cells per component.
    Returns {"colours": {colour: {"cells", "components", "largest", "verdict"}},
             "border": [colours touching the grid border]}.
    """
    g = grid() if g is None else np.asarray(g)
    stats = {}
    for o in objects(g):
        e = stats.setdefault(o["colour"], {"cells": 0, "components": 0, "largest": 0})
        e["cells"] += o["size"]
        e["components"] += 1
        e["largest"] = max(e["largest"], o["size"])
    for e in stats.values():
        ratio = e["cells"] / max(e["components"], 1)
        e["verdict"] = "wall-like" if e["cells"] >= 20 and ratio >= 8 else "item-like"
    border = []
    for colour in stats:
        m = g == colour
        if m[0, :].any() or m[-1, :].any() or m[:, 0].any() or m[:, -1].any():
            border.append(colour)
    return {"colours": stats, "border": sorted(border)}
