FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

# Aligné sur l'UID/GID de l'utilisateur hôte (franck) pour que les bind
# mounts de la session Claude Code (~/.claude*, ~/.local/*/claude) restent
# lisibles/inscriptibles sans bricolage de permissions. Voir README.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" franck \
    && useradd -m -u "${APP_UID}" -g "${APP_GID}" -d /home/franck -s /bin/bash franck

COPY --from=builder /install /usr/local

WORKDIR /app
COPY app ./app

RUN chown -R franck:franck /app

USER franck
ENV HOME=/home/franck \
    PATH="/home/franck/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
