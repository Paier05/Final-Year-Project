def move_cluster_to(target_row, target_col, max_actions=6):
    """Move the teal/maroon cluster toward (target_row, target_col) using known actions.

    ACTION1=up5, ACTION2=down5, ACTION3=left5, ACTION4=right5.
    Executes up to max_actions moves in this turn, stopping early if the cluster
    reaches the target or an action produces no change. Returns a list of
    (action, n_changed) tuples.
    """
    results = []
    for _ in range(max_actions):
        g = grid()
        teal = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]
        mar = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 9]
        cells = teal + mar
        if not cells:
            break
        cr = sum(r for r, c in cells) / len(cells)
        cc = sum(c for r, c in cells) / len(cells)
        dr = target_row - cr
        dc = target_col - cc
        if abs(dr) < 2 and abs(dc) < 2:
            break
        if abs(dr) >= abs(dc):
            a = 1 if dr < 0 else 2
        else:
            a = 3 if dc < 0 else 4
        r = action(a)
        results.append((a, r.get("n_changed", 0)))
        if r.get("n_changed", 0) == 0:
            break
    return results
