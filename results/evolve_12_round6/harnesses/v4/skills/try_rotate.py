def try_rotate():
    """Try ACTION5 and ACTION7 to find which one rotates the cluster.

    Returns the action number (5 or 7) that caused a change, or None if neither worked.
    """
    g0 = grid()
    for a in [5, 7]:
        try:
            r = action(a)
            if r.get("n_changed", 0) > 0:
                return a
        except Exception:
            pass
    return None
