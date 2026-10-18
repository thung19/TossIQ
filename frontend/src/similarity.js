// Visual-similarity presentation for the similar-item lookup (RecentEvents).
//
// The API reports cosine distance, which is what Oracle's VECTOR_DISTANCE
// returns: 0 means the two photos point in the same direction in Cohere's
// embedding space, 1 means unrelated. An operator should not have to read
// that, so a distance is shown as a percentage.

function matchPercent(distance) {
  const clamped = Math.min(1, Math.max(0, 1 - distance));
  return Math.round(clamped * 100);
}

/** e.g. "96% visual match" */
export function similarityText(distance) {
  return `${matchPercent(distance)}% visual match`;
}
