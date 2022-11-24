FROM golang:1.18

# Clone go algorand
RUN mkdir -p "/Users/fergal/"
WORKDIR "/Users/fergal/"
RUN git clone https://github.com/algorand/go-algorand.git

# Checkout v3.8.1
WORKDIR "/Users/fergal/go-algorand/"
RUN git checkout v3.8.1-stable

# run algo node builds
RUN ./scripts/configure_dev.sh
RUN ./scripts/buildtools/install_buildtools.sh
RUN  make install

# Run on host machine:
# ====================
# ```
# docker build -t local/algojig .;
# docker run -v $(pwd):/algojig -ti local/algojig /bin/bash -c "cd /algojig/gojig; go build -o ../algojig/algojig_linux_x86_64";
# ```
