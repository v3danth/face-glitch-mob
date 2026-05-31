import logging
from web.ui import create_ui
from web.theme import theme

# Configure logging for the web application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("face_glitch_mob_web")

if __name__ == "__main__":
    logger.info("Initializing Face Glitch Mob Studio Web Application...")
    demo, custom_css = create_ui()
    logger.info("Starting local web server on port 7860...")
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        theme=theme,
        css=custom_css,
        footer_links=[]
    )
