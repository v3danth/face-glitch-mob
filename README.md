# Face Glitch Mob

A Python project to apply stylized glass effects to face(s) in images using OpenCV and NumPy.

## Features
- Detects faces in an input image using Haar cascades
- Applies a glass tile effect to each detected face
- Physically based glass: Snell refraction, Cauchy dispersion, Fresnel reflection,
  GGX highlights, surface scattering and Beer-Lambert absorption
- Glass styles: frosted, clear, glossy, prism, ripple, magnify, crystal, ice, hazy,
  chromatic, and liquid (Apple-style Liquid Glass)
- Tints: dyed colour, auto (random hue per tile), rainbow (dichroic thin-film
  interference) and noise (pigment grain); ice and prism grain direction
- Face Grid Painter (web UI, `python app.py`): click cells on enlarged faces to
  give each tile its own pattern, tint and direction
- Highly configurable via `.env` file
- Modular codebase for easy extension

## Privacy Use Case
privacy is a top priority. This project is designed to help protect your privacy on social media platforms by automatically obscuring or stylizing faces in your images before sharing them online. By applying glass effects to faces, you can prevent facial recognition algorithms from easily identifying individuals, giving you more control over your digital footprint.

This tool is ideal for:
- Users who want to share photos online without exposing their identity
- Content creators who need to anonymize subjects
- Anyone concerned about privacy on social media platforms

## Requirements
- Python 3.8+
- OpenCV (`opencv-python`)
- NumPy
- python-dotenv

Install dependencies:
```bash
pip install opencv-python numpy python-dotenv
```

## Web apps
Two front ends, served by one local server (binds to 127.0.0.1 only):
```bash
python -m server.app
```
- **Glass Studio** at http://127.0.0.1:8000/studio/ renders with the Python
  physics in `utils/`. Photos go only to the local server and are held in
  memory, never written to disk.
- **Glass GL** at http://127.0.0.1:8000/gl/ runs the same physics as WebGL
  shaders and detects faces in the browser; photos never leave the page.

Both share `frontend/shared/` (state machines, settings validation, layout).
Design and state diagrams: `docs/frontend-design.md`.

## Tests and simulators
```bash
python -m unittest discover -s tests -t .              # physics, tints, API
node --test frontend/shared/*.test.js frontend/studio/*.test.js frontend/gl/*.test.js
python tools/simulate_api.py --clients 8 --actions 20  # needs the server running
node tools/e2e_studio.mjs input/input.jpg              # real headless Chromium; needs the server
python tools/simulate_ui.py                            # the legacy Gradio UI
```

## Usage (scripts)
1. Place your input image as `input.jpg` in the project root (or set `INPUT_IMAGE` in `.env`).
2. Configure parameters in the `.env` file as needed.
3. Run the main script:
```bash
python main.py
```
4. The output image will be saved to the path specified by `OUTPUT_PATH` in `.env` (default: `output/output_with_faces.jpg`).


## Configuration
The project supports configurable parameters via a `.env` file and a central `Config` class for easy customization. All configurable parameters are stored in the `.env` file. See below for key options:

- `FACE_CASCADE_PATH`: Path to Haar cascade XML for face detection
- `FACE_SCALE_FACTOR`: Image resize factor before detection
- `FACE_DETECT_SCALE`: Scale factor for face detection
- `FACE_DETECT_MIN_NEIGHBORS`: Minimum neighbors for detection
- `FACE_DETECT_WEIGHT_THRESHOLD`: Weight threshold for valid faces
- `GRID_SIZE`: Number of tiles per face
- `DISTORTION_STRENGTH_MIN`/`MAX`: Range of surface relief per tile (8 = nominal shape)
- `NOISE_FACTOR`: Strength of small manufacturing ripples in the glass
- `OUTPUT_PATH`: Output image path
- `INPUT_IMAGE`: Input image path

## Project Structure
```
main.py                # Entry point
config.py              # Config class loading .env
cli.py                 # CLI for single images and folders
.env                   # Configurable parameters
server/app.py          # Local API + static server for both front ends
frontend/
    shared/            # State machines, model, board geometry (+ tests)
    studio/            # HTML/JS page rendering through the Python API
    gl/                # WebGL page rendering in the browser
tools/                 # User simulators (API, legacy Gradio UI)
docs/                  # Design docs
utils/
    detect.py          # Haar face detection, multi-scale voting, per-thread cascades
    face.py            # Face tiling, linear-light conversion
    materials.py       # Material presets (IOR, Abbe, roughness...) and tile renderer
    optics.py          # Snell, Fresnel, dispersion, GGX, absorption
    surfaces.py        # Glass height fields (lens, ridges, facets, capsule...)
    tiles.py           # TileStyle, material choice and per-tile relief
    tints.py           # Dye absorption, thin-film rainbow, pigment noise
web/painter.py         # Face board drawing and click-to-cell mapping
old_files/             # Legacy scripts
```

## Extending
- Add a glass style by writing a height field in `utils/surfaces.py` and a
  `Material` entry in `utils/materials.py`; the CLI and web UI pick it up automatically.

## License
MIT License

---
