#!/bin/bash
set -e

streamlit run server.py --server.port=8501 --server.address=0.0.0.0
