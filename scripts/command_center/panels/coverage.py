"""Coverage panel — autonomous-vacuum workflow control + readiness check.

The single screen of truth for "what's running, what's blocking, what to
start next" during a coverage run. Every actionable problem we've hit
during live testing has its own indicator and one-key recovery.

Sections (top → bottom):
  1. Pi services      — systemctl is-active for the 11 edge services
  2. Mac processes    — EKF, Nav2, Foxglove, tracker, coverage_node
  3. Nav2 lifecycle   — per-node state of the 8 lifecycle-managed Nav2 nodes
  4. cmd_vel pipeline — the mux input/output rates (catches zombie teleop)
  5. Coverage status  — current waypoint progress
  6. ALERTS           — actionable warnings ("zombie teleop blocking nav")
  7. Actions          — keyboard shortcuts to run each piece in order

Key bindings (only active when this tab is focused):
  e — start EKF
  n — start Nav2 with selected map (input field)
  f — toggle Foxglove bridge
  t — toggle Coverage tracker
  p — run coverage planner in PREVIEW mode (publishes path, no motion)
  r — run coverage planner LIVE
  l — recover Nav2 lifecycle (RESET → STARTUP)
  k — kill zombie teleop (clears mux block)
  s — save current map
  X — kill EVERYTHING Mac-side (clean slate)
"""
from __future__ import annotations

from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static, Input


# Friendly per-row symbols
GREEN_DOT = "[green]●[/]"
RED_DOT = "[red]●[/]"
GRAY_DOT = "[dim]○[/]"
YELLOW_DOT = "[yellow]●[/]"


def _status_dot(active: bool, missing: bool = False) -> str:
    if missing:
        return GRAY_DOT
    return GREEN_DOT if active else RED_DOT


class CoveragePanel(Widget):
    """Coverage workflow control + comprehensive readiness check."""

    def compose(self):
        # Row 1 — services / processes / lifecycle
        with Horizontal(id="cov-row-1"):
            with Container(classes="panel-box-green") as c:
                c.border_title = "Pi Services"
                yield Static("[dim]Loading…[/]", id="cov-pi-services")
            with Container(classes="panel-box-blue") as c:
                c.border_title = "Mac Processes"
                yield Static("[dim]Loading…[/]", id="cov-mac-procs")
            with Container(classes="panel-box-cyan") as c:
                c.border_title = "Nav2 Lifecycle"
                yield Static("[dim]Loading…[/]", id="cov-nav2-lifecycle")

        # Row 2 — cmd_vel pipeline + alerts
        with Horizontal(id="cov-row-2"):
            with Container(classes="panel-box-yellow") as c:
                c.border_title = "cmd_vel Pipeline"
                yield Static("[dim]Loading…[/]", id="cov-cmdvel")
            with Container(classes="panel-box-magenta") as c:
                c.border_title = "ALERTS"
                yield Static("[dim]No alerts[/]", id="cov-alerts")

        # Row 3 — coverage progress + map picker
        with Horizontal(id="cov-row-3"):
            with Container(classes="panel-box-blue") as c:
                c.border_title = "Coverage Progress"
                yield Static("[dim]Not running[/]", id="cov-progress")
            with Container(classes="panel-box-green") as c:
                c.border_title = "Map / Save"
                yield Static("Map for nav (yaml path):", id="cov-map-label")
                yield Input(
                    placeholder="~/maps/livingroom.yaml",
                    id="cov-map-input",
                )
                yield Static(" ", id="cov-result")

        # Row 4 — /rosout tail (WARN+ only)
        with Container(classes="panel-box-magenta") as c:
            c.border_title = "ROS Logs (WARN/ERROR/FATAL from /rosout)"
            yield Static("[dim]No warnings/errors yet[/]", id="cov-rosout")

        # Row 4 — actions
        with Container(classes="panel-box-cyan") as c:
            c.border_title = "Actions"
            yield Static(
                " [bold yellow]A[/] AUTO-START full stack (EKF→/scan→Nav2→Foxglove→Tracker)\n"
                "\n"
                " [bold]e[/] start EKF       "
                "[bold]n[/] start Nav2       "
                "[bold]f[/] toggle Foxglove   "
                "[bold]F[/] restart Foxglove\n"
                " [bold]t[/] toggle tracker  "
                "[bold]p[/] coverage PREVIEW  "
                "[bold]r[/] coverage LIVE     "
                "[bold]S[/] STOP coverage\n"
                " [bold]i[/] AMCL init pose  "
                "[bold]l[/] Nav2 RECOVER     "
                "[bold]k[/] kill teleop       "
                "[bold]s[/] save map\n"
                " [bold]X[/] kill EVERYTHING (Mac side, clean slate)",
                id="cov-actions",
            )

    # ── Key dispatch ──────────────────────────────────────────────────

    def process_key(self, key: str) -> bool:
        # Capital-letter actions before lowercase to avoid collisions.
        if key in ("A", "shift+a"):
            self._auto_start()
        elif key in ("F", "shift+f"):
            self._restart_foxglove()
        elif key in ("S", "shift+s"):
            self._stop_coverage()
        elif key in ("X", "shift+x"):
            self._kill_all()
        elif key == "a":
            self._auto_start()
        elif key == "e":
            self._start_ekf()
        elif key == "n":
            self._start_nav2()
        elif key == "f":
            self._toggle_foxglove()
        elif key == "t":
            self._toggle_tracker()
        elif key == "p":
            self._start_coverage(preview=True)
        elif key == "r":
            self._start_coverage(preview=False)
        elif key == "l":
            self._recover_nav2()
        elif key == "k":
            self._kill_teleop()
        elif key == "i":
            self._publish_initial_pose()
        elif key == "s":
            self._save_map()
        else:
            return False
        return True

    # ── Action handlers ───────────────────────────────────────────────

    def _auto_start(self):
        """Run the full bring-up sequence in the background."""
        try:
            map_path = self.query_one("#cov-map-input", Input).value.strip()
        except Exception:
            map_path = ""
        import os
        if not map_path:
            # Pick the most recently modified map yaml
            maps = self.app.pm.list_maps()
            if maps:
                map_path = max(maps, key=os.path.getmtime)
                try:
                    self.query_one("#cov-map-input", Input).value = map_path
                except Exception:
                    pass
            else:
                self._show_result("[red]No map yaml found in ~/maps. SLAM first, then save.[/]")
                return
        map_path = os.path.expanduser(map_path)
        ok, err = self.app.pm.validate_map_for_nav(map_path)
        if not ok:
            self._show_result(f"[red]{err}[/]")
            return

        # Track step progress in a thread-safe list so the worker
        # thread that calls on_step can mutate while UI thread reads
        # via _refresh_auto_status. Lock protects against torn reads.
        import threading
        self._auto_steps = []
        if not hasattr(self, "_auto_steps_lock"):
            self._auto_steps_lock = threading.Lock()
        def on_step(label, status):
            symbol = {"pending": "[yellow]…[/]",
                      "ok": "[green]✓[/]",
                      "failed": "[red]✗[/]",
                      "recovering": "[yellow]↻[/]"}.get(status, "•")
            # Worker thread may fire this while UI thread iterates the
            # list — lock both ends. Replace existing label entry or
            # append a new one.
            with self._auto_steps_lock:
                for i, (lbl, _) in enumerate(self._auto_steps):
                    if lbl == label:
                        self._auto_steps[i] = (label, symbol)
                        break
                else:
                    self._auto_steps.append((label, symbol))
            self._refresh_auto_status()

        self._show_result(
            f"[green]Auto-starting full stack with map: {map_path}[/]")
        # Pass ros_bridge so the macro can publish /initialpose for AMCL
        # at the end of bringup (was previously a separate manual step).
        if not self.app.pm.auto_start_full_stack(
                map_path, on_step=on_step, ros_bridge=self.app.ros):
            # Reentrancy guard fired — another auto-start is in flight.
            self._show_result(
                "[yellow]Auto-start already in progress — wait for it to finish[/]")

    def _refresh_auto_status(self):
        with self._auto_steps_lock:
            steps = list(self._auto_steps)  # snapshot
        if not steps:
            return
        lines = [f"  {sym} {lbl}" for lbl, sym in steps]
        try:
            self.query_one("#cov-result", Static).update(
                "[bold]Auto-start progress:[/]\n" + "\n".join(lines))
        except Exception:
            pass

    def _start_ekf(self):
        if self.app.pm.start_ekf():
            self._show_result("[green]EKF started[/]")
        else:
            self._show_result("[red]EKF start failed[/]")

    def _start_nav2(self):
        try:
            map_path = self.query_one("#cov-map-input", Input).value.strip()
        except Exception:
            map_path = ""
        if not map_path:
            self._show_result("[yellow]Enter a map yaml path first[/]")
            return
        ok, err = self.app.pm.validate_map_for_nav(map_path)
        if not ok:
            self._show_result(f"[red]{err}[/]")
            return
        import os
        map_path = os.path.expanduser(map_path)
        if self.app.pm.start_nav2(map_path):
            self._show_result(f"[green]Nav2 starting with {map_path}[/]")
        else:
            self._show_result("[red]Nav2 start failed[/]")

    def _toggle_foxglove(self):
        status = self.app.pm.get_status()
        if status.get("foxglove") == "running":
            self.app.pm.stop_foxglove()
            self._show_result("[yellow]Foxglove stopped[/]")
        else:
            ok = self.app.pm.start_foxglove()
            self._show_result("[green]Foxglove started[/]" if ok else "[red]Foxglove failed[/]")

    def _toggle_tracker(self):
        status = self.app.pm.get_status()
        if status.get("tracker") in ("running", "running (external)"):
            self.app.pm.stop_coverage_tracker()
            self._show_result("[yellow]Tracker stopped[/]")
        else:
            ok = self.app.pm.start_coverage_tracker()
            self._show_result("[green]Tracker started[/]" if ok else "[red]Tracker failed[/]")

    def _start_coverage(self, preview: bool):
        status = self.app.pm.get_status()
        if status.get("coverage") in ("running", "running (external)"):
            self._show_result("[yellow]Coverage already running. Stop with X first.[/]")
            return
        ok = self.app.pm.start_coverage(preview_only=preview)
        mode = "PREVIEW" if preview else "LIVE"
        self._show_result(
            f"[green]Coverage {mode} dispatched[/]" if ok else f"[red]Coverage {mode} failed[/]"
        )

    def _recover_nav2(self):
        # The recovery runs in a worker thread (~25-35s). UI shouldn't
        # block waiting; the lifecycle indicators in the Nav2 panel will
        # flip back to active when it succeeds.
        if self.app.pm.recover_nav2_lifecycle():
            self._show_result(
                "[yellow]Nav2 RESET → STARTUP dispatched. "
                "Watch the lifecycle column — nodes flip back to active in ~30s.[/]"
            )
        else:
            self._show_result("[red]Recovery couldn't start (manager shutting down?)[/]")

    def _kill_teleop(self):
        n = self.app.pm.kill_zombie_teleop()
        if n > 0:
            self._show_result(
                f"[green]Killed {n} local teleop process(es); Pi cleanup dispatched[/]"
            )
        else:
            self._show_result(
                "[green]No local teleop running; Pi cleanup dispatched anyway[/]"
            )

    def _publish_initial_pose(self):
        """Seed AMCL with /initialpose at origin (0,0,0). Without this,
        AMCL refuses to publish map→odom TF and Nav2 won't navigate."""
        if not self.app.ros:
            self._show_result("[red]ROS bridge not connected[/]")
            return
        ok = self.app.ros.publish_initial_pose(0.0, 0.0, 0.0)
        if ok:
            self._show_result(
                "[green]Published /initialpose at (0,0,0). "
                "AMCL warnings should stop within ~1 sec.[/]"
            )
        else:
            self._show_result("[red]/initialpose publish failed (see log)[/]")

    def _save_map(self):
        try:
            map_input = self.query_one("#cov-map-input", Input).value.strip()
        except Exception:
            map_input = ""
        if not map_input:
            self._show_result("[yellow]Enter a map name in the input field[/]")
            return
        import os
        name = os.path.splitext(os.path.basename(map_input))[0] or "rovac_map"
        # Async — worker thread runs map_saver_cli (5-15s).
        self.app.pm.save_map(name)
        self._show_result(
            f"[yellow]Map save dispatched: ~/maps/{name}.yaml[/]\n"
            f"[dim]Watch the log for 'Map save \"{name}\": OK' (5-15s)[/]"
        )

    def _stop_coverage(self):
        """Stop ONLY coverage_node — keep Nav2, EKF, tracker running so
        the user can re-run the planner without re-bringing-up the stack."""
        self.app.pm.stop_coverage()
        # Also kill any externally-spawned coverage_node we don't track
        import subprocess
        try:
            subprocess.run(['pkill', '-f', 'coverage_node.py'],
                           capture_output=True, timeout=2)
        except Exception:
            pass
        self._show_result(
            "[yellow]Coverage stopped. Nav2/EKF/tracker still running. "
            "Press 'p' or 'r' to start a new run.[/]"
        )

    def _restart_foxglove(self):
        """Stop + start the Foxglove bridge. Useful when channel IDs go
        stale after a Nav2 lifecycle reset and the bridge holds them."""
        self.app.pm.stop_foxglove()
        # Brief delay so the port frees up
        self.set_timer(1.5, self._restart_foxglove_step2)
        self._show_result("[yellow]Restarting Foxglove bridge…[/]")

    def _restart_foxglove_step2(self):
        ok = self.app.pm.start_foxglove()
        self._show_result(
            "[green]Foxglove bridge restarted. Reload Foxglove client.[/]"
            if ok else "[red]Foxglove restart failed[/]"
        )

    def _kill_all(self):
        self.app.pm.stop_all()
        self._show_result("[yellow]Killed all Mac-side processes[/]")

    def _show_result(self, msg: str):
        try:
            self.query_one("#cov-result", Static).update(msg)
        except Exception:
            pass

    # ── Periodic refresh ──────────────────────────────────────────────

    def update_state(self, state: dict, logs: list, proc_status: dict):
        self._update_pi_services()
        self._update_mac_procs(proc_status)
        self._update_nav2_lifecycle()
        self._update_cmdvel(state)
        self._update_progress(state, proc_status)
        self._update_alerts(state, proc_status)
        self._update_rosout_tail()

    def _update_rosout_tail(self):
        """Render last ~8 WARN/ERROR/FATAL entries from /rosout, with
        consecutive-duplicate counts so a spammy AMCL doesn't drown out
        single-shot errors from other nodes."""
        if not self.app.ros:
            return
        try:
            entries = self.app.ros.get_rosout_tail()
        except Exception:
            entries = []
        if not entries:
            text = "[dim]No warnings/errors yet[/]"
        else:
            level_color = {
                "WARN":  "yellow",
                "ERROR": "red",
                "FATAL": "red bold",
            }
            recent = entries[-8:]
            lines = []
            for entry in recent:
                # Each entry is (level, node, text, count); be defensive
                # to old 3-tuple format in case of mid-restart upgrade.
                if len(entry) == 4:
                    level, node, msg, count = entry
                else:
                    level, node, msg = entry
                    count = 1
                color = level_color.get(level, "white")
                count_str = f" [dim](×{count})[/]" if count > 1 else ""
                lines.append(
                    f"[{color}]{level:<5}[/] "
                    f"[dim]{node[:18]:<18}[/] {msg}{count_str}"
                )
            text = "\n".join(lines)
        try:
            self.query_one("#cov-rosout", Static).update(text)
        except Exception:
            pass

    def _update_pi_services(self):
        # Pi service status is expensive (SSH). Cache between refreshes.
        if not hasattr(self, "_pi_cache_tick"):
            self._pi_cache_tick = 0
            self._pi_cache = {}
        self._pi_cache_tick += 1
        # Refresh every 5 ticks (~5s)
        if self._pi_cache_tick % 5 == 1:
            try:
                self._pi_cache = self.app.pm.pi_all_service_status()
            except Exception:
                self._pi_cache = {}

        if not self._pi_cache:
            text = "[red]Pi unreachable[/]"
        else:
            # Compact rendering: each service on ONE line. The previous
            # `:<22` padding pushed the status off the right edge of the
            # narrow column, wasting half the vertical space to wrapping.
            # Now the dot color implicitly conveys 'active'; status text
            # is shown only when NOT active (tells you the failure mode).
            lines = []
            for svc, status in self._pi_cache.items():
                short = svc.replace("rovac-edge-", "")
                if status == "active":
                    lines.append(f"{GREEN_DOT} [green]{short}[/]")
                else:
                    lines.append(
                        f"{RED_DOT} [red]{short}[/] [dim]({status})[/]")
            text = "\n".join(lines)
        try:
            self.query_one("#cov-pi-services", Static).update(text)
        except Exception:
            pass

    def _update_mac_procs(self, proc_status: dict):
        rows = [
            ("EKF",       "ekf"),
            ("Nav2",      "nav2"),
            ("Foxglove",  "foxglove"),
            ("SLAM",      "slam"),
            ("Tracker",   "tracker"),
            ("Coverage",  "coverage"),
        ]
        # Cross-check Foxglove against actual port-listening cache —
        # process_status's "running" can lie if the bridge crashed
        # but Popen still has a record of it.
        try:
            port_alive = self.app.pm.foxglove_bridge_alive()
        except Exception:
            port_alive = False

        lines = []
        for label, key in rows:
            st = proc_status.get(key, "stopped")
            # Special handling for Foxglove: trust the port check
            if key == "foxglove":
                if port_alive:
                    lines.append(f"{GREEN_DOT} {label:<10} [dim]listening :8765[/]")
                elif st == "running":
                    lines.append(f"{YELLOW_DOT} {label:<10} [yellow]process up, port DOWN[/]")
                elif st.startswith("exited"):
                    lines.append(f"{RED_DOT} {label:<10} [red]{st}[/]")
                else:
                    lines.append(f"{GRAY_DOT} {label:<10} [dim]stopped[/]")
                continue
            if st == "running":
                lines.append(f"{GREEN_DOT} {label:<10} [dim]running[/]")
            elif st == "running (external)":
                lines.append(f"{YELLOW_DOT} {label:<10} [dim]running (not managed)[/]")
            elif st.startswith("exited"):
                lines.append(f"{RED_DOT} {label:<10} [red]{st}[/]")
            else:
                lines.append(f"{GRAY_DOT} {label:<10} [dim]stopped[/]")
        try:
            self.query_one("#cov-mac-procs", Static).update("\n".join(lines))
        except Exception:
            pass

    def _update_nav2_lifecycle(self):
        if not hasattr(self, "_nav_cache_tick"):
            self._nav_cache_tick = 0
            self._nav_cache = {}
        self._nav_cache_tick += 1
        # Lifecycle queries are expensive (8 service calls). Refresh every 6 ticks.
        if self._nav_cache_tick % 6 == 1:
            try:
                self._nav_cache = self.app.pm.query_nav2_lifecycle()
            except Exception:
                self._nav_cache = {}

        if not self._nav_cache:
            text = "[dim]Nav2 not running[/]"
        else:
            lines = []
            for n, state in self._nav_cache.items():
                short = n.lstrip('/')
                if state == "active":
                    lines.append(f"{GREEN_DOT} {short:<18} [dim]{state}[/]")
                elif state == "inactive":
                    lines.append(f"{YELLOW_DOT} {short:<18} [yellow]{state}[/]")
                elif state == "unknown":
                    lines.append(f"{GRAY_DOT} {short:<18} [dim]{state}[/]")
                else:
                    lines.append(f"{RED_DOT} {short:<18} [red]{state}[/]")
            text = "\n".join(lines)
        try:
            self.query_one("#cov-nav2-lifecycle", Static).update(text)
        except Exception:
            pass

    def _update_cmdvel(self, state: dict):
        teleop_hz = state.get("cmd_vel_teleop_hz", 0.0)
        joy_hz = state.get("cmd_vel_joy_hz", 0.0)
        smoothed_hz = state.get("cmd_vel_smoothed_hz", 0.0)
        cmd_hz = state.get("cmd_vel_hz", 0.0)
        active = state.get("mux_active", "?")

        def hz_color(hz: float, expected_quiet: bool = False) -> str:
            if expected_quiet:
                return f"[red]{hz:.1f}[/]" if hz > 0.5 else f"[green]{hz:.1f}[/]"
            return f"[green]{hz:.1f}[/]" if hz > 0.5 else f"[dim]{hz:.1f}[/]"

        text = (
            f"[bold]Mux inputs (priority order):[/]\n"
            f"  1 /cmd_vel_teleop    {hz_color(teleop_hz, expected_quiet=True)} Hz\n"
            f"  2 /cmd_vel_joy       {hz_color(joy_hz, expected_quiet=True)} Hz\n"
            f"  4 /cmd_vel_smoothed  {hz_color(smoothed_hz)} Hz\n"
            f"\n"
            f"[bold]Output to motors:[/]\n"
            f"  /cmd_vel             {hz_color(cmd_hz)} Hz\n"
            f"  active source: [bold]{active}[/]"
        )
        try:
            self.query_one("#cov-cmdvel", Static).update(text)
        except Exception:
            pass

    def _update_progress(self, state: dict, proc_status: dict):
        wp_total = state.get("coverage_total", 0)
        cov_pct = state.get("coverage_pct", 0.0)
        visited = state.get("coverage_visited_cells", 0)
        free = state.get("coverage_free_cells", 0)

        if (proc_status.get("coverage") not in ("running", "running (external)")
                and wp_total == 0):
            text = "[dim]coverage_node not running, no plan yet[/]"
        else:
            text = (
                f"Plan size:    {wp_total} waypoints\n"
                f"Visited:      {visited} / {free} cells\n"
                f"Floor cover:  [bold]{cov_pct:.1f}%[/]"
            )
        try:
            self.query_one("#cov-progress", Static).update(text)
        except Exception:
            pass

    def on_mount(self):
        """Pre-fill map input with the most recently modified map yaml."""
        import os
        try:
            maps = self.app.pm.list_maps()
        except Exception:
            maps = []
        if maps:
            latest = max(maps, key=lambda p: os.path.getmtime(p))
            try:
                self.query_one("#cov-map-input", Input).value = latest
            except Exception:
                pass

    def _update_alerts(self, state: dict, proc_status: dict):
        alerts = []

        # Zombie teleop / joy override (HIGHEST priority — silently breaks runs)
        teleop_hz = state.get("cmd_vel_teleop_hz", 0.0)
        joy_hz = state.get("cmd_vel_joy_hz", 0.0)
        if teleop_hz > 0.5:
            alerts.append(
                f"[red]✗ /cmd_vel_teleop publishing at {teleop_hz:.0f} Hz — "
                "this OVERRIDES Nav2. Press [bold]k[/] to kill zombie teleop.[/]"
            )
        if joy_hz > 0.5:
            alerts.append(
                f"[red]✗ /cmd_vel_joy publishing at {joy_hz:.0f} Hz — "
                "ps2 controller may be active.[/]"
            )

        # Foxglove bridge dead — Foxglove client will show no data
        try:
            fox_alive = self.app.pm.foxglove_bridge_alive()
        except Exception:
            fox_alive = False
        if not fox_alive:
            alerts.append(
                "[yellow]⚠ Foxglove bridge port :8765 not listening — "
                "Foxglove client won't receive data. Press [bold]f[/] to start.[/]"
            )

        # Nav2 lifecycle stuck
        if hasattr(self, "_nav_cache") and self._nav_cache:
            stuck = [n for n, s in self._nav_cache.items()
                     if s not in ("active", "unknown")]
            if stuck:
                names = ", ".join(s.lstrip('/') for s in stuck)
                alerts.append(
                    f"[yellow]⚠ Nav2 nodes not active: {names}. "
                    "Press [bold]l[/] to RESET → STARTUP.[/]"
                )

        # EKF not running but Nav2 wants it
        if (proc_status.get("nav2") == "running"
                and proc_status.get("ekf") not in ("running", "running (external)")):
            alerts.append(
                "[yellow]⚠ Nav2 is running but EKF is not — "
                "Nav2 needs /odometry/filtered. Press [bold]e[/].[/]"
            )

        # Tracker offline during a run
        if (proc_status.get("coverage") in ("running", "running (external)")
                and proc_status.get("tracker") not in ("running", "running (external)")):
            alerts.append(
                "[yellow]⚠ Coverage running without tracker — "
                "no ground-truth visited grid. Press [bold]t[/].[/]"
            )

        text = "\n".join(alerts) if alerts else "[green]✓ No alerts[/]"
        try:
            self.query_one("#cov-alerts", Static).update(text)
        except Exception:
            pass
