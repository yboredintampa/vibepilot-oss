# image_gen.py
from __future__ import annotations
import os, random, time, pathlib, urllib.request
from typing import Optional, Dict, Any

# Uses the official SDK (pip install replicate)
try:
    import replicate
except Exception:
    replicate = None

IMAGES_DIR = pathlib.Path("posts/images")

# -------- Public helpers --------
def images_enabled() -> bool:
    """Image gen is considered enabled iff token + SDK are present AND ALLOW_IMAGE_POSTS != '0'."""
    if os.getenv("ALLOW_IMAGE_POSTS", "1") == "0":
        return False
    tok = os.getenv("REPLICATE_API_TOKEN", "")
    return bool(tok and replicate is not None)

def choose_style() -> Dict[str, Any]:
    """Randomized, authentic-looking style mix."""
    # Weights roughly: warm film 40%, glossy 25%, matte 25%, b&w 10%
    styles = [
        ("warm_film", 0.40, {"width": _pick([1024, 1280, 1536]), "height": _pick([1024, 1280, 1536])}),
        ("glossy",    0.25, {"width": _pick([1024, 1280, 1536, 2048]), "height": _pick([1024, 1280, 1536, 2048])}),
        ("matte",     0.25, {"width": _pick([1024, 1280, 1536]), "height": _pick([1024, 1280, 1536])}),
        ("bw_film",   0.10, {"width": _pick([1024, 1280]), "height": _pick([1024, 1280])}),
    ]
    r = random.random()
    acc = 0.0
    for name, w, dims in styles:
        acc += w
        if r <= acc:
            return {"name": name, **dims}
    # fallback
    return {"name": "warm_film", "width": 1024, "height": 1024}

def generate_image(prompt: str,
                   outdir: str = "posts/images",
                   width: int = 768,
                   height: int = 768,
                   num_outputs: int = 1,
                   model: str | None = None) -> str:
    """
    Generate an image via Replicate and save it locally.
    Returns the saved file path (string).
    """
    import os, base64, re as _re, urllib.request, time
    try:
        import replicate
    except Exception as e:
        raise RuntimeError(f"replicate SDK not installed: {e}")

    token = os.getenv("REPLICATE_API_TOKEN")
    if not token:
        raise RuntimeError("REPLICATE_API_TOKEN not set")

    model = model or os.getenv("REPLICATE_OWNER_MODEL", "black-forest-labs/flux-schnell")
    os.makedirs(outdir, exist_ok=True)

    out = replicate.run(model,
        input={"prompt": prompt, "width": int(width, use_file_output=False), "height": int(height), "num_outputs": int(num_outputs)},
        use_file_output=False
    )

    if isinstance(out, (list, tuple)) and out:
        uri = out[0]
    elif isinstance(out, str):
        uri = out
    else:
        raise RuntimeError(f"Unexpected replicate output: {type(out)} -> {out!r}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = f"img_{ts}.png"
    fpath = os.path.join(outdir, fname)

    if isinstance(uri, str) and uri.startswith("data:image/"):
        m = _re.match(r'^data:image/[^;]+;base64,(.+)$', uri)
        if not m:
            raise RuntimeError("Could not parse data URL from Replicate output")
        raw = base64.b64decode(m.group(1))
        with open(fpath, "wb") as fp:
            fp.write(raw)
    else:
        urllib.request.urlretrieve(uri, fpath)

    return fpath
def _pick(lst):
    return random.choice(lst)
