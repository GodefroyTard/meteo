# Image du lot planifié. Elle n'embarque pas le serveur web : celui-ci tourne encore
# sur l'hôte, et le lot n'a besoin que de la CLI et d'un accès à la base.
FROM python:3.13-slim

# cron plutôt qu'une boucle sleep : une boucle dérive de la durée de chaque passage,
# et l'heure de collecte finirait par glisser dans la journée.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY docker/crontab /app/crontab
COPY docker/demarrer.sh /app/demarrer.sh
RUN chmod +x /app/demarrer.sh && crontab /app/crontab

CMD ["/app/demarrer.sh"]
