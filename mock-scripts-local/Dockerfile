FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir prometheus-client

COPY mock_exporter_local_droplet1.py mock_exporter_local_droplet2.py \
     mock_exporter_local_droplet3.py mock_exporter_local_droplet4.py ./

ENTRYPOINT ["python"]
