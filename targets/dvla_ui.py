"""Run DVLA's own Streamlit UI unchanged, on DeepSeek instead of its hard-wired GPT-4.

Usage (from the DVLA folder, so its images and config resolve):
    ../.venv-dvla/bin/streamlit run ../../../../targets/dvla_ui.py --server.address 127.0.0.1 --server.port 8501
"""
import os
import sys

sys.path.insert(0, os.getcwd())
import utils  # DVLA's utils.py

utils.fetch_model_config = lambda: "deepseek/deepseek-flash"
with open("main.py", encoding="utf-8") as f:
    exec(compile(f.read(), "main.py", "exec"))
