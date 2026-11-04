def teal_centroid():
    """Promoted from the player's own inline helper (defined in 1 episodes, called 5 times)."""
    g = grid()
    cells = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]
    if not cells:
        return None
    return (sum((r for r, c in cells)) / len(cells), sum((c for r, c in cells)) / len(cells))
