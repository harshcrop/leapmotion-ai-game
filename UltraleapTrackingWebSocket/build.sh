#!/bin/sh

RED='\033[0;31m'
NC='\033[0m' # No Color

mkdir -p build/output
cd build
cmake .. && make
if [ $? -eq 0 ]; then
    echo "Build succeeded, copying to output folder"
    cp Ultraleap-Tracking-WS ./output/
else
    echo "${RED}Build failed, consult the output to see what happened...${NC}"
fi