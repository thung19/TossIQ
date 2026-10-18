"""One-off backfill of WASTE_EVENTS.IMAGE_EMBEDDING for events stored before
visual memory existed (or whose embedding call failed at capture time).

Events persisted by api.py now store the item photo's Cohere Embed v4
embedding alongside the row, which is what the visual-memory features search
(db.find_similar_events, db.cluster_unknown_events). Events already in the
table have an image in Object Storage but no embedding, so they are invisible
to that search until this script embeds them.

Deliberately standalone and manual -- it costs one OCI Generative AI embedding
call per event, so it is never run from application startup or a request path.
Run it against real credentials:

    python backfill_event_embeddings.py             # every pending event
    python backfill_event_embeddings.py --limit 20  # first 20, oldest first
    python backfill_event_embeddings.py --dry-run   # report, embed nothing

Re-runnable: the work queue is "has an image key, has no embedding"
(db.list_events_missing_embedding), and storing an embedding removes that
event from it, so a second run picks up only what the first did not finish.
Events whose image is missing from Object Storage, or whose embedding call
fails, are reported and skipped -- never retried in a loop and never fatal, so
one unreachable object does not stop the run.
"""

import argparse
import io
import logging
import sys

from PIL import Image, UnidentifiedImageError

import db
import image_embed
import oci_storage

logger = logging.getLogger("tossiq")


def backfill(limit: int | None = None, dry_run: bool = False) -> dict:
    """Embeds every pending event's stored photo, returning a tally of what
    happened: `pending` considered, `embedded` stored, `missing_image` skipped
    because Object Storage had no readable image, `embed_failed` skipped
    because the embedding call returned None."""
    pending = db.list_events_missing_embedding(limit=limit)
    tally = {
        "pending": len(pending),
        "embedded": 0,
        "missing_image": 0,
        "embed_failed": 0,
    }
    if dry_run:
        for event in pending:
            print(f"  would embed event {event['event_id']} from {event['image_key']}")
        return tally

    for event in pending:
        event_id, image_key = event["event_id"], event["image_key"]
        contents = oci_storage.download_image(image_key)
        if contents is None:
            print(f"  skip event {event_id}: image {image_key} not readable")
            tally["missing_image"] += 1
            continue

        try:
            image = Image.open(io.BytesIO(contents))
            image.load()
            image = image.convert("RGB")
        except (UnidentifiedImageError, OSError):
            print(f"  skip event {event_id}: stored object {image_key} is not a readable image")
            tally["missing_image"] += 1
            continue

        # embed_image never raises; None means the OCI call failed and this
        # event stays in the queue for a later run.
        embedding = image_embed.embed_image(image)
        if embedding is None:
            print(f"  skip event {event_id}: embedding call failed")
            tally["embed_failed"] += 1
            continue

        db.set_event_embedding(event_id, embedding)
        tally["embedded"] += 1
        print(f"  embedded event {event_id}")

    return tally


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="embed at most this many events (oldest first); default is all pending",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be embedded without calling OCI or writing anything",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    tally = backfill(limit=args.limit, dry_run=args.dry_run)

    print(
        f"\n{tally['pending']} event(s) pending an embedding; "
        f"{tally['embedded']} embedded, "
        f"{tally['missing_image']} skipped (image unreadable), "
        f"{tally['embed_failed']} skipped (embedding call failed)."
    )
    if args.dry_run:
        print("Dry run: nothing was embedded or written.")
    elif tally["embed_failed"]:
        print("Re-run to retry the events whose embedding call failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
