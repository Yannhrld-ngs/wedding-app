# --- ffmpeg: must come BEFORE importing gradio ---
import static_ffmpeg
static_ffmpeg.add_paths()   # downloads ffmpeg on first run, then adds it to PATH

import shutil
import subprocess
import time
import uuid
from pathlib import Path

import gradio as gr

if shutil.which("ffmpeg") is None:
    raise SystemExit("ffmpeg introuvable malgré static_ffmpeg")

# ---------- Settings ----------
DUREE = 30     # seconds max
PITCH = 1.4    # > 1 higher voice, < 1 deeper voice (e.g. 0.7)
VOICE_FILTER = f"aresample=48000,asetrate=48000*{PITCH},aresample=48000,atempo={1/PITCH:.4f}"

SAVE_DIR = Path("C:/Users/Yann-Harold NGUESSAN/Videos/Test")
SAVE_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Processing ----------
def ffmpeg(*args):
    """Runs ffmpeg and shows a readable error on screen if it fails."""
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise gr.Error(f"ffmpeg : {result.stderr.strip()[-300:]}")


def traiter(video_path, progress=gr.Progress()):
    """Saves the original (max 30 s) and the modified-voice copy, then resets the camera."""
    if not video_path:
        # Triggered by the camera reset itself: change nothing
        yield gr.update(), gr.update()
        return

    yield gr.update(), "### ⏳ Enregistrement en cours de sauvegarde…"

    name = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    original = SAVE_DIR / f"{name}_original.mp4"
    modified = SAVE_DIR / f"{name}_modified.mp4"

    progress(0.1, desc="Sauvegarde…")
    ffmpeg("-i", video_path, "-t", str(DUREE),
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-movflags", "+faststart", str(original))

    progress(0.6, desc="Modification de la voix…")
    ffmpeg("-i", str(original), "-c:v", "copy", "-af", VOICE_FILTER,
           "-c:a", "aac", "-movflags", "+faststart", str(modified))

    #print(f"[ok] {original.name} + {modified.name}")
    # None = empties the component: the camera is ready for the next recording
    yield None, "### ✅ Merci, message enregistré ! Prêt pour le suivant."


# ---------- Countdown ----------
def demarrer():
    return time.time(), ""


def arreter():
    return None, ""


def afficher_compteur(t0):
    if t0 is None:
        return ""
    restant = DUREE - int(time.time() - t0)
    if restant > 0:
        return f"### 🔴 Enregistrement : {restant} s restantes"
    return f"### ⏹ {DUREE} s atteintes : cliquez sur ■ (la vidéo sera coupée à {DUREE} s)"


# ---------- Theme ----------
TERRACOTTA = gr.themes.Color(
    name="terracotta",
    c50="#FBF1EE", c100="#F6E0D9", c200="#EDC1B3", c300="#E3A18C",
    c400="#D97B5F", c500="#C8553D", c600="#B04832", c700="#923B29",
    c800="#742F21", c900="#5A251A", c950="#3D1911",
)

WHITE, TEXT, BORDER, SOFT = "#FFFFFF", "#3D2B25", "#EDC1B3", "#FBF1EE"

theme = gr.themes.Soft(primary_hue=TERRACOTTA, neutral_hue="stone").set(
    # Light mode
    body_background_fill=WHITE,
    background_fill_primary=WHITE,
    background_fill_secondary=SOFT,
    block_background_fill=WHITE,
    block_border_color=BORDER,
    block_label_background_fill=SOFT,
    block_label_text_color="#B04832",
    block_title_text_color="#B04832",
    body_text_color=TEXT,
    input_background_fill=WHITE,
    border_color_primary=BORDER,
    button_primary_background_fill="#C8553D",
    button_primary_background_fill_hover="#B04832",
    button_primary_text_color=WHITE,
    # Dark mode forced to the same colours (no black background)
    body_background_fill_dark=WHITE,
    background_fill_primary_dark=WHITE,
    background_fill_secondary_dark=SOFT,
    block_background_fill_dark=WHITE,
    block_border_color_dark=BORDER,
    block_label_background_fill_dark=SOFT,
    block_label_text_color_dark="#B04832",
    block_title_text_color_dark="#B04832",
    body_text_color_dark=TEXT,
    body_text_color_subdued_dark="#742F21",
    input_background_fill_dark=WHITE,
    border_color_primary_dark=BORDER,
    button_primary_background_fill_dark="#C8553D",
    button_primary_background_fill_hover_dark="#B04832",
    button_primary_text_color_dark=WHITE,
    button_secondary_background_fill_dark=SOFT,
    button_secondary_text_color_dark=TEXT,
)

CSS = """
.gradio-container { background: #FFFFFF !important; max-width: 820px !important; margin: auto; }
.gradio-container h2 { color: #C8553D; }
.gradio-container video { background: #FBF1EE !important; border-radius: 10px; }
"""

# Gradio 6+ takes theme/css in launch(), older versions in Blocks()
GRADIO6 = int(gr.__version__.split(".")[0]) >= 6
blocks_style = {} if GRADIO6 else {"theme": theme, "css": CSS}
launch_style = {"theme": theme, "css": CSS} if GRADIO6 else {}


# ---------- Interface ----------
with gr.Blocks(title="Un mot aux mariés", **blocks_style) as demo:
    gr.Markdown("## Un mot aux mariés\nCliquez sur ● pour enregistrer, puis sur ■ pour arrêter.")
    video = gr.Video(sources=["webcam"], include_audio=True, format="mp4",
                     label=f"Votre message ({DUREE} s max)")
    compteur = gr.Markdown()
    message = gr.Markdown()

    debut = gr.State(None)
    timer = gr.Timer(1)

    video.start_recording(demarrer, None, [debut, message], show_progress="hidden")
    video.stop_recording(arreter, None, [debut, compteur], show_progress="hidden")
    timer.tick(afficher_compteur, debut, compteur, show_progress="hidden")
    video.change(traiter, [video], [video, message], show_progress="full")


if __name__ == "__main__":
    #print(f"Vidéos enregistrées dans : {SAVE_DIR}")
    demo.launch(show_error=True, **launch_style)