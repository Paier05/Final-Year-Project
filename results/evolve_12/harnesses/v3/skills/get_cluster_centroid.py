def get_cluster_centroid(g, colors=[12, 9]):
    """Promoted from the player's own inline helper (defined in 1 episodes, called 4 times)."""
    ys, xs = np.where(np.isin(g, colors))
    if len(ys) == 0:
        return None
    return (np.mean(ys), np.mean(xs))
