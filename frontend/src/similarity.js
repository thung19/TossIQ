// Visual-similarity presentation, shared by the similar-item lookup and the
// unknown-item clusters.
//
// The API reports cosine distance, which is what Oracle's VECTOR_DISTANCE
// returns: 0 means the two photos point in the same direction in Cohere's
// embedding space, 1 means unrelated. An operator should not have to read
// that, so a distance is shown as a percentage plus a plain-language band.

export function matchPercent(distance) {
  const clamped = Math.min(1, Math.max(0, 1 - distance));
  return Math.round(clamped * 100);
}

// Band edges are presentation only -- they describe how close a match is, and
// deliberately do not claim two photos are the same item. Like the clustering
// threshold itself these are heuristics, not calibrated against a real body of
// disposal photos.
const BANDS = [
  [0.1, 'near-identical'],
  [0.25, 'very similar'],
  [0.45, 'similar'],
];

export function similarityLabel(distance) {
  const band = BANDS.find(([limit]) => distance <= limit);
  return band ? band[1] : 'loosely similar';
}

/** e.g. "96% visual match - near-identical" */
export function similarityText(distance) {
  return `${matchPercent(distance)}% visual match — ${similarityLabel(distance)}`;
}
