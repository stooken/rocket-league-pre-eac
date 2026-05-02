# Rocket League Pre-EAC Recovery (EGS Version)

A pair of standalone Python tools that download and launch the **pre Easy-Anti-Cheat build of Rocket League** (`++Prime+Update58-CL-512269`, the build that shipped prior to April 28, 2026 and is compatible with the last BakkesMod release) directly from Epic's CDN, using a saved manifest file.

I created this tool because I mistakenly updated without backing up the files, and therefore lost my ability to train with BakkesMod. With (in my opinion) much more options in terms of training, it was pretty shocking seeing how lacking vanilla Rocket League's options truly were. From that disappointment, this program was created. Legendary CLI was giving me problems with overriding the manifest, hence why that was not just used instead.

There's a chance that I was simply misusing [legendary](https://github.com/derrod/legendary), or a minor bug due to powershell being.... powershell. If this seems like it may be too complicated (I can promise you it isn't), then that may be of use to you. It's still CLI though, and this tool has a more directed purpose.

---

## What's in this repo

| File                          | What it does                                                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `rl_pre_eac_downloader.py`    | Downloads the pre-EAC game files from Epic's CDN. Run this once.                                                                          |
| `rl_pre_eac_launcher.py`      | Launches the game with the correct Epic auth handshake so the main menu loads. Run this every time you want to play.                      |
| `rl_pre_eac.manifest`         | The saved pre-EAC manifest file. The downloader needs this as input.                                                                      |
| `requirements.txt`            | Python dependencies for both scripts.                                                                                                     |

The scripts can live **anywhere on your system** — Desktop, Documents, a tools folder, wherever. They don't care where they are. The only path that matters is where you install the game files, and the launcher remembers that for you after first run.

---

## What this is for

- Playing Rocket League **offline** — main menu, freeplay, custom training, and custom maps all work via the included launcher script.
- Running **BakkesMod** and its plugin ecosystem on a clean, unmodified pre-EAC install.
- Preserving access to a version of the game licensed to your account, after Epic replaced it.

## What this is *not* for

- Online play. The pre-EAC build cannot queue for online matches. Psyonix's matchmaker requires EAC clients, and up-to-date builds. This tool is not designed to enable online play or cheating, and should not be used to attempt either.
- Bypassing ownership. You need a Rocket League license on your own Epic Games account. The tool authenticates as you and pulls game files from Epic's CDN through that account.
- Distributing game files. This tool downloads files for *your* account from Epic's servers. It does not redistribute Psyonix or Epic content.

This tool is for people who specifically want a clean separate install of the pre-EAC build.

---

## Requirements

### Software

- **Windows** (the script writes Windows-style paths, Linux is a WIP, updates to come)
- **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/) — make sure to tick "Add to PATH" during install)
- The Python packages listed in `requirements.txt`:
  ```
  legendary-gl
  requests
  tqdm
  ```
- **[legendary](https://github.com/derrod/legendary)** authenticated to your Epic account. The launcher script will run `legendary auth` for you on first launch if you haven't already, but you can also do it manually with `legendary auth` ahead of time. Credentials are stored in `%USERPROFILE%\.config\legendary\` and both scripts read them from there.

### Account

- Your Epic Games account must own Rocket League. The tools will not let you download or launch a game you don't own.

### The manifest file

**The downloader requires a saved copy of the pre-EAC manifest file.** It's what enables us to download this older version. Epic doesn't publicly archive previous build manifests, thankfully though, I was able to get into contact with someone kind enough to send over their manifest file.

By default, **the downloader will only run on the canonical manifest distributed alongside this tool**, identified by SHA-1 and SHA-256. If your manifest doesn't match either hash, the script will refuse to run and tell you exactly which hash it saw vs. expected. You can override this with `--accept-different-manifest` if you have a manifest from a different verified source, but you take on the responsibility of vetting it yourself in that case.

A correct manifest will have these properties:

| Property | Value |
|---|---|
| File size | 4,142,465 bytes |
| SHA-1 of file | `C3B8E170AA9DD01848B0F31ECD354BC011CB47AA` |
| SHA-256 of file | `B4D2CF205224FA9079E94351FBD8F6F7422324D71D16749FA9F94F0857EB4454` |
| Build version (inside body) | `++Prime+Update58-CL-512269` |
| Epic AppName used by the downloader | `Sugar` (Rocket League's Epic AppName for CDN lookup) |

You can verify a candidate manifest with:

```powershell
Get-FileHash "path\to\manifest" -Algorithm SHA1
Get-FileHash "path\to\manifest" -Algorithm SHA256
```

---

## Installation

Before we begin with the text installation, here is a YouTube video walking you through the downloader. The description also contains a very concise step-by-step text tutorial on what to do if you want to just download ASAP and don't care for the technical stuff. The actual time spent setting things up only takes maybe ~3 minutes. The reason the video is 16 Minutes is because I left it completely uncut. I did this so a user can see exactly what happens at each step of the script, and what the download itself looks like. [Here](https://www.youtube.com/watch?v=qwOsRcCXEjM) is the link to that video. I am currently working on cutting it down for a more concise version for those who just want to go ahead and download ASAP.

> **Note:** The video covers the downloader. The launcher script is newer than the video — see the "After the install" section below for how to use it.

```powershell
# Clone or download this repo, cd into it
pip install -r requirements.txt
```

That's it for installation. You don't need to manually run `legendary auth` — the launcher will prompt you for it on first run if your account isn't authenticated yet.

---

## Step 1: Download the game files

```powershell
python rl_pre_eac_downloader.py `
    --manifest "C:\path\to\rl_pre_eac.manifest" `
    --install-dir "C:\Games\RocketLegacy"
```

### Flags

| Flag                            | Purpose                                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `--manifest <path>`             | Path to your pre-EAC manifest file (required)                                                                                         |
| `--install-dir <path>`          | Where to install. Use a path **outside** `C:\Program Files\Epic Games\` so the Epic launcher can't touch it.                          |
| `--workers N`                   | Parallel download workers (1 to 64, default 16) (advanced)                                                                            |
| `--verify-only`                 | Run stage 1 only and exit. Downloads the 37 compressed chunks for `RocketLeague.exe` (~15 MB over the wire) and verifies the reassembled ~38.7 MB executable. Useful for confirming Epic is still serving the old chunks before committing to the full ~38 GiB download. (advanced) |
| `--accept-different-manifest`   | Bypass the manifest provenance gate. Use only if you understand what you're loading. (advanced)                                       |
| `--reference-exe-sha1 <hash>`   | Override the hardcoded reference SHA-1 used in stage 1. (advanced)                                                                    |
| `--reference-exe-sha256 <hash>` | Override the hardcoded reference SHA-256 used in stage 1 (set to empty string to skip the SHA-256 check) (advanced)                   |

### What happens during the run

1. **Manifest provenance gate.** SHA-1 *and* SHA-256 of your manifest are computed and compared to the known-good values. Refuses to proceed if either differs (unless overridden).

2. **Manifest parsing + build-version gate.** Confirms the manifest's internal build version is `++Prime+Update58-CL-512269`.

3. **CDN base URL fetch.** Asks Epic's API for the current CDN base URL via your authenticated legendary session. The path layout is identical between old and new builds, so this works for old chunks too.

4. **Stage 1 — download & verify RocketLeague.exe (~15 MB over the wire, ~38.7 MB assembled).** Downloads the 37 chunks needed to assemble that one file. Reassembles it. Verifies:
   1. The manifest's claimed SHA-1 and size for `RocketLeague.exe` match the hardcoded reference values (checked before download begins), and
   2. The reassembled `RocketLeague.exe` matches the manifest's SHA-1 claim and both hardcoded reference hashes (SHA-1 and SHA-256).

   If any check fails, the script aborts. No bandwidth wasted.

5. **Stage 2 — bulk download.** Pre-allocates all 19,744 files at full size, then downloads all 36,531 chunks in parallel. Each chunk is hash-verified after decompression before being written to disk.

6. **Post-install verification.** After all chunks are written, the script reads every reconstructed file from disk and SHA-1s it against the manifest's claimed file hash. The script will not declare success unless every file matches.

Total: ~38 GiB written, ~35 GiB transferred over the wire. Speed depends on your connection.

---

## Step 2: Launch the game

The downloader places verified files on disk, but the game won't reach the main menu on its own. The pre-EAC `RocketLeague.exe` launches with `-EpicPortal`, which expects the Epic Games Launcher to be running and providing an auth handshake. Without that handshake, the game has no Epic identity, so anything that touches Psyonix services (main menu, inventory, car selection) silently fails. Freeplay and BakkesMod still work, but the rest of the game doesn't.

The fix is to launch through **legendary** instead of EGL. Legendary authenticates against your Epic account the same way EGL does, but won't try to update or "repair" your install back to the post-EAC build.

There are two ways to do this — the launcher script that handles everything, or a manual setup if you'd rather do it yourself.

### Option A: Use `rl_pre_eac_launcher.py` (recommended)

```powershell
python rl_pre_eac_launcher.py
```

On first run, the script will:

1. Check that legendary is authenticated with your Epic account, and run the browser login flow if not.
2. Confirm your account owns Rocket League.
3. Prompt you for the install path you used with the downloader, and save it to `%APPDATA%\rl_pre_eac\config.json` so it doesn't ask again.
4. Register the install with legendary (`legendary import Sugar <path> --disable-check`).
5. Launch the game with the correct auth args injected.

On every subsequent run, it skips straight to launching. Make a desktop shortcut to the script (or a `.bat` file that runs it) and that's your launch button. BakkesMod attaches normally.

#### Flags

| Flag                    | Purpose                                                                 |
| ----------------------- | ----------------------------------------------------------------------- |
| `--install-dir <path>`  | Override the saved install path for one run.                            |
| `--reconfigure`         | Discard the saved install path and prompt again.                        |
| `--reimport`            | Force re-running `legendary import` (use after moving the install).     |
| `-- <args>`             | Anything after `--` is passed through to `RocketLeague.exe`.            |

#### Making a double-click shortcut

The simplest approach is a `.bat` file in the same folder as the launcher script:

```bat
@echo off
python "%~dp0rl_pre_eac_launcher.py"
pause
```

`%~dp0` resolves to "the folder this `.bat` lives in," so as long as the `.bat` and the `.py` stay together, you can move the pair anywhere on disk and the shortcut still works.

### Option B: Manual setup

If you'd rather not run the launcher script, here's the equivalent manual setup. The launcher automates exactly these steps.

1. Install legendary. Either grab the standalone `legendary.exe` from the [legendary releases page](https://github.com/derrod/legendary/releases) and put it somewhere convenient, or use the `legendary-gl` pip package (already installed if you ran `pip install -r requirements.txt`) and call it via `python -m legendary`.

2. Authenticate legendary against your Epic account (skip if you've done this before):
   ```powershell
   .\legendary.exe auth
   ```

3. Register your install with legendary. Replace the path with your actual install root (the folder containing `Binaries\`, `TAGame\`, `Engine\`):
   ```powershell
   .\legendary.exe import Sugar "C:\Games\RocketLegacy" --disable-check
   ```
   `--disable-check` is required. Without it, legendary tries to verify your files against the current (post-EAC) manifest from Epic, which won't match your pre-EAC files, and the import will fail. You'll see a message suggesting you run `legendary repair Sugar`. **Do not run that.** It will overwrite your pre-EAC files with the post-EAC build.

4. Launch the game:
   ```powershell
   .\legendary.exe launch Sugar `
       --override-exe "C:\Games\RocketLegacy\Binaries\Win64\RocketLeague.exe" `
       --skip-version-check
   ```
   `--skip-version-check` is required. Legendary now thinks the latest Sugar build is the post-EAC one, and without this flag it will refuse to launch your "outdated" install.

5. Optionally save that as a `.bat` file for double-click launching.

### Things to never do with this install

Whether you use the launcher script or set things up manually, these all destroy the install:

- **Never run `legendary repair Sugar`.** It will replace your pre-EAC files with the post-EAC build.
- **Never run `legendary update Sugar`.** Same outcome.
- **Never import this folder into the Epic Games Launcher.** EGL will detect a "broken" install and force-update it.
- **Never run "verify integrity"** on this folder from any launcher.

The pre-EAC install should be a folder that no launcher except the launcher script (or your manual `legendary launch` command) ever touches.

### BakkesMod

[Install BakkesMod](https://www.bakkesmod.com/). The installer should detect the install path automatically. If it doesn't, point it at the `RocketLeague.exe` inside your pre-EAC install. Make sure BakkesMod is running before you launch the game.

### Notes

- This setup doesn't conflict with a separate up-to-date Rocket League install for online play. Legendary tracks the pre-EAC install in its own database; whatever launcher you use for the live build (Heroic, EGL, etc.) operates independently.
- Legendary's auth refreshes automatically as long as you launch occasionally. If it fully expires, the next launch will prompt a one-time browser login.
- Keep your manifest file and a copy of the verified `RocketLeague.exe` somewhere safe. If your install gets corrupted, you can re-run the downloader and rebuild.

---

## Verifying you got the real thing

If the downloader printed all "OK" lines and the post-install verification passed, you have an installation whose every byte is hash-matched against the manifest. But here's a sanity check anyway:

```powershell
$rl = "C:\Games\RocketLegacy\Binaries\Win64"
"--- Win64 .exe files ---"
Get-ChildItem $rl -File -Filter "*.exe"
"--- EAC folder present? ---"
Test-Path "$rl\EasyAntiCheat"
"--- RocketLeague.exe SHA-1 (should be BBE15A72...) ---"
(Get-FileHash "$rl\RocketLeague.exe" -Algorithm SHA1).Hash
```

Old build: `RocketLeague.exe` is the only top-level exe in `Win64\`, no `EasyAntiCheat` folder, hash matches.
New build: `Launcher.exe` is present alongside, `EasyAntiCheat` folder exists, different hash.

---

## Security model

This tool runs an executable on your machine and writes ~38 GiB of files to your filesystem based on instructions in a manifest file. That's a meaningful amount of trust. Here's what the downloader does to manage that, and what it doesn't.

### What the downloader protects against

- **Tampered manifest.** SHA-1 *and* SHA-256 gates at startup refuse unrecognized manifests by default. Both known-good hashes are hardcoded in the script.
- **Malformed manifest structure.** Before any download, every chunk_part in the manifest is validated: filenames pass the path validator, every chunk_part references an existing chunk, no negative offsets/sizes, no writes past computed file size, no reads past chunk window. Catches malformed manifests with a clear error rather than silent corruption mid-download.
- **Path traversal in manifest filenames.** Every filename from the manifest is run through a strict path validator before being joined onto the install directory. Absolute paths, drive letters, UNC paths, `..` segments, NUL bytes, Windows reserved device names (CON, NUL, AUX, etc.), and resolved-path-escapes are all rejected.
- **Symlinks inside the install tree.** The script refuses to write through a symlink. The check happens both at allocation time and *immediately before each individual write*, under the per-file lock — closing the TOCTOU window where a local process could otherwise swap a file for a symlink between allocation and write. Note: Windows NTFS junctions are a distinct reparse point type from symlinks; `Path.is_symlink()` may not catch all junction configurations on older Python or Windows versions.
- **Smuggled CDN URLs.** Chunk paths from the manifest are validated and percent-encoded before being concatenated into URLs. HTTP redirects are disabled on chunk fetches so a server-side response can't redirect us off-host.
- **Silent corruption.** Every chunk is SHA-1 verified after decompression against the manifest's claim, *and* every reconstructed file is SHA-1 verified end-to-end against the manifest's claim after the bulk download finishes. Verification refuses to follow a swapped symlink even at the last step.
- **Leaked logs.** Query strings and fragments are stripped from the CDN base URL before it's printed, on the off-chance Epic ever returns signed URLs.
- **Resource exhaustion.** `--workers` is capped at 64.

### What the launcher's trust model looks like

The launcher is much simpler than the downloader. It doesn't fetch game files, doesn't validate hashes, and doesn't write anything to your install directory. It only:

- Reads legendary's local credential store to confirm you're logged in.
- Calls `legendary import` and `legendary launch` as subprocesses.
- Saves your install path to a config file in `%APPDATA%`.

The launcher inherits legendary's trust model for the auth and launch operations, and inherits the downloader's trust model for the install itself. There's nothing new to verify on the launcher side.

### What neither script protects against

- **A subtly tampered version of the script itself.** All the trust anchors (manifest hash, reference exe hashes, build version string) are embedded in the downloader. If you got a modified copy, those checks are meaningless. This is the only place I have put the tools I created — if you downloaded them from anywhere else, beware.

---

## How it actually works

### The trust chain

A manifest file is just a description: "the file `RocketLeague.exe` consists of these 37 chunks, in this order, and its SHA-1 should be `BBE15A72…`." If we trust the manifest, we trust what we end up with. So how do we trust the manifest?

Three independent checks, plus structural validation, plus a final end-to-end verification:

1. **The manifest file itself is hash-checked** against known-good SHA-1 *and* SHA-256 values hardcoded in the script. If you have a manifest from this repo's release, this passes; if not, the script refuses to proceed by default.
2. **The manifest's structure is validated end-to-end** before any download: every filename passes the path-traversal sanitizer, every chunk_part references a real chunk, and no chunk_part has out-of-bounds offsets/sizes.
3. **The manifest's body, when decompressed, contains the literal string `++Prime+Update58-CL-512269`.** This rules out the manifest being a relabeled current-build manifest.
4. **The manifest's claimed SHA-1 and file size for `RocketLeague.exe` are matched against external reference values** hardcoded in the script. This is the cross-check between the manifest and an outside trust source. (SHA-256 is checked on the reassembled binary in the next step.)
5. **Stage 1 reassembles `RocketLeague.exe` from chunks fetched live from Epic's CDN** and confirms the reassembled file matches both the manifest's claim and the external reference. This proves the chunk pipeline produces bit-identical content.
6. **After stage 2, every reconstructed file is hash-verified end-to-end** against the manifest's claim. This catches any reassembly error, partial-write corruption, or silent disk error that the per-chunk check might miss.

Any failure in any of these aborts the run.

### Why old chunks still work

Epic's CDN content is content-addressed — chunks are stored at paths derived from their hash and GUID. When a new build is published, the manifest changes (new file → new chunk references), but the old chunk *files* aren't necessarily deleted, just unreferenced. If Stage 1 succeeds, Epic is still serving the required chunks. This can change without notice.

This is the single biggest fragility in this approach: it depends on Epic continuing to serve content for an old build that they have no incentive to keep serving. Save your manifest. Save your install. Don't assume this script will work in 2027.

### Why the launcher needs `legendary import` and `--skip-version-check`

When you launch Rocket League with `-EpicPortal`, the game expects to talk to a running launcher process over a local IPC channel to get an Epic auth ticket. EGL is the standard provider; legendary fills the same role for non-EGL launches by minting an exchange code and passing it as `-AUTH_LOGIN`/`-AUTH_PASSWORD`/`-AUTH_TYPE=exchangecode` arguments alongside `-EpicPortal`. The game trades the exchange code for a session token at startup, and Psyonix's services come online.

For legendary to do that for a specific app, the app has to be in legendary's `installed.json` database. The downloader writes files to disk but doesn't touch that database (the database schema is internal and we don't want to be coupled to it). So we use `legendary import` to register the install — which is what the import command is designed for: telling legendary about a game it didn't install.

`--disable-check` is needed during import because legendary fetches the *current* manifest for `Sugar` from Epic's API and verifies the on-disk files against it. The current manifest is the post-EAC build (with an `EasyAntiCheat` folder and `Launcher.exe`), and our pre-EAC files don't match. Disabling the check lets the import succeed against the older files.

`--skip-version-check` is needed during launch because legendary now thinks the "latest" Sugar build is the post-EAC one, and would otherwise refuse to launch a "stale" install or try to update it.

---

## Troubleshooting

### Downloader

#### `Legendary login failed. Run \`legendary auth\` first.`

Run `legendary auth` (or `python -m legendary auth`) in a terminal and complete the browser login. Then try again.

#### `'Sugar' not in your account.`

Your Epic account doesn't own Rocket League. You need a license. (Yes, even though Rocket League is free-to-play, you have to "claim" it on your account once for it to show up.)

OR

Run `legendary list` to confirm Rocket League appears in your account's game list. If you just claimed it, give it a minute and re-run `legendary auth` if it doesn't show up.

#### `Manifest hashes do not match the known-good values.`

Your manifest isn't the canonical one this tool was built for. Either find the canonical one (matches `C3B8E170…` SHA-1 and `B4D2CF20…` SHA-256), or pass `--accept-different-manifest` if you have a verified manifest from another source.

#### Stage 1 fails: `manifest claim does not match external reference`

The manifest passed the SHA gate but its claim for `RocketLeague.exe` doesn't match the hardcoded reference. This shouldn't happen with the canonical manifest. If you used `--accept-different-manifest`, your manifest may be a different build than expected.

#### Chunks 404 during download

Epic may have deleted the old chunks from their CDN, the CDN base URL structure may have changed, your auth token may have expired, or the manifest or source may be wrong. Try re-running once (auth tokens can be refreshed). If it persists, the most likely cause is Epic no longer serving the old chunks — in that case, you'd need someone who already has a complete pre-EAC install to share files directly.

#### Script crashes mid-download

Re-run with the same args. Pre-allocation skips files that are already at the right size, and chunk writes are idempotent (writing the same bytes to the same offset is a no-op). Not full resume, but close enough that re-running works in practice.

#### Post-install verification fails on some files

The chunk content didn't reassemble correctly. Re-run the script — failed files will get rewritten. If failures persist, your network is corrupting downloads or your disk is bad.

### Launcher

#### `legendary-gl is not installed`

Run `pip install -r requirements.txt` from the repo folder, or `pip install legendary-gl` directly.

#### `Game Sugar is not currently installed!`

Sugar isn't registered with legendary yet. The launcher handles this automatically; if you're seeing it, you ran `legendary launch` directly without going through the launcher. Either use the launcher script, or run `legendary import Sugar <install-dir> --disable-check` manually first.

#### Main menu still won't load after launching via the launcher

Confirm legendary is actually authenticated — `legendary status` (or `python -m legendary status`) should show your Epic username. Confirm you launched *through* the launcher, not by double-clicking `RocketLeague.exe` directly. If both are true and the menu still won't load, your Epic auth token may have silently failed to refresh; run `legendary auth --delete` followed by `legendary auth` to force a fresh login, then try again.

#### Launcher prompts for install path every time

The config write is failing. Check that `%APPDATA%\rl_pre_eac\` is writable by your user, and that no antivirus is quarantining files in that folder.

#### Install completed but BakkesMod won't inject

Make sure BakkesMod is running before you launch the game, and that it's configured to point at the same `RocketLeague.exe` the launcher is using.

#### The launcher launches the game but it crashes immediately

Almost always means the pre-EAC files have been partially overwritten by a post-EAC update — usually because EGL got pointed at the folder, or `legendary repair`/`legendary update` was run. Re-run the downloader to restore the install.

---

## Acknowledgements

- The community member who saved and shared the pre-EAC manifest and reference binary in the days after the April 28 update. This tool would be impossible without those artifacts.
- [legendary](https://github.com/derrod/legendary) by Rodney "derrod" — the underlying Epic Games library this tool builds on.
- [BakkesMod](https://www.bakkesmod.com/) and the plugin ecosystem authors. Decade of work, deserves preservation.

---

## License

MIT. See `LICENSE`.

This project does not distribute Rocket League game binaries, the Epic Games Launcher, BakkesMod, or any Psyonix/Epic copyrighted game content. It includes the downloader and launcher scripts and, if bundled, a manifest metadata file used solely to request game files from Epic's CDN under your own account. Game files are downloaded from Epic's servers by you, for your account.

## Disclaimer

This is community software, provided as-is, with no affiliation with Psyonix, Epic Games, or BakkesMod. Use at your own risk. The author of this tool is not responsible for account actions, install corruption, or any issues that arise from using it. Don't use this tool to attempt online play or anything that would violate Rocket League's Terms of Service.
