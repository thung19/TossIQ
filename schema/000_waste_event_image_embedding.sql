-- Visual memory: every advanced-analysis disposal event stores its item
-- photo's Cohere Embed v4 embedding on the event row, which is what
-- db.find_similar_events and db.cluster_unknown_events search. Without this
-- column every insert_waste_event call fails with ORA-00904.
ALTER TABLE waste_events ADD (image_embedding VECTOR(1536, FLOAT32));
