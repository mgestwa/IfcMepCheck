"""Download the open sample IFC models used for manual checks and regression tests.

The models are not committed (samples/ is git-ignored). All of them are
published under CC BY 4.0: keep the attribution printed by --list when you
share results based on them.

Usage:
    python scripts/get_samples.py              # default samples
    python scripts/get_samples.py --all        # also the large optional ones
    python scripts/get_samples.py duplex-mep   # selected samples
    python scripts/get_samples.py --list
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OFFICIAL = "https://raw.githubusercontent.com/buildingSMART/Sample-Test-Files/main/"
COMMUNITY = (
    "https://media.githubusercontent.com/media/"
    "buildingsmart-community/Community-Sample-Test-Files/main/"
)
OFFICIAL_ATTRIBUTION = (
    "(C) buildingSMART International Ltd., CC BY 4.0, "
    "https://github.com/buildingSMART/Sample-Test-Files"
)
COMMUNITY_REPO = "https://github.com/buildingsmart-community/Community-Sample-Test-Files"


@dataclass(frozen=True)
class Sample:
    name: str
    filename: str
    url: str
    size: int
    sha256: str
    attribution: str
    optional: bool = False


def _url(base: str, path: str) -> str:
    return base + urllib.parse.quote(path)


SAMPLES = (
    Sample(
        name="building-hvac-ifc2x3",
        filename="Building-Hvac_IFC2X3.ifc",
        url=_url(OFFICIAL, "IFC 2.3.0.1 (IFC 2x3 TC1)/Simple-Scene/Building-Hvac.ifc"),
        size=69_893,
        sha256="f39478ce12ae2029eed8b565551412a3a4b518d10a8b501bc5e9c2a8a6d78bdb",
        attribution=OFFICIAL_ATTRIBUTION,
    ),
    Sample(
        name="building-hvac-ifc4",
        filename="Building-Hvac_IFC4.ifc",
        url=_url(OFFICIAL, "IFC 4.0.2.1 (IFC 4 ADD2 TC1)/Simple-Scene/Building-Hvac.ifc"),
        size=111_375,
        sha256="2c17ecad2b0fbd3335420ee42ba48963b5a395294e86bcdcfc786ee559f9a344",
        attribution=OFFICIAL_ATTRIBUTION,
    ),
    Sample(
        name="building-hvac-ifc4x3",
        filename="Building-Hvac_IFC4X3.ifc",
        url=_url(OFFICIAL, "IFC 4.3.2.0 (IFC 4.3 ADD2)/Simple-Scene/Building-Hvac.ifc"),
        size=111_304,
        sha256="22891586f153793d098811caec8a510cd404f6c2f1979fb329eeeebc3f475642",
        attribution=OFFICIAL_ATTRIBUTION,
    ),
    Sample(
        name="duplex-mep",
        filename="Duplex_MEP_20110907.ifc",
        url=_url(COMMUNITY, "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment/Duplex_MEP_20110907.ifc"),
        size=17_871_432,
        sha256="13976a8e223f177a6d7123679e4b02e750cd90c13f7bb20c593be125d9407119",
        attribution=(
            'BSI (2020) "Duplex Apartment Test Files," buildingSMART International, '
            f"CC BY 4.0, {COMMUNITY_REPO}"
        ),
    ),
    Sample(
        name="clinic-hvac",
        filename="Clinic_HVAC.ifc",
        url=_url(COMMUNITY, "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_HVAC.ifc"),
        size=26_914_597,
        sha256="39c88a79f48fbe56da86afb0fb3ebd188f8930df3df7dbfbd9ecaa535aaeab9b",
        attribution=(
            'BSI (2020) "Medical-Dental Test Files," buildingSMART International, '
            f"CC BY 4.0, {COMMUNITY_REPO}"
        ),
        optional=True,
    ),
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(sample: Sample, dest: Path) -> Path:
    target = dest / sample.filename
    if target.exists() and sha256_of(target) == sample.sha256:
        print(f"up to date  {target}")
        return target

    dest.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    request = urllib.request.Request(sample.url, headers={"User-Agent": "mepcheck-get-samples"})
    print(f"downloading {sample.name} ({sample.size / 1e6:.1f} MB) ...", flush=True)
    with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as out:
        for chunk in iter(lambda: response.read(1 << 16), b""):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != sample.sha256:
        part.unlink()
        raise SystemExit(f"Checksum mismatch for {sample.name}; the file was removed.")
    part.replace(target)
    print(f"saved       {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download open sample IFC models.")
    parser.add_argument("names", nargs="*", help="Samples to download (default: all non-optional).")
    parser.add_argument("--all", action="store_true", help="Include the large optional samples.")
    parser.add_argument("--list", action="store_true", help="List samples and their attribution.")
    parser.add_argument("--dest", type=Path, default=Path("samples"), help="Target directory.")
    args = parser.parse_args(argv)

    if args.list:
        for sample in SAMPLES:
            flag = " (optional)" if sample.optional else ""
            print(f"{sample.name:<22} {sample.size / 1e6:>6.1f} MB{flag}\n    {sample.attribution}")
        return 0

    by_name = {sample.name: sample for sample in SAMPLES}
    unknown = sorted(set(args.names) - by_name.keys())
    if unknown:
        parser.error(f"unknown sample(s): {', '.join(unknown)}; see --list")
    if args.names:
        selected = [by_name[name] for name in args.names]
    else:
        selected = [sample for sample in SAMPLES if args.all or not sample.optional]

    for sample in selected:
        download(sample, args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
