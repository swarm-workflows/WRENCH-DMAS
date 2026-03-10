FROM wrenchproject/wrench-build:ubuntu-noble-gcc13

LABEL org.opencontainers.image.authors="silvarf@ornl.gov,henric@hawaii.edu"


#################################################
# INSTALL WRENCH
#################################################

USER root
WORKDIR /tmp

RUN echo "wrench ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# install libasio-dev
RUN apt-get update && apt-get install -y \ 
    libasio-dev \
    libcurl4-openssl-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libjpeg-dev \
    libpng-dev \
    libssl-dev \
    libtiff5-dev \
    libxml2-dev \
    python3 \
    python3-pip \
    python3-venv \
    r-base \
    && rm -rf /var/lib/apt/lists/*

# Install required R packages
RUN R -e "install.packages(c('jsonlite', 'ggplot2', 'gridExtra', 'readr'), repos='https://cloud.r-project.org')"

# Upgrade pip to the latest version
RUN python3 -m venv /opt/venv
RUN /opt/venv/bin/python3 -m pip install --upgrade pip

# Install jsonref and python dependencies for the SWARM simulator
COPY requirements.txt .
RUN /opt/venv/bin/pip install --break-system-packages jsonref -r requirements.txt

RUN git config --global http.postBuffer 524288000
# reinstall SimGrid
RUN git clone https://github.com/simgrid/simgrid.git && cd simgrid && mkdir build && cd build && cmake .. -Denable_lto=off && make -j1 && make install && cd .. && /bin/rm -rvf simgrid

# reinstall FSMod
RUN git clone https://github.com/simgrid/file-system-module.git && cd file-system-module && mkdir build && cd build && cmake .. && make -j1 && make install && cd .. && /bin/rm -rvf file-system-module

# install WRENCH
RUN git clone https://github.com/wrench-project/wrench.git && cd wrench && mkdir build && cd build && cmake .. && make -j1 wrench-daemon examples && make install && cp -r ./examples /home/wrench/ && chown -R wrench /home/wrench && cd ../.. && /bin/rm -rf wrench

#################################################
# WRENCH's user
#################################################
USER wrench
WORKDIR /home/wrench

RUN cd && git clone https://github.com/frs69wq/SWARM-DMAS-wrench.git && cd SWARM-DMAS-wrench && mkdir build && cd build && cmake .. && make -j
WORKDIR /home/wrench/SWARM-DMAS-wrench/build

# set user's environment variable
ENV PATH="/opt/venv/bin:$PATH"
ENV CXX="g++-13" CC="gcc-13"
ENV LD_LIBRARY_PATH=/usr/local/lib

