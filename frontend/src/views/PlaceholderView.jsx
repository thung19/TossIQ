export default function PlaceholderView({ hidden, text }) {
  return (
    <div className="view" hidden={hidden}>
      <div className="placeholder-view">{text}</div>
    </div>
  );
}
