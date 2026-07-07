
# Ultraleap Tracking WebSocket

![Wow](res/unbelievable.png)

- [:question: What is it ?](#question-what-is-it-)
- [:sparkles: What can it do ?](#sparkles-what-can-it-do-)
- [:wrench: How to build ?](#wrench-how-to-build-)
  - [:blue\_square: Windows](#blue_square-windows)
    - [:package: `vcpkg` instructions](#package-vcpkg-instructions)
  - [:penguin: Linux](#penguin-linux)
    - [:whale: `docker` instructions](#whale-docker-instructions)
  - [:apple: MacOS](#apple-macos)
- [:checkered\_flag: How to use ?](#checkered_flag-how-to-use-)
- [:memo: Authors & Contributors](#memo-authors--contributors)

## :question: What is it ?

With the release of Ultraleap Gemini V5 hand tracking, the websocket feature present in Leap Motion Orion V4 was removed. This meant that [LeapJS](https://github.com/leapmotion/leapjs) experiences would no longer work with the newer tracking software.

This **Ultraleap Tracking WebSocket** repository aims to maintain some form of retro-compatibility with LeapJS and enable web developers to receive tracking data in their browser with the latest generation of Ultraleap hand tracking.

## :sparkles: What can it do ?

For now the goal is to be 100% compatible with what was called protocol `v6` in LeapJS which includes LeapJS version 0.6.0 through to 1.1.1. Here is a quick list of the features of `v6` and which ones has been implemented so far:

* Connection on `v6.json` endpoint :heavy_check_mark:
* Stream tracking data :heavy_check_mark:
* Focus and background messages :heavy_check_mark:
* Switch to HMD mode :heavy_check_mark:
* Switch to Screentop mode :heavy_check_mark: (NEW - use latest LeapJS `master` branch)
* Device events :x:
* Gestures :x:
* Secure WebSocket :x:

## :wrench: How to build ?

### :blue_square: Windows

You'll need [Ultraleap Gemini V5 or above](https://leap2.ultraleap.com/downloads) hand tracking to be installed, and OpenSSL too. You also have to add libwebsockets. If you have `vcpkg`, there is [specific instructions](#package-vcpkg-instructions) that might make things easier for you.

Pull the content of this repository and use CMake to build the solution:

```bash
# Pull repository
git clone https://github.com/ultraleap/UltraleapTrackingWebSocket.git
cd ultraleap-tracking-websocket

# Prepare build
mkdir build
cd build

# Build solution
cmake ..
```

Then in the `build` folder you should be able to find your solution and build the executable with Visual Studio.

#### :package: `vcpkg` instructions

Start by [installing and setting vcpkg](https://vcpkg.io/en/getting-started.html). Then install libwebsockets with `vcpkg install libwebsockets --triplet x64-windows`. From then, you can follow these instructions:

```bash
# Pull repository
git clone https://github.com/ultraleap/UltraleapTrackingWebSocket.git
cd ultraleap-tracking-websocket

# Prepare build
mkdir build
cd build

# Build solution
cmake -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake ..
cmake --build .
```

### :penguin: Linux

To build on Linux, you'll need to have a couple of dependencies installed on your system:

* CMake (package `cmake` on Ubuntu/Debian)
* Ultraleap's tracking service and SDK (Ultraleap's website has [instructions on how to add the repository and install the packages](https://docs.ultraleap.com/linux/)
* libwebsockets (package `libwebsockets-dev` on Ubuntu/Debian)

If you satisfy those dependencies, you can go ahead, pull the repository and build the executable:

```bash
# Pull repository
git clone https://github.com/ultraleap/UltraleapTrackingWebSocket.git
cd ultraleap-tracking-websocket

# Prepare build
mkdir build
cd build

# Build solution
cmake ..
```

#### :whale: `docker` instructions

Very useful if you want to cross-build for Linux, or avoid having to build and add libwebsockets to your system. Run the following on a Linux-based system:

```bash
# Build Docker image
docker build -t leapws-builder:latest .

# Run the container (also mounts the result folder)
docker run -v "$(pwd)/output":/code/build/output --rm -it leapws-builder:latest
```

The resulting build should be found in the `output` folder.

### :apple: MacOS

Ensure you have Xcode or at least the XCode Command Line Tools installed, and that [homebrew](https://brew.sh) is installed and set up. Make sure you also have installed [Ultraleap Gemini V5 or above](https://leap2.ultraleap.com/downloads) hand tracking service for Mac.

Install `libwebsockets` with `brew install libwebsockets`. From there, you can follow the instructions:

```bash
# Pull repository
git clone https://github.com/ultraleap/UltraleapTrackingWebSocket.git
cd ultraleap-tracking-websocket

# Prepare build folder
mkdir build
cd build

# Build solution and executable
cmake ..
cmake --build .
```

## :checkered_flag: How to use ?

Once built, run the executable to start the websocket server.

Download the [LeapJS repository](https://github.com/leapmotion/leapjs) and run one of the webpages from the `examples` folder such as `dumper.html` to see the hand data coming through.

## :memo: Authors & Contributors
- Author: [Rodolphe Houdas](https://github.com/rodolpheh)
- Contributors:
	- [James Provan](https://github.com/JamesProvan-UL)