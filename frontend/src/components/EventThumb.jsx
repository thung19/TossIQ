export default function EventThumb({ imageUrl }) {
  if (!imageUrl) return <div className="event-thumb-placeholder">&mdash;</div>;
  return <img className="event-thumb" src={imageUrl} alt="" />;
}
