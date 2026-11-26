#!/usr/bin/env bash
# Builds platform/web/dist/sharpvox.mjs and sharpvox.wasm.
# Needs em++ from the emsdk version in EMSDK_VERSION.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
dist="$here/dist"
cd "$root"

expected_emsdk="$(tr -d '[:space:]' < "$here/EMSDK_VERSION")"
actual_emsdk="$(em++ --version | sed -n 's/^emcc ([^)]*) \([0-9.]*\).*/\1/p')"
if [ "$actual_emsdk" != "$expected_emsdk" ]; then
	if [ "${SHARPVOX_ALLOW_EMSDK_MISMATCH:-0}" = "1" ]; then
		echo "warning: em++ is $actual_emsdk, expected $expected_emsdk; output won't be reproducible" >&2
	else
		echo "error: em++ is '$actual_emsdk' but EMSDK_VERSION pins $expected_emsdk" >&2
		echo "set SHARPVOX_ALLOW_EMSDK_MISMATCH=1 to build anyway" >&2
		exit 1
	fi
fi

commit="$(git rev-parse HEAD)"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
	commit="$commit-dirty"
fi

# No HAVE_MECAB, so the IPADIC dictionary is left out.
srcs=(
	src/Tables.cpp
	src/KlattSynthesizerFP.cpp
	src/PitchInterpolator.cpp
	src/AudioProcessor.cpp
	src/SpeechRenderer.cpp
	src/TtsEngine.cpp
	src/Phonemizer.cpp
	src/LetterToSoundFlite.cpp
	src/LetterToSoundFliteModel.cpp
	src/LetterToSoundNRL.cpp
	src/DictionaryReader.cpp
	src/LibraryDataDictionary.cpp
	src/LibraryDataSymbols.cpp
	src/HeteronymResolver.cpp
	src/TextCommands.cpp
	src/KlattschParser.cpp
	src/VoicePresets.cpp
	src/JapaneseParser.cpp
	platform/lib/SharpVox.cpp
	platform/web/SharpVoxWeb.cpp
)

rm -rf "$dist"
mkdir -p "$dist"

# -ffile-prefix-map keeps the checkout path out of the output so builds match.
em++ -std=c++17 -O2 -Iinclude \
	-ffile-prefix-map="$root"=. \
	-DSHARPVOX_GIT_COMMIT="\"$commit\"" \
	-fwasm-exceptions \
	-sMODULARIZE=1 \
	-sEXPORT_ES6=1 \
	-sEXPORT_NAME=SharpVoxModule \
	-sENVIRONMENT=web,worker \
	-sALLOW_MEMORY_GROWTH=1 \
	-sSTACK_SIZE=2097152 \
	-sINCOMING_MODULE_JS_API=wasmBinary,locateFile \
	-sEXPORTED_FUNCTIONS=_malloc,_free \
	-sEXPORTED_RUNTIME_METHODS=stringToNewUTF8,UTF8ToString,HEAP16 \
	"${srcs[@]}" \
	-o "$dist/sharpvox.mjs"

(cd "$dist" && sha256sum sharpvox.mjs sharpvox.wasm > SHA256SUMS)
cat "$dist/SHA256SUMS"
