FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

COPY requirements.txt .

# torch is installed from PyTorch's CPU index rather than PyPI. On Linux the
# default PyPI torch wheel declares hard dependencies on the nvidia-cu13 CUDA
# runtime packages, which add several GB to the image for hardware this project
# never uses. The embedding model runs on CPU only.
#
# PyTorch's index is primary and PyPI is the fallback, so everything other than
# torch still resolves from PyPI. Versions come from requirements.txt either
# way, so index order only decides which torch build wins: the CPU index offers
# 2.13.0+cpu, which outranks PyPI's plain 2.13.0 while still satisfying the pin.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
