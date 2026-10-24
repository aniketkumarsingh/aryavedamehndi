FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    U2NET_HOME=/models

WORKDIR /app
COPY pyproject.toml README.md ./
COPY image_studio ./image_studio
RUN pip install --no-cache-dir ".[ai,server]"

# Bake the segmentation model into the image so the first request isn't a ~900 MB download.
# Build with --build-arg MASK_MODEL=isnet-general-use for a smaller, faster (lower quality) image.
ARG MASK_MODEL=birefnet-general
RUN python -c "from rembg import new_session; new_session('${MASK_MODEL}')"

RUN useradd --create-home studio && chown -R studio /models
USER studio

EXPOSE 8100
# Presets from a mounted folder: -v $PWD/presets:/presets -e IMAGE_STUDIO_PRESETS_DIR=/presets
CMD ["uvicorn", "image_studio.server:app", "--host", "0.0.0.0", "--port", "8100"]
