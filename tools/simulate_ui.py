"""
Simulated users for the web UI.

Replays real Gradio wiring in-process: every user action fires exactly the
listeners the browser would fire (programmatic updates fire `change` but
never `release`, `.then` chains run after their parent), and after each
action a set of oracles checks that what the UI shows is what it should
show. Each violation is printed with the action script that produced it.

    python tools/simulate_ui.py --image input/input.jpg --steps 300 --seed 1
"""

import argparse
import inspect
import os
import random
import sys
import tempfile
import traceback

import gradio as gr
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.handlers import painter_handler  # noqa: E402
from web.ui import create_ui  # noqa: E402

# Events a real user action raises on each kind of control, in the order
# the browser sends them. Typing into a slider's number box is "type".
USER_EVENTS = {
    "drag": ("change", "input", "release"),
    "type": ("change", "input", "submit"),
    "toggle": ("change", "input", "select"),
    "upload": ("change", "upload"),
    "clear": ("change", "clear"),
    "click": ("click",),
    "select": ("select",),
}


class Session:
    """One browser tab's worth of component values plus the event engine."""

    def __init__(self):
        self.demo, _ = create_ui()
        self.values = {}
        self.by_label = {}
        for block_id, block in self.demo.blocks.items():
            if hasattr(block, "value"):
                self.values[block_id] = getattr(block, "value", None)
            label = getattr(block, "label", None) or getattr(block, "value", None)
            if isinstance(label, str):
                self.by_label.setdefault(label, []).append(block_id)
        for block_id, block in self.demo.blocks.items():
            if isinstance(block, gr.State):
                self.values[block_id] = block.value
        self.errors = []
        self.log = []

    def block(self, label, index=0):
        return self.by_label[label][index]

    def listeners(self, block_id, event):
        return [
            (key, fn)
            for key, fn in self.demo.fns.items()
            if (block_id, event) in fn.targets
        ]

    def run_fn(self, key, fn, event_data=None):
        args = [preprocess(c, self.values.get(c._id)) for c in fn.inputs]
        kwargs = {}
        # Gradio injects event data by the handler's type hints, not a flag.
        for name, param in inspect.signature(fn.fn).parameters.items():
            if param.annotation is gr.SelectData or param.annotation == "gr.SelectData":
                kwargs[name] = event_data
        try:
            result = fn.fn(*args, **kwargs)
        except Exception as exc:  # the oracle: a handler must never raise
            self.errors.append(f"{fn.name} raised {type(exc).__name__}: {exc}")
            self.errors.append(traceback.format_exc(limit=3))
            return
        outputs = fn.outputs
        if len(outputs) == 1:
            result = (result,)
        changed = []
        for comp, value in zip(outputs, result):
            old = self.values.get(comp._id)
            self.values[comp._id] = value
            if not same(old, value):
                changed.append(comp._id)
        for comp_id in changed:
            for k, f in self.listeners(comp_id, "change"):
                self.run_fn(k, f)
        for k, f in self.demo.fns.items():
            if f.trigger_after == key:
                self.run_fn(k, f)

    def act(self, kind, label, value=None, index=0, event_data=None):
        """A user action on the control labelled `label`."""
        block_id = self.block(label, index)
        self.log.append((kind, label, summarize(value)))
        if kind not in ("click", "select"):
            self.values[block_id] = value
        for event in USER_EVENTS[kind]:
            for key, fn in self.listeners(block_id, event):
                self.run_fn(key, fn, event_data)


def preprocess(component, value):
    """What the handler receives: Gradio converts uploads to the image mode."""
    if isinstance(component, gr.Image) and isinstance(value, Image.Image):
        mode = getattr(component, "image_mode", "RGB")
        return value.convert(mode) if mode else value
    return value


def same(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.shape == b.shape and np.array_equal(a, b)
    try:
        return a == b
    except Exception:
        return a is b


def summarize(value):
    if isinstance(value, Image.Image):
        return f"<image {value.mode} {value.size}>"
    if isinstance(value, gr.SelectData):
        return f"<click {value.index}>"
    return value


class Painter:
    """Typed access to the painter tab and its oracles."""

    def __init__(self, session):
        self.s = session
        v = session.values
        self.state_id = next(
            c._id
            for f in session.demo.fns.values()
            if f.name == "load_image"
            for c in f.outputs
            if isinstance(c, gr.State)
        )
        load = next(f for f in session.demo.fns.values() if f.name == "load_image")
        self.source_id = load.inputs[0]._id
        self.board_id, self.output_id = (c._id for c in load.outputs[1:3])
        self.view_ids = [c._id for c in load.inputs[1:6]]
        self.uploaded = None
        self.v = v

    def view(self):
        return [self.v[i] for i in self.view_ids]

    def check(self, uploads):
        """Oracles that must hold after every action settles."""
        problems = []
        state = self.v[self.state_id]
        board = self.v[self.board_id]
        output = self.v[self.output_id]
        if state is None:
            return problems
        grid = self.v[self.view_ids[0]]

        bad_cells = [c for c in state["cells"] if c[1] >= int(grid) or c[2] >= int(grid)]
        if bad_cells:
            problems.append(f"painted cells {bad_cells[:3]} lie outside the {grid}x{grid} grid shown")
        painted_grid = state.get("grid")
        if painted_grid is not None and int(painted_grid) != int(grid) and state["cells"]:
            problems.append(f"cells painted on a {painted_grid}x grid are now read as a {grid}x grid")

        if self.uploaded is not None and state.get("_sim_source") is not self.uploaded:
            problems.append("board and output still show a previous photo after a new upload")

        try:
            want_board, want_output = painter_handler.refresh(state, *self.view())
        except Exception as exc:
            problems.append(f"refresh with current controls raised {type(exc).__name__}: {exc}")
            return problems
        if not same(board, want_board):
            problems.append("board is stale: it differs from a render with the current controls")
        if output is not None and self.uploaded is not None:
            want = (self.uploaded.size[1], self.uploaded.size[0])
            if output.shape[:2] != want:
                problems.append(f"output is {output.shape[1]}x{output.shape[0]}, upload was {want[1]}x{want[0]}")
        return problems


def tag_state(painter):
    """Remember which upload the painter state was built from (sim-only marker)."""
    state = painter.v[painter.state_id]
    if state is not None and "_sim_source" not in state:
        state["_sim_source"] = painter.v[painter.source_id]


def photo_variants(path):
    base = Image.open(path)
    w, h = base.size
    return {
        "rgb": base.convert("RGB"),
        "rgba_png": base.convert("RGBA"),
        "grayscale": base.convert("L"),
        "mirrored": base.convert("RGB").transpose(Image.FLIP_LEFT_RIGHT),
        "no_face": Image.new("RGB", (640, 480), (90, 120, 160)),
        "tiny": base.convert("RGB").resize((max(w // 40, 8), max(h // 40, 8))),
    }


def random_user(rng, painter, photos):
    """One plausible (or rude) user action on the painter tab."""
    s = painter.s
    board = painter.v[painter.board_id]
    actions = [
        ("upload", lambda: ("upload", "Source Image", photos[rng.choice(list(photos))], 1)),
        ("detect", lambda: ("click", "Detect Faces", None, 0)),
        ("paint", lambda: ("select", "Faces (click to paint)", None, 0)),
        ("paint_all", lambda: ("click", "Paint All Cells", None, 0)),
        ("preset", lambda: ("click", "Frosted Panes Preset", None, 0)),
        ("clear", lambda: ("click", "Clear Painting", None, 0)),
        ("grid_drag", lambda: ("drag", "Cells per face side", rng.randint(1, 12), 0)),
        ("grid_type", lambda: ("type", "Cells per face side", rng.randint(1, 12), 0)),
        ("seed", lambda: ("type", "Seed (same seed, same glass)", rng.choice([7, 3, -1, None, 2**40]), 0)),
        ("seamless", lambda: ("toggle", "Seamless blend between tiles", rng.random() < 0.5, 0)),
        ("likeness_drag", lambda: ("drag", "Likeness (recognisable as a thumbnail, hidden when zoomed)", rng.choice([0.0, 0.5, 0.9]), 1)),
        ("intensity_type", lambda: ("type", "Intensity (lower shows more of the face)", rng.choice([0.3, 0.5, 1.0]), 1)),
        ("brush", lambda: ("drag", "Tint strength", rng.choice([0.2, 0.55, 0.9]), 1)),
        ("remove_photo", lambda: ("clear", "Source Image", None, 1)),
    ]
    name, make = rng.choice(actions)
    kind, label, value, index = make()
    if kind == "select":
        if board is None:
            return name, None
        h, w = board.shape[:2]
        value = gr.SelectData(None, {"index": [rng.randrange(w + 20), rng.randrange(h + 20)], "value": None})
        s.act("select", label, index=index, event_data=value)
        return name, value
    if kind == "upload":
        painter.uploaded = value
    if kind == "clear" and label == "Source Image":
        painter.uploaded = None
    s.act(kind, label, value, index=index)
    return name, value


def run_random(image, steps, seed):
    rng = random.Random(seed)
    photos = photo_variants(image)
    session = Session()
    painter = Painter(session)
    found = {}
    for step in range(steps):
        before_errors = len(session.errors)
        random_user(rng, painter, photos)
        tag_state(painter)
        problems = session.errors[before_errors:] + painter.check(photos)
        for problem in problems:
            key = problem.splitlines()[0][:90]
            if key not in found and not problem.startswith("Traceback"):
                found[key] = list(session.log[-6:])
    return found


def scripted_cases(image):
    """The rude cases, each a named script with its own oracle."""
    photos = photo_variants(image)
    results = {}

    def fresh():
        session = Session()
        return session, Painter(session)

    # Single image tab with awkward photos.
    for name in ("rgba_png", "grayscale", "tiny", "no_face", "rgb"):
        s, _ = fresh()
        s.act("upload", "Source Image", photos[name], index=0)
        s.act("click", "Apply Glass Effect")
        out_id = next(f for f in s.demo.fns.values() if f.name == "process_web_image").outputs
        output, status = (s.values[c._id] for c in out_id)
        if status and status.startswith("Error"):
            results[f"single image, {name} upload"] = status
        elif output is not None and output.shape[:2] != photos[name].size[::-1]:
            results[f"single image, {name} upload"] = (
                f"output {output.shape[1]}x{output.shape[0]} but upload was {photos[name].size[0]}x{photos[name].size[1]}"
            )

    # Min distortion above max.
    s, _ = fresh()
    s.act("upload", "Source Image", photos["rgb"], index=0)
    s.act("drag", "Min Distortion Strength", 25.0, index=0)
    s.act("drag", "Max Distortion Strength", 2.0, index=0)
    s.act("click", "Apply Glass Effect")
    status = s.values[next(f for f in s.demo.fns.values() if f.name == "process_web_image").outputs[1]._id]
    if status and status.startswith("Error"):
        results["single image, min distortion > max"] = status

    # Settings from one tab (or one user) leaking into another.
    s, p = fresh()
    s.act("upload", "Source Image", photos["rgb"], index=1)
    s.act("click", "Detect Faces")
    board_before = s.values[p.board_id]
    s.act("upload", "Source Image", photos["rgb"], index=0)
    s.act("drag", "Min Distortion Strength", 28.0, index=0)
    s.act("drag", "Max Distortion Strength", 30.0, index=0)
    s.act("drag", "Noise Factor", 10.0, index=0)
    s.act("click", "Apply Glass Effect")
    s.act("toggle", "Seamless blend between tiles", False)
    s.act("toggle", "Seamless blend between tiles", True)
    if board_before is not None and not same(board_before, s.values[p.board_id]):
        results["single image tab settings leak into the painter"] = (
            "same photo, seed and controls render differently after the single image tab ran"
        )

    # Preset fired while the grid also changes: order must not matter.
    s, p = fresh()
    s.act("upload", "Source Image", photos["rgb"], index=1)
    s.act("click", "Detect Faces")
    s.act("click", "Frosted Panes Preset")
    state = s.values[p.state_id]
    if not state or len(state["cells"]) != 9 * len(state["faces"]):
        results["preset paints every cell"] = f"cells after preset: {0 if not state else len(state['cells'])}"

    # Bulk: writing into the input folder overwrites the originals.
    with tempfile.TemporaryDirectory() as folder:
        photos["rgb"].save(os.path.join(folder, "a.jpg"))
        before = open(os.path.join(folder, "a.jpg"), "rb").read()
        with open(os.path.join(folder, "broken.jpg"), "wb") as f:
            f.write(b"not an image")
        photos["rgb"].save(os.path.join(folder, "z.png"))
        s, _ = fresh()
        s.act("type", "Absolute Path to Input Directory", folder)
        s.act("type", "Absolute Path to Output Directory", folder)
        s.act("click", "Run Batch Obscurer")
        log = s.values[next(f for f in s.demo.fns.values() if f.name == "process_web_bulk").outputs[0]._id]
        if open(os.path.join(folder, "a.jpg"), "rb").read() != before:
            results["bulk, output folder = input folder"] = "originals were overwritten in place"
        if "2/" not in str(log) and "Error" not in str(log):
            results["bulk, one unreadable file"] = f"log: {log}"

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--image", default="input/input.jpg")
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    print("== scripted cases")
    scripted = scripted_cases(args.image)
    for name, detail in scripted.items():
        print(f"BUG  {name}: {detail}")
    print(f"{len(scripted)} scripted failure(s)")

    print(f"\n== random users: {args.steps} steps, seed {args.seed}")
    found = run_random(args.image, args.steps, args.seed)
    for problem, script in found.items():
        print(f"BUG  {problem}")
        for kind, label, value in script:
            print(f"       {kind:7s} {label} {'' if value is None else value}")
    print(f"{len(found)} distinct painter failure(s)")
    return 1 if scripted or found else 0


if __name__ == "__main__":
    sys.exit(main())
