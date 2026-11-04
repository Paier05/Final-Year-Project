def bfs_to_target(from_row, from_col, to_row, to_col, blocked_colours=(), g=None):
    """Shortest 4-connected path length between two cells.

    Cells whose colour is in blocked_colours are impassable. Returns the number
    of single-cell steps, or None if the target is unreachable or blocked.
    """
    g = grid() if g is None else np.asarray(g)
    h, w = g.shape
    blocked = {int(c) for c in blocked_colours}
    start, goal = (int(from_row), int(from_col)), (int(to_row), int(to_col))
    for r, c in (start, goal):
        if not (0 <= r < h and 0 <= c < w):
            return None
    if int(g[goal]) in blocked:
        return None
    queue = collections.deque([start])
    dist = {start: 0}
    while queue:
        cell = queue.popleft()
        if cell == goal:
            return dist[cell]
        r, c = cell
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in dist and int(g[nr, nc]) not in blocked:
                dist[(nr, nc)] = dist[cell] + 1
                queue.append((nr, nc))
    return None
