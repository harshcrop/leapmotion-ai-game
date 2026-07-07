FROM ubuntu:jammy

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update \
 && apt install -y ca-certificates wget gpg \
 && wget -qO - https://repo.ultraleap.com/keys/apt/gpg | gpg --dearmor | tee /etc/apt/trusted.gpg.d/ultraleap.gpg \
 && echo 'deb [arch=amd64] https://repo.ultraleap.com/apt stable main' | tee /etc/apt/sources.list.d/ultraleap.list \
 && echo "path-include=/usr/share/doc/ultraleap-hand-tracking-service/*" | tee -a /etc/dpkg/dpkg.cfg.d/excludes \
 && apt update \
 && apt install -y --force-yes build-essential cmake ultraleap-hand-tracking-service \
 && apt clean

WORKDIR /libwebsockets

RUN apt install -y libssl-dev git
RUN git clone https://github.com/warmcat/libwebsockets.git . \
 && mkdir build \
 && cd build \
 && cmake .. \
 && make \
 && make install \
 && ldconfig

COPY *.c /code/
COPY *.h /code/
COPY CMakeLists.txt /code/
COPY build.sh /code/
WORKDIR /code

RUN apt-get install dos2unix
RUN chmod u+x build.sh && dos2unix build.sh

ENTRYPOINT [ "./build.sh" ]