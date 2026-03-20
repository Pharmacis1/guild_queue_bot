FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install PostgreSQL client tools (pg_dump, pg_restore)
RUN apt-get update && apt-get install -y wget build-essential libpq-dev python3-dev && \
    wget --quiet -O /etc/apt/trusted.gpg.d/postgresql.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc && \
    echo "deb http://apt.postgresql.org/pub/repos/apt jammy-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && apt-get install -y postgresql-client-16 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install core dependencies separately to isolate potential failures
RUN pip install --no-cache-dir aiogram aiohttp aiofiles alembic APScheduler pydantic fastapi uvicorn greenlet
RUN pip install --no-cache-dir SQLAlchemy asyncpg
# Install the rest
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "alembic upgrade head && python main.py"]
