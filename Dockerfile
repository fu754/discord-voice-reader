FROM python:3.11.7-bookworm

RUN apt update && apt install -y libopus0 ffmpeg

COPY ./ /app
WORKDIR /app

RUN pip install -r requirements.txt
