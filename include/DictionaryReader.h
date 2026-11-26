#ifndef SHARPVOX_DICTIONARY_READER_H
#define SHARPVOX_DICTIONARY_READER_H

#include <cstdint>
#include <string>
#include <vector>
#include <functional>

namespace SharpVox {

	class DictReader {
	    public:
		explicit DictReader(const uint8_t* data, int32_t dataLen);

		// Returns phoneme bytes for the given word, or empty vector if not found.
		std::vector<uint8_t> Search(const std::string& word) const;

		// Calls callback(word, phons) for every entry in the dictionary.
		void EnumerateAll(std::function<void(const std::string&, const std::vector<uint8_t>&)> callback) const;

		int32_t WordCount() const {
			return _wordCount;
		}

	    private:
		const uint8_t* _data;
		int32_t	       _dataLen;
		int32_t	       _wordCount;
		int32_t	       _restartInterval;
		int32_t	       _wordsEnd;

		// Built on load: offsets of every _restartInterval-th entry, which
		// stores its whole word, in the word and phoneme streams.
		struct Restart {
			uint32_t word;
			uint32_t phons;
		};
		std::vector<Restart> _restarts;

		// Reads the entry at wordOff/phonsOff, rebuilding its word in place
		// from the previous entry's word, then advances both offsets.
		void		     ReadEntry(int32_t& wordOff, int32_t& phonsOff, std::string& word, int32_t& entryPhonsOff) const;
		std::vector<uint8_t> UnfoldPhons(int32_t phonsOff) const;
	};

} // namespace SharpVox

#endif // SHARPVOX_DICTIONARY_READER_H
