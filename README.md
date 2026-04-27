# Face Glitch Mob

A Python project to apply stylized glass effects to face(s) in images using OpenCV and NumPy.

## Features
- Detects faces in an input image using Haar cascades
- Applies a glass tile effect to each detected face
- Supports multiple glass styles: frosted, clear, glossy
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

## Usage
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
- `DISTORTION_STRENGTH_MIN`/`MAX`: Range for distortion strength
- `NOISE_FACTOR`: Noise factor for distortion
- `FROSTED_KERNEL_CHOICES`: Kernel sizes for frosted blur
- `CLEAR_BLUR_KERNEL`: Kernel size for clear blur
- `GLOSSY_BLUR_KERNEL`: Kernel size for glossy blur
- `HIGHLIGHT_BLUR_KERNEL`: Kernel size for highlight blur
- `HIGHLIGHT_LINE_COLOR`: RGB color for highlight line
- `HIGHLIGHT_LINE_THICKNESS`: Thickness of highlight line
- `HIGHLIGHT_LINE_POSITION`: Relative position of highlight line
- `GLOSSY_WEIGHT`/`HIGHLIGHT_WEIGHT`: Blending weights
- `OUTPUT_PATH`: Output image path
- `INPUT_IMAGE`: Input image path

## Project Structure
```
main.py                # Entry point
config.py              # Config class loading .env
cli.py                 # CLI tools TODO owo
.env                   # Configurable parameters
utils/
    blending.py        # Blending functions
    distortion.py      # Distortion logic
    face.py            # Face effect logic
    materials.py       # Glass material effects
    mesh.py            # Mesh/grid utilities
    remap.py           # Remapping helpers
    tiles.py           # Tile effect logic
old_files/             # Legacy scripts
```

## Extending
- Added new glass styles in `utils/materials.py` but still not working coz they it looks bad and need to update `choose_mode` in `utils/tiles.py`.
- Add new configuration options for choose_mode to `.env` and `config.py`.

## License
MIT License

---
