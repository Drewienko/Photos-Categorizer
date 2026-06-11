import os
import sys

# When running from a PyInstaller bundle, add the extraction dir to PATH
# so that the bundled ffmpeg binary is found by ffmpeg-python.
if hasattr(sys, "_MEIPASS"):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")
