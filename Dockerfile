FROM resin/rpi-raspbian:latest
MAINTAINER kenneth.jiang+dockerhub@gmail.com

ARG version

RUN apt-get update && apt-get install -y --no-install-recommends \
    python-pip \
    python-dev \
    build-essential \
    git \
    avrdude \
    curl \
    wget \
    unzip

RUN echo "Cloning OctoPrint repository..."

WORKDIR /octoprint
RUN curl -o octoprint.tar.gz -L https://github.com/foosel/OctoPrint/archive/${version}.tar.gz
RUN tar -xvf octoprint.tar.gz --strip 1
RUN echo "Building OctoPrint..."
# RUN pip install --upgrade pip
# Workaround for a pip version mismatch
# RUN apt-get update && apt-get remove -f python-pip && apt-get install -y python-pip && apt-get remove -f python-pip easy_install -U pip
RUN pip install setuptools
RUN pip install -r requirements.txt
RUN python setup.py install
VOLUME /data
COPY config.yaml /data/config.yaml

ADD . /app
WORKDIR /app
RUN python setup.py develop

RUN echo "Starting OctoPrint..."

EXPOSE 5000
CMD ["octoprint",  "--iknowwhatimdoing", "--basedir" ,"/data", "--debug"]
