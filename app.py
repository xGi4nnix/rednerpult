import json
import os
import tempfile
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import safe_join
from werkzeug.utils import secure_filename
from PIL import Image, ImageSequence, UnidentifiedImageError


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
SLIDES_DIR = DATA_DIR / "slides"
LOGOS_DIR = DATA_DIR / "logos"
STATE_FILE = DATA_DIR / "state.json"

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TRANSITIONS = {"cut", "fade"}
BG_CURRENT = "__background__"
BLACK_CURRENT = "__black__"
DEFAULT_LOGO = {"filename": "", "x": 0.5, "y": 0.5, "w": 0.34}
DEFAULT_STATE = {
    "current": "logo.png",
    "version": 1,
    "transition": "cut",
    "duration": 500,
    "order": [],
    "background": "blank.png",
    "logo": DEFAULT_LOGO,
}

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET") or "dev-only-change-me"
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        STATE_FILE.write_text(json.dumps(DEFAULT_STATE, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def slide_exists(filename: str) -> bool:
    if filename != os.path.basename(filename):
        return False
    if not allowed_file(filename):
        return False
    resolved = safe_join(str(SLIDES_DIR), filename)
    return bool(resolved and Path(resolved).is_file())


def logo_exists(filename: str) -> bool:
    if filename != os.path.basename(filename):
        return False
    if not allowed_file(filename):
        return False
    resolved = safe_join(str(LOGOS_DIR), filename)
    return bool(resolved and Path(resolved).is_file())


def read_state() -> dict:
    ensure_storage()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {**DEFAULT_STATE, "current": "", "version": 0}

    current = state.get("current") if isinstance(state.get("current"), str) else ""
    version = state.get("version") if isinstance(state.get("version"), int) else 0
    transition = state.get("transition") if state.get("transition") in TRANSITIONS else DEFAULT_STATE["transition"]
    duration = state.get("duration") if isinstance(state.get("duration"), int) else DEFAULT_STATE["duration"]
    existing = set(slide_filenames_sorted())
    order = state.get("order") if isinstance(state.get("order"), list) else []
    order = [name for name in order if isinstance(name, str) and name in existing]
    order.extend(name for name in sorted(existing, key=str.casefold) if name not in order)
    background = state.get("background") if isinstance(state.get("background"), str) else DEFAULT_STATE["background"]
    if background and not slide_exists(background):
        background = ""
    if current and current not in {BG_CURRENT, BLACK_CURRENT} and not slide_exists(current):
        current = ""
    logo = state.get("logo") if isinstance(state.get("logo"), dict) else {}
    logo_filename = logo.get("filename") if isinstance(logo.get("filename"), str) else ""
    if logo_filename and not logo_exists(logo_filename):
        logo_filename = ""
    logo_state = {
        "filename": logo_filename,
        "x": min(max(float(logo.get("x", DEFAULT_LOGO["x"])), 0), 1) if isinstance(logo.get("x", DEFAULT_LOGO["x"]), (int, float)) else DEFAULT_LOGO["x"],
        "y": min(max(float(logo.get("y", DEFAULT_LOGO["y"])), 0), 1) if isinstance(logo.get("y", DEFAULT_LOGO["y"]), (int, float)) else DEFAULT_LOGO["y"],
        "w": min(max(float(logo.get("w", DEFAULT_LOGO["w"])), 0.05), 1) if isinstance(logo.get("w", DEFAULT_LOGO["w"]), (int, float)) else DEFAULT_LOGO["w"],
    }
    return {
        "current": current,
        "version": max(version, 0),
        "transition": transition,
        "duration": min(max(duration, 0), 5000),
        "order": order,
        "background": background,
        "logo": logo_state,
    }


def write_state(state: dict) -> None:
    ensure_storage()
    fd, tmp_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=DATA_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
    os.replace(tmp_name, STATE_FILE)


def slide_filenames_sorted() -> list[str]:
    ensure_storage()
    files = []
    for path in SLIDES_DIR.iterdir():
        if path.is_file() and allowed_file(path.name):
            files.append(path.name)
    return sorted(files, key=str.casefold)


def list_slides() -> list[str]:
    return read_state()["order"]


def rotate_slide_file(filename: str) -> None:
    resolved = safe_join(str(SLIDES_DIR), filename)
    if not resolved:
        raise ValueError("invalid path")

    source = Path(resolved)
    suffix = source.suffix.lower()
    fd, tmp_name = tempfile.mkstemp(prefix=f"{source.stem}-rotate-", suffix=suffix, dir=SLIDES_DIR)
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        with Image.open(source) as image:
            if suffix == ".gif" and getattr(image, "is_animated", False):
                frames = []
                durations = []
                for frame in ImageSequence.Iterator(image):
                    frames.append(frame.convert("RGBA").rotate(-90, expand=True))
                    durations.append(frame.info.get("duration", image.info.get("duration", 100)))
                frames[0].save(
                    tmp_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=image.info.get("loop", 0),
                    disposal=2,
                )
            else:
                rotated = image.rotate(-90, expand=True)
                save_kwargs = {}
                if suffix in {".jpg", ".jpeg"}:
                    rotated = rotated.convert("RGB")
                    save_kwargs = {"quality": 95, "optimize": True}
                elif suffix == ".png":
                    save_kwargs = {"optimize": True}
                rotated.save(tmp_path, **save_kwargs)
        os.replace(tmp_path, source)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def save_image_like_original(image: Image.Image, target: Path, tmp_path: Path) -> None:
    suffix = target.suffix.lower()
    save_kwargs = {}
    if suffix in {".jpg", ".jpeg"}:
        image = image.convert("RGB")
        save_kwargs = {"quality": 95, "optimize": True}
    elif suffix == ".png":
        save_kwargs = {"optimize": True}
    image.save(tmp_path, **save_kwargs)


def crop_slide_file(filename: str, crop: dict) -> None:
    resolved = safe_join(str(SLIDES_DIR), filename)
    if not resolved:
        raise ValueError("invalid path")

    source = Path(resolved)
    suffix = source.suffix.lower()
    values = []
    for key in ("x", "y", "w", "h"):
        value = crop.get(key)
        if not isinstance(value, (int, float)):
            raise ValueError("invalid crop")
        values.append(float(value))

    x_norm, y_norm, w_norm, h_norm = values
    if w_norm <= 0 or h_norm <= 0:
        raise ValueError("invalid crop")

    fd, tmp_name = tempfile.mkstemp(prefix=f"{source.stem}-crop-", suffix=suffix, dir=SLIDES_DIR)
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        with Image.open(source) as image:
            width, height = image.size
            left = max(0, min(int(round(x_norm * width)), width - 1))
            top = max(0, min(int(round(y_norm * height)), height - 1))
            right = max(left + 1, min(int(round((x_norm + w_norm) * width)), width))
            bottom = max(top + 1, min(int(round((y_norm + h_norm) * height)), height))
            if right - left < 2 or bottom - top < 2:
                raise ValueError("crop too small")

            if suffix == ".gif" and getattr(image, "is_animated", False):
                frames = []
                durations = []
                for frame in ImageSequence.Iterator(image):
                    frames.append(frame.convert("RGBA").crop((left, top, right, bottom)))
                    durations.append(frame.info.get("duration", image.info.get("duration", 100)))
                frames[0].save(
                    tmp_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=image.info.get("loop", 0),
                    disposal=2,
                )
            else:
                save_image_like_original(image.crop((left, top, right, bottom)), source, tmp_path)
        os.replace(tmp_path, source)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


BASE_STYLE = """
<style>
  :root {
    color-scheme: light;
    --bg: #f6f8fb;
    --surface: #ffffff;
    --surface-2: #f0f4f8;
    --surface-3: #e6edf5;
    --text: #111827;
    --muted: #667085;
    --soft: #98a2b3;
    --line: #d9e2ec;
    --primary: #2457d6;
    --primary-dark: #173ea1;
    --accent: #00a88f;
    --danger: #d92d20;
    --warning: #b54708;
    --shadow: 0 20px 50px rgba(15, 23, 42, .10);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  button, input { font: inherit; }
  a { color: inherit; }
  .page { max-width: 1440px; margin: 0 auto; padding: 20px; }
  h1 { margin: 0; font-size: 1.3rem; line-height: 1.1; letter-spacing: 0; }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    margin-bottom: 12px;
  }
  .connection-status {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    background: #f0fdf4;
    color: #047857;
    padding: 8px 11px;
    font-size: .88rem;
    font-weight: 950;
  }
  .connection-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: #12b76a;
    box-shadow: 0 0 0 4px rgba(18, 183, 106, .14);
  }
  .connection-status.offline {
    border-color: #fecdca;
    background: #fff4f3;
    color: #b42318;
  }
  .connection-status.offline .connection-dot {
    background: var(--danger);
    box-shadow: 0 0 0 4px rgba(217, 45, 32, .14);
  }
  .shell {
    display: grid;
    grid-template-columns: minmax(340px, 420px) minmax(360px, 1fr);
    gap: 14px;
    align-items: stretch;
    min-height: min(680px, calc(100vh - 40px));
  }
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  .library {
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    min-height: 0;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 11px 14px;
    border-bottom: 1px solid var(--line);
  }
  .panel-title { font-weight: 900; }
  .panel-subtitle { margin-top: 3px; color: var(--muted); font-size: .86rem; font-weight: 700; }
  .button, .upload button, .login button {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px 14px;
    min-height: 44px;
    background: var(--surface);
    color: var(--text);
    font-weight: 900;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .button:hover, .upload button:hover, .login button:hover { border-color: var(--primary); }
  .button.primary { background: var(--primary); border-color: var(--primary); color: #fff; }
  .button.primary:hover { background: var(--primary-dark); border-color: var(--primary-dark); }
  .button.blank { background: #101828; border-color: #101828; color: #fff; }
  .upload {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 10px 14px;
    background: var(--surface-2);
    border-bottom: 1px solid var(--line);
  }
  .upload input[type=file] { max-width: 100%; color: var(--muted); }
  .upload button[hidden] { display: none; }
  .settings {
    display: grid;
    grid-template-columns: 1fr 105px auto;
    align-items: end;
    gap: 10px;
    padding: 10px 12px;
    background: var(--surface);
    border-bottom: 1px solid var(--line);
  }
  .settings label { display: grid; gap: 7px; color: var(--muted); font-weight: 800; }
  .settings input {
    width: 100%;
    min-height: 40px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 10px;
  }
  .segment { display: flex; gap: 8px; flex-wrap: wrap; }
  .segment button { min-width: 82px; }
  .segment button.active { background: var(--surface-3); border-color: var(--primary); color: var(--primary); }
  .message { margin: 14px 0; color: var(--danger); font-weight: 700; }
  .save-state {
    min-height: 1.1em;
    color: var(--muted);
    font-size: .78rem;
    font-weight: 850;
    text-align: center;
  }
  .save-state.error { color: var(--danger); }
  .slide-list { display: block; min-height: 0; overflow: auto; }
  .slide-row {
    display: grid;
    grid-template-columns: 50px minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    border: 0;
    border-bottom: 1px solid var(--line);
    background: var(--surface);
    padding: 9px 11px;
    text-align: left;
    cursor: pointer;
    color: var(--text);
  }
  .slide-row:hover, .slide-row.selected { background: #eef4ff; }
  .slide-row.active { box-shadow: inset 4px 0 0 var(--accent); }
  .slide-row.bg-row { background: #f8fafc; }
  .slide-row.bg-row .thumb { display: grid; place-items: center; color: #fff; font-weight: 950; font-size: .72rem; }
  .slide-row.dragging { opacity: .45; }
  .slide-row.drag-over { outline: 2px solid var(--primary); outline-offset: -2px; }
  .thumb { width: 50px; height: 50px; border-radius: 8px; object-fit: cover; background: #000; border: 1px solid var(--line); }
  .slide-name { min-width: 0; font-weight: 900; word-break: break-word; }
  .slide-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    word-break: normal;
  }
  .slide-tools { display: flex; align-items: center; gap: 8px; }
  .slide-meta { color: var(--muted); font-size: .82rem; font-weight: 900; white-space: nowrap; }
  .slide-meta.live { color: #047857; }
  .row-action {
    width: 38px;
    height: 38px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    font-weight: 950;
    cursor: pointer;
  }
  .row-action:hover { border-color: var(--primary); color: var(--primary); }
  .row-action.delete { color: var(--danger); }
  .row-action.delete:hover { border-color: #fecdca; background: #fff4f3; }
  .output-stack {
    position: sticky;
    top: 10px;
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto auto;
    gap: 10px;
    align-self: stretch;
    min-height: 0;
    padding: 8px 12px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
  }
  .monitors-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(150px, .34fr) minmax(0, 1fr);
    gap: 18px;
    align-items: stretch;
    min-height: 0;
  }
  .switch-column {
    display: grid;
    align-content: center;
    justify-items: center;
    gap: 12px;
    min-width: 0;
  }
  .switch-button {
    width: min(180px, 100%);
    min-height: 54px;
    border-color: var(--danger);
    background: var(--danger);
    color: #fff;
    font-size: 1rem;
    box-shadow: 0 14px 32px rgba(217, 45, 32, .22);
  }
  .switch-button:hover {
    border-color: #b42318;
    background: #b42318;
  }
  .monitor {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    align-items: stretch;
    gap: 8px;
    min-height: 0;
  }
  .monitor-label {
    font-size: clamp(1.2rem, 2.1vw, 1.7rem);
    font-weight: 950;
    color: #020617;
    text-transform: uppercase;
    text-align: center;
  }
  .monitor-stage {
    display: grid;
    place-items: center;
    min-height: 0;
  }
  .monitor-frame {
    height: min(52vh, 520px);
    width: auto;
    aspect-ratio: 9 / 16;
    margin: 0 auto;
    border-radius: 0;
    background: #000;
    overflow: hidden;
    border: 0;
    box-shadow: 0 12px 30px rgba(15, 23, 42, .14);
    position: relative;
  }
  .monitor-frame img { width: 100%; height: 100%; object-fit: contain; display: block; }
  .program-frame img {
    position: absolute;
    inset: 0;
  }
  .program-transition-layer {
    opacity: 0;
    pointer-events: none;
  }
  .monitor-frame .logo-overlay {
    position: absolute;
    transform: translate(-50%, -50%);
    height: auto;
    object-fit: contain;
  }
  .transition-strip {
    display: block;
    width: 100%;
  }
  .transition-strip .settings {
    border: 0;
    background: transparent;
    padding: 0;
    grid-template-columns: 1fr;
    align-items: center;
    gap: 7px;
    width: 100%;
  }
  .transition-strip .settings label { color: var(--text); }
  .transition-strip .segment { justify-content: center; }
  .transition-strip .segment button {
    min-width: 78px;
    min-height: 34px;
    padding: 6px 12px;
    border-color: #f59e0b;
    background: #fff7ed;
  }
  .transition-strip .segment button[data-transition="fade"] {
    border-color: #8ab4f8;
    background: #eff6ff;
  }
  .transition-strip .segment button.active {
    color: var(--text);
    box-shadow: inset 0 0 0 2px currentColor;
  }
  .preview-body { display: grid; gap: 7px; }
  .preview-name { font-size: .9rem; font-weight: 950; word-break: break-word; }
  .utility-actions { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .logo-upload { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; }
  .logo-upload input[type=file] { min-width: 0; color: var(--muted); }
  .blackout-button {
    width: min(180px, 100%);
    min-height: 42px;
    background: #101828;
    border-color: #101828;
    color: #fff;
  }
  .rotate {
    background: var(--surface);
    border: 1px solid var(--line);
    color: var(--text);
  }
  .hint { color: var(--muted); font-weight: 700; }
  .credit {
    position: fixed;
    right: 14px;
    bottom: 10px;
    color: rgba(102, 112, 133, .62);
    font-size: .72rem;
    font-weight: 800;
    pointer-events: auto;
    text-decoration: none;
  }
  .crop-modal {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: none;
    place-items: center;
    padding: 20px;
    background: rgba(15, 23, 42, .72);
  }
  .crop-modal.open { display: grid; }
  .crop-panel {
    width: min(1040px, 100%);
    max-height: calc(100vh - 40px);
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    background: var(--surface);
    border-radius: 8px;
    border: 1px solid var(--line);
    box-shadow: 0 28px 90px rgba(15, 23, 42, .35);
    overflow: hidden;
  }
  .crop-head, .crop-actions { padding: 12px 14px; border-bottom: 1px solid var(--line); }
  .crop-actions { border-top: 1px solid var(--line); border-bottom: 0; display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
  .crop-title { font-weight: 950; }
  .crop-help { margin-top: 4px; color: var(--muted); font-size: .9rem; font-weight: 800; }
  .crop-workspace {
    min-height: 0;
    display: grid;
    place-items: center;
    padding: 14px;
    background: #0b1220;
    overflow: auto;
  }
  .crop-canvas {
    position: relative;
    display: inline-block;
    max-width: 100%;
    max-height: calc(100vh - 210px);
  }
  .logo-stage {
    position: relative;
    width: min(360px, 72vw);
    aspect-ratio: 9 / 16;
    background: #111827;
    overflow: hidden;
    border-radius: 8px;
    box-shadow: 0 20px 70px rgba(2, 6, 23, .38);
  }
  .logo-stage > img:first-child { width: 100%; height: 100%; object-fit: cover; display: block; }
  .logo-placement {
    position: absolute;
    transform: translate(-50%, -50%);
    cursor: grab;
    touch-action: none;
    outline: 2px solid rgba(36, 87, 214, .9);
    outline-offset: 3px;
  }
  .logo-placement:active { cursor: grabbing; }
  .logo-size { display: flex; align-items: center; gap: 10px; color: var(--text); font-weight: 900; }
  .logo-size input { accent-color: var(--primary); }
  .crop-canvas img {
    display: block;
    max-width: 100%;
    max-height: calc(100vh - 210px);
    object-fit: contain;
    user-select: none;
    -webkit-user-drag: none;
  }
  .crop-box {
    position: absolute;
    border: 3px solid #fff;
    box-shadow: 0 0 0 9999px rgba(2, 6, 23, .58), 0 0 0 1px rgba(36, 87, 214, .8);
    cursor: move;
    touch-action: none;
  }
  .crop-box::after {
    content: "9:16";
    position: absolute;
    right: 8px;
    bottom: 8px;
    border-radius: 999px;
    background: rgba(255,255,255,.9);
    color: var(--text);
    padding: 4px 8px;
    font-size: .72rem;
    font-weight: 950;
  }
  .login { min-height: 100vh; display: grid; place-items: center; padding: 18px; }
  .login form {
    width: min(420px, 100%);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 22px;
    box-shadow: var(--shadow);
  }
  .login label { display: grid; gap: 7px; margin: 14px 0; color: var(--muted); font-weight: 700; }
  .login input { width: 100%; min-height: 48px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface); color: var(--text); padding: 10px; }
  @media (max-width: 900px) {
    .page { padding: 12px; }
    .shell { grid-template-columns: 1fr; min-height: 0; }
    .library { grid-row: 2; min-height: auto; }
    .output-stack {
      grid-row: 1;
      order: -1;
      position: static;
      padding: 10px;
      gap: 10px;
    }
    .monitors-row {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .monitor.preview { order: 1; }
    .monitor.program { order: 2; }
    .switch-column {
      order: 3;
      grid-column: 1 / -1;
      align-content: stretch;
      gap: 8px;
    }
    .switch-button {
      width: 100%;
      min-height: 48px;
    }
    .monitor-label { text-align: center; font-size: 1rem; }
    .settings, .utility-actions { grid-template-columns: 1fr; }
    .transition-strip .settings { grid-template-columns: 1fr minmax(90px, .5fr); }
    .button, .upload button, .settings button { width: 100%; }
    .settings label, .settings input, .segment { width: 100%; }
    .segment { flex-wrap: nowrap; }
    .segment button { flex: 1; min-width: 0; }
    .slide-list { max-height: 48vh; }
    .monitor-frame { height: min(36vh, 340px); }
    .crop-modal { padding: 10px; }
    .crop-actions .button { width: 100%; }
  }
  @media (max-width: 560px) {
    .page { padding: 8px; }
    .shell { gap: 10px; }
    .output-stack { padding: 8px; }
    .monitors-row { gap: 8px; }
    .monitor { gap: 5px; }
    .monitor-label { font-size: .82rem; }
    .monitor-frame {
      height: min(32vh, 270px);
      box-shadow: 0 8px 22px rgba(15, 23, 42, .12);
    }
    .transition-strip .settings {
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .switch-button {
      min-height: 50px;
      font-size: .96rem;
    }
    .blackout-button {
      width: 100%;
      min-height: 46px;
    }
    .preview-body { gap: 8px; }
    .preview-name { font-size: .84rem; }
    .upload {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .upload input[type=file] { width: 100%; }
    .slide-row {
      grid-template-columns: 46px minmax(0, 1fr) auto;
      padding: 8px;
    }
    .thumb { width: 46px; height: 46px; }
    .row-action {
      width: 36px;
      height: 36px;
    }
    .slide-tools { gap: 6px; }
    .slide-meta { font-size: .76rem; }
    .credit { display: none; }
  }
</style>
"""


@app.route("/")
def index():
    return redirect(url_for("control"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        expected_user = os.environ.get("ADMIN_USER", "admin")
        expected_password = os.environ.get("ADMIN_PASSWORD", "admin")
        if request.form.get("username") == expected_user and request.form.get("password") == expected_password:
            session.clear()
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("control"))
        error = "Login fehlgeschlagen"

    return render_template_string(
        """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login</title>{{ style|safe }}</head>
        <body><main class="login"><form method="post"><h1>Pult Display</h1>{% if error %}<div class="message">{{ error }}</div>{% endif %}
        <label>Benutzername <input name="username" autocomplete="username" required autofocus></label>
        <label>Passwort <input name="password" type="password" autocomplete="current-password" required></label>
        <button type="submit">Einloggen</button></form></main></body></html>""",
        style=BASE_STYLE,
        error=error,
    )


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/control")
@login_required
def control():
    state = read_state()
    slides = list_slides()
    message = request.args.get("message", "")
    if "hochgeladen" in message:
        message = ""
    return render_template_string(
        """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Steuerung</title>{{ style|safe }}</head>
        <body><main class="page">
        <header class="topbar">
          <div class="connection-status" id="connection-status" role="status" aria-live="polite">
            <span class="connection-dot" aria-hidden="true"></span>
            <span id="connection-text">Verbindung Okay</span>
          </div>
        </header>
        {% if message %}<div class="message">{{ message }}</div>{% endif %}
        {% set selected = bg_current if state.current == bg_current else (state.current if state.current in slides else (slides[0] if slides else bg_current)) %}
        <section class="shell">
          <aside class="panel library">
            <div class="panel-head">
              <div><div class="panel-title">Grafiken</div><div class="panel-subtitle">Ziehen zum Sortieren</div></div>
              <span class="hint">{{ slides|length }} Dateien</span>
            </div>
            <form class="upload" action="{{ url_for('upload') }}" method="post" enctype="multipart/form-data">
              <input id="slide-upload-input" type="file" name="file" accept=".png,.jpg,.jpeg,.webp,.gif,image/png,image/jpeg,image/webp,image/gif" multiple required>
              <button id="slide-upload-submit" type="submit" hidden disabled>Upload</button>
            </form>
            <section class="slide-list" aria-label="Grafiken">
              <article class="slide-row bg-row {% if state.current == bg_current %}active{% endif %} {% if selected == bg_current %}selected{% endif %}" data-slide="{{ bg_current }}" data-bg="1" data-src="{% if state.background %}{{ url_for('slides', filename=state.background) }}?v={{ state.version }}{% endif %}" role="button" tabindex="0">
                {% if state.background %}<img class="thumb" src="{{ url_for('slides', filename=state.background) }}?v={{ state.version }}" alt="">{% else %}<span class="thumb">BG</span>{% endif %}
                <span class="slide-name">bg</span>
                <span class="slide-tools">
                  <span class="slide-meta {% if state.current == bg_current %}live{% endif %}">{% if state.current == bg_current %}Live{% else %}Bereit{% endif %}</span>
                </span>
              </article>
              {% for slide in slides %}
              <article class="slide-row {% if slide == state.current %}active{% endif %} {% if slide == selected %}selected{% endif %}" draggable="true" data-slide="{{ slide }}" data-src="{{ url_for('slides', filename=slide) }}?v={{ state.version }}" role="button" tabindex="0">
                <img class="thumb" src="{{ url_for('slides', filename=slide) }}?v={{ state.version }}" alt="">
                <span class="slide-name">{{ slide }}</span>
                <span class="slide-tools">
                  <span class="slide-meta {% if slide == state.current %}live{% endif %}">{% if slide == state.current %}Live{% else %}Bereit{% endif %}</span>
                  <button class="row-action rotate" data-row-rotate="{{ slide }}" type="button" title="90 Grad drehen">↻</button>
                  <button class="row-action delete" data-row-delete="{{ slide }}" type="button" title="Löschen">×</button>
                </span>
              </article>
              {% endfor %}
            </section>
          </aside>

          <section class="output-stack">
            <div class="monitors-row">
              <section class="monitor preview">
                <div class="monitor-label">Preview</div>
                <div class="monitor-stage">
                  <div class="monitor-frame">
                    {% if selected == bg_current and state.background %}<img id="preview-image" src="{{ url_for('slides', filename=state.background) }}?v={{ state.version }}" alt="">{% elif selected and selected != bg_current %}<img id="preview-image" src="{{ url_for('slides', filename=selected) }}?v={{ state.version }}" alt="">{% else %}<img id="preview-image" alt="">{% endif %}
                  </div>
                </div>
              </section>

              <div class="switch-column">
                <button class="button switch-button" id="take-slide" type="button">Umschalten</button>
                <section class="transition-strip" aria-label="Übergang">
                  <section class="settings">
                    <span class="segment">
                      <button class="button {% if state.transition == 'cut' %}active{% endif %}" data-transition="cut" type="button">Cut</button>
                      <button class="button {% if state.transition == 'fade' %}active{% endif %}" data-transition="fade" type="button">Fade</button>
                    </span>
                    <label>Zeit ms
                      <input id="duration" type="number" min="0" max="5000" step="100" value="{{ state.duration }}">
                    </label>
                  </section>
                </section>
                <div class="save-state" id="settings-status" aria-live="polite"></div>
                <button class="button blackout-button" data-set="{{ black_current }}" type="button">Schwarz</button>
              </div>

              <section class="monitor program">
                <div class="monitor-label">Program</div>
                <div class="monitor-stage">
                  <div class="monitor-frame program-frame" id="program-frame">
                    {% if state.current == bg_current and state.background %}
                      <img id="program-image" src="{{ url_for('slides', filename=state.background) }}?v={{ state.version }}" alt="">
                      {% if state.logo.filename %}<img class="logo-overlay" src="{{ url_for('logos', filename=state.logo.filename) }}?v={{ state.version }}" alt="" style="left: {{ state.logo.x * 100 }}%; top: {{ state.logo.y * 100 }}%; width: {{ state.logo.w * 100 }}%;">{% endif %}
                    {% elif state.current == black_current %}
                      <img id="program-image" alt="">
                    {% elif state.current %}
                      <img id="program-image" src="{{ url_for('slides', filename=state.current) }}?v={{ state.version }}" alt="">
                    {% else %}
                      <img id="program-image" alt="">
                    {% endif %}
                    <img class="program-transition-layer" id="program-next-image" alt="">
                  </div>
                </div>
              </section>
            </div>

            <section class="preview-body">
              <div class="preview-name" id="preview-name">{% if selected == bg_current %}bg{% else %}{{ selected or "Keine Grafik vorhanden" }}{% endif %}</div>
              <div class="utility-actions">
                <button class="button" id="open-crop" type="button">Ausschnitt bearbeiten</button>
              </div>
            </section>
          </section>
        </section>
        <section class="crop-modal" id="crop-modal" aria-hidden="true">
          <div class="crop-panel">
            <div class="crop-head">
              <div class="crop-title">Ausschnitt bearbeiten</div>
              <div class="crop-help">Den 9:16-Rahmen verschieben und speichern. Die Grafik wird dauerhaft zugeschnitten.</div>
            </div>
            <div class="crop-workspace">
              <div class="crop-canvas" id="crop-canvas">
                <img id="crop-image" alt="">
                <div class="crop-box" id="crop-box"></div>
              </div>
            </div>
            <div class="crop-actions">
              <button class="button" id="cancel-crop" type="button">Abbrechen</button>
              <button class="button primary" id="save-crop" type="button">Ausschnitt speichern</button>
            </div>
          </div>
        </section>
        <section class="crop-modal" id="logo-modal" aria-hidden="true">
          <div class="crop-panel">
            <div class="crop-head">
              <div class="crop-title">Logo positionieren</div>
              <div class="crop-help">Logo auf dem Hintergrund verschieben, Größe einstellen und speichern.</div>
            </div>
            <div class="crop-workspace">
              <div class="logo-stage" id="logo-stage">
                {% if state.background %}<img id="logo-bg-image" src="{{ url_for('slides', filename=state.background) }}?v={{ state.version }}" alt="">{% else %}<img id="logo-bg-image" alt="">{% endif %}
                {% if state.logo.filename %}<img class="logo-placement" id="logo-placement" src="{{ url_for('logos', filename=state.logo.filename) }}?v={{ state.version }}" alt="">{% else %}<img class="logo-placement" id="logo-placement" alt="" style="display:none">{% endif %}
              </div>
            </div>
            <div class="crop-actions">
              <label class="logo-size">Größe <input id="logo-size" type="range" min="5" max="100" value="{{ (state.logo.w * 100)|round|int }}"></label>
              <button class="button" id="cancel-logo" type="button">Abbrechen</button>
              <button class="button primary" id="save-logo" type="button">Logo speichern</button>
            </div>
          </div>
        </section>
        <a class="credit" href="https://gianniborn.de">2026 Gianni Born</a>
        </main>
        <script>
	          let selectedName = {{ selected|tojson }};
	          const slideOrder = {{ slides|tojson }};
	          const currentName = {{ state.current|tojson }};
	          const bgCurrent = {{ bg_current|tojson }};
	          const blackCurrent = {{ black_current|tojson }};
	          const blackImageSrc = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
	          const logoState = {{ state.logo|tojson }};
	          const previewImage = document.getElementById("preview-image");
	          const previewName = document.getElementById("preview-name");
	          const programImage = document.getElementById("program-image");
	          const programNextImage = document.getElementById("program-next-image");
	          const durationInput = document.getElementById("duration");
	          const settingsStatus = document.getElementById("settings-status");
	          const connectionStatus = document.getElementById("connection-status");
	          const connectionText = document.getElementById("connection-text");
	          const slideUploadInput = document.getElementById("slide-upload-input");
	          const slideUploadSubmit = document.getElementById("slide-upload-submit");
	          const cropModal = document.getElementById("crop-modal");
	          const cropImage = document.getElementById("crop-image");
	          const cropBox = document.getElementById("crop-box");
	          const cropCanvas = document.getElementById("crop-canvas");
	          const logoModal = document.getElementById("logo-modal");
	          const logoStage = document.getElementById("logo-stage");
	          const logoPlacement = document.getElementById("logo-placement");
	          const logoSize = document.getElementById("logo-size");
	          let cropRect = {x: 0, y: 0, w: 0, h: 0};
	          let cropDrag = null;
	          let logoDrag = null;
	          let logoRect = {x: logoState.x || 0.5, y: logoState.y || 0.5, w: logoState.w || 0.34};
	          let settingsTimer = null;

	          slideUploadInput.addEventListener("change", () => {
	            const hasFiles = slideUploadInput.files && slideUploadInput.files.length > 0;
	            slideUploadSubmit.hidden = !hasFiles;
	            slideUploadSubmit.disabled = !hasFiles;
	          });

	          function selectSlide(row) {
	            selectedName = row.dataset.slide;
	            document.querySelectorAll("[data-slide]").forEach((item) => item.classList.toggle("selected", item === row));
	            previewName.textContent = selectedName === bgCurrent ? "bg" : selectedName;
	            if (row.dataset.src) previewImage.src = `${row.dataset.src}&t=${Date.now()}`;
	          }
          function selectedRow() {
            return selectedName ? document.querySelector(`[data-slide="${CSS.escape(selectedName)}"]`) : null;
          }
          function clampCrop() {
            const imageRect = cropImage.getBoundingClientRect();
            cropRect.x = Math.max(0, Math.min(cropRect.x, imageRect.width - cropRect.w));
            cropRect.y = Math.max(0, Math.min(cropRect.y, imageRect.height - cropRect.h));
          }
          function renderCropBox() {
            clampCrop();
            cropBox.style.left = `${cropRect.x}px`;
            cropBox.style.top = `${cropRect.y}px`;
            cropBox.style.width = `${cropRect.w}px`;
            cropBox.style.height = `${cropRect.h}px`;
          }
          function resetCropBox() {
            const imageRect = cropImage.getBoundingClientRect();
            let cropHeight = imageRect.height;
            let cropWidth = cropHeight * 9 / 16;
            if (cropWidth > imageRect.width) {
              cropWidth = imageRect.width;
              cropHeight = cropWidth * 16 / 9;
            }
            cropRect = {
              x: (imageRect.width - cropWidth) / 2,
              y: (imageRect.height - cropHeight) / 2,
              w: cropWidth,
              h: cropHeight
            };
            renderCropBox();
          }
	          function openCropEditor() {
	            if (!selectedName || selectedName === bgCurrent) return;
	            const row = selectedRow();
	            if (!row) return;
            cropModal.classList.add("open");
            cropModal.setAttribute("aria-hidden", "false");
            cropImage.onload = resetCropBox;
            cropImage.src = `${row.dataset.src}&crop=${Date.now()}`;
          }
	          function closeCropEditor() {
	            cropModal.classList.remove("open");
	            cropModal.setAttribute("aria-hidden", "true");
	          }
	          function clampLogo() {
	            logoRect.x = Math.max(0, Math.min(logoRect.x, 1));
	            logoRect.y = Math.max(0, Math.min(logoRect.y, 1));
	            logoRect.w = Math.max(0.05, Math.min(logoRect.w, 1));
	          }
	          function renderLogoPlacement() {
	            clampLogo();
	            logoPlacement.style.left = `${logoRect.x * 100}%`;
	            logoPlacement.style.top = `${logoRect.y * 100}%`;
	            logoPlacement.style.width = `${logoRect.w * 100}%`;
	            logoPlacement.style.height = "auto";
	            logoSize.value = Math.round(logoRect.w * 100);
	          }
	          function openLogoEditor() {
	            if (!logoState.filename) {
	              alert("Bitte zuerst ein Logo hochladen.");
	              return;
	            }
	            logoModal.classList.add("open");
	            logoModal.setAttribute("aria-hidden", "false");
	            logoPlacement.style.display = "block";
	            renderLogoPlacement();
	          }
	          function closeLogoEditor() {
	            logoModal.classList.remove("open");
	            logoModal.setAttribute("aria-hidden", "true");
	          }
	          async function animateProgramTransition(nextSrc = previewImage ? previewImage.src : "") {
	            if (!programImage || !programNextImage || !nextSrc) return 0;
	            const duration = Math.max(0, Math.min(Number.parseInt(durationInput.value, 10) || 0, 5000));
	            const fadeMs = transition === "fade" ? duration : 0;
	            await new Promise((resolve) => {
	              programNextImage.onload = resolve;
	              programNextImage.onerror = resolve;
	              programNextImage.src = nextSrc;
	              if (programNextImage.complete) resolve();
	            });
	            programNextImage.style.transition = "none";
	            programNextImage.style.opacity = fadeMs > 0 ? "0" : "1";
	            void programNextImage.offsetWidth;
	            if (fadeMs > 0) programNextImage.style.transition = `opacity ${fadeMs}ms linear`;
	            programNextImage.style.opacity = "1";
	            window.setTimeout(() => {
	              programImage.src = programNextImage.src;
	              programNextImage.style.transition = "none";
	              programNextImage.style.opacity = "0";
	            }, fadeMs + 80);
	            return fadeMs;
	          }
	          async function setCurrent(name, options = {}) {
	            const animationMs = options.animate ? await animateProgramTransition(options.previewSrc) : 0;
	            const response = await fetch("/api/current", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({current: name})
            });
            if (!response.ok) {
              alert("Grafik konnte nicht gesetzt werden.");
              return;
            }
	            window.setTimeout(() => window.location.reload(), animationMs + 120);
	          }
	          async function setBackground(name) {
	            if (!name || name === bgCurrent) return;
	            const response = await fetch("/api/background", {
	              method: "POST",
	              headers: {"Content-Type": "application/json"},
	              body: JSON.stringify({background: name})
	            });
	            if (!response.ok) {
	              alert("Hintergrund konnte nicht gesetzt werden.");
	              return;
	            }
	            window.location.reload();
	          }
          document.querySelectorAll("[data-set]").forEach((button) => {
            button.addEventListener("click", async () => {
              button.disabled = true;
              const saved = await saveSettings(false);
              const previewSrc = button.dataset.set === blackCurrent ? blackImageSrc : `/slides/${encodeURIComponent(button.dataset.set)}?v=${Date.now()}`;
              if (saved) await setCurrent(button.dataset.set, {animate: true, previewSrc});
              button.disabled = false;
            });
          });
          document.getElementById("take-slide").addEventListener("click", async () => {
            if (!selectedName) return;
            const saved = await saveSettings(false);
            if (saved) setCurrent(selectedName, {animate: true});
          });
	          document.getElementById("open-crop").addEventListener("click", openCropEditor);
	          document.getElementById("cancel-crop").addEventListener("click", closeCropEditor);
	          document.getElementById("cancel-logo").addEventListener("click", closeLogoEditor);
	          cropModal.addEventListener("click", (event) => {
	            if (event.target === cropModal) closeCropEditor();
	          });
	          logoModal.addEventListener("click", (event) => {
	            if (event.target === logoModal) closeLogoEditor();
	          });
          cropBox.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            cropBox.setPointerCapture(event.pointerId);
            cropDrag = {pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, x: cropRect.x, y: cropRect.y};
          });
          cropBox.addEventListener("pointermove", (event) => {
            if (!cropDrag || cropDrag.pointerId !== event.pointerId) return;
            cropRect.x = cropDrag.x + event.clientX - cropDrag.startX;
            cropRect.y = cropDrag.y + event.clientY - cropDrag.startY;
            renderCropBox();
          });
          cropBox.addEventListener("pointerup", () => { cropDrag = null; });
          cropBox.addEventListener("pointercancel", () => { cropDrag = null; });
	          document.getElementById("save-crop").addEventListener("click", async () => {
	            if (!selectedName || selectedName === bgCurrent) return;
            const imageRect = cropImage.getBoundingClientRect();
            const crop = {
              x: cropRect.x / imageRect.width,
              y: cropRect.y / imageRect.height,
              w: cropRect.w / imageRect.width,
              h: cropRect.h / imageRect.height
            };
            const response = await fetch("/api/crop", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({current: selectedName, crop})
            });
            if (!response.ok) {
              alert("Ausschnitt konnte nicht gespeichert werden.");
              return;
            }
	            window.location.reload();
	          });
	          logoPlacement.addEventListener("pointerdown", (event) => {
	            event.preventDefault();
	            logoPlacement.setPointerCapture(event.pointerId);
	            const stageRect = logoStage.getBoundingClientRect();
	            logoDrag = {
	              pointerId: event.pointerId,
	              offsetX: event.clientX - (stageRect.left + logoRect.x * stageRect.width),
	              offsetY: event.clientY - (stageRect.top + logoRect.y * stageRect.height)
	            };
	          });
	          logoPlacement.addEventListener("pointermove", (event) => {
	            if (!logoDrag || logoDrag.pointerId !== event.pointerId) return;
	            const stageRect = logoStage.getBoundingClientRect();
	            logoRect.x = (event.clientX - logoDrag.offsetX - stageRect.left) / stageRect.width;
	            logoRect.y = (event.clientY - logoDrag.offsetY - stageRect.top) / stageRect.height;
	            renderLogoPlacement();
	          });
	          logoPlacement.addEventListener("pointerup", () => { logoDrag = null; });
	          logoPlacement.addEventListener("pointercancel", () => { logoDrag = null; });
	          logoSize.addEventListener("input", () => {
	            logoRect.w = Number.parseInt(logoSize.value, 10) / 100;
	            renderLogoPlacement();
	          });
	          document.getElementById("save-logo").addEventListener("click", async () => {
	            const response = await fetch("/api/logo-position", {
	              method: "POST",
	              headers: {"Content-Type": "application/json"},
	              body: JSON.stringify({logo: logoRect})
	            });
	            if (!response.ok) {
	              alert("Logo konnte nicht gespeichert werden.");
	              return;
	            }
	            window.location.reload();
	          });
          async function deleteSlide(name) {
            if (!name) return;
            if (!window.confirm(`${name} wirklich löschen?`)) return;
            const response = await fetch("/api/delete", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({current: name, confirm: true})
            });
            if (!response.ok) {
              alert("Grafik konnte nicht gelöscht werden.");
              return;
            }
            window.location.reload();
          }
          async function rotateSlide(name) {
            if (!name) return;
            const response = await fetch("/api/rotate", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({current: name})
            });
            if (!response.ok) {
              alert("Grafik konnte nicht gedreht werden.");
              return;
            }
            window.location.reload();
          }
          document.querySelectorAll("[data-row-delete]").forEach((button) => {
            button.addEventListener("click", (event) => {
              event.stopPropagation();
              event.preventDefault();
              deleteSlide(button.dataset.rowDelete);
            });
          });
          document.querySelectorAll("[data-row-rotate]").forEach((button) => {
            button.addEventListener("click", (event) => {
              event.stopPropagation();
              event.preventDefault();
              rotateSlide(button.dataset.rowRotate);
            });
          });
          const list = document.querySelector(".slide-list");
          let dragged = null;
          function orderedSlides() {
            return Array.from(document.querySelectorAll("[data-slide]")).map((row) => row.dataset.slide);
          }
          async function saveOrder() {
            await fetch("/api/order", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({order: orderedSlides()})
            });
          }
          document.querySelectorAll("[data-slide]").forEach((row) => {
            row.addEventListener("click", () => selectSlide(row));
            row.addEventListener("dragstart", () => {
              dragged = row;
              row.classList.add("dragging");
            });
            row.addEventListener("dragend", async () => {
              row.classList.remove("dragging");
              document.querySelectorAll(".drag-over").forEach((item) => item.classList.remove("drag-over"));
              dragged = null;
              await saveOrder();
            });
            row.addEventListener("dragover", (event) => {
              event.preventDefault();
              if (!dragged || dragged === row) return;
              row.classList.add("drag-over");
              const rect = row.getBoundingClientRect();
              const before = event.clientY < rect.top + rect.height / 2;
              list.insertBefore(dragged, before ? row : row.nextSibling);
            });
            row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
          });
          let transition = "{{ state.transition }}";
          function setSettingsStatus(text, isError = false) {
            if (!settingsStatus) return;
            settingsStatus.textContent = text;
            settingsStatus.classList.toggle("error", isError);
          }
          function queueSaveSettings() {
            window.clearTimeout(settingsTimer);
            setSettingsStatus("Wird gespeichert...");
            settingsTimer = window.setTimeout(() => saveSettings(false), 350);
          }
          document.querySelectorAll("[data-transition]").forEach((button) => {
            button.addEventListener("click", () => {
              transition = button.dataset.transition;
              document.querySelectorAll("[data-transition]").forEach((item) => item.classList.toggle("active", item === button));
              queueSaveSettings();
            });
          });
          durationInput.addEventListener("input", queueSaveSettings);
          async function saveSettings(reload = true) {
            window.clearTimeout(settingsTimer);
            const duration = Number.parseInt(durationInput.value, 10);
            try {
              const response = await fetch("/api/settings", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({transition, duration})
              });
              if (!response.ok) {
                setSettingsStatus("Speichern fehlgeschlagen", true);
                if (reload) alert("Einstellungen konnten nicht gespeichert werden.");
                return false;
              }
              setSettingsStatus("Gespeichert");
              if (reload) window.location.reload();
              return true;
            } catch (error) {
              setSettingsStatus("Speichern fehlgeschlagen", true);
              if (reload) alert("Einstellungen konnten nicht gespeichert werden.");
              return false;
            }
          }
          async function checkConnection() {
            try {
              const controller = new AbortController();
              const timeout = window.setTimeout(() => controller.abort(), 2200);
              const response = await fetch("/health", {cache: "no-store", signal: controller.signal});
              window.clearTimeout(timeout);
              const ok = response.ok;
              connectionStatus.classList.toggle("offline", !ok);
              connectionText.textContent = ok ? "Verbindung Okay" : "Verbindung gestört";
            } catch (error) {
              connectionStatus.classList.add("offline");
              connectionText.textContent = "Verbindung gestört";
            }
          }
          checkConnection();
          window.setInterval(checkConnection, 3000);
        </script></body></html>""",
        style=BASE_STYLE,
        state=state,
        slides=slides,
        message=message,
        bg_current=BG_CURRENT,
        black_current=BLACK_CURRENT,
    )


@app.route("/display")
def display():
    return """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Display</title>
    <style>
      html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: #000; cursor: none; }
      #stage { position: fixed; inset: 0; display: grid; place-items: center; background: #000; }
      .scene { position: fixed; inset: 0; opacity: 0; display: none; background: #000; overflow: hidden; }
      .slide-img, .bg-img { position: absolute; inset: 0; width: 100vw; height: 100vh; object-fit: cover; }
      .logo-img { position: absolute; transform: translate(-50%, -50%); height: auto; }
      #waiting { color: rgba(255,255,255,.35); font: 600 22px system-ui, sans-serif; }
    </style></head><body><main id="stage"><div class="scene" id="scene-a"></div><div class="scene" id="scene-b"></div><div id="waiting">Warte auf Grafik...</div></main>
    <script>
      const scenes = [document.getElementById("scene-a"), document.getElementById("scene-b")];
      const waiting = document.getElementById("waiting");
      let current = "";
      let version = -1;
      let visibleIndex = 0;
      function showEmpty() {
        current = "";
        scenes.forEach((scene) => {
          scene.replaceChildren();
          scene.style.display = "none";
          scene.style.opacity = "0";
          scene.style.transition = "";
        });
        waiting.style.display = "block";
      }
      function buildScene(scene, state) {
        scene.replaceChildren();
        if (state.current === "__black__") {
          return Promise.resolve(true);
        }
        if (state.current === "__background__") {
          if (!state.background) return Promise.resolve(false);
          const bg = new Image();
          bg.className = "bg-img";
          bg.alt = "";
          bg.src = `/slides/${encodeURIComponent(state.background)}?v=${state.version}&t=${Date.now()}`;
          scene.appendChild(bg);
          if (state.logo && state.logo.filename) {
            const logo = new Image();
            logo.className = "logo-img";
            logo.alt = "";
            logo.style.left = `${(state.logo.x || 0.5) * 100}%`;
            logo.style.top = `${(state.logo.y || 0.5) * 100}%`;
            logo.style.width = `${(state.logo.w || 0.34) * 100}vw`;
            logo.src = `/logos/${encodeURIComponent(state.logo.filename)}?v=${state.version}&t=${Date.now()}`;
            scene.appendChild(logo);
          }
          return new Promise((resolve) => {
            bg.onload = () => resolve(true);
            bg.onerror = () => resolve(false);
          });
        }
        const img = new Image();
        img.className = "slide-img";
        img.alt = "";
        img.src = `/slides/${encodeURIComponent(state.current)}?v=${state.version}&t=${Date.now()}`;
        scene.appendChild(img);
        return new Promise((resolve) => {
          img.onload = () => resolve(true);
          img.onerror = () => resolve(false);
        });
      }
      async function showState(state) {
        const nextIndex = 1 - visibleIndex;
        const visible = scenes[visibleIndex];
        const next = scenes[nextIndex];
        const ok = await buildScene(next, state);
        if (!ok) return;
        const fadeMs = state.transition === "fade" ? Math.max(0, Math.min(Number(state.duration) || 0, 5000)) : 0;
        waiting.style.display = "none";
        next.style.transition = "none";
        visible.style.transition = "none";
        next.style.display = "block";
        next.style.opacity = fadeMs > 0 ? "0" : "1";
        void next.offsetWidth;
        if (fadeMs > 0) {
          next.style.transition = `opacity ${fadeMs}ms linear`;
          visible.style.transition = `opacity ${fadeMs}ms linear`;
        }
        next.style.opacity = "1";
        visible.style.opacity = "0";
        window.setTimeout(() => {
          visible.style.display = "none";
          visibleIndex = nextIndex;
        }, fadeMs + 50);
      }
      async function tick() {
        try {
          const response = await fetch("/api/current", {cache: "no-store"});
          if (!response.ok) return;
          const state = await response.json();
          if (state.current && (state.current !== current || state.version !== version)) {
            current = state.current;
            version = state.version;
            showState(state);
          } else if (!state.current) {
            showEmpty();
          }
        } catch (error) {}
      }
      tick();
      setInterval(tick, 400);
    </script></body></html>"""


@app.route("/api/current", methods=["GET", "POST"])
def api_current():
    if request.method == "GET":
        return jsonify(read_state())

    if not session.get("logged_in"):
        abort(401)

    payload = request.get_json(silent=True) or {}
    requested = payload.get("current", "")
    state = read_state()
    if requested == BLACK_CURRENT:
        pass
    elif requested == BG_CURRENT:
        if not state["background"]:
            return jsonify({"ok": False, "error": "background missing"}), 400
    elif not isinstance(requested, str) or requested != os.path.basename(requested) or not slide_exists(requested):
        return jsonify({"ok": False, "error": "unknown slide"}), 400

    version = state["version"] + 1
    new_state = {**state, "current": requested, "version": version}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/background", methods=["POST"])
@login_required
def api_background():
    payload = request.get_json(silent=True) or {}
    requested = payload.get("background", "")
    if not isinstance(requested, str) or requested != os.path.basename(requested) or not slide_exists(requested):
        return jsonify({"ok": False, "error": "unknown slide"}), 400

    state = read_state()
    new_state = {**state, "background": requested, "current": BG_CURRENT, "version": state["version"] + 1}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/logo-position", methods=["POST"])
@login_required
def api_logo_position():
    payload = request.get_json(silent=True) or {}
    logo = payload.get("logo")
    if not isinstance(logo, dict):
        return jsonify({"ok": False, "error": "invalid logo"}), 400

    state = read_state()
    if not state["logo"]["filename"]:
        return jsonify({"ok": False, "error": "logo missing"}), 400

    try:
        logo_state = {
            "filename": state["logo"]["filename"],
            "x": min(max(float(logo.get("x", state["logo"]["x"])), 0), 1),
            "y": min(max(float(logo.get("y", state["logo"]["y"])), 0), 1),
            "w": min(max(float(logo.get("w", state["logo"]["w"])), 0.05), 1),
        }
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid logo"}), 400

    new_state = {**state, "logo": logo_state, "current": BG_CURRENT, "version": state["version"] + 1}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/settings", methods=["POST"])
@login_required
def api_settings():
    payload = request.get_json(silent=True) or {}
    transition = payload.get("transition")
    duration = payload.get("duration")

    if transition not in TRANSITIONS:
        return jsonify({"ok": False, "error": "unknown transition"}), 400
    if not isinstance(duration, int):
        return jsonify({"ok": False, "error": "invalid duration"}), 400

    state = read_state()
    new_state = {
        **state,
        "transition": transition,
        "duration": min(max(duration, 0), 5000),
        "version": state["version"] + 1,
    }
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/rotate", methods=["POST"])
@login_required
def api_rotate():
    payload = request.get_json(silent=True) or {}
    requested = payload.get("current", "")
    if not isinstance(requested, str) or requested != os.path.basename(requested) or not slide_exists(requested):
        return jsonify({"ok": False, "error": "unknown slide"}), 400
    if requested == read_state()["background"]:
        return jsonify({"ok": False, "error": "background cannot be deleted"}), 400

    try:
        rotate_slide_file(requested)
    except (OSError, UnidentifiedImageError, ValueError):
        return jsonify({"ok": False, "error": "rotate failed"}), 400

    state = read_state()
    new_state = {**state, "version": state["version"] + 1}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/delete", methods=["POST"])
@login_required
def api_delete():
    payload = request.get_json(silent=True) or {}
    requested = payload.get("current", "")
    confirmed = payload.get("confirm") is True
    if not confirmed:
        return jsonify({"ok": False, "error": "confirmation required"}), 400
    if not isinstance(requested, str) or requested != os.path.basename(requested) or not slide_exists(requested):
        return jsonify({"ok": False, "error": "unknown slide"}), 400

    resolved = safe_join(str(SLIDES_DIR), requested)
    if not resolved:
        return jsonify({"ok": False, "error": "invalid path"}), 400

    try:
        Path(resolved).unlink()
    except OSError:
        return jsonify({"ok": False, "error": "delete failed"}), 400

    state = read_state()
    current = "" if state["current"] == requested else state["current"]
    order = [name for name in state["order"] if name != requested]
    new_state = {**state, "current": current, "order": order, "version": state["version"] + 1}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/crop", methods=["POST"])
@login_required
def api_crop():
    payload = request.get_json(silent=True) or {}
    requested = payload.get("current", "")
    crop = payload.get("crop")
    if not isinstance(requested, str) or requested != os.path.basename(requested) or not slide_exists(requested):
        return jsonify({"ok": False, "error": "unknown slide"}), 400
    if not isinstance(crop, dict):
        return jsonify({"ok": False, "error": "invalid crop"}), 400

    try:
        crop_slide_file(requested, crop)
    except (OSError, UnidentifiedImageError, ValueError):
        return jsonify({"ok": False, "error": "crop failed"}), 400

    state = read_state()
    new_state = {**state, "version": state["version"] + 1}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/api/order", methods=["POST"])
@login_required
def api_order():
    payload = request.get_json(silent=True) or {}
    requested_order = payload.get("order")
    if not isinstance(requested_order, list):
        return jsonify({"ok": False, "error": "invalid order"}), 400

    existing = set(slide_filenames_sorted())
    order = []
    for name in requested_order:
        if isinstance(name, str) and name in existing and name not in order:
            order.append(name)
    order.extend(name for name in sorted(existing, key=str.casefold) if name not in order)

    state = read_state()
    new_state = {**state, "order": order}
    write_state(new_state)
    return jsonify({"ok": True, **new_state})


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    uploads = [file for file in request.files.getlist("file") if file and file.filename]
    if not uploads:
        return redirect(url_for("control", message="Keine Datei ausgewählt."))

    ensure_storage()
    state = read_state()
    order = list(state["order"])
    saved = []
    skipped = []

    for uploaded in uploads:
        filename = secure_filename(uploaded.filename)
        if not filename or not allowed_file(filename):
            skipped.append(uploaded.filename)
            continue

        target = safe_join(str(SLIDES_DIR), filename)
        if not target:
            skipped.append(uploaded.filename)
            continue

        uploaded.save(target)
        order = [name for name in order if name != filename]
        order.append(filename)
        saved.append(filename)

    if not saved:
        return redirect(url_for("control", message="Keine erlaubte Grafik ausgewählt."))

    write_state({**state, "order": order})
    return redirect(url_for("control"))


@app.route("/upload-logo", methods=["POST"])
@login_required
def upload_logo():
    uploaded = request.files.get("logo")
    if not uploaded or not uploaded.filename:
        return redirect(url_for("control", message="Kein Logo ausgewählt."))

    filename = secure_filename(uploaded.filename)
    if not filename or not allowed_file(filename):
        return redirect(url_for("control", message="Logo-Dateityp nicht erlaubt."))

    target = safe_join(str(LOGOS_DIR), filename)
    if not target:
        abort(400)

    ensure_storage()
    uploaded.save(target)
    state = read_state()
    logo = {**state["logo"], "filename": filename}
    new_state = {**state, "logo": logo, "current": BG_CURRENT, "version": state["version"] + 1}
    write_state(new_state)
    return redirect(url_for("control", message="Logo hochgeladen."))


@app.route("/slides/<path:filename>")
def slides(filename):
    if filename != os.path.basename(filename) or not allowed_file(filename):
        abort(404)
    return send_from_directory(SLIDES_DIR, filename, conditional=True)


@app.route("/logos/<path:filename>")
def logos(filename):
    if filename != os.path.basename(filename) or not allowed_file(filename):
        abort(404)
    return send_from_directory(LOGOS_DIR, filename, conditional=True)


@app.route("/health")
def health():
    return jsonify({"ok": True})


ensure_storage()


if __name__ == "__main__":
    # Nur für lokalen Entwicklungsbetrieb. Im Container startet Gunicorn app:app.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False, threaded=True)
