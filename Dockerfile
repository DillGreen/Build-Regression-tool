FROM python:3.11-slim

LABEL maintainer="DillGreen"
LABEL description="Unity Build Regression Checker — detects and diagnoses Unity build time regressions"

WORKDIR /app

COPY Requirements ./Requirements
RUN pip install --no-cache-dir -r Requirements

COPY builddiff_advanced.py ./builddiff_advanced.py
COPY entrypoint.sh ./entrypoint.sh

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
