def check_orientation(g=None):
    """Check the current orientation of the player cluster.
    
    Returns 'horizontal' if the cluster is wider than it is tall, 'vertical' otherwise.
    """
    g = grid() if g is None else np.asarray(g)
    teal = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]
    mar = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 9]
    cells = teal + mar
    if not cells:
        return None
    
    rows = [r for r, c in cells]
    cols = [c for r, c in cells]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    
    height = max_r - min_r + 1
    width = max_c - min_c + 1
    
    return 'horizontal' if width > height else 'vertical'
