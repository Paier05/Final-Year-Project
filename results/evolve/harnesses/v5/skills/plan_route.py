def plan_route():
    """Plan an efficient route to collect all maroon items.
    
    Returns a list of (action, x, y) tuples representing the sequence of actions
    to take, where action is 1-4 for ACTION1-4, and x, y are the target coordinates.
    """
    pp = player_position()
    if pp is None:
        return []
    
    items = collect_items()
    if not items:
        return []
    
    # Get player's current position
    pr, pc = pp['centroid']
    
    # Sort maroon items by distance from player
    item_centers = []
    for group in items:
        if group:
            r = sum(r for r, c in group) / len(group)
            c = sum(c for r, c in group) / len(group)
            item_centers.append((r, c))
    
    if not item_centers:
        return []
    
    # Sort by distance
    item_centers.sort(key=lambda pos: (pos[0] - pr) ** 2 + (pos[1] - pc) ** 2)
    
    # Plan route to nearest item first
    target_r, target_c = item_centers[0]
    
    # Calculate moves needed (1 cell per action)
    dr = int(round(target_r - pr))
    dc = int(round(target_c - pc))
    
    # Generate action sequence
    actions = []
    # Move up/down first
    for _ in range(abs(dr)):
        actions.append((1 if dr > 0 else 2, None, None))
    # Then move left/right
    for _ in range(abs(dc)):
        actions.append((3 if dc > 0 else 4, None, None))
    
    return actions
