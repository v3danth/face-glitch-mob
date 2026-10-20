import os
import gradio as gr
from config import Config
from utils.materials import MATERIAL_NAMES
from utils.tints import TINT_MODES
from web.handlers import painter_handler, process_web_image, process_web_bulk
from web.painter import legend_html


def create_ui():
    # Read the external CSS file dynamically
    css_path = os.path.join(os.path.dirname(__file__), "css", "style.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            custom_css = f.read()
    except Exception:
        custom_css = ""

    with gr.Blocks(title="Face Glitch Mob Studio") as demo:
        gr.HTML(
            """
            <div class="glass-card" style="text-align: center; margin-top: 1rem;">
                <h1 class="gradient-title">FACE GLITCH MOB</h1>
                <p class="gradient-subtitle">Stylized Privacy Glassifier: Beautiful, mathematical privacy shields for social sharing.</p>
            </div>
            """
        )

        with gr.Tabs():
            # Single Image Tab
            with gr.TabItem("Single Image Studio"):
                with gr.Row():
                    # Input column
                    with gr.Column(scale=1):
                        gr.HTML("<h3>Upload and Style</h3>")
                        input_img = gr.Image(label="Source Image", type="pil")
                        process_btn = gr.Button("Apply Glass Effect", elem_classes="btn-primary")

                        with gr.Group(elem_classes="glass-card"):
                            style_choice = gr.Radio(
                                choices=["random", *MATERIAL_NAMES],
                                value="random",
                                label="Glass Material Style"
                            )
                            grid_size_slider = gr.Slider(
                                minimum=2, maximum=25, value=6, step=1,
                                label="Grid Density (Tiles per face side)"
                            )
                            feather_edges_check = gr.Checkbox(
                                value=True,
                                label="Feather Tile Borders (Smooth Seamless Blend)"
                            )
                            likeness_single = likeness_slider()
                            intensity_single = intensity_slider()
                            tint_mode_single, tint_color_single, tint_strength_single = tint_controls()

                        with gr.Accordion("Advanced Tuning Parameters", open=False, elem_classes="glass-card"):
                            with gr.Group():
                                gr.HTML("<h4>Distortion Configs</h4>")
                                dist_min = gr.Slider(minimum=1.0, maximum=30.0, value=5.0, step=0.5, label="Min Distortion Strength")
                                dist_max = gr.Slider(minimum=1.0, maximum=30.0, value=12.0, step=0.5, label="Max Distortion Strength")
                                noise = gr.Slider(minimum=0.0, maximum=10.0, value=2.0, step=0.1, label="Noise Factor")

                            with gr.Group():
                                gr.HTML("<h4>Face Detector Configs</h4>")
                                scale_slider = gr.Slider(minimum=0.1, maximum=1.0, value=0.5, step=0.05, label="Image Scale (Pre-detection resize)")
                                det_scale = gr.Slider(minimum=1.05, maximum=1.5, value=1.1, step=0.01, label="Detection Search Scale")
                                det_neighbors = gr.Slider(minimum=1, maximum=10, value=5, step=1, label="Detection Min Neighbors")
                                det_thresh = gr.Slider(minimum=0.0, maximum=20.0, value=2.0, step=0.5, label="Verification Weight Threshold")

                        # button moved to top

                    # Output column
                    with gr.Column(scale=1):
                        gr.HTML("<h3>Processed Result</h3>")
                        output_img = gr.Image(label="Privacy‑Shielded Output", type="numpy", elem_id="output_image", min_width=0)
                        status_text = gr.Textbox(label="System Output Diagnostics", interactive=False)

                # Link processing events
                process_btn.click(
                    fn=process_web_image,
                    inputs=[
                        input_img,
                        style_choice,
                        grid_size_slider,
                        dist_min,
                        dist_max,
                        noise,
                        feather_edges_check,
                        likeness_single,
                        intensity_single,
                        tint_mode_single,
                        tint_color_single,
                        tint_strength_single,
                        scale_slider,
                        det_scale,
                        det_neighbors,
                        det_thresh
                    ],
                    outputs=[output_img, status_text]
                )

            with gr.TabItem("Face Grid Painter"):
                painter_tab()

            # Batch Processing Tab
            with gr.TabItem("Batch Folder Obscurer"):
                gr.HTML("<h3>Bulk Privacy Obscurer</h3>")
                gr.Markdown(
                    "Process entire directories of photos automatically. Useful for batch archiving or sanitizing family albums."
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes="glass-card"):
                            input_dir_text = gr.Textbox(
                                placeholder="/absolute/path/to/source/images",
                                label="Absolute Path to Input Directory"
                            )
                            output_dir_text = gr.Textbox(
                                placeholder="/absolute/path/to/save/results",
                                label="Absolute Path to Output Directory"
                            )

                        with gr.Group(elem_classes="glass-card"):
                            bulk_style = gr.Dropdown(
                                choices=["random", *MATERIAL_NAMES],
                                value="random",
                                label="Glass Style Preset"
                            )
                            bulk_grid = gr.Slider(minimum=2, maximum=25, value=6, step=1, label="Grid Density")
                            bulk_feather = gr.Checkbox(value=True, label="Feather Tile Borders")

                        bulk_btn = gr.Button("Run Batch Obscurer", elem_classes="btn-primary")

                    with gr.Column(scale=1):
                        with gr.Accordion("Bulk Detector Tuning", open=False, elem_classes="glass-card"):
                            bulk_dist_min = gr.Slider(minimum=1.0, maximum=30.0, value=5.0, step=0.5, label="Min Distortion Strength")
                            bulk_dist_max = gr.Slider(minimum=1.0, maximum=30.0, value=12.0, step=0.5, label="Max Distortion Strength")
                            bulk_noise = gr.Slider(minimum=0.0, maximum=10.0, value=2.0, step=0.1, label="Noise Factor")
                            bulk_scale = gr.Slider(minimum=0.1, maximum=1.0, value=0.5, step=0.05, label="Pre-detection scaling")
                            bulk_det_scale = gr.Slider(minimum=1.05, maximum=1.5, value=1.1, step=0.01, label="Search scale")
                            bulk_det_neighbors = gr.Slider(minimum=1, maximum=10, value=5, step=1, label="Min neighbors")
                            bulk_det_thresh = gr.Slider(minimum=0.0, maximum=20.0, value=2.0, step=0.5, label="Threshold weight")

                        bulk_status = gr.Textbox(label="Batch Operation Logs", interactive=False, lines=6)

                # Link bulk processing events
                bulk_btn.click(
                    fn=process_web_bulk,
                    inputs=[
                        input_dir_text,
                        output_dir_text,
                        bulk_style,
                        bulk_grid,
                        bulk_dist_min,
                        bulk_dist_max,
                        bulk_noise,
                        bulk_feather,
                        bulk_scale,
                        bulk_det_scale,
                        bulk_det_neighbors,
                        bulk_det_thresh
                    ],
                    outputs=[bulk_status]
                )

    return demo, custom_css


def likeness_slider():
    return gr.Slider(
        minimum=0.0,
        maximum=1.0,
        value=Config.LIKENESS,
        step=0.05,
        label="Likeness (recognisable as a thumbnail, hidden when zoomed)",
    )


def intensity_slider():
    return gr.Slider(
        minimum=0.1,
        maximum=1.5,
        value=Config.INTENSITY,
        step=0.05,
        label="Intensity (lower shows more of the face)",
    )


def tint_controls():
    mode = gr.Radio(
        choices=TINT_MODES,
        value="none",
        label="Tint",
        info="color: dyed glass. palette: mild cool washes. auto: random hue per tile. "
        "rainbow: dichroic thin film. noise: pigment grain.",
    )
    color = gr.ColorPicker(value="#5aaaff", label="Tint colour (for color mode)")
    strength = gr.Slider(minimum=0.0, maximum=1.0, value=0.5, step=0.05, label="Tint strength")
    return mode, color, strength


def painter_tab():
    """Click cells on enlarged faces to give each tile its own glass and tint."""
    state = gr.State(None)
    with gr.Row():
        with gr.Column(scale=1):
            source = gr.Image(label="Source Image", type="pil")
            load_btn = gr.Button("Detect Faces", elem_classes="btn-primary")
            status = gr.Textbox(label="Status", interactive=False)

            with gr.Group(elem_classes="glass-card"):
                gr.HTML("<h4>Grid</h4>")
                grid = gr.Slider(minimum=1, maximum=12, value=4, step=1, label="Cells per face side")
                seed = gr.Number(value=7, precision=0, label="Seed (same seed, same glass)")
                feather = gr.Checkbox(value=True, label="Seamless blend between tiles")
                likeness = likeness_slider()
                intensity = intensity_slider()

            with gr.Group(elem_classes="glass-card"):
                gr.HTML("<h4>Brush</h4>")
                material = gr.Dropdown(choices=["random", *MATERIAL_NAMES], value="liquid", label="Glass pattern")
                tint_mode, tint_color, tint_strength = tint_controls()
                random_direction = gr.Checkbox(value=True, label="Random grain direction (ice, prism)")
                angle = gr.Slider(minimum=0, maximum=180, value=0, step=5, label="Grain direction (degrees)")
                with gr.Row():
                    preset_btn = gr.Button("Frosted Panes Preset", elem_classes="btn-primary")
                    fill_btn = gr.Button("Paint All Cells", elem_classes="btn-secondary")
                    clear_btn = gr.Button("Clear Painting", elem_classes="btn-secondary")

            with gr.Accordion("Face Detector Configs", open=False, elem_classes="glass-card"):
                scale = gr.Slider(minimum=0.1, maximum=1.0, value=0.5, step=0.05, label="Image Scale (Pre-detection resize)")
                det_scale = gr.Slider(minimum=1.05, maximum=1.5, value=1.1, step=0.01, label="Detection Search Scale")
                det_neighbors = gr.Slider(minimum=1, maximum=10, value=5, step=1, label="Detection Min Neighbors")
                det_thresh = gr.Slider(minimum=0.0, maximum=20.0, value=2.0, step=0.5, label="Verification Weight Threshold")

        with gr.Column(scale=1):
            gr.HTML("<h3>Face Board</h3><p>Click a cell to paint it with the brush. Click it again with the same brush to clear it.</p>")
            board = gr.Image(label="Faces (click to paint)", type="numpy", interactive=False)
            gr.HTML(legend_html())
            output = gr.Image(label="Output", type="numpy", elem_id="output_image")

    view = [grid, seed, feather, likeness, intensity]
    brush = [material, tint_mode, tint_color, tint_strength, random_direction, angle]
    rendered = [state, board, output]

    load_btn.click(
        painter_handler.load_image,
        inputs=[source, *view, scale, det_scale, det_neighbors, det_thresh],
        outputs=[*rendered, status],
    )
    board.select(painter_handler.paint_cell, inputs=[state, *view, *brush], outputs=rendered)
    fill_btn.click(painter_handler.paint_all, inputs=[state, *view, *brush], outputs=rendered)
    # Smooth frosted 3x3 panes with crisp edges and mild cool washes: crisp
    # edges keep each pane's tint distinct instead of averaging them away, and
    # half intensity leaves feature shapes readable but not identifiable.
    preset_btn.click(
        lambda: ("frosted", "palette", 0.55, 3, False, 0.5),
        outputs=[material, tint_mode, tint_strength, grid, feather, intensity],
    ).then(painter_handler.paint_all, inputs=[state, *view, *brush], outputs=rendered)
    clear_btn.click(painter_handler.clear_cells, inputs=[state, *view], outputs=rendered)
    # Cell coordinates mean nothing on a different grid, so start over.
    grid.release(painter_handler.clear_cells, inputs=[state, *view], outputs=rendered)
    for control in (seed, feather):
        control.change(painter_handler.rerender, inputs=[state, *view], outputs=rendered)
    for control in (likeness, intensity):
        control.release(painter_handler.rerender, inputs=[state, *view], outputs=rendered)
