def block_info(g):
    """Promoted from the player's own inline helper (defined in 1 episodes, called 5 times)."""
    teal = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]
    mar = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 9]

    def bb(cells):
        if not cells:
            return None
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        return (min(rs), max(rs), min(cs), max(cs))
    return (bb(teal), bb(mar), len(teal), len(mar))
