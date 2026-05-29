from typing import Callable

import flet as ft

from ..context import AppContext
from .common import (
    ACCENT_COLOR,
    BORDER_COLOR,
    DARKER_BG,
    MUTED_TEXT,
    PANEL_ALT_BG,
    PANEL_BG,
)


class AppShell:
    def __init__(
        self,
        ctx: AppContext,
        *,
        load_axis_param_controls_for_solution: Callable,
        flexlink_start_sim: Callable,
        flexlink_stop_sim: Callable,
        set_rotary_sim_labels: Callable,
        prompt_solution_axis_params_if_connected: Callable,
        point_to_point_control_page,
        axis_connection_page,
        cam_calc_container,
        rotary_profile_container,
        rotary_cam_math_help_list,
        rotary_sim_container,
        flexlink_calc_container,
        flexlink_sim_container,
        flexlink_help_list,
        rotarylink_calc_container,
        rotarylink_help_list,
        shear_calc_container,
        movelink_help_list,
        flying_shear_monitor_page,
    ):
        self.ctx = ctx
        self.load_axis_param_controls_for_solution = load_axis_param_controls_for_solution
        self.flexlink_start_sim = flexlink_start_sim
        self.flexlink_stop_sim = flexlink_stop_sim
        self.set_rotary_sim_labels = set_rotary_sim_labels
        self.prompt_solution_axis_params_if_connected = prompt_solution_axis_params_if_connected

        self.point_to_point_control_page = point_to_point_control_page
        self.axis_connection_page = axis_connection_page
        self.cam_calc_container = cam_calc_container
        self.rotary_profile_container = rotary_profile_container
        self.rotary_cam_math_help_list = rotary_cam_math_help_list
        self.rotary_sim_container = rotary_sim_container
        self.flexlink_calc_container = flexlink_calc_container
        self.flexlink_sim_container = flexlink_sim_container
        self.flexlink_help_list = flexlink_help_list
        self.rotarylink_calc_container = rotarylink_calc_container
        self.rotarylink_help_list = rotarylink_help_list
        self.shear_calc_container = shear_calc_container
        self.movelink_help_list = movelink_help_list
        self.flying_shear_monitor_page = flying_shear_monitor_page

        self.app_root = ft.Container(expand=True)

    def build_solution_tabs(self, solution):
        if solution == "point_to_point":
            tab_specs = [
                (
                    ft.Tab(label="Point To Point", icon=ft.Icons.OPEN_WITH),
                    self.point_to_point_control_page,
                ),
                (
                    ft.Tab(label="Axis Configuration / Connection", icon=ft.Icons.TUNE),
                    self.axis_connection_page,
                ),
            ]
        elif solution == "rotary_knife":
            tab_specs = [
                (
                    ft.Tab(label="Rotary Knife Cam", icon=ft.Icons.AUTORENEW),
                    ft.Container(content=self.cam_calc_container, padding=20, expand=True),
                ),
                (
                    ft.Tab(label="Profile View", icon=ft.Icons.SHOW_CHART),
                    ft.Container(content=self.rotary_profile_container, padding=20, expand=True),
                ),
                (
                    ft.Tab(label="Help", icon=ft.Icons.FUNCTIONS),
                    self.rotary_cam_math_help_list,
                ),
                (
                    ft.Tab(label="Connection and Axis Config", icon=ft.Icons.TUNE),
                    self.axis_connection_page,
                ),
                (
                    ft.Tab(label="Live Monitor", icon=ft.Icons.ANALYTICS),
                    ft.Container(content=self.rotary_sim_container, padding=20, expand=True),
                ),
            ]
        elif solution == "flow_wrapper":
            tab_specs = [
                (
                    ft.Tab(label="Configure FlexLink", icon=ft.Icons.WAVES),
                    ft.Container(
                        content=ft.Column(
                            [self.flexlink_calc_container],
                            spacing=14,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        padding=20,
                        expand=True,
                    ),
                ),
                (
                    ft.Tab(label="Simulation", icon=ft.Icons.PLAY_CIRCLE),
                    ft.Container(content=self.flexlink_sim_container, padding=20, expand=True),
                ),
                (
                    ft.Tab(label="FlexLink Help", icon=ft.Icons.FUNCTIONS),
                    self.flexlink_help_list,
                ),
                (
                    ft.Tab(label="Axis Configuration / Connection", icon=ft.Icons.TUNE),
                    self.axis_connection_page,
                ),
            ]
        elif solution == "rotarylink":
            tab_specs = [
                (
                    ft.Tab(label="RotaryLink Sim", icon=ft.Icons.AUTORENEW),
                    ft.Container(content=self.rotary_sim_container, padding=20, expand=True),
                ),
                (
                    ft.Tab(label="Configure RotaryLink", icon=ft.Icons.CYCLONE),
                    ft.Container(
                        content=ft.Column(
                            [self.rotarylink_calc_container],
                            spacing=14,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        padding=20,
                        expand=True,
                    ),
                ),
                (
                    ft.Tab(label="RotaryLink Help", icon=ft.Icons.FUNCTIONS),
                    self.rotarylink_help_list,
                ),
                (
                    ft.Tab(label="Axis Configuration / Connection", icon=ft.Icons.TUNE),
                    self.axis_connection_page,
                ),
            ]
        else:
            tab_specs = [
                (
                    ft.Tab(label="Configure Shear", icon=ft.Icons.CALCULATE),
                    ft.Container(
                        content=ft.Column(
                            [self.shear_calc_container],
                            spacing=14,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        padding=20,
                        expand=True,
                    ),
                ),
                (ft.Tab(label="MoveLink Help", icon=ft.Icons.FUNCTIONS), self.movelink_help_list),
                (
                    ft.Tab(label="Axis Configuration / Connection", icon=ft.Icons.TUNE),
                    self.axis_connection_page,
                ),
                (
                    ft.Tab(label="Live Monitor", icon=ft.Icons.ANALYTICS),
                    self.flying_shear_monitor_page,
                ),
            ]

        def on_solution_tab_change(e):
            if solution == "flow_wrapper" and int(e.control.selected_index or 0) == 1:
                self.flexlink_start_sim()
            else:
                self.flexlink_stop_sim()

        return ft.Tabs(
            length=len(tab_specs),
            selected_index=0,
            on_change=on_solution_tab_change,
            content=ft.Column(
                [
                    ft.TabBar(
                        tabs=[tab for tab, _ in tab_specs],
                        label_color=ft.Colors.CYAN_200,
                        unselected_label_color=MUTED_TEXT,
                        indicator_color=ACCENT_COLOR,
                        divider_color=BORDER_COLOR,
                    ),
                    ft.TabBarView(
                        controls=[content for _, content in tab_specs],
                        expand=1,
                    ),
                ],
                expand=1,
            ),
            expand=1,
        )

    def set_workspace_appbar(self, solution_name):
        page = self.ctx.page
        page.appbar = ft.AppBar(
            title=ft.Text(f"Trio {solution_name} Setup", size=18, weight=ft.FontWeight.BOLD),
            bgcolor=PANEL_BG,
            color=ft.Colors.WHITE,
            elevation=0,
            actions=[
                ft.TextButton(
                    "Change solution",
                    icon=ft.Icons.SWAP_HORIZ,
                    on_click=lambda e: self.show_solution_picker(),
                    style=ft.ButtonStyle(color=ft.Colors.CYAN_200),
                ),
                ft.Container(
                    content=ft.Text(
                        solution_name,
                        size=12,
                        color=ft.Colors.CYAN_200,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.Padding.only(right=16),
                    alignment=ft.Alignment.CENTER,
                ),
            ],
        )

    def show_solution_workspace(self, solution):
        page = self.ctx.page
        current_solution = self.ctx.current_solution

        current_solution["value"] = solution
        self.load_axis_param_controls_for_solution(solution)
        if solution != "flow_wrapper":
            self.flexlink_stop_sim()
        self.set_rotary_sim_labels(solution)
        solution_name = (
            "Point To Point Move" if solution == "point_to_point"
            else "Rotary Knife" if solution == "rotary_knife"
            else "VFFS" if solution == "flow_wrapper"
            else "RotaryLink" if solution == "rotarylink"
            else "Flying Shear"
        )
        page.title = f"Trio {solution_name} Setup"
        self.set_workspace_appbar(solution_name)
        self.app_root.content = self.build_solution_tabs(solution)
        page.update()
        self.prompt_solution_axis_params_if_connected(solution)

    def solution_card(self, label, subtitle, icon, solution):
        base_bg = PANEL_BG
        base_border = BORDER_COLOR
        hover_bg = "#262b32"
        hover_border = ACCENT_COLOR

        icon_badge = ft.Container(
            content=ft.Icon(icon, size=30, color=ft.Colors.CYAN_200),
            width=58,
            height=58,
            bgcolor=PANEL_ALT_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=14,
            alignment=ft.Alignment.CENTER,
        )

        cta = ft.Row(
            [
                ft.Text("Configure", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_200),
                ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=ft.Colors.CYAN_200),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        card = ft.Container(
            content=ft.Column(
                [
                    icon_badge,
                    ft.Container(height=2),
                    ft.Text(label, size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Text(subtitle, size=13, color=MUTED_TEXT, max_lines=3),
                    ft.Container(expand=True),
                    cta,
                ],
                spacing=8,
                expand=True,
            ),
            width=320,
            height=270,
            padding=ft.Padding.all(22),
            bgcolor=base_bg,
            border=ft.Border.all(1, base_border),
            border_radius=14,
            on_click=lambda e: self.show_solution_workspace(solution),
            ink=True,
            animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
        )

        def _on_hover(e):
            hovered = e.data == "true"
            card.bgcolor = hover_bg if hovered else base_bg
            card.border = ft.Border.all(1, hover_border if hovered else base_border)
            card.update()

        card.on_hover = _on_hover
        return card

    def placeholder_training_card(self, label, subtitle, icon):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=30, color=MUTED_TEXT),
                        width=58,
                        height=58,
                        bgcolor=DARKER_BG,
                        border=ft.Border.all(1, BORDER_COLOR),
                        border_radius=14,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Container(height=2),
                    ft.Text(label, size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_300),
                    ft.Text(subtitle, size=13, color=MUTED_TEXT, max_lines=3),
                ],
                spacing=8,
                expand=True,
            ),
            width=320,
            height=210,
            padding=ft.Padding.all(22),
            bgcolor=PANEL_ALT_BG,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=14,
        )

    def training_section(self, title, subtitle, controls):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Column(
                        [
                            ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text(subtitle, size=12, color=MUTED_TEXT),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    ft.Row(
                        controls,
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20,
                        wrap=True,
                        run_spacing=20,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.START,
                spacing=14,
            ),
            width=1420,
        )

    def show_solution_picker(self):
        page = self.ctx.page
        current_solution = self.ctx.current_solution

        page.title = "Trio Motion Training Suite"
        page.appbar = None
        current_solution["value"] = None
        self.flexlink_stop_sim()

        hero = ft.Column(
            [
                ft.Text(
                    "Trio Motion Training Suite",
                    size=38,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE,
                ),
                ft.Text(
                    "Choose a training module to begin configuring the controller.",
                    size=14,
                    color=MUTED_TEXT,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

        basic_section = self.training_section(
            "Basic",
            "Introductory single-axis motion examples for learning Trio BASIC fundamentals.",
            [
                self.solution_card(
                    "Point To Point Move",
                    "Single-axis relative MOVE and absolute MOVEABS examples with generated Trio BASIC.",
                    ft.Icons.OPEN_WITH,
                    "point_to_point",
                ),
            ],
        )

        advanced_section = self.training_section(
            "Advanced",
            "Application-level examples for linked motion, camming, and synchronized axes.",
            [
                self.solution_card(
                    "Flying Shear",
                    "Linear cut-on-the-fly with a matched-speed shear axis driven by a MOVELINK profile.",
                    ft.Icons.CONTENT_CUT,
                    "flying_shear",
                ),
                self.solution_card(
                    "Rotary Knife",
                    "Continuous rotary drum knife synchronised to the line via CAMBOX.",
                    ft.Icons.AUTORENEW,
                    "rotary_knife",
                ),
                self.solution_card(
                    "VFFS",
                    "Continuous vertical form-fill-seal: cross-seal jaws synced 1:1 to film pull via FLEXLINK, with heat-seal dwell validation.",
                    ft.Icons.WAVES,
                    "flow_wrapper",
                ),
                self.solution_card(
                    "RotaryLink",
                    "Rotary linked move with explicit accel, sync, and mergeable phase distances.",
                    ft.Icons.CYCLONE,
                    "rotarylink",
                ),
            ],
        )

        self.app_root.content = ft.Container(
            content=ft.Column(
                [hero, basic_section, advanced_section],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.START,
                spacing=30,
                scroll=ft.ScrollMode.AUTO,
            ),
            expand=True,
            alignment=ft.Alignment.TOP_CENTER,
            padding=ft.Padding.symmetric(horizontal=24, vertical=34),
        )
        page.update()
