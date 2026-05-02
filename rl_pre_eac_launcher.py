#!/usr/bin/env python3
"""
rl_pre_eac_launcher.py
----------------------
Launches the pre-EAC Rocket League build (CL-512269) through legendary,
so the game receives a valid Epic auth handshake at startup. Without
this, the game's `-EpicPortal` arg has nobody to talk to, the auth
silently fails, and the main menu / car selection / Psyonix services
never load — even though freeplay and BakkesMod still work.

This script is meant to be run *after* rl_pre_eac_downloader.py has
already placed a verified pre-EAC install on disk.

What it does:

  1. Confirms `legendary` (the CLI from legendary-gl) is available, and
     finds the right way to invoke it (direct exe, python -m, or the
     entry-point shim that pip drops in a non-PATH directory on
     Microsoft Store Python installs).
  2. Confirms the user is logged in to legendary. If not, runs
     `legendary auth` so they can complete the one-time browser flow.
  3. Loads the install path from a config file, or prompts for it on
     first run and saves it.
  4. Confirms `Sugar` is registered as installed in legendary's
     installed.json. If it isn't, runs `legendary import Sugar <path>
     --disable-check` to register the on-disk install. The --disable-
     check flag is required because legendary fetches the *current*
     Sugar manifest from Epic during import, which describes the
     post-EAC build (with an EasyAntiCheat folder and Launcher.exe).
     Our pre-EAC files won't match that manifest, so without --disable-check the
     import bails.
  5. Launches the game with `legendary launch Sugar --override-exe <exe>
     --skip-version-check`. --skip-version-check is required for the
     same reason: legendary now thinks the latest build is the post-EAC
     one, and would otherwise refuse to launch a "stale" install or
     try to update it.

What it deliberately does NOT do:

  * Does not run `legendary repair` or `legendary update` on Sugar.
    Either of those would replace pre-EAC files with the current build
    and destroy the install.
  * Does not modify legendary's installed.json directly. We let
    legendary's own `import` command write that file, since the schema
    is internal and not promised to be stable.
  * Does not interact with the Epic Games Launcher in any way.

See README.md for the full background on why this is necessary.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import which

try:
    from legendary.core import LegendaryCore
except ImportError:
    sys.exit(
        "ERROR: legendary-gl is not installed.\n"
        "Run: pip install legendary-gl"
    )


# ===== Constants ==========================================================

APP_NAME = "Sugar"
TARGET_EXE_REL = Path("Binaries") / "Win64" / "RocketLeague.exe"
DEFAULT_INSTALL_DIR = Path(r"C:\Games\RocketLegacy")

# Where we keep the per-user config (just the install path right now).
# We use %APPDATA% on Windows so it lives next to other per-user app data
# rather than in the install folder or the script folder.
if sys.platform == "win32":
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "rl_pre_eac"
else:
    CONFIG_DIR = Path.home() / ".config" / "rl_pre_eac"
CONFIG_PATH = CONFIG_DIR / "config.json"


# ===== Locating the legendary CLI =========================================

def find_legendary_cli() -> list[str]:
    """Return the argv prefix that invokes the legendary CLI.

    Tries, in order:
      1. `legendary` on PATH (works for the standalone .exe and for pip
         installs that put the script dir on PATH).
      2. The entry-point shim pip created when `legendary-gl` was
         installed, located via importlib metadata. This is the case
         that breaks on Microsoft Store Python — pip drops the shim in
         a sandboxed Scripts directory that PATH doesn't include.
      3. `python -m legendary` as a final fallback. This works whenever
         the legendary-gl package is importable, even if no shim exists.
    """
    # 1. Already on PATH?
    on_path = which("legendary")
    if on_path:
        return [on_path]

    # 2. Look for the pip-generated shim via the package's entry points.
    try:
        from importlib.metadata import distribution
        dist = distribution("legendary-gl")
        # The 'console_scripts' entry point we want is named 'legendary'.
        # The actual exe/script lives next to it in the same Scripts dir.
        # We don't need to parse the entry point — we just need the
        # Scripts dir path, which we can get from any of the package's
        # installed files.
        scripts_dir = None
        for f in dist.files or []:
            # Look for legendary.exe (Windows) or just legendary (Unix)
            # under any "Scripts" or "bin" directory adjacent to the
            # package.
            name_lower = f.name.lower()
            if name_lower in ("legendary.exe", "legendary"):
                resolved = (dist.locate_file(f)).resolve()
                if resolved.exists():
                    scripts_dir = resolved
                    break
        if scripts_dir is not None:
            return [str(scripts_dir)]
    except Exception:
        # If anything in the metadata lookup fails, just fall through
        # to the python -m fallback.
        pass

    # 3. python -m legendary. We checked at import time that the package
    #    is importable, so this is guaranteed to at least find the
    #    module. It will work for almost everything except commands
    #    that introspect sys.argv[0] expecting a specific name (none of
    #    the commands we use do this).
    return [sys.executable, "-m", "legendary"]


def run_legendary(cli: list[str], *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Invoke the legendary CLI with the given args, streaming output to
    the user's terminal. We don't capture stdout/stderr — legendary's
    progress output (login flow, import progress) is something the user
    needs to see live.
    """
    cmd = list(cli) + list(args)
    print(f"\n>>> {' '.join(cmd)}\n")
    return subprocess.run(cmd, check=check)


# ===== Config =============================================================

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"WARNING: {CONFIG_PATH} is malformed, ignoring it.")
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def prompt_for_install_dir() -> Path:
    """Ask the user where the pre-EAC install lives. We validate that
    the expected RocketLeague.exe is actually under that path before
    accepting the answer — otherwise we'd save a useless config and
    fail later in a more confusing way.
    """
    print()
    print("First-time setup: where is your pre-EAC Rocket League install?")
    print(f"This is the folder you passed to --install-dir when you ran")
    print(f"the downloader. It should contain Binaries\\, TAGame\\, etc.")
    print(f"(Default if you press Enter: {DEFAULT_INSTALL_DIR})")
    print()

    while True:
        raw = input("Install path: ").strip().strip('"').strip("'")
        candidate = Path(raw) if raw else DEFAULT_INSTALL_DIR
        exe_path = candidate / TARGET_EXE_REL
        if exe_path.is_file():
            print(f"OK: found {exe_path}")
            return candidate.resolve()
        print(
            f"  '{exe_path}' does not exist. Make sure you're entering the\n"
            r"  install root (the folder *containing* Binaries\), not the"
            "\n  Win64 folder or the exe itself. Try again, or Ctrl+C to quit."
        )


# ===== Legendary state checks =============================================

def ensure_authenticated(cli: list[str]) -> None:
    """Make sure legendary has a valid stored login. We use the in-process
    LegendaryCore for the check (cheap, no subprocess), and shell out to
    `legendary auth` only if we actually need the interactive browser
    flow.
    """
    core = LegendaryCore()
    try:
        if core.login():
            print("Legendary login: OK (existing credentials valid).")
            return
    except Exception as e:
        # core.login() can raise InvalidCredentialsError when the
        # stored token is no longer accepted. Fall through to the
        # interactive auth flow.
        print(f"Legendary login check failed ({type(e).__name__}): "
              f"running interactive auth.")

    print()
    print("Legendary needs to authenticate against your Epic account.")
    print("A browser window will open for the Epic login flow.")
    print()
    run_legendary(cli, "auth")

    # Re-check after auth.
    core = LegendaryCore()
    if not core.login():
        sys.exit(
            "ERROR: legendary auth completed but credentials are still "
            "not valid. Try running `legendary auth` manually and "
            "investigate from there."
        )


def ensure_owns_sugar(_core_unused=None) -> None:
    """Confirm the authenticated account actually owns Rocket League.
    Without this, the import step would fail later with a less obvious
    error message.
    """
    core = LegendaryCore()
    # core.login() is cheap if creds are already valid (it just refreshes
    # if needed), so calling it again here is fine.
    core.login()
    game = core.get_game(APP_NAME)
    if not game:
        sys.exit(
            f"ERROR: '{APP_NAME}' (Rocket League) is not in this Epic\n"
            f"account's library. You need to claim Rocket League on this\n"
            f"account once before legendary can see it. (Yes, even though\n"
            f"the game is free-to-play.)"
        )


def is_sugar_imported() -> bool:
    """Check legendary's installed.json to see if Sugar already has an
    entry. We use the in-process API rather than parsing the file
    directly so we're not coupled to its schema.
    """
    core = LegendaryCore()
    installed = core.get_installed_game(APP_NAME)
    return installed is not None


def import_sugar(cli: list[str], install_dir: Path) -> None:
    """Register the on-disk install with legendary. --disable-check is
    mandatory: see file docstring for why.
    """
    print()
    print(f"Registering install at {install_dir} with legendary...")
    run_legendary(
        cli,
        "import",
        APP_NAME,
        str(install_dir),
        "--disable-check",
    )
    if not is_sugar_imported():
        sys.exit(
            "ERROR: import command appeared to succeed but Sugar still\n"
            "isn't showing as installed. Something is off — try running\n"
            f"`legendary import Sugar \"{install_dir}\" --disable-check`\n"
            "manually and check its output."
        )
    print("Import: OK.")


# ===== Main ===============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Launch the pre-EAC Rocket League build through legendary "
            "so Epic auth flows correctly and the main menu loads."
        ),
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=None,
        help=(
            "Path to the pre-EAC install root. Overrides the saved "
            "config for this run. If neither this flag nor a saved "
            "config is present, you'll be prompted on first run."
        ),
    )
    parser.add_argument(
        "--reconfigure",
        action="store_true",
        help="Discard the saved install path and prompt for it again.",
    )
    parser.add_argument(
        "--reimport",
        action="store_true",
        help=(
            "Force re-running `legendary import` even if Sugar is "
            "already registered. Use this if you've moved the install."
        ),
    )
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help=(
            "Any additional arguments after `--` are passed straight "
            "through to RocketLeague.exe via legendary."
        ),
    )
    args = parser.parse_args()

    # Resolve install dir: CLI flag > saved config > prompt.
    cfg = load_config()
    if args.reconfigure:
        cfg.pop("install_dir", None)

    if args.install_dir is not None:
        install_dir = args.install_dir.resolve()
    elif "install_dir" in cfg:
        install_dir = Path(cfg["install_dir"])
    else:
        install_dir = prompt_for_install_dir()
        cfg["install_dir"] = str(install_dir)
        save_config(cfg)
        print(f"Saved install path to {CONFIG_PATH}.")

    # Sanity-check the install dir before doing anything expensive.
    exe_path = install_dir / TARGET_EXE_REL
    if not exe_path.is_file():
        sys.exit(
            f"ERROR: {exe_path} does not exist.\n"
            f"Either the install path is wrong (re-run with --reconfigure)\n"
            f"or the install is incomplete (re-run rl_pre_eac_downloader.py)."
        )

    # Locate the legendary CLI we'll be shelling out to.
    cli = find_legendary_cli()

    # Walk through the gates in order: auth, ownership, install registration.
    ensure_authenticated(cli)
    ensure_owns_sugar()

    if args.reimport or not is_sugar_imported():
        import_sugar(cli, install_dir)
    else:
        print("Sugar already imported in legendary: OK.")

    # Build the launch command. --skip-version-check is mandatory; see
    # the file docstring for the explanation.
    launch_args = [
        "launch",
        APP_NAME,
        "--override-exe",
        str(exe_path),
        "--skip-version-check",
    ]

    # Pass through any user-supplied extra args. argparse.REMAINDER
    # leaves a leading "--" in the list if the user used one, so trim
    # it. (Without --, REMAINDER captures everything that doesn't match
    # known flags, which is fine too.)
    extras = list(args.extra_args)
    if extras and extras[0] == "--":
        extras = extras[1:]
    if extras:
        launch_args.extend(extras)

    print()
    print("Launching Rocket League (pre-EAC build)...")
    print("Don't close this window — closing it will close the game.")
    # We let legendary stream its own output. The launch command blocks
    # until the game exits.
    return run_legendary(cli, *launch_args, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
