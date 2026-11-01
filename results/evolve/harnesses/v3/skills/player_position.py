def player_position():
    """Find the player's current position (the lime bar at the bottom)."""
    g = grid()
    lime_cells = [(r, c) for r in range(g.shape[0]) for c in range(g.shape[1]) if g[r, c] == 11]
    if not lime_cells:
        return None
    rows = [r for r, c in lime_cells]
    cols = [c for r, c in lime_cells]
    return {"row_min": min(rows), "row_max": max(rows), "col_min": min(cols), "col_max": max(cols), "centroid": [sum(rows)/len(rows), sum(cols)/len(cols)]}
