#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


WCH_DRIVER_PAGE_URL = "https://www.wch-ic.com/downloads/CH34XSER_MAC_ZIP.html"
WCH_DRIVER_DIRECT_URL = "https://www.wch-ic.com/download/file?id=334"
WCH_DRIVER_BUNDLED_ZIP = Path("drivers/macos/CH341SER_MAC.ZIP")
WCH_DRIVER_BUNDLED_ZIP_SHA256 = Path("drivers/macos/CH341SER_MAC.ZIP.sha256")
LINUX_UDEV_RULE_DST = "/etc/udev/rules.d/99-lidar-nano-usb.rules"
LINUX_STABLE_SYMLINK = "/dev/rovac_lidar"

DEFAULT_UDEV_RULES = """# LIDAR Nano USB (CH340) stable symlink
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="rovac_lidar", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5523", SYMLINK+="rovac_lidar", MODE="0666"
"""


@dataclass(frozen=True)
class CommandResult:
    code: int
    stdout: str
    stderr: str


def run_cmd(cmd: list[str], timeout_s: float | None = 20) -> CommandResult:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError as exc:
        return CommandResult(127, "", f"{exc}")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "Timed out")


def lsof_pids(device: str) -> list[int]:
    result = run_cmd(["lsof", device], timeout_s=2)
    if not result.stdout:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pids.append(int(parts[1]))
        except ValueError:
            continue
    return sorted(set(pids))


def lsof_processes(device: str) -> list[dict[str, object]]:
    result = run_cmd(["lsof", device], timeout_s=2)
    if result.code != 0 or not result.stdout:
        return []
    rows: list[dict[str, object]] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        cmd = parts[0]
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        user = parts[2]
        cmdline = None
        ps = run_cmd(["ps", "-p", str(pid), "-o", "command="], timeout_s=2)
        if ps.code == 0 and ps.stdout.strip():
            cmdline = ps.stdout.strip()
        rows.append({"pid": pid, "cmd": cmd, "user": user, "cmdline": cmdline})
    return rows


def pyserial_status() -> tuple[bool, str]:
    try:
        import serial  # noqa: F401

        return True, "pyserial available"
    except Exception as exc:
        return False, f"pyserial missing ({exc})"


def macos_ch34x_driver_status() -> tuple[bool, str]:
    result = run_cmd(["systemextensionsctl", "list"], timeout_s=15)
    if result.code != 0 and not result.stdout:
        return False, f"systemextensionsctl unavailable ({result.stderr.strip() or 'unknown error'})"

    for line in result.stdout.splitlines():
        if "cn.wch.CH34xVCPDriver" not in line:
            continue
        return True, line.strip()
    return False, "cn.wch.CH34xVCPDriver not detected"


def load_udev_rule_text(repo_dir: Path) -> str:
    rule_path = repo_dir / "udev" / "99-lidar-nano-usb.rules"
    if rule_path.exists():
        return rule_path.read_text(encoding="utf-8")
    return DEFAULT_UDEV_RULES


def find_tools(repo_dir: Path) -> dict[str, Path]:
    tools_dir = repo_dir / "tools"
    return {
        "usb_audit": tools_dir / "usb_audit.py",
        "find_port": tools_dir / "find_lidar_port.py",
        "bridge_probe": tools_dir / "bridge_probe.py",
        "xv11_diag": tools_dir / "xv11_diagnostics.py",
    }


def best_effort_open(path: Path) -> tuple[bool, str]:
    if platform.system() == "Darwin":
        result = run_cmd(["open", str(path)], timeout_s=5)
        if result.code == 0:
            return True, "Opened in Installer"
        return False, result.stderr.strip() or "Failed to open"
    return False, "Open not supported on this platform"


def choose_wch_driver_zip_url(page_url: str, html: str) -> str | None:
    links = re.findall(r'href="([^"]+)"', html, flags=re.IGNORECASE)
    zip_links: list[str] = []
    for link in links:
        if not link.lower().endswith(".zip"):
            continue
        absolute = urllib.parse.urljoin(page_url, link)
        zip_links.append(absolute)
    preferred = [u for u in zip_links if "ch34" in u.lower() and "mac" in u.lower()]
    return (preferred[0] if preferred else (zip_links[0] if zip_links else None))


def download_file(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=30) as resp:
        dest.write_bytes(resp.read())


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_expected_sha256(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    match = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    return match.group(0).lower() if match else None


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


def find_first_pkg_or_dmg(search_dir: Path) -> Path | None:
    for ext in (".pkg", ".dmg"):
        matches = sorted(search_dir.rglob(f"*{ext}"))
        if matches:
            return matches[0]
    return None


def cli_fallback(repo_dir: Path) -> int:
    print("LIDAR Nano USB Installer (CLI fallback)")
    print("")
    print("GUI requires tkinter, which is not available in this Python environment.")
    print("")
    print("Recommended next step:")
    print("  ./install_once.sh")
    print("")
    tools = find_tools(repo_dir)
    if tools["usb_audit"].exists():
        print("Safe checks:")
        print(f"  {sys.executable} {tools['usb_audit']}")
    return 1


def prepare_macos_wch_driver(repo_dir: Path, log) -> Path | None:
    bundled_zip = (repo_dir / WCH_DRIVER_BUNDLED_ZIP).resolve()
    bundled_sha = (repo_dir / WCH_DRIVER_BUNDLED_ZIP_SHA256).resolve()

    zip_path: Path | None = None
    if bundled_zip.exists():
        log(f"Using bundled driver zip (offline): {bundled_zip}")
        expected = read_expected_sha256(bundled_sha)
        if expected:
            try:
                actual = sha256sum(bundled_zip)
                if actual != expected:
                    log(f"⚠️  Driver zip SHA256 mismatch (expected {expected}, got {actual}).")
            except OSError as exc:
                log(f"⚠️  Could not hash bundled driver zip: {exc}")
        zip_path = bundled_zip
    else:
        log("Bundled driver zip not found; downloading from WCH...")
        log(f"Source page: {WCH_DRIVER_PAGE_URL}")
        log(f"Direct download: {WCH_DRIVER_DIRECT_URL}")
        temp_dir = Path(tempfile.mkdtemp(prefix="lidar_nano_usb_driver_"))
        zip_path = temp_dir / "wch_ch34x_driver.zip"
        download_file(WCH_DRIVER_DIRECT_URL, zip_path)
        log(f"Downloaded: {zip_path}")

    # Validate that it is a zip.
    try:
        with zipfile.ZipFile(zip_path, "r") as _:
            pass
    except Exception as exc:
        log(f"Download/bundle is not a valid zip: {exc}")
        return None

    extract_dir = Path(tempfile.mkdtemp(prefix="lidar_nano_usb_driver_extracted_"))
    extract_zip(zip_path, extract_dir)
    installer = find_first_pkg_or_dmg(extract_dir)
    if not installer:
        log("Could not find a .pkg or .dmg inside the driver zip.")
        return None
    return installer


def run_cli_checks(repo_dir: Path, debug: bool = False) -> int:
    tools = find_tools(repo_dir)
    platform_name = platform.system()

    print("=== LIDAR Nano USB Installer (CLI) ===")
    print(f"Platform: {platform_name} {platform.release()}")
    print(f"Python: {sys.executable}")

    ok, detail = pyserial_status()
    print(f"pyserial: {'OK' if ok else 'MISSING'} ({detail})")

    if platform_name == "Darwin":
        present, status_line = macos_ch34x_driver_status()
        print(f"CH34x driver: {'OK' if present else 'NOT DETECTED'}")
        print(f"  {status_line}")
        if not present:
            print(f"Download page: {WCH_DRIVER_PAGE_URL}")

    if platform_name == "Linux":
        if os.path.exists(LINUX_STABLE_SYMLINK):
            print(f"{LINUX_STABLE_SYMLINK}: present ({os.path.realpath(LINUX_STABLE_SYMLINK)})")
        else:
            print(f"{LINUX_STABLE_SYMLINK}: not present (optional; install udev rule once)")
            print(f"udev rule dst: {LINUX_UDEV_RULE_DST}")
            rule_src = repo_dir / "udev" / "99-lidar-nano-usb.rules"
            if rule_src.exists():
                print(f"udev rule src: {rule_src}")

    if debug:
        print("")
        print("Tools:")
        for name, path in tools.items():
            print(f"- {name}: {path} ({'exists' if path.exists() else 'missing'})")

    print("")
    print("Next checks:")
    if tools["usb_audit"].exists():
        print(f"  {sys.executable} {tools['usb_audit']}        # safe, no serial reads")
    if tools["find_port"].exists():
        print(f"  {sys.executable} {tools['find_port']}")
    if tools["bridge_probe"].exists():
        print(f"  {sys.executable} {tools['bridge_probe']}     # safe, bounded sample")
    if tools["xv11_diag"].exists():
        print(f"  {sys.executable} {tools['xv11_diag']}        # RPM + basic data quality (bounded)")
    return 0


def main() -> int:
    repo_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="GUI/CLI installer for the LIDAR Nano USB module.")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run checks in the terminal and exit (no GUI).",
    )
    parser.add_argument(
        "--prepare-macos-driver",
        action="store_true",
        help="Prepare the WCH CH34x macOS driver and print the .pkg/.dmg path (macOS only).",
    )
    parser.add_argument(
        "--open-installer",
        action="store_true",
        help="With --prepare-macos-driver: open the resulting installer (.pkg/.dmg).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Extra logging (in GUI: also mirror logs to stdout).",
    )
    args = parser.parse_args()

    if args.prepare_macos_driver:
        if platform.system() != "Darwin":
            print("--prepare-macos-driver is only supported on macOS.", file=sys.stderr)
            return 2
        installer = prepare_macos_wch_driver(repo_dir, log=lambda m: print(m, flush=True))
        if not installer:
            return 3
        print(str(installer))
        if args.open_installer:
            ok, detail = best_effort_open(installer)
            if not ok:
                print(f"Failed to open installer: {detail}", file=sys.stderr)
                return 4
        return 0

    if args.cli:
        return run_cli_checks(repo_dir, debug=args.debug)

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception:
        return cli_fallback(repo_dir)

    class InstallerApp:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.repo_dir = repo_dir
            self.tools = find_tools(repo_dir)
            self.platform = platform.system()
            self.debug = bool(args.debug)
            self.selected_installer: Path | None = None

            self.status_platform = tk.StringVar(value=f"{self.platform} {platform.release()}")
            self.status_pyserial = tk.StringVar(value="Unknown")
            self.status_driver = tk.StringVar(value="—")
            self.status_symlink = tk.StringVar(value="—")
            self.status_port = tk.StringVar(value="—")
            self.status_port_busy = tk.StringVar(value="—")
            self.status_data_flow = tk.StringVar(value="—")
            self.status_rpm = tk.StringVar(value="—")
            self.status_quality = tk.StringVar(value="—")

            self.last_check: dict[str, object] = {}

            self._build_ui()
            self.run_checks()
            self._bring_to_front()

        def _bring_to_front(self) -> None:
            def _activate() -> None:
                try:
                    self.root.update_idletasks()
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                    self.root.attributes("-topmost", True)
                    self.root.after(250, lambda: self.root.attributes("-topmost", False))
                except Exception:
                    pass

            self.root.after(100, _activate)

        def _build_ui(self) -> None:
            self.root.title("LIDAR Nano USB Installer")
            self.root.minsize(760, 520)

            try:
                style = ttk.Style()
                if "clam" in style.theme_names():
                    style.theme_use("clam")
            except Exception:
                pass

            outer = ttk.Frame(self.root, padding=16)
            outer.grid(row=0, column=0, sticky="nsew")
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=1)
            outer.columnconfigure(0, weight=1)

            header = ttk.Frame(outer)
            header.grid(row=0, column=0, sticky="ew")
            header.columnconfigure(0, weight=1)

            ttk.Label(
                header,
                text="LIDAR Nano USB — One-Time Installer",
                font=("Helvetica", 18, "bold"),
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(header, textvariable=self.status_platform).grid(row=1, column=0, sticky="w")

            status = ttk.Labelframe(outer, text="Status", padding=12)
            status.grid(row=1, column=0, sticky="ew", pady=(14, 0))
            status.columnconfigure(1, weight=1)

            ttk.Label(status, text="Python").grid(row=0, column=0, sticky="w")
            ttk.Label(status, text=sys.executable).grid(row=0, column=1, sticky="w")

            ttk.Label(status, text="pyserial").grid(row=1, column=0, sticky="w", pady=(6, 0))
            ttk.Label(status, textvariable=self.status_pyserial).grid(row=1, column=1, sticky="w", pady=(6, 0))

            if self.platform == "Darwin":
                ttk.Label(status, text="CH34x driver").grid(row=2, column=0, sticky="w", pady=(6, 0))
                ttk.Label(status, textvariable=self.status_driver).grid(row=2, column=1, sticky="w", pady=(6, 0))
            elif self.platform == "Linux":
                ttk.Label(status, text="/dev/rovac_lidar").grid(row=2, column=0, sticky="w", pady=(6, 0))
                ttk.Label(status, textvariable=self.status_symlink).grid(row=2, column=1, sticky="w", pady=(6, 0))

            ttk.Label(status, text="Detected port").grid(row=3, column=0, sticky="w", pady=(6, 0))
            ttk.Label(status, textvariable=self.status_port).grid(row=3, column=1, sticky="w", pady=(6, 0))

            ttk.Label(status, text="Port busy").grid(row=4, column=0, sticky="w", pady=(6, 0))
            ttk.Label(status, textvariable=self.status_port_busy).grid(row=4, column=1, sticky="w", pady=(6, 0))

            ttk.Label(status, text="Data flow").grid(row=5, column=0, sticky="w", pady=(6, 0))
            ttk.Label(status, textvariable=self.status_data_flow).grid(row=5, column=1, sticky="w", pady=(6, 0))

            ttk.Label(status, text="RPM").grid(row=6, column=0, sticky="w", pady=(6, 0))
            ttk.Label(status, textvariable=self.status_rpm).grid(row=6, column=1, sticky="w", pady=(6, 0))

            ttk.Label(status, text="Quality").grid(row=7, column=0, sticky="w", pady=(6, 0))
            ttk.Label(status, textvariable=self.status_quality).grid(row=7, column=1, sticky="w", pady=(6, 0))

            actions = ttk.Labelframe(outer, text="Actions", padding=12)
            actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
            actions.columnconfigure(0, weight=1)
            actions.columnconfigure(1, weight=1)
            actions.columnconfigure(2, weight=1)

            ttk.Button(actions, text="Run Checks", command=self.run_checks).grid(row=0, column=0, sticky="ew")
            ttk.Button(actions, text="Install pyserial", command=self.install_pyserial).grid(
                row=0, column=1, sticky="ew", padx=(10, 0)
            )
            ttk.Button(actions, text="Free Port", command=self.free_port).grid(
                row=0, column=2, sticky="ew", padx=(10, 0)
            )

            if self.platform == "Darwin":
                ttk.Button(actions, text="Install CH34x Driver", command=self.download_wch_driver).grid(
                    row=1, column=0, sticky="ew", pady=(10, 0)
                )
                ttk.Button(actions, text="Select Driver (.zip/.pkg)", command=self.select_driver_installer).grid(
                    row=1, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
                )
                ttk.Button(actions, text="Open Selected Installer", command=self.open_selected_installer).grid(
                    row=1, column=2, sticky="ew", padx=(10, 0), pady=(10, 0)
                )
            elif self.platform == "Linux":
                ttk.Button(actions, text="Install udev Rule", command=self.install_udev_rule).grid(
                    row=1, column=0, sticky="ew", pady=(10, 0)
                )
                ttk.Button(actions, text="Re-check Symlink", command=self.run_checks).grid(
                    row=1, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
                )

            ttk.Button(actions, text="Run Safe Probe", command=self.run_probe).grid(
                row=2, column=0, sticky="ew", pady=(10, 0)
            )
            ttk.Button(actions, text="Run USB Audit", command=self.run_usb_audit).grid(
                row=2, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
            )
            ttk.Button(actions, text="Live RPM (10s)", command=self.live_rpm).grid(
                row=2, column=2, sticky="ew", padx=(10, 0), pady=(10, 0)
            )
            ttk.Button(actions, text="Run Diagnostics", command=self.run_diagnostics).grid(
                row=3, column=0, sticky="ew", pady=(10, 0)
            )
            ttk.Button(actions, text="Capture Raw…", command=self.capture_raw).grid(
                row=3, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
            )
            ttk.Button(actions, text="Save Report…", command=self.save_report).grid(
                row=3, column=2, sticky="ew", padx=(10, 0), pady=(10, 0)
            )

            log_frame = ttk.Labelframe(outer, text="Log", padding=0)
            log_frame.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
            outer.rowconfigure(3, weight=1)

            self.log_text = tk.Text(log_frame, height=14, wrap="word", state="disabled")
            self.log_text.grid(row=0, column=0, sticky="nsew")
            log_frame.rowconfigure(0, weight=1)
            log_frame.columnconfigure(0, weight=1)

            scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            self.log_text.configure(yscrollcommand=scroll.set)

            footer = ttk.Frame(outer)
            footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
            footer.columnconfigure(0, weight=1)
            ttk.Label(
                footer,
                text=(
                    "Note: CH340-based devices can’t be fully driverless on macOS. "
                    "This installer guides the one-time driver setup and config checks."
                ),
                foreground="#444",
            ).grid(row=0, column=0, sticky="w")

        def _ui(self, fn) -> None:
            self.root.after(0, fn)

        def log(self, message: str) -> None:
            if self.debug:
                print(message, flush=True)

            def _append() -> None:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", message.rstrip() + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")

            self._ui(_append)

        def _run_async(self, label: str, fn) -> None:
            def worker() -> None:
                self.log(f"--- {label} ---")
                try:
                    fn()
                except Exception as exc:
                    self.log(f"ERROR: {exc}")
                    self._ui(lambda: messagebox.showerror("Installer Error", str(exc)))

            threading.Thread(target=worker, daemon=True).start()

        def run_checks(self) -> None:
            def _checks() -> None:
                ok, detail = pyserial_status()
                self._ui(lambda: self.status_pyserial.set("OK" if ok else f"Missing ({detail})"))
                self.last_check = {"pyserial": {"ok": ok, "detail": detail, "python": sys.executable}}

                if not ok:
                    self._ui(lambda: self.status_port.set("— (pyserial missing)"))
                    self._ui(lambda: self.status_port_busy.set("—"))
                    self._ui(lambda: self.status_data_flow.set("—"))
                    self._ui(lambda: self.status_rpm.set("—"))
                    self._ui(lambda: self.status_quality.set("—"))
                    return

                if self.platform == "Darwin":
                    present, status_line = macos_ch34x_driver_status()
                    self._ui(lambda: self.status_driver.set(status_line))
                    self.last_check["macos_driver"] = {
                        "present": present,
                        "status": status_line,
                    }
                    if present:
                        self.log("✓ macOS CH34x DriverKit extension detected.")
                    else:
                        self.log("⚠️  macOS CH34x driver not detected. Install once, then re-plug the device.")
                        self.log(f"Download page: {WCH_DRIVER_PAGE_URL}")

                if self.platform == "Linux":
                    if os.path.exists(LINUX_STABLE_SYMLINK):
                        self._ui(lambda: self.status_symlink.set(f"Present ({os.path.realpath(LINUX_STABLE_SYMLINK)})"))
                        self.last_check["linux_symlink"] = {
                            "present": True,
                            "path": LINUX_STABLE_SYMLINK,
                            "resolved": os.path.realpath(LINUX_STABLE_SYMLINK),
                        }
                        self.log(f"✓ {LINUX_STABLE_SYMLINK} present.")
                    else:
                        self._ui(lambda: self.status_symlink.set("Not present"))
                        self.last_check["linux_symlink"] = {
                            "present": False,
                            "path": LINUX_STABLE_SYMLINK,
                        }
                        self.log(f"ℹ️  {LINUX_STABLE_SYMLINK} not present (optional: install udev rule).")

                # Detect the most likely port and do a quick bounded sample (only if port is free).
                port_info = self._run_tool_json(self.tools["find_port"], [], timeout_s=10)
                if not port_info or not port_info.get("found"):
                    self._ui(lambda: self.status_port.set("Not found"))
                    self._ui(lambda: self.status_port_busy.set("—"))
                    self._ui(lambda: self.status_data_flow.set("—"))
                    self._ui(lambda: self.status_rpm.set("—"))
                    self._ui(lambda: self.status_quality.set("—"))
                    self.last_check["port"] = {"found": False}
                    return

                device = str(port_info.get("device"))
                resolved = port_info.get("resolved_device")
                self.last_check["port"] = port_info
                if resolved:
                    self._ui(lambda: self.status_port.set(f"{device} → {resolved}"))
                else:
                    self._ui(lambda: self.status_port.set(device))

                pids = lsof_pids(device)
                if pids:
                    self._ui(lambda: self.status_port_busy.set(f"Yes (pids: {', '.join(map(str, pids))})"))
                    self._ui(lambda: self.status_data_flow.set("Skipped (busy)"))
                    self._ui(lambda: self.status_rpm.set("—"))
                    self._ui(lambda: self.status_quality.set("—"))
                    self.last_check["port_busy_pids"] = pids
                    for p in lsof_processes(device)[:6]:
                        self.log(f"Busy: PID {p.get('pid')} {p.get('cmdline') or p.get('cmd')}")
                    return

                self._ui(lambda: self.status_port_busy.set("No"))
                self.last_check["port_busy_pids"] = []

                probe = self._run_tool_json(
                    self.tools["bridge_probe"],
                    ["--port", device, "--sample-seconds", "0.5"],
                    timeout_s=10,
                )
                if not probe:
                    self._ui(lambda: self.status_data_flow.set("Unknown"))
                    self._ui(lambda: self.status_rpm.set("—"))
                    self._ui(lambda: self.status_quality.set("—"))
                    return

                self.last_check["quick_probe"] = probe
                bytes_received = probe.get("bytes_received") or 0
                candidates = probe.get("header_index_candidates") or 0
                rpm = probe.get("rpm_est")
                rpm_method = probe.get("rpm_est_method")
                ratio = None
                if bytes_received:
                    expected = bytes_received / 22.0
                    if expected > 0:
                        ratio = (candidates / expected) if candidates else 0.0
                if bytes_received and candidates:
                    flow = f"OK ({candidates} hdr/index)"
                    if ratio is not None:
                        flow += f", {ratio*100:.0f}% sync"
                    self._ui(lambda: self.status_data_flow.set(flow))
                elif bytes_received:
                    self._ui(lambda: self.status_data_flow.set("Bytes only (no hdr/index)"))
                else:
                    self._ui(lambda: self.status_data_flow.set("No data"))
                if isinstance(rpm, (int, float)):
                    self._ui(lambda: self.status_rpm.set(f"{rpm:.1f} ({rpm_method})" if rpm_method else f"{rpm:.1f}"))
                else:
                    self._ui(lambda: self.status_rpm.set("—"))
                if ratio is not None:
                    grade = "GOOD" if ratio >= 0.8 else ("WARN" if ratio >= 0.6 else "BAD")
                    self._ui(lambda: self.status_quality.set(f"{grade} ({ratio*100:.0f}% sync)"))
                else:
                    self._ui(lambda: self.status_quality.set("—"))

            self._run_async("Checks", _checks)

        def _ask_yesno(self, title: str, message: str) -> bool:
            decision: dict[str, bool] = {}
            event = threading.Event()

            def _ask() -> None:
                decision["value"] = bool(messagebox.askyesno(title, message))
                event.set()

            self._ui(_ask)
            event.wait()
            return bool(decision.get("value", False))

        def _get_detected_device(self) -> str | None:
            port = self.last_check.get("port")
            if isinstance(port, dict):
                dev = port.get("device")
                if isinstance(dev, str) and dev.strip():
                    return dev
            return None

        def free_port(self) -> None:
            def _free() -> None:
                device = self._get_detected_device()
                if not device:
                    self.log("No detected port available. Run 'Run Checks' first.")
                    return
                procs = lsof_processes(device)
                if not procs:
                    self.log(f"No processes currently holding: {device}")
                    return
                lines = []
                for p in procs:
                    pid = p.get("pid")
                    cmdline = p.get("cmdline") or p.get("cmd")
                    user = p.get("user")
                    lines.append(f"- PID {pid} ({user}): {cmdline}")
                message = (
                    f"The following processes are holding {device}:\n\n"
                    + "\n".join(lines[:10])
                    + ("\n\nKill them now?" if len(lines) <= 10 else "\n\n(Showing first 10)\n\nKill them now?")
                )
                if not self._ask_yesno("Free Port", message):
                    self.log("Canceled.")
                    return
                pids = [str(p["pid"]) for p in procs if isinstance(p.get("pid"), int)]
                if not pids:
                    self.log("No valid PIDs found to kill.")
                    return
                self.log("Sending SIGTERM: " + ", ".join(pids))
                run_cmd(["kill", "-TERM", *pids], timeout_s=5)
                time.sleep(0.5)
                still = lsof_pids(device)
                if still:
                    self.log("Still holding. Sending SIGKILL: " + ", ".join(map(str, still)))
                    run_cmd(["kill", "-KILL", *[str(pid) for pid in still]], timeout_s=5)
                self.run_checks()

            self._run_async("Free port", _free)

        def live_rpm(self) -> None:
            def _live() -> None:
                ok, detail = pyserial_status()
                if not ok:
                    self.log(f"pyserial missing; cannot run live RPM ({detail}).")
                    return
                device = self._get_detected_device()
                if not device:
                    port_info = self._run_tool_json(self.tools["find_port"], [], timeout_s=10) or {}
                    device = port_info.get("device") if isinstance(port_info, dict) else None
                if not device:
                    self.log("No port detected.")
                    return
                if lsof_pids(device):
                    self.log("Port is busy; use 'Free Port' or close the holding process first.")
                    return
                rpms: list[float] = []
                for i in range(10):
                    probe = self._run_tool_json(
                        self.tools["bridge_probe"],
                        ["--port", device, "--sample-seconds", "1.0"],
                        timeout_s=12,
                    )
                    if not probe:
                        self.log("Probe failed.")
                        break
                    rpm = probe.get("rpm_est")
                    method = probe.get("rpm_est_method")
                    if isinstance(rpm, (int, float)):
                        rpms.append(float(rpm))
                        self.log(f"t+{i+1:02d}s: {rpm:.1f} RPM ({method})")
                    else:
                        self.log(f"t+{i+1:02d}s: RPM unavailable")
                if rpms:
                    import statistics

                    med = statistics.median(rpms)
                    stdev = statistics.pstdev(rpms) if len(rpms) > 1 else 0.0
                    self.log(f"Live RPM summary: median={med:.1f}, stdev={stdev:.1f} (n={len(rpms)})")

            self._run_async("Live RPM", _live)

        def install_pyserial(self) -> None:
            def _install() -> None:
                ok, _ = pyserial_status()
                if ok:
                    self.log("pyserial already installed.")
                    return
                cmd = [sys.executable, "-m", "pip", "install", "--user", "pyserial"]
                self.log("Running: " + " ".join(cmd))
                result = run_cmd(cmd, timeout_s=300)
                if result.stdout.strip():
                    self.log(result.stdout.rstrip())
                if result.stderr.strip():
                    self.log(result.stderr.rstrip())
                if result.code == 0:
                    self.log("✓ Installed pyserial.")
                else:
                    self.log("⚠️  Failed to install pyserial. You may need to install it manually.")
                self.run_checks()

            self._run_async("Install pyserial", _install)

        def download_wch_driver(self) -> None:
            if self.platform != "Darwin":
                messagebox.showinfo("Not Supported", "Driver download is only available on macOS.")
                return

            def _download() -> None:
                candidate = prepare_macos_wch_driver(self.repo_dir, log=self.log)
                if not candidate:
                    self.log("Could not prepare the WCH driver bundle automatically.")
                    self.log(f"Manual download page: {WCH_DRIVER_PAGE_URL}")
                    return

                self.selected_installer = candidate
                self.log(f"Selected installer: {candidate}")
                ok, detail = best_effort_open(candidate)
                if ok:
                    self.log("Installer opened. Complete installation, then click 'Run Checks' again.")
                else:
                    self.log(f"Failed to open installer: {detail}")

            self._run_async("Install CH34x driver", _download)

        def select_driver_installer(self) -> None:
            if self.platform != "Darwin":
                messagebox.showinfo("Not Supported", "Driver selection is only available on macOS.")
                return
            path = filedialog.askopenfilename(
                title="Select CH34x driver installer (.pkg, .dmg, or .zip)",
                filetypes=[
                    ("Driver installers", "*.pkg *.dmg *.zip"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return
            selected = Path(path).expanduser().resolve()
            self.selected_installer = selected
            self.log(f"Selected: {selected}")

            if selected.suffix.lower() == ".zip":
                try:
                    temp_dir = Path(tempfile.mkdtemp(prefix="lidar_nano_usb_driver_"))
                    extract_dir = temp_dir / "extracted"
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    self.log(f"Extracting zip to: {extract_dir}")
                    extract_zip(selected, extract_dir)
                    candidate = find_first_pkg_or_dmg(extract_dir)
                    if not candidate:
                        messagebox.showwarning(
                            "No Installer Found",
                            "Could not find a .pkg or .dmg inside this zip file.",
                        )
                        return
                    self.selected_installer = candidate
                    self.log(f"Selected installer from zip: {candidate}")
                except Exception as exc:
                    messagebox.showerror("Zip Error", str(exc))

        def open_selected_installer(self) -> None:
            if self.platform != "Darwin":
                messagebox.showinfo("Not Supported", "Open installer is only available on macOS.")
                return
            if not self.selected_installer:
                messagebox.showinfo("No Selection", "Select a driver installer first.")
                return
            ok, detail = best_effort_open(self.selected_installer)
            if ok:
                self.log("Installer opened. Complete installation, then click 'Run Checks' again.")
            else:
                messagebox.showerror("Open Failed", detail)

        def install_udev_rule(self) -> None:
            if self.platform != "Linux":
                messagebox.showinfo("Not Supported", "udev rule install is only available on Linux.")
                return

            def _install() -> None:
                rule_text = load_udev_rule_text(self.repo_dir)
                try:
                    Path(LINUX_UDEV_RULE_DST).write_text(rule_text, encoding="utf-8")
                    self.log(f"✓ Wrote udev rule: {LINUX_UDEV_RULE_DST}")
                except PermissionError:
                    self.log("⚠️  Permission denied writing udev rule.")
                    self.log("Re-run this installer as root, or run these commands:")
                    src = self.repo_dir / "udev" / "99-lidar-nano-usb.rules"
                    self.log(f"  sudo cp {src} {LINUX_UDEV_RULE_DST}")
                    self.log("  sudo udevadm control --reload-rules")
                    self.log("  sudo udevadm trigger")
                    return

                reload_result = run_cmd(["udevadm", "control", "--reload-rules"], timeout_s=15)
                trigger_result = run_cmd(["udevadm", "trigger"], timeout_s=15)
                if reload_result.code == 0 and trigger_result.code == 0:
                    self.log("✓ Reloaded udev rules.")
                else:
                    self.log("ℹ️  Could not reload udev rules automatically. You may need:")
                    self.log("  sudo udevadm control --reload-rules")
                    self.log("  sudo udevadm trigger")
                self.run_checks()

            self._run_async("Install udev rule", _install)

        def _run_tool(self, path: Path, args: list[str], timeout_s: float = 30) -> CommandResult | None:
            if not path.exists():
                self.log(f"Tool not found: {path}")
                return None
            cmd = [sys.executable, str(path), *args]
            self.log("Running: " + " ".join(cmd))
            result = run_cmd(cmd, timeout_s=timeout_s)
            if result.stdout.strip():
                self.log(result.stdout.rstrip())
            if result.stderr.strip():
                self.log(result.stderr.rstrip())
            return result

        def _run_tool_json(self, path: Path, args: list[str], timeout_s: float = 30) -> dict | None:
            if not path.exists():
                self.log(f"Tool not found: {path}")
                return None

            full_args = list(args)
            if "--json" not in full_args:
                full_args.append("--json")

            cmd = [sys.executable, str(path), *full_args]
            self.log("Running: " + " ".join(cmd))
            result = run_cmd(cmd, timeout_s=timeout_s)
            if result.stderr.strip():
                self.log(result.stderr.rstrip())
            raw = result.stdout.strip()
            if not raw:
                self.log("No output from tool.")
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                self.log("Failed to parse JSON output from tool.")
                self.log(raw[:5000])
                return None

        def run_probe(self) -> None:
            def _probe() -> None:
                ok, detail = pyserial_status()
                if not ok:
                    self.log(f"pyserial missing; cannot run probe ({detail}).")
                    return
                probe = self._run_tool_json(self.tools["bridge_probe"], ["--handshake"], timeout_s=20)
                if not probe:
                    return
                self.last_check["probe"] = probe

                device = probe.get("device")
                if device:
                    self._ui(lambda: self.status_port.set(str(device)))

                if probe.get("busy"):
                    busy_pids = probe.get("busy_pids") or []
                    self._ui(
                        lambda: self.status_port_busy.set(
                            f"Yes (pids: {', '.join(map(str, busy_pids))})" if busy_pids else "Yes"
                        )
                    )
                    self._ui(lambda: self.status_data_flow.set("Skipped (busy)"))
                    self._ui(lambda: self.status_rpm.set("—"))
                    self._ui(lambda: self.status_quality.set("—"))
                else:
                    self._ui(lambda: self.status_port_busy.set("No"))

                bytes_received = probe.get("bytes_received") or 0
                candidates = probe.get("header_index_candidates") or 0
                rpm = probe.get("rpm_est")
                rpm_method = probe.get("rpm_est_method")
                ratio = None
                if bytes_received:
                    expected = bytes_received / 22.0
                    if expected > 0:
                        ratio = (candidates / expected) if candidates else 0.0
                if bytes_received and candidates:
                    flow = f"OK ({candidates} hdr/index)"
                    if ratio is not None:
                        flow += f", {ratio*100:.0f}% sync"
                    self._ui(lambda: self.status_data_flow.set(flow))
                elif bytes_received:
                    self._ui(lambda: self.status_data_flow.set("Bytes only (no hdr/index)"))
                else:
                    self._ui(lambda: self.status_data_flow.set("No data"))

                if isinstance(rpm, (int, float)):
                    self._ui(lambda: self.status_rpm.set(f"{rpm:.1f} ({rpm_method})" if rpm_method else f"{rpm:.1f}"))
                    self.log(f"Probe: {bytes_received} bytes, {candidates} hdr/index, ~{rpm:.1f} RPM ({rpm_method})")
                else:
                    self._ui(lambda: self.status_rpm.set("—"))
                    self.log(f"Probe: {bytes_received} bytes, {candidates} hdr/index")

                if ratio is not None:
                    grade = "GOOD" if ratio >= 0.8 else ("WARN" if ratio >= 0.6 else "BAD")
                    self._ui(lambda: self.status_quality.set(f"{grade} ({ratio*100:.0f}% sync)"))
                else:
                    self._ui(lambda: self.status_quality.set("—"))

                for k in ("firmware_id", "firmware_version", "firmware_status", "firmware_baud"):
                    v = probe.get(k)
                    if v:
                        self.log(f"{k}: {v}")

                for line in probe.get("ascii_bang_lines") or []:
                    self.log(f"ASCII: {line}")

                for note in probe.get("notes") or []:
                    self.log(f"Note: {note}")

            self._run_async("Safe probe", _probe)

        def run_usb_audit(self) -> None:
            def _audit() -> None:
                ok, detail = pyserial_status()
                if not ok:
                    self.log(f"pyserial missing; cannot run usb audit ({detail}).")
                    return
                audit = self._run_tool_json(self.tools["usb_audit"], [], timeout_s=20)
                if not audit:
                    return
                self.last_check["usb_audit"] = audit

                candidates = audit.get("candidates") or []
                if candidates:
                    first = candidates[0]
                    dev = first.get("device")
                    vid = first.get("vid")
                    pid = first.get("pid")
                    if dev:
                        self._ui(lambda: self.status_port.set(str(dev)))
                    if vid and pid:
                        self.log(f"Candidate: {dev} ({vid}:{pid})")
                    if len(candidates) > 1:
                        self.log(f"Candidates: {len(candidates)} ports")
                else:
                    self.log("No CH340-style candidate ports detected.")

                if self.platform == "Darwin":
                    md = audit.get("macos_driver")
                    if isinstance(md, dict) and md.get("state"):
                        self._ui(lambda: self.status_driver.set(str(md.get("state"))))

                assessment = audit.get("assessment")
                if assessment:
                    self.log(f"Assessment: {assessment}")

            self._run_async("USB audit", _audit)

        def run_diagnostics(self) -> None:
            def _diag() -> None:
                ok, detail = pyserial_status()
                if not ok:
                    self.log(f"pyserial missing; cannot run diagnostics ({detail}).")
                    return
                if not self.tools["xv11_diag"].exists():
                    self.log(f"Tool not found: {self.tools['xv11_diag']}")
                    return
                diag = self._run_tool_json(self.tools["xv11_diag"], ["--seconds", "10"], timeout_s=40)
                if not diag:
                    return
                self.last_check["xv11_diag"] = diag

                packets = diag.get("packets_total")
                rpm = diag.get("rpm_est")
                rpm_method = diag.get("rpm_est_method")
                quality_grade = diag.get("quality_grade")
                quality_score = diag.get("quality_score")
                hdr_ratio = diag.get("header_recognition_ratio")
                bytes_per_s = diag.get("bytes_per_s")
                invalid = diag.get("measurements_invalid")
                total = diag.get("measurements_total")
                missing = diag.get("missing_indexes")

                if isinstance(packets, int):
                    self._ui(lambda: self.status_data_flow.set(f"OK ({packets} pkts/10s)" if packets else "No packets"))
                if isinstance(rpm, (int, float)):
                    self._ui(lambda: self.status_rpm.set(f"{rpm:.1f} ({rpm_method})" if rpm_method else f"{rpm:.1f}"))
                    self.log(f"RPM (best): {rpm:.1f} ({rpm_method})")
                else:
                    self._ui(lambda: self.status_rpm.set("—"))
                if isinstance(quality_score, int) and isinstance(quality_grade, str):
                    self._ui(lambda: self.status_quality.set(f"{quality_grade} ({quality_score}/100)"))
                elif isinstance(hdr_ratio, (int, float)):
                    grade = "GOOD" if hdr_ratio >= 0.8 else ("WARN" if hdr_ratio >= 0.6 else "BAD")
                    self._ui(lambda: self.status_quality.set(f"{grade} ({hdr_ratio*100:.0f}% hdr sync)"))
                else:
                    self._ui(lambda: self.status_quality.set("—"))
                if bytes_per_s:
                    self.log(f"Data rate: {bytes_per_s:.0f} B/s")
                if isinstance(invalid, int) and isinstance(total, int) and total:
                    self.log(f"Invalid measurements: {invalid}/{total} ({(invalid/total)*100:.1f}%)")
                if isinstance(missing, int):
                    self.log(f"Missing indexes (in sample): {missing}")
                if isinstance(hdr_ratio, (int, float)):
                    self.log(f"Header/index recognition: {hdr_ratio*100:.1f}%")
                if isinstance(quality_score, int) and isinstance(quality_grade, str):
                    self.log(f"Quality: {quality_grade} ({quality_score}/100)")

                d50 = diag.get("distance_mm_p50")
                d90 = diag.get("distance_mm_p90")
                if isinstance(d50, (int, float)) or isinstance(d90, (int, float)):
                    self.log(f"Distance (mm): p50={d50:.0f} p90={d90:.0f}" if d50 and d90 else f"Distance: p50={d50} p90={d90}")

                s50 = diag.get("signal_p50")
                if isinstance(s50, (int, float)):
                    self.log(f"Signal p50: {s50:.0f}")

                for line in diag.get("ascii_bang_lines") or []:
                    self.log(f"ASCII: {line}")

                for note in diag.get("notes") or []:
                    self.log(f"Note: {note}")

            self._run_async("Diagnostics", _diag)

        def capture_raw(self) -> None:
            def _capture(path: str) -> None:
                ok, detail = pyserial_status()
                if not ok:
                    self.log(f"pyserial missing; cannot capture ({detail}).")
                    return
                diag = self._run_tool_json(
                    self.tools["xv11_diag"],
                    ["--seconds", "10", "--write-raw", path],
                    timeout_s=50,
                )
                if diag:
                    self.last_check["xv11_raw_capture"] = {"path": path, "result": diag}
                    self.log(f"Raw capture saved: {path}")

            if not self.tools["xv11_diag"].exists():
                messagebox.showinfo("Not Supported", "Diagnostics tool not found.")
                return
            path = filedialog.asksaveasfilename(
                title="Save raw XV11 capture",
                defaultextension=".bin",
                filetypes=[("Binary", "*.bin"), ("All files", "*.*")],
            )
            if not path:
                return
            self._run_async("Capture raw", lambda: _capture(path))

        def save_report(self) -> None:
            def _save(path: str) -> None:
                report: dict[str, object] = {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "platform": self.platform,
                    "python": sys.executable,
                }
                ok, detail = pyserial_status()
                report["pyserial"] = {"ok": ok, "detail": detail}

                if self.platform == "Darwin":
                    present, status_line = macos_ch34x_driver_status()
                    report["macos_driver"] = {"present": present, "status": status_line}
                if self.platform == "Linux":
                    report["linux_symlink"] = {
                        "path": LINUX_STABLE_SYMLINK,
                        "present": os.path.exists(LINUX_STABLE_SYMLINK),
                        "resolved": os.path.realpath(LINUX_STABLE_SYMLINK) if os.path.exists(LINUX_STABLE_SYMLINK) else None,
                    }

                if ok:
                    report["find_port"] = self._run_tool_json(self.tools["find_port"], [], timeout_s=10)
                    report["usb_audit"] = self._run_tool_json(self.tools["usb_audit"], [], timeout_s=20)
                    report["probe"] = self._run_tool_json(
                        self.tools["bridge_probe"], ["--handshake", "--sample-seconds", "1.0"], timeout_s=25
                    )
                    if self.tools["xv11_diag"].exists():
                        report["xv11_diag"] = self._run_tool_json(
                            self.tools["xv11_diag"], ["--seconds", "5"], timeout_s=30
                        )

                Path(path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
                self.log(f"Saved report: {path}")

            path = filedialog.asksaveasfilename(
                title="Save installer report (JSON)",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return
            self._run_async("Save report", lambda: _save(path))

    print("Launching GUI installer... (close the window to exit)", flush=True)
    try:
        root = tk.Tk()
    except Exception as exc:
        print(f"Failed to start GUI: {exc}", file=sys.stderr)
        print("Tip: run in terminal mode: ./install_ui.py --cli", file=sys.stderr)
        return 1
    app = InstallerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
