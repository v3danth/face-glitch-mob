import os
import gradio as gr
from web.handlers import process_web_image, process_web_bulk


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
                                choices=["random", "frosted", "clear", "glossy", "prism", "ripple", "magnify", "crystal", "ice", "hazy", "chromatic"],
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
                        scale_slider,
                        det_scale,
                        det_neighbors,
                        det_thresh
                    ],
                    outputs=[output_img, status_text]
                )

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
                                choices=["random", "frosted", "clear", "glossy", "prism", "ripple", "magnify", "crystal", "ice", "hazy", "chromatic"],
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
