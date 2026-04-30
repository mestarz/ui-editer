#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
mkdir -p build
cd build
cmake -DCMAKE_BUILD_TYPE=Release .. >/dev/null
make -j"$(nproc)"
echo
echo "built: $(pwd)/libnvgrender.so"
