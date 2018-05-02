FROM ubuntu:latest
MAINTAINER David Johnson <david.johnson@oerc.ox.ac.uk>

RUN apt-get update -y
RUN apt-get install -y python3-pip python3-dev build-essential git
COPY . /app
WORKDIR /app
RUN pip3 install -r requirements.txt
ENTRYPOINT ["python3"]
CMD ["isarest.py"]
