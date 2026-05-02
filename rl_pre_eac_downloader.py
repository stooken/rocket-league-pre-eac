#!/usr/bin/env python3
"""
rl_pre_eac_downloader.py
------------------------
Downloads the pre-EAC Rocket League build (CL-512269) using a saved
manifest file, fetching chunks directly from Epic's CDN.

This is the hardened community-distribution version. Compared to a naive
implementation, it does the following safety work:

  * Verifies the manifest's SHA-1 against a known-good value before doing
    anything else. The script refuses to run on an unrecognized manifest
    unless --accept-different-manifest is passed.
  * Sanitizes every filename from the manifest before joining it onto the
    install directory: rejects absolute paths, traversal (..), NUL bytes,
    Windows reserved device names, and resolves+confirms containment.
  * Rejects writes through symlinks; Windows junction handling depends on
    Python/Windows behavior and is not treated as a primary trust boundary.
  * Sanitizes chunk paths from the manifest before forming CDN URLs and
    disables HTTP redirects on chunk fetches.
  * Caps parallel workers at 64.
  * Hash-verifies every chunk after decompression (manifest SHA-1).
  * After the bulk download, hash-verifies every reconstructed file end to
    end. The script will not declare success if any file's hash drifts
    from the manifest's claim.
  * Uses one HTTP session per worker thread.
  * Redacts query strings from logged URLs.

See README.md for usage, the trust model, and how to obtain a manifest.
"""

import argparse
import hashlib
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

try:
    from legendary.core import LegendaryCore
    from legendary.models.chunk import Chunk
    from legendary.models.manifest import Manifest
except ImportError:
    sys.exit("ERROR: pip install legendary-gl requests tqdm")
try:
    import requests
except ImportError:
    sys.exit("ERROR: pip install requests")
try:
    from tqdm import tqdm
except ImportError:
    sys.exit("ERROR: pip install tqdm")


# ===== Constants ==========================================================

APP_NAME = "Sugar"
TARGET_EXE = "Binaries/Win64/RocketLeague.exe"
EXPECTED_BUILD = "++Prime+Update58-CL-512269"

# Provenance anchors. The manifest hash is the gate that determines whether
# this script will run at all on default settings; the EXE hashes are the
# external check that stage 1 uses to confirm the chunk pipeline is producing
# bit-identical content. All three values come from artifacts hashed
# independently and confirmed to be self-consistent (the manifest's own
# claim for RocketLeague.exe matches REFERENCE_EXE_SHA1).
KNOWN_GOOD_MANIFEST_SHA1 = "C3B8E170AA9DD01848B0F31ECD354BC011CB47AA"
KNOWN_GOOD_MANIFEST_SHA256 = (
    "B4D2CF205224FA9079E94351FBD8F6F7422324D71D16749FA9F94F0857EB4454"
)
REFERENCE_EXE_SHA1 = "BBE15A722E0E6D28B0FB4205FB068E04D97A8F65"
REFERENCE_EXE_SHA256 = (
    "F8714F894D7E31A94928F55756D81E704C2F34204491D2C5E2B44D8B9865B2CE"
)
REFERENCE_EXE_SIZE = 38_727_504

MAX_WORKERS = 64
DEFAULT_WORKERS = 16
HTTP_TIMEOUT = 30
CHUNK_RETRY_ATTEMPTS = 4
CHUNK_RETRY_BACKOFF = 1.5
HASH_BLOCK_SIZE = 1024 * 1024  # 1 MiB

# Windows reserved device names. Case-insensitive, checked against the part
# before any extension. Refusing these prevents weird I/O behavior from a
# manifest that lists e.g. "CON" or "NUL.dll" as filenames.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


# ===== Path/URL safety helpers ===========================================

def validate_filename(rel: str) -> Path:
    """Validate a manifest-supplied filename without touching the filesystem.
    Returns the normalized relative Path on success, raises ValueError otherwise.

    Performs the same syntactic checks as safe_join() — rejecting absolute
    paths, drive letters, UNC, traversal, NUL bytes, Windows reserved names,
    and empty strings — but does not resolve through the filesystem. Used
    for bulk validation of manifest entries during structure checking.
    """
    if not isinstance(rel, str) or not rel:
        raise ValueError("filename must be a non-empty string")
    if "\x00" in rel:
        raise ValueError(f"NUL byte in path: {rel!r}")

    rel_norm = rel.replace("\\", "/")
    if rel_norm.startswith("/"):
        raise ValueError(f"absolute or UNC path rejected: {rel}")
    if len(rel_norm) >= 2 and rel_norm[1] == ":":
        raise ValueError(f"drive-letter path rejected: {rel}")

    rel_path = Path(rel_norm)
    if rel_path.is_absolute():
        raise ValueError(f"absolute path rejected: {rel}")
    if not rel_path.parts:
        raise ValueError(f"empty path rejected: {rel!r}")

    for part in rel_path.parts:
        if part in ("", ".", ".."):
            raise ValueError(f"path traversal in: {rel}")
        stem = part.split(".")[0].upper()
        if stem in _WINDOWS_RESERVED:
            raise ValueError(f"Windows reserved name in path: {rel}")
    return rel_path


def safe_join(root: Path, rel: str) -> Path:
    """Join a manifest-supplied filename onto an install root, refusing any
    form of traversal or escape. Returns a resolved, contained absolute path.
    """
    rel_path = validate_filename(rel)
    root_resolved = root.resolve()
    out = (root_resolved / rel_path).resolve()
    try:
        out.relative_to(root_resolved)
    except ValueError:
        raise ValueError(f"path escapes install dir: {rel}")
    return out


def safe_chunk_path(chunk_path: str) -> str:
    """Validate and URL-encode a chunk path from the manifest before it gets
    concatenated into a CDN URL. Refuses anything that could redirect us to
    a different host, smuggle a query string, or traverse path components.
    """
    if not isinstance(chunk_path, str) or not chunk_path:
        raise ValueError("chunk path must be a non-empty string")
    p = chunk_path.replace("\\", "/")
    if p.startswith("/"):
        raise ValueError(f"absolute chunk path rejected: {chunk_path}")
    if len(p) >= 2 and p[1] == ":":
        raise ValueError(f"drive-letter chunk path rejected: {chunk_path}")
    if "://" in p or "?" in p or "#" in p:
        raise ValueError(f"non-relative chunk path rejected: {chunk_path}")
    parts = p.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ValueError(f"path traversal in chunk path: {chunk_path}")
    return "/".join(quote(part, safe="") for part in parts)


def redact_url(url: str) -> str:
    """Strip query string and fragment for logging — defense against
    accidentally leaking signed URL material in console output or pasted logs.
    """
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc, u.path, "", ""))


def reject_symlink(path: Path) -> None:
    """Refuse to write through a symlink. Path.is_symlink() does not follow
    links, so it correctly detects a symlink even if the target doesn't exist.
    Note: Windows NTFS junctions are a distinct reparse point type and may not
    be caught by is_symlink() on all Python/Windows versions; junction
    protection is not treated as a primary trust boundary.
    """
    if path.is_symlink():
        raise RuntimeError(f"Refusing to write through symlink/junction: {path}")


# ===== Per-thread HTTP session ===========================================

_thread_local = threading.local()

def get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


# ===== Hash helpers =======================================================

def sha1_of_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(HASH_BLOCK_SIZE), b""):
            h.update(block)
    return h.hexdigest().upper()


def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest().upper()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


# ===== Legendary integration =============================================

def get_base_url() -> str:
    """Use the user's stored legendary credentials to ask Epic's API for a
    current CDN base URL. The path layout is identical between old and new
    builds, so this base URL works for old chunks too as long as Epic
    hasn't garbage-collected them.
    """
    core = LegendaryCore()
    if not core.login():
        sys.exit("ERROR: legendary login failed. Run `legendary auth` first.")
    game = core.get_game(APP_NAME)
    if not game:
        sys.exit(f"ERROR: '{APP_NAME}' not in your account.")
    _, base_urls, _ = core.get_cdn_urls(game, platform="Windows")
    if not base_urls:
        sys.exit("ERROR: no CDN URLs returned by Epic API.")
    return base_urls[0].rstrip("/")


def parse_manifest(path: Path) -> Manifest:
    print(f"Parsing manifest: {path}")
    with open(path, "rb") as f:
        m = Manifest.read_all(f.read())
    print(f"  Build:  {m.meta.build_version}")
    print(f"  Files:  {len(m.file_manifest_list.elements):,}")
    print(f"  Chunks: {len(m.chunk_data_list.elements):,}")
    if m.meta.build_version != EXPECTED_BUILD:
        sys.exit(
            f"ERROR: manifest is not {EXPECTED_BUILD} (got "
            f"{m.meta.build_version}). Wrong manifest."
        )
    return m


def validate_manifest_structure(manifest: Manifest) -> None:
    """Sanity-check every entry in the manifest before we trust any of it.

    Verifies that:
      * every filename passes the filename validator (no traversal etc.)
      * every chunk_part references a real chunk in the chunk list
      * no chunk_part has negative offsets/sizes
      * no chunk_part writes past the file's computed total size
      * no chunk_part reads past its source chunk's window size

    Without this, a malformed manifest (especially one accepted via
    --accept-different-manifest) could produce silent corruption, weird
    exceptions deep in the worker, or wasted bandwidth before failing.
    Doing it once upfront gives a clear single-point-of-failure error.
    """
    print("Validating manifest structure...")
    chunks_by_guid = {c.guid_num: c for c in manifest.chunk_data_list.elements}

    for fm in manifest.file_manifest_list.elements:
        try:
            validate_filename(fm.filename)
        except ValueError as e:
            sys.exit(f"ERROR: invalid filename in manifest: {e}")

        file_size = sum(p.size for p in fm.chunk_parts)
        if file_size < 0:
            sys.exit(f"ERROR: {fm.filename}: negative computed file size")

        for cp in fm.chunk_parts:
            if cp.guid_num not in chunks_by_guid:
                sys.exit(
                    f"ERROR: {fm.filename}: chunk_part references unknown "
                    f"chunk guid {cp.guid_str}"
                )
            if cp.offset < 0 or cp.size < 0 or cp.file_offset < 0:
                sys.exit(
                    f"ERROR: {fm.filename}: negative offset/size in chunk_part"
                )
            if cp.file_offset + cp.size > file_size:
                sys.exit(
                    f"ERROR: {fm.filename}: chunk_part writes past file size "
                    f"({cp.file_offset}+{cp.size} > {file_size})"
                )
            chunk_size = chunks_by_guid[cp.guid_num].window_size
            if cp.offset + cp.size > chunk_size:
                sys.exit(
                    f"ERROR: {fm.filename}: chunk_part reads past chunk window "
                    f"({cp.offset}+{cp.size} > {chunk_size})"
                )
    print(f"  OK: {len(manifest.file_manifest_list.elements):,} files, all chunk_parts in bounds.")


def verify_manifest_sha(path: Path, accept_different: bool) -> None:
    """Provenance gate. The manifest controls every filesystem path and CDN
    path the script touches, so we refuse to proceed unless its hashes
    match the known-good values distributed with this tool.

    Both SHA-1 and SHA-256 are checked. Mismatching either fails the gate.
    """
    print("Verifying manifest provenance...")
    with open(path, "rb") as f:
        data = f.read()
    actual_sha1 = hashlib.sha1(data).hexdigest().upper()
    actual_sha256 = hashlib.sha256(data).hexdigest().upper()

    print(f"  Manifest SHA-1:   {actual_sha1}")
    print(f"  Expected:         {KNOWN_GOOD_MANIFEST_SHA1}")
    print(f"  Manifest SHA-256: {actual_sha256}")
    print(f"  Expected:         {KNOWN_GOOD_MANIFEST_SHA256}")

    sha1_match = actual_sha1 == KNOWN_GOOD_MANIFEST_SHA1
    sha256_match = actual_sha256 == KNOWN_GOOD_MANIFEST_SHA256

    if sha1_match and sha256_match:
        print("  OK: matches the canonical pre-EAC manifest.")
        return

    if accept_different:
        print()
        print("  This manifest does not match the canonical hashes.")
        print("  Continuing because --accept-different-manifest was passed.")
        print()
        print("  Path sanitization, chunk-path validation, and end-to-end")
        print("  hash verification remain ACTIVE — a malicious manifest cannot")
        print("  escape the install directory or silently install corrupt files.")
        print("  But the provenance gate is now bypassed: you are responsible")
        print("  for vetting that this manifest came from a trustworthy source")
        print("  and represents the build you actually want.")
        return

    print()
    print("  ERROR: manifest hashes do not match the known-good values.")
    print("  Possible causes:")
    print("    - the file is corrupted")
    print("    - the manifest is from a different source than this tool")
    print("    - the file has been tampered with")
    print()
    print("  If you intentionally want to use a different manifest, re-run")
    print("  with --accept-different-manifest. This bypasses the provenance")
    print("  gate; do it at your own risk and only with a manifest you trust.")
    sys.exit(1)


# ===== Chunk download/decode =============================================

def download_chunk_bytes(base_url: str, chunk_path: str) -> bytes:
    """Fetch one .chunk file from the CDN with retries, returning raw bytes.

    chunk_path is sanitized and percent-encoded; redirects are disabled so
    a malicious server-side response can't redirect us off-host.
    """
    safe_path = safe_chunk_path(chunk_path)
    url = f"{base_url}/{safe_path}"
    session = get_session()
    last_err = None
    for attempt in range(CHUNK_RETRY_ATTEMPTS):
        try:
            r = session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=False)
            if r.status_code == 200 and len(r.content) > 0:
                return r.content
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(CHUNK_RETRY_BACKOFF * (attempt + 1))
    raise RuntimeError(f"failed: {chunk_path}: {last_err}")


def decode_chunk(raw: bytes) -> bytes:
    chunk = Chunk.read_buffer(raw)
    return chunk.data


# ===== Stage 1: download & verify RocketLeague.exe =======================

def stage1_verify(
    manifest: Manifest, base_url: str, ref_sha1: str, ref_sha256: str | None
) -> bool:
    print("\n========== STAGE 1: download & verify RocketLeague.exe ==========")
    target = next(
        (e for e in manifest.file_manifest_list.elements if e.filename == TARGET_EXE),
        None,
    )
    if target is None:
        print(f"  ERROR: {TARGET_EXE} not in manifest.")
        return False

    claimed_sha1 = target.hash.hex().upper()
    claimed_size = sum(p.size for p in target.chunk_parts)

    print(f"  Manifest claim:    size={claimed_size:,}  sha1={claimed_sha1}")
    print(f"  External anchor:   size={REFERENCE_EXE_SIZE:,}  sha1={ref_sha1}")
    if ref_sha256:
        print(f"                                                       sha256={ref_sha256}")

    if claimed_sha1 != ref_sha1 or claimed_size != REFERENCE_EXE_SIZE:
        print("  ERROR: manifest's claim does not match external reference. Abort.")
        return False

    chunks_by_guid = {c.guid_num: c for c in manifest.chunk_data_list.elements}
    needed = sorted({cp.guid_num for cp in target.chunk_parts})
    print(f"  Need {len(needed)} unique chunks for this file.")

    decoded: dict[int, bytes] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {
            pool.submit(download_chunk_bytes, base_url, chunks_by_guid[g].path): g
            for g in needed
        }
        for fut in tqdm(
            as_completed(futs), total=len(futs), desc="  downloading", unit="chunk"
        ):
            guid = futs[fut]
            try:
                raw = fut.result()
                data = decode_chunk(raw)
                expected_sha = chunks_by_guid[guid].sha_hash
                if expected_sha and hashlib.sha1(data).digest() != expected_sha:
                    print(f"\n  ERROR: chunk SHA mismatch on {chunks_by_guid[guid].path}")
                    return False
                decoded[guid] = data
            except Exception as e:
                print(f"\n  ERROR: chunk {chunks_by_guid[guid].path}: {e}")
                return False

    buf = bytearray(claimed_size)
    for cp in target.chunk_parts:
        buf[cp.file_offset:cp.file_offset + cp.size] = (
            decoded[cp.guid_num][cp.offset:cp.offset + cp.size]
        )

    actual_sha1 = sha1_hex(bytes(buf))
    actual_sha256 = sha256_hex(bytes(buf))
    print(f"\n  Reassembled SHA-1:   {actual_sha1}")
    print(f"  Reassembled SHA-256: {actual_sha256}")

    if actual_sha1 != claimed_sha1:
        print("  ERROR: reassembled SHA-1 does not match manifest claim.")
        return False
    if actual_sha1 != ref_sha1:
        print("  ERROR: reassembled SHA-1 does not match external reference.")
        return False
    if ref_sha256 and actual_sha256 != ref_sha256:
        print("  ERROR: reassembled SHA-256 does not match external reference.")
        return False
    print("  OK: pipeline produces bit-identical content vs reference.")
    return True


# ===== Stage 2: full download =============================================

def build_chunk_refs(manifest: Manifest):
    refs = defaultdict(list)
    for fi, fm in enumerate(manifest.file_manifest_list.elements):
        for cp in fm.chunk_parts:
            refs[cp.guid_num].append((fi, cp))
    return refs


def allocate_files(manifest: Manifest, install_dir: Path) -> dict[int, Path]:
    """Pre-create every file at full size. Returns a map from file index to
    the resolved safe path for that file, used later by the chunk writer."""
    print("Allocating files on disk...")
    safe_paths: dict[int, Path] = {}
    for fi, fm in enumerate(
        tqdm(manifest.file_manifest_list.elements, desc="  alloc", unit="file")
    ):
        path = safe_join(install_dir, fm.filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            reject_symlink(path)
        size = sum(p.size for p in fm.chunk_parts)
        if path.exists() and path.stat().st_size == size:
            safe_paths[fi] = path
            continue
        with open(path, "wb") as f:
            if size > 0:
                f.truncate(size)
        safe_paths[fi] = path
    return safe_paths


def stage2_full(
    manifest: Manifest, base_url: str, install_dir: Path, workers: int
) -> bool:
    print(f"\n========== STAGE 2: full download to {install_dir} ==========")
    install_dir.mkdir(parents=True, exist_ok=True)
    install_dir_resolved = install_dir.resolve()
    safe_paths = allocate_files(manifest, install_dir)

    files = manifest.file_manifest_list.elements
    chunks = manifest.chunk_data_list.elements
    refs = build_chunk_refs(manifest)

    total_bytes = sum(sum(p.size for p in fm.chunk_parts) for fm in files)
    print(
        f"  Total to write: {total_bytes / (1024**3):.2f} GiB "
        f"across {len(files):,} files"
    )
    print(f"  Chunks to download: {len(chunks):,} with {workers} workers")

    # Pre-create per-file locks so we don't race on lock creation in workers.
    file_locks: dict[int, threading.Lock] = {
        fi: threading.Lock() for fi in range(len(files))
    }

    def fetch_and_apply(chunk_info):
        raw = download_chunk_bytes(base_url, chunk_info.path)
        data = decode_chunk(raw)
        if chunk_info.sha_hash and hashlib.sha1(data).digest() != chunk_info.sha_hash:
            raise RuntimeError(f"SHA mismatch on chunk {chunk_info.path}")
        wrote_local = 0
        for fi, cp in refs[chunk_info.guid_num]:
            path = safe_paths[fi]
            with file_locks[fi]:
                # Re-check immediately before opening, under the lock. Closes
                # the TOCTOU window between allocation (which already rejected
                # symlinks) and the actual write — a local process could
                # otherwise swap the file for a symlink in between.
                reject_symlink(path)
                try:
                    path.resolve().relative_to(install_dir_resolved)
                except ValueError:
                    raise RuntimeError(
                        f"path escaped install dir before write: {path}"
                    )
                with open(path, "r+b") as f:
                    f.seek(cp.file_offset)
                    f.write(data[cp.offset:cp.offset + cp.size])
            wrote_local += cp.size
        return wrote_local

    pbar = tqdm(total=total_bytes, unit="B", unit_scale=True, desc="  downloading")
    failures = []
    written = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_and_apply, c): c for c in chunks}
        for fut in as_completed(futs):
            try:
                n = fut.result()
                written += n
                pbar.update(n)
            except Exception as e:
                failures.append((futs[fut].path, str(e)))
                pbar.write(f"  FAIL {futs[fut].path}: {e}")
    pbar.close()

    if failures:
        print(f"\n  {len(failures)} chunk(s) failed:")
        for p, err in failures[:10]:
            print(f"    {p} : {err}")
        if len(failures) > 10:
            print(f"    ... and {len(failures) - 10} more")
        return False
    print(f"\n  OK: wrote {written / (1024**3):.2f} GiB.")
    return True


# ===== Post-install: hash-verify every file ===============================

def _verify_one_file(args):
    fm, install_dir, install_dir_resolved = args
    try:
        path = safe_join(install_dir, fm.filename)
    except ValueError as e:
        return (fm.filename, f"unsafe path: {e}")
    expected_size = sum(p.size for p in fm.chunk_parts)
    expected_sha = fm.hash.hex().upper()
    if not path.exists():
        return (fm.filename, "missing")
    # Refuse to follow a symlink that may have been swapped in between
    # write and verify. Also re-confirm containment.
    if path.is_symlink():
        return (fm.filename, "symlink/junction detected during verify")
    try:
        path.resolve().relative_to(install_dir_resolved)
    except ValueError:
        return (fm.filename, "path escaped install dir during verify")
    if path.stat().st_size != expected_size:
        return (fm.filename, f"size {path.stat().st_size} != {expected_size}")
    actual_sha = sha1_of_file(path)
    if actual_sha != expected_sha:
        return (fm.filename, f"hash {actual_sha} != {expected_sha}")
    return None


def verify_install(manifest: Manifest, install_dir: Path, workers: int = 8) -> bool:
    """Read every reconstructed file and SHA-1 it against the manifest's
    claim. This catches any reassembly bug, partial-write corruption, or
    silent disk error that the per-chunk verify in stage 2 might miss."""
    print("\n========== POST-INSTALL: hash-verify all files ==========")
    files = manifest.file_manifest_list.elements
    install_dir_resolved = install_dir.resolve()
    items = [(fm, install_dir, install_dir_resolved) for fm in files]
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in tqdm(
            pool.map(_verify_one_file, items),
            total=len(items),
            desc="  verifying",
            unit="file",
        ):
            if result is not None:
                failures.append(result)

    if failures:
        print(f"\n  FAIL: {len(failures)} files failed verification:")
        for name, err in failures[:20]:
            print(f"    {name}: {err}")
        if len(failures) > 20:
            print(f"    ... and {len(failures) - 20} more")
        return False
    print(f"  OK: all {len(files):,} files match manifest hashes.")
    return True


# ===== Entry =============================================================

def main():
    p = argparse.ArgumentParser(
        description="Download the pre-EAC Rocket League build (CL-512269) from Epic's CDN.",
    )
    p.add_argument("--manifest", required=True, type=Path,
                   help="path to the pre-EAC manifest file")
    p.add_argument("--install-dir", required=True, type=Path,
                   help="destination directory; use a path outside Epic's managed folders")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                   help=f"parallel download workers (1-{MAX_WORKERS}, default {DEFAULT_WORKERS})")
    p.add_argument("--verify-only", action="store_true",
                   help="run stage 1 only and exit (no bulk download)")
    p.add_argument("--accept-different-manifest", action="store_true",
                   help="bypass the manifest provenance gate (USE WITH CAUTION)")
    p.add_argument("--reference-exe-sha1", default=REFERENCE_EXE_SHA1,
                   help="override the external reference SHA-1 for stage 1")
    p.add_argument("--reference-exe-sha256", default=REFERENCE_EXE_SHA256,
                   help="override the external reference SHA-256 for stage 1 "
                        "(set to empty string to skip the SHA-256 check)")
    args = p.parse_args()

    if not args.manifest.exists():
        sys.exit(f"ERROR: manifest not found: {args.manifest}")
    if args.workers < 1 or args.workers > MAX_WORKERS:
        sys.exit(f"ERROR: --workers must be between 1 and {MAX_WORKERS}")

    # 1) Provenance gate
    verify_manifest_sha(args.manifest, args.accept_different_manifest)

    # 2) Parse + build-version gate
    manifest = parse_manifest(args.manifest)

    # 3) Structural validation — catches malformed chunk_parts upfront
    validate_manifest_structure(manifest)

    # 4) CDN base URL
    base_url = get_base_url()
    print(f"Using CDN base URL: {redact_url(base_url)}")

    ref_sha1 = args.reference_exe_sha1.upper().strip()
    ref_sha256 = args.reference_exe_sha256.upper().strip() or None

    # 5) Stage 1 — small download + external-reference cross-check
    if not stage1_verify(manifest, base_url, ref_sha1, ref_sha256):
        sys.exit("Stage 1 failed. Aborting before bulk download.")

    if args.verify_only:
        print("\n--verify-only requested; stopping after stage 1.")
        return

    # 6) Stage 2 — full download
    if not stage2_full(manifest, base_url, args.install_dir, args.workers):
        sys.exit("Stage 2 download failed. Re-run to retry; partial writes remain.")

    # 7) Post-install verification
    if not verify_install(manifest, args.install_dir):
        sys.exit(
            "Post-install verification failed. The install directory contains "
            "corrupted files; do not launch."
        )

    print("\n=== Done. Install verified. ===")
    print(f"  Game files:  {args.install_dir}")
    print("  Launch with: python rl_pre_eac_launcher.py")
    print("  (Running RocketLeague.exe directly will not load the main menu —")
    print("   the launcher script provides the Epic auth handshake the game needs.)")


if __name__ == "__main__":
    main()
