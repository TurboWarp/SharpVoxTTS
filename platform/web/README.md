# Web build

Builds SharpVox as a WebAssembly ES module with a small C API. English only.
`platform/wasm` is the separate backend for the demo web UI.

## Building

Install the emsdk version listed in `EMSDK_VERSION`, then run:

```sh
source /path/to/emsdk/emsdk_env.sh
platform/web/build.sh   # or: make web
```

Output goes to `dist/`: `sharpvox.mjs`, `sharpvox.wasm`, and `SHA256SUMS`.

Building the same commit with the same emsdk version should produce identical
files. CI builds twice to check this and attests the output, which you can
verify with:

```sh
gh attestation verify sharpvox.wasm --repo TurboWarp/SharpVoxTTS
```

`sv_version()` returns the commit hash the module was built from.

## Usage

```js
import SharpVoxModule from "./sharpvox.mjs";

// Pass { wasmBinary } if you fetched sharpvox.wasm yourself
const Module = await SharpVoxModule();

const handle = Module._sv_create();
const text = Module.stringToNewUTF8("Hello world");
const length = Module._sv_speak(handle, text, 22050); // -1 on error
Module._free(text);

// 16-bit mono PCM, valid until the next _sv_speak on this handle
const index = Module._sv_samples(handle) >> 1;
const pcm = Module.HEAP16.slice(index, index + length);

Module._sv_destroy(handle);
```
