FROM python:3.11

WORKDIR /usr/src/backend

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN pip install --upgrade pip

RUN apt-get update && apt-get install -y \
    pkg-config \
    python3-dev \
    libcairo2-dev \
    libgirepository1.0-dev \
    gir1.2-glib-2.0 \
    build-essential \
    meson \
    cmake

COPY ./deploy/requirements.txt /usr/src/backend/requirements.txt
RUN pip install --default-timeout=200 -r requirements.txt

COPY ./entrypoint.sh /usr/src/backend/entrypoint.sh

COPY . /usr/src/backend/

RUN ["chmod", "+x", "/usr/src/backend/entrypoint.sh"]

ENTRYPOINT ["sh", "/usr/src/backend/entrypoint.sh"]
