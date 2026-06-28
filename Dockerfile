FROM python:3.14.6-bookworm

RUN apt update && apt install -y libopus0 ffmpeg

COPY ./ /app
WORKDIR /app

RUN pip install -r requirements.txt
