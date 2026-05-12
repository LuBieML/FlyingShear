"""Trio BASIC generation for rotary-knife CAMBOX profiles."""


def emit_cam_basic_program(
    table_values,
    diag,
    cut_length,
    link_axis,
    drum_axis,
    table_start,
    cutter_op,
    values_per_line=10,
):
    n_pts = len(table_values)
    table_end = table_start + n_pts - 1
    lines = []
    lines.append(f"' Rotary knife cam table - {n_pts} pts, "
                 f"{diag['table_resolution_deg']:.4f}°/point on drum")
    lines.append(f"' Drum: {diag['drum_circumference']:.2f} mm circumference, "
                 f"{int(diag['cut_segment_counts'])} counts per cut segment")
    lines.append("' Drum zero: blade at top. Material contact/cut is 180 deg from zero.")
    lines.append(f"' Cut zone: {diag['cut_zone_master_mm']:.2f} mm of material "
                 f"(R={diag['R']:.4f})")
    lines.append(f"' Inside cut window: ratio={diag['v_cut']:.4f} center, "
                 f"{diag['v_cut_at_edge_normalized']:.4f} at edges "
                 f"({diag['cosine_correction_at_edge']:.4f}x cosine correction)")
    lines.append(f"' Outside cut window: ratio={diag['v_out']:.4f}")
    lines.append("")
    lines.append(f"link_ax    = {link_axis}")
    lines.append(f"drum_ax    = {drum_axis}")
    lines.append(f"cut_length = {cut_length:g}")
    lines.append(f"cutter_op  = {cutter_op}")
    lines.append("")
    lines.append("' Load cam table (encoder counts on drum axis)")
    for chunk_start in range(0, n_pts, values_per_line):
        chunk = table_values[chunk_start:chunk_start + values_per_line]
        idx = table_start + chunk_start
        lines.append(f"TABLE({idx}, {', '.join(str(v) for v in chunk)})")
    lines.append("")
    lines.append("BASE(drum_ax)")
    lines.append("SERVO = ON")
    lines.append("' Jog/home the blade to the top before this line; that is drum position 0.")
    lines.append("DEFPOS(0)")
    lines.append("")
    lines.append("' Bit 2 = repeat continuously")
    lines.append(f"CAMBOX({table_start}, {table_end}, 1, cut_length, link_ax, 4)")
    return "\n".join(lines)


def emit_cam_quicktest_basic_program(
    table_values,
    diag,
    cut_length,
    link_axis,
    drum_axis,
    table_start,
    cutter_op,
):
    n_pts = len(table_values)
    table_end = table_start + n_pts - 1
    lines = []
    lines.append(f"' Rotary knife QuickTest cam - {n_pts} pts, "
                 f"{diag['table_resolution_deg']:.4f}°/point on drum")
    lines.append(f"' Drum: {diag['drum_circumference']:.2f} mm circumference, "
                 f"{int(diag['cut_segment_counts'])} counts per cut segment")
    lines.append("' Drum zero: blade at top. Material contact/cut is 180 deg from zero.")
    lines.append(f"' Cut zone: {diag['cut_zone_master_mm']:.2f} mm of material "
                 f"(R={diag['R']:.4f})")
    lines.append(f"' Inside cut window: ratio={diag['v_cut']:.4f} center, "
                 f"{diag['v_cut_at_edge_normalized']:.4f} at edges "
                 f"({diag['cosine_correction_at_edge']:.4f}x cosine correction)")
    lines.append(f"' Outside cut window: ratio={diag['v_out']:.4f}")
    lines.append("")
    lines.append("' QUICKTEST MODE")
    lines.append(f"' Load controller table indexes {table_start} to {table_end} with the")
    lines.append("' app button: SetMultiTableValues(start_index, count, values).")
    lines.append("' Re-send table data after every profile recalculation.")
    lines.append("")
    lines.append(f"link_ax    = {link_axis}")
    lines.append(f"drum_ax    = {drum_axis}")
    lines.append(f"cut_length = {cut_length:g}")
    lines.append(f"cutter_op  = {cutter_op}")
    lines.append("")
    lines.append("BASE(drum_ax)")
    lines.append("SERVO = ON")
    lines.append("' Jog/home the blade to the top before this line; that is drum position 0.")
    lines.append("DEFPOS(0)")
    lines.append("")
    lines.append("' Bit 2 = repeat continuously")
    lines.append(f"CAMBOX({table_start}, {table_end}, 1, cut_length, link_ax, 4)")
    return "\n".join(lines)
