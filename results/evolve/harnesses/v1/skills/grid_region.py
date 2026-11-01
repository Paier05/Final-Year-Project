def grid_region(row0, col0, row1, col1, g=None):
    """Raw colour indices of a rectangle, as text (one hex digit per cell).

    Use it to zoom in when objects() is too coarse. At most 1024 cells.
    """
    g = grid() if g is None else np.asarray(g)
    h, w = g.shape
    r0, c0 = max(0, int(row0)), max(0, int(col0))
    r1, c1 = min(h - 1, int(row1)), min(w - 1, int(col1))
    if r1 < r0 or c1 < c0:
        return "empty range (need row0<=row1 and col0<=col1)"
    if (r1 - r0 + 1) * (c1 - c0 + 1) > 1024:
        return "region too large; ask for at most 1024 cells"
    lines = ["     " + "".join(str(c % 10) for c in range(c0, c1 + 1))]
    for r in range(r0, r1 + 1):
        lines.append(f"r{r:>3} " + "".join(format(int(v), "x") for v in g[r, c0:c1 + 1]))
    return "\n".join(lines)
