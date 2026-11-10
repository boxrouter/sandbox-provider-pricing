# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Built archives retain the package license and public distribution metadata."""

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LICENSE_FILES = ("LICENSE", "NOTICE")


def test_wheel_and_sdist_include_license_files(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    subprocess.run(
        [uv, "build", "--out-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        cwd=ROOT,
        text=True,
    )

    wheels = list(tmp_path.glob("*.whl"))
    sdists = list(tmp_path.glob("*.tar.gz"))
    assert len(wheels) == 1
    assert len(sdists) == 1

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = wheel.read(metadata_name).decode("utf-8")
        assert "License-Expression: Apache-2.0" in metadata
        assert "License-File: LICENSE" in metadata
        assert "License-File: NOTICE" in metadata
        assert "Private :: Do Not Upload" not in metadata

        for filename in LICENSE_FILES:
            wheel_matches = [
                name
                for name in names
                if PurePosixPath(name).name == filename and "licenses" in PurePosixPath(name).parts
            ]
            assert len(wheel_matches) == 1
            assert wheel.read(wheel_matches[0]) == (ROOT / filename).read_bytes()

    with tarfile.open(sdists[0], mode="r:gz") as source:
        members = source.getmembers()
        for filename in LICENSE_FILES:
            sdist_matches = [
                member
                for member in members
                if PurePosixPath(member.name).name == filename and member.isfile()
            ]
            assert len(sdist_matches) == 1
            payload = source.extractfile(sdist_matches[0])
            assert payload is not None
            assert payload.read() == (ROOT / filename).read_bytes()
