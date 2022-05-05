FROM python:slim

ARG TZ=America/New_York

RUN \
    pip install requests \
    && pip install python-kasa \
    && pip install influxdb-client \
    && pip cache purge

RUN mkdir /app
COPY ./sbtemp.py /app
RUN chmod 755 /app/sbtemp.py

ENTRYPOINT [ "python3", "-u", "/app/sbtemp.py" ]