"""Design-match verification.

Compares the artist's uploaded completed-work photo against the reference
design the consumer chose, and produces a 0-100 "match score" used to gate
payment release.

Implementation: perceptual hashing (ImageHash) over the two images. It's a
lightweight, dependency-light stand-in for a full ML embedding model - swap
`score_similarity` for a CLIP-embedding cosine-similarity call later for
higher accuracy on intricate henna patterns; nothing else in the booking
flow needs to change, since callers only see a 0-100 score either way.
"""

from io import BytesIO

import imagehash
from PIL import Image


def score_similarity(image_a_bytes: bytes, image_b_bytes: bytes) -> float:
    hash_a = imagehash.phash(Image.open(BytesIO(image_a_bytes)).convert("RGB"), hash_size=16)
    hash_b = imagehash.phash(Image.open(BytesIO(image_b_bytes)).convert("RGB"), hash_size=16)

    max_bits = len(hash_a.hash) ** 2  # 16x16 hash -> 256 bits
    hamming_distance = hash_a - hash_b
    similarity = (1 - hamming_distance / max_bits) * 100
    return round(max(0.0, min(100.0, similarity)), 1)
