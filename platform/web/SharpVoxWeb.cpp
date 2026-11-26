// C API for using SharpVoxSpeaker from JavaScript.

#include <emscripten.h>

#include <cstdint>
#include <string>
#include <vector>

#include "../lib/SharpVox.h"

#ifndef SHARPVOX_GIT_COMMIT
#define SHARPVOX_GIT_COMMIT "unknown"
#endif

using SharpVox::SharpVoxSpeaker;

namespace {

struct Handle {
	SharpVoxSpeaker      speaker;
	std::vector<int16_t> samples;
};

void OnBuffer(SharpVoxSpeaker* /*speaker*/, const int16_t* buf, int32_t len, void* userdata) {
	auto* h = static_cast<Handle*>(userdata);
	h->samples.insert(h->samples.end(), buf, buf + len);
}

}  // namespace

extern "C" {

EMSCRIPTEN_KEEPALIVE const char* sv_version(void) {
	return SHARPVOX_GIT_COMMIT;
}

EMSCRIPTEN_KEEPALIVE Handle* sv_create(void) {
	return new Handle();
}

EMSCRIPTEN_KEEPALIVE void sv_destroy(Handle* h) {
	delete h;
}

// Returns the number of samples, or -1 if the engine threw. Samples stay
// valid until the next sv_speak call.
EMSCRIPTEN_KEEPALIVE int32_t sv_speak(Handle* h, const char* text, int32_t sampleRate) {
	h->samples.clear();
	try {
		if (h->speaker.SampleRate != sampleRate) {
			h->speaker.SampleRate = sampleRate;
			h->speaker.ApplyVoiceInPlace();
		}
		h->speaker.Speak(std::string(text), OnBuffer, h);
	} catch (...) {
		h->samples.clear();
		return -1;
	}
	return static_cast<int32_t>(h->samples.size());
}

EMSCRIPTEN_KEEPALIVE const int16_t* sv_samples(Handle* h) {
	return h->samples.data();
}

}  // extern "C"
