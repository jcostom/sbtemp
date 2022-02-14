FROM python:slim

ENV TZ=America/New_York

RUN \
    pip3 install requests \
    && pip3 install python-kasa \
    && pip3 install influxdb-client

RUN mkdir /app
COPY ./sbtemp.py /app
RUN chmod 755 /app/sbtemp.py

ENTRYPOINT [ "python3", "-u", "/app/sbtemp.py" ]