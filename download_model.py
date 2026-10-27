"""Download versioned official pose/hand models; never fetch camera data."""

from pathlib import Path
import hashlib
import argparse
import urllib.request


MODEL_HASHES = {
    "full": "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1",
    "lite": "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
    "hands": "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482",
}


def download(variant="full"):
    name = "gesture_recognizer" if variant == "hands" else f"pose_landmarker_{variant}"
    family = "gesture_recognizer" if variant == "hands" else "pose_landmarker"
    MODEL_PATH = Path(__file__).resolve().parent / "models" / f"{name}.task"
    MODEL_URL = f"https://storage.googleapis.com/mediapipe-models/{family}/{name}/float16/1/{name}.task"
    MODEL_SHA256 = MODEL_HASHES[variant]
    MODEL_PATH.parent.mkdir(exist_ok=True)
    if MODEL_PATH.is_file() and hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == MODEL_SHA256:
        print(f"Verified existing model: {MODEL_PATH}")
        return
    temporary = MODEL_PATH.with_suffix(".part")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
            with temporary.open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
        if temporary.stat().st_size < 1_000_000:
            raise RuntimeError("Model download was unexpectedly small; try again.")
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError("Model checksum mismatch; existing model was not replaced.")
        temporary.replace(MODEL_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Model ready: {MODEL_PATH}")
    print(f"SHA256: {hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=MODEL_HASHES, default="full")
    download(parser.parse_args().variant)
