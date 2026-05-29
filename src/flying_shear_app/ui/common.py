import flet as ft


DARK_BG = "#17191c"
DARKER_BG = "#111316"
PANEL_BG = "#20242a"
PANEL_ALT_BG = "#181b20"
BORDER_COLOR = "#343a40"
ACCENT_COLOR = "#007acc"
TEXT_COLOR = "#d4d4d4"
MUTED_TEXT = ft.Colors.GREY_500
SUCCESS_COLOR = ft.Colors.GREEN_300
WARNING_COLOR = ft.Colors.AMBER_300
ERROR_COLOR = ft.Colors.RED_300

LABEL_STYLE = {"size": 12, "color": ft.Colors.GREY_400, "width": 130}
VALUE_STYLE_M = {
    "size": 14,
    "color": ft.Colors.CYAN_200,
    "weight": ft.FontWeight.BOLD,
    "width": 120,
}
VALUE_STYLE_S = {
    "size": 14,
    "color": ft.Colors.ORANGE_200,
    "weight": ft.FontWeight.BOLD,
    "width": 120,
}


def _update_if_mounted(control):
    if getattr(control, "parent", None) is None:
        return False
    try:
        control.update()
        return True
    except AssertionError:
        return False
    except RuntimeError as ex:
        if "must be added to the page first" in str(ex):
            return False
        raise


def make_show_snack(page):
    def show_snack(message, type_="info"):
        palette = {
            "success": ("#133a25", ft.Icons.CHECK_CIRCLE, SUCCESS_COLOR),
            "warning": ("#3a2a0d", ft.Icons.WARNING_AMBER, WARNING_COLOR),
            "error": ("#3a1515", ft.Icons.ERROR, ERROR_COLOR),
            "info": ("#102d3f", ft.Icons.INFO, ft.Colors.CYAN_200),
        }
        bg, icon, icon_color = palette.get(type_, palette["info"])
        snack = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(icon, size=18, color=icon_color),
                    ft.Text(message, color=ft.Colors.WHITE, size=13),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=bg,
            behavior=ft.SnackBarBehavior.FLOATING,
            show_close_icon=True,
            close_icon_color=ft.Colors.WHITE,
            duration=4200,
        )
        if hasattr(page, "show_dialog"):
            page.show_dialog(snack)
        else:
            page.snack_bar = snack
            snack.open = True
            page.update()

    return show_snack


def section_header(title, subtitle=None, icon=None):
    leading = []
    if icon:
        leading.append(ft.Icon(icon, size=18, color=ft.Colors.CYAN_200))
    return ft.Row(
        leading + [
            ft.Column(
                [
                    ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Text(subtitle, size=12, color=MUTED_TEXT) if subtitle else ft.Container(height=0),
                ],
                spacing=2,
                tight=True,
            )
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def control_cluster(title, controls, icon=None, col=None, height=None):
    heading = [ft.Text(title.upper(), size=10, color=MUTED_TEXT, weight=ft.FontWeight.BOLD)]
    if icon:
        heading.insert(0, ft.Icon(icon, size=14, color=MUTED_TEXT))
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(heading, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row(
                    controls,
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=8,
            tight=True,
        ),
        bgcolor=PANEL_ALT_BG,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=12,
        height=height,
        col=col or {"xs": 12, "md": 6, "xl": 3},
    )


def canvas_paint(color, width=1, dash=None, style=ft.PaintingStyle.STROKE):
    return ft.Paint(
        color=color,
        stroke_width=width,
        stroke_cap=ft.StrokeCap.ROUND,
        stroke_dash_pattern=dash,
        style=style,
    )
