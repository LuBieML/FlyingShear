"""Pure ROTARYLINK profile calculations and validation."""


def calculate_rotarylink_profile(
    distance,
    link_dist,
    acc,
    sync,
    sync_pos=None,
    previous_sync_end=None,
):
    """Return derived ROTARYLINK phase distances.

    ROTARYLINK phase arguments are base-axis distances. The link-axis phase
    distances are proportional to total link distance and are used for
    diagnostics and sync_pos validation.
    """
    distance = float(distance)
    link_dist = float(link_dist)
    acc = float(acc)
    sync = float(sync)
    sync_pos_value = None if sync_pos is None else float(sync_pos)
    previous_sync_end_value = (
        None if previous_sync_end is None else float(previous_sync_end)
    )

    if distance <= 0:
        raise ValueError("distance must be > 0")
    if link_dist <= 0:
        raise ValueError("link_dist must be > 0")
    if acc < 0:
        raise ValueError("acc must be >= 0")
    if sync < 0:
        raise ValueError("sync must be >= 0")
    if acc + sync > distance:
        raise ValueError("acc + sync must be <= distance")

    decel = distance - acc - sync
    link_acc = acc / distance * link_dist
    link_sync = sync / distance * link_dist
    link_decel = decel / distance * link_dist

    if sync_pos_value is not None:
        if sync_pos_value < 0:
            raise ValueError("sync_pos must be >= 0")
        if sync_pos_value <= link_acc:
            raise ValueError("sync_pos must be greater than the link-axis acceleration distance")
        if previous_sync_end_value is not None and sync_pos_value <= previous_sync_end_value:
            raise ValueError("sync_pos must be greater than the previous sync phase end")

    sync_end = None if sync_pos_value is None else sync_pos_value + link_sync
    cycle_end = None if sync_pos_value is None else sync_end + link_decel
    start_link_pos = None if sync_pos_value is None else sync_pos_value - link_acc

    return {
        "distance": distance,
        "link_dist": link_dist,
        "acc": acc,
        "sync": sync,
        "decel": decel,
        "link_acc": link_acc,
        "link_sync": link_sync,
        "link_decel": link_decel,
        "sync_pos": sync_pos_value,
        "start_link_pos": start_link_pos,
        "sync_end": sync_end,
        "cycle_end": cycle_end,
    }
