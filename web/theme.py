import gradio as gr

theme = gr.themes.Soft(
    primary_hue="sky",
    secondary_hue="violet",
    neutral_hue="slate"
).set(
    body_background_fill="#080c14",
    block_background_fill="rgba(15, 23, 42, 0.4)",
    block_border_color="rgba(255, 255, 255, 0.08)",
    button_primary_background_fill="linear-gradient(135deg, #0284c7 0%, #7e22ce 100%)",
    button_primary_text_color="white",
    input_background_fill="rgba(30, 41, 59, 0.4)",
    input_border_color="rgba(255, 255, 255, 0.08)"
)
