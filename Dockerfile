FROM python:3.12-slim

ARG INSTALL_EXTRAS=
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=emailauto.config.settings

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY manage.py ./

RUN pip install --no-cache-dir -e ".${INSTALL_EXTRAS}"

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
