def verify_move(action_id, x=None, y=None):
    """Perform an action and verify if the player actually moved.
    
    Returns a dict with 'moved' (bool), 'result' (action result), and 'new_pos' (player position).
    If the player did not move (no change or 'other change' that doesn't shift centroid), 'moved' is False.
    """
    pp_before = player_position()
    if pp_before is None:
        return {'moved': False, 'result': None, 'new_pos': None, 'error': 'Player not found'}
    
    result = action(action_id, x, y)
    pp_after = player_position()
    
    if pp_after is None:
        return {'moved': False, 'result': result, 'new_pos': None, 'error': 'Player lost'}
    
    # Check if centroid changed significantly (more than 0.5 cells)
    moved = False
    if pp_before['centroid'] != pp_after['centroid']:
        dr = abs(pp_before['centroid'][0] - pp_after['centroid'][0])
        dc = abs(pp_before['centroid'][1] - pp_after['centroid'][1])
        if dr > 0.5 or dc > 0.5:
            moved = True
    
    return {'moved': moved, 'result': result, 'new_pos': pp_after}
