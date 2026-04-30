# Rocket League Pre-EAC Recovery (Offline only)

A standalone Python tool that downloads the **pre Easy-Anti-Cheat build of Rocket League** (`++Prime+Update58-CL-512269`,  the build that shipped prior to April 28, 2026 and is compatible with the last BakkesMod release) directly from Epic's CDN, using a saved manifest file.

I created this tool because I mistakenly updated without backing up the files, and therefore lost my ability to train with BakkesMod. With (in my opinion) much more options in terms of training, it was pretty shocking seeing how lacking vanilla Rocket League's options truly were. From that disappointment, this program was created. Legendary CLI was giving me problems with overriding the manifest, hence why that was not just used instead. 

There's a chance that I was simply misusing [legendary](https://github.com/derrod/legendary), or a minor bug due to powershell being.... powershell. If this seems like it may be too complicated (I can promise you it isn't), then that may be of use to you. It's still CLI though, and this tool has a more directed purpose.

---

## What this is for

- Playing Rocket League **offline**, in freeplay, or custom maps. Custom training and access to the main menu is a WIP.
- Running **BakkesMod** and its plugin ecosystem on a clean, unmodified pre-EAC install
- Preserving access to a version of the game licensed to your account, after Epic replaced it

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
- **[legendary](https://github.com/derrod/legendary)** authenticated to your Epic account (run `legendary auth` once before using this tool — it stores your credentials in `%USERPROFILE%\.config\legendary\` and this tool reads them from there)

### Account

- Your Epic Games account must own Rocket League. The tool will not let you download a game you don't own.

### The manifest file

**The tool requires a saved copy of the pre-EAC manifest file.** It's what enables us to download this older version. Epic doesn't publicly archive previous build manifests, thankfully though, I was able to get into contact with someone kind enough to send over what their manifest file.

By default, **the script will only run on the canonical manifest distributed alongside this tool**, identified by SHA-1 and SHA-256. If your manifest doesn't match either hash, the script will refuse to run and tell you exactly which hash it saw vs. expected. You can override this with `--accept-different-manifest` if you have a manifest from a different verified source, but you take on the responsibility of vetting it yourself in that case.

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

```powershell
# Clone or download this repo, cd into it
pip install -r requirements.txt

# One-time: authenticate legendary if you haven't already
legendary auth
```

---

## Usage

```powershell
python rl_pre_eac_downloader.py `
    --manifest "C:\path\to\rl_pre_eac.manifest" `
    --install-dir "C:\Games\RocketLegacy\rocketleague"
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

## After the install (IMPORTANT)

The script doesn't create a shortcut or configure BakkesMod for you. Quick steps:

1. **Make a desktop shortcut** to `C:\Games\RocketLegacy\rocketleague\Binaries\Win64\RocketLeague.exe`
2. **Right-click the shortcut → Properties → Target** and add ` -EpicPortal` to the end:
   ```
   "C:\Games\RocketLegacy\rocketleague\Binaries\Win64\RocketLeague.exe" -EpicPortal
   ```
3. **Install [BakkesMod](https://www.bakkesmod.com/)**. The installer will detect the install path automatically. If it doesn't, point it at your `RocketLeague.exe`.
4. **Always launch via this shortcut.** If you ever launch this install through the Epic Games Launcher, EGL may detect a "broken" install and force-update it back to the post-EAC build. We don't want that.

### Recommended hygiene

- Keep your manifest file and a copy of the verified `RocketLeague.exe` somewhere safe. If your install gets corrupted, you can re-run the script and rebuild.
- Don't run Steam or EGL's "verify integrity" on this folder. Your game should be in some random folder no game launcher ever thinks about.

---

## Verifying you got the real thing

If the script printed all "OK" lines and the post-install verification passed, you have an installation whose every byte is hash-matched against the manifest. But here's a sanity check anyway:

```powershell
$rl = "C:\Games\RocketLegacy\rocketleague\Binaries\Win64"
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

This tool runs an executable on your machine and writes ~38 GiB of files to your filesystem based on instructions in a manifest file. That's a meaningful amount of trust. Here's what the script does to manage that, and what it doesn't.

### What the script protects against

- **Tampered manifest.** SHA-1 *and* SHA-256 gates at startup refuse unrecognized manifests by default. Both known-good hashes are hardcoded in the script.
- **Malformed manifest structure.** Before any download, every chunk_part in the manifest is validated: filenames pass the path validator, every chunk_part references an existing chunk, no negative offsets/sizes, no writes past computed file size, no reads past chunk window. Catches malformed manifests with a clear error rather than silent corruption mid-download.
- **Path traversal in manifest filenames.** Every filename from the manifest is run through a strict path validator before being joined onto the install directory. Absolute paths, drive letters, UNC paths, `..` segments, NUL bytes, Windows reserved device names (CON, NUL, AUX, etc.), and resolved-path-escapes are all rejected.
- **Symlinks inside the install tree.** The script refuses to write through a symlink. The check happens both at allocation time and *immediately before each individual write*, under the per-file lock — closing the TOCTOU window where a local process could otherwise swap a file for a symlink between allocation and write. Note: Windows NTFS junctions are a distinct reparse point type from symlinks; `Path.is_symlink()` may not catch all junction configurations on older Python or Windows versions.
- **Smuggled CDN URLs.** Chunk paths from the manifest are validated and percent-encoded before being concatenated into URLs. HTTP redirects are disabled on chunk fetches so a server-side response can't redirect us off-host.
- **Silent corruption.** Every chunk is SHA-1 verified after decompression against the manifest's claim, *and* every reconstructed file is SHA-1 verified end-to-end against the manifest's claim after the bulk download finishes. Verification refuses to follow a swapped symlink even at the last step.
- **Leaked logs.** Query strings and fragments are stripped from the CDN base URL before it's printed, on the off-chance Epic ever returns signed URLs.
- **Resource exhaustion.** `--workers` is capped at 64.

### What the script does NOT protect against

- **A subtly tampered version of the script itself.** All the trust anchors (manifest hash, reference exe hashes, build version string) are embedded in the script. If you got a modified copy, those checks are meaningless. This is the only place I have put the tool I created, if you downloaded it from anywhere else, beware.

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

---

## Troubleshooting

### `Legendary login failed. Run \`legendary auth\` first.`

Run `legendary auth` in a terminal and complete the browser login. Then try again.

### `'Sugar' not in your account.`

Your Epic account doesn't own Rocket League. You need a license. (Yes, even though Rocket League is free-to-play, you have to "claim" it on your account once for it to show up.)

OR

Run "legendary list" to confirm Rocket League appears in your account's game list. If you just claimed it, give it a minute and re-run "legendary auth" if it doesn't show up.

### `Manifest hashes do not match the known-good values.`

Your manifest isn't the canonical one this tool was built for. Either find the canonical one (matches `C3B8E170…` SHA-1 and `B4D2CF20…` SHA-256), or pass `--accept-different-manifest` if you have a verified manifest from another source.

### Stage 1 fails: `manifest claim does not match external reference`

The manifest passed the SHA gate but its claim for `RocketLeague.exe` doesn't match the hardcoded reference. This shouldn't happen with the canonical manifest. If you used `--accept-different-manifest`, your manifest may be a different build than expected.

### Chunks 404 during download

Epic may have deleted the old chunks from their CDN, the CDN base URL structure may have changed, your auth token may have expired, or the manifest or source may be wrong. Try re-running once (auth tokens can be refreshed). If it persists, the most likely cause is Epic no longer serving the old chunks — in that case, you'd need someone who already has a complete pre-EAC install to share files directly.

### Script crashes mid-download

Re-run with the same args. Pre-allocation skips files that are already at the right size, and chunk writes are idempotent (writing the same bytes to the same offset is a no-op). Not full resume, but close enough that re-running works in practice.

### Post-install verification fails on some files

The chunk content didn't reassemble correctly. Re-run the script — failed files will get rewritten. If failures persist, your network is corrupting downloads or your disk is bad.

### Install completed but BakkesMod won't inject

Make sure BakkesMod is running before you launch, and that it's configured to point at the same `RocketLeague.exe` you're launching with `-EpicPortal`.

---

## Acknowledgements

- The community member who saved and shared the pre-EAC manifest and reference binary in the days after the April 28 update. This tool would be impossible without those artifacts.
- [legendary](https://github.com/derrod/legendary) by Rodney "derrod" — the underlying Epic Games library this tool builds on.
- [BakkesMod](https://www.bakkesmod.com/) and the plugin ecosystem authors. Decade of work, deserves preservation.

---

## License

MIT. See `LICENSE`.

This project does not distribute Rocket League game binaries, the Epic Games Launcher, BakkesMod, or any Psyonix/Epic copyrighted game content. It includes the downloader script and, if bundled, a manifest metadata file used solely to request game files from Epic's CDN under your own account. Game files are downloaded from Epic's servers by you, for your account.

## Disclaimer

This is community software, provided as-is, with no affiliation with Psyonix, Epic Games, or BakkesMod. Use at your own risk. The author of this tool is not responsible for account actions, install corruption, or any issues that arise from using it. Don't use this tool to attempt online play or anything that would violate Rocket League's Terms of Service.
