def collect_items():
    """Find all maroon (9) items and return their positions grouped by proximity."""
    g = grid()
    maroon_cells = [(r, c) for r in range(g.shape[0]) for c in range(g.shape[1]) if g[r, c] == 9]
    if not maroon_cells:
        return []
    # Group cells that are close together (within 3 cells)
    groups = []
    used = set()
    for r, c in maroon_cells:
        if (r, c) in used:
            continue
        group = [(r, c)]
        used.add((r, c))
        for r2, c2 in maroon_cells:
            if (r2, c2) not in used and abs(r - r2) <= 3 and abs(c - c2) <= 3:
                group.append((r2, c2))
                used.add((r2, c2))
        groups.append(group)
    return groups
