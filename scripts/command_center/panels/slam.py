"""SLAM panel — SLAM/Foxglove process control and map management."""

from __future__ import annotations

from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static, Input


class SlamPanel(Widget):
    """SLAM control — start/stop SLAM, Foxglove, save maps."""

    def compose(self):
        with Horizontal(id="slam-layout"):
            # Left: SLAM Control
            with Container(classes="panel-box-green") as c:
                c.border_title = "SLAM Control"
                yield Static(
                    "SLAM:     [dim]○ Stopped[/]\n"
                    "Foxglove: [dim]○ Stopped[/]\n"
                    "Nav2:     [dim]○ Stopped[/]",
                    id="slam-status",
                )
                yield Static(
                    "\n"
                    " [bold]S[/] Start SLAM    [bold]X[/] Stop SLAM\n"
                    " [bold]F[/] Toggle Foxglove (ws://localhost:8765)\n"
                    " [bold]M[/] Save Map\n",
                    id="slam-keys",
                )
                yield Static("Map File:", id="slam-map-label")
                yield Input(
                    placeholder="my_map",
                    id="slam-map-input",
                )
                yield Static(" ", id="slam-save-result")

            # Middle: Map Stats
            with Container(classes="panel-box-blue") as c:
                c.border_title = "Map Stats"
                yield Static("[dim]No map data (start SLAM first)[/]", id="slam-map-stats")

            # Right: SLAM Tips
            with Container(classes="panel-box-cyan") as c:
                c.border_title = "SLAM Tips"
                yield Static(
                    "[dim]Drive slowly for best scan matching\n"
                    "/map topic appears ~5s after first match\n"
                    "Use Foxglove 3D panel, frame='map'\n"
                    "Save map before stopping SLAM[/]",
                )

    def process_key(self, key: str) -> bool:
        """Handle SLAM key bindings. Called by App dispatcher. Returns True if handled."""
        if key == "s":
            self._start_slam()
        elif key == "x":
            self._stop_slam()
        elif key == "f":
            self._toggle_foxglove()
        elif key == "m":
            self._save_map()
        else:
            return False
        return True

    def _start_slam(self) -> None:
        if self.app.pm.start_slam():
            self._show_result("[green]SLAM started[/]")
        else:
            self._show_result("[red]Failed to start SLAM[/]")

    def _stop_slam(self) -> None:
        self.app.pm.stop_slam()
        self._show_result("[yellow]SLAM stopped[/]")

    def _toggle_foxglove(self) -> None:
        status = self.app.pm.get_status()
        if status.get("foxglove") == "running":
            self.app.pm.stop_foxglove()
            self._show_result("[yellow]Foxglove stopped[/]")
        else:
            if self.app.pm.start_foxglove():
                self._show_result("[green]Foxglove started[/]")
            else:
                self._show_result("[red]Failed to start Foxglove[/]")

    def _save_map(self) -> None:
        try:
            input_widget = self.query_one("#slam-map-input", Input)
            name = input_widget.value.strip()
        except Exception:
            name = ""

        if not name:
            self._show_result("[yellow]Enter a map name first[/]")
            return

        self._show_result(f"[dim]Saving map '{name}'...[/]")
        if self.app.pm.save_map(name):
            self._show_result(f"[green]Map saved: ~/maps/{name}[/]")
        else:
            self._show_result(f"[red]Failed to save map '{name}'[/]")

    def _show_result(self, msg: str) -> None:
        try:
            self.query_one("#slam-save-result", Static).update(msg)
        except Exception:
            pass

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_status(proc_status)
        self._update_map_stats(state)

    def _update_status(self, proc_status: dict) -> None:
        parts = []

        # SLAM status
        slam_st = proc_status.get("slam")
        if slam_st == "running":
            parts.append("SLAM:     [green]● Running[/]")
        elif slam_st and slam_st.startswith("exited"):
            parts.append(f"SLAM:     [red]● {slam_st}[/]")
        else:
            parts.append("SLAM:     [dim]○ Stopped[/]")

        # Foxglove status
        fox_st = proc_status.get("foxglove")
        if fox_st == "running":
            parts.append("Foxglove: [green]● Running[/]")
        elif fox_st and fox_st.startswith("exited"):
            parts.append(f"Foxglove: [red]● {fox_st}[/]")
        else:
            parts.append("Foxglove: [dim]○ Stopped[/]")

        # Nav2 status
        nav_st = proc_status.get("nav2")
        if nav_st == "running":
            parts.append("Nav2:     [green]● Running[/]")
        elif nav_st and nav_st.startswith("exited"):
            parts.append(f"Nav2:     [red]● {nav_st}[/]")
        else:
            parts.append("Nav2:     [dim]○ Stopped[/]")

        try:
            self.query_one("#slam-status", Static).update("\n".join(parts))
        except Exception:
            pass

    def _update_map_stats(self, state: dict) -> None:
        w = state.get("map_width", 0)
        h = state.get("map_height", 0)
        res = state.get("map_resolution", 0)
        hz = state.get("map_hz", 0)

        if w == 0 and h == 0:
            text = "[dim]No map data (start SLAM first)[/]"
        else:
            # Estimate coverage
            area = w * h * res * res  # total cells * area per cell
            text = (
                f"Size:        {w} x {h} cells\n"
                f"Resolution:  {res:.3f} m/cell\n"
                f"Coverage:    {area:.2f} m²\n"
                f"Update Rate: {hz:.1f} Hz"
            )

        try:
            self.query_one("#slam-map-stats", Static).update(text)
        except Exception:
            pass
