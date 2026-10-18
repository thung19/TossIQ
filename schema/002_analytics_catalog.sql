-- Analytics schema: the catalog detail and the review trail the analytics
-- page is built on.
--
-- Two things this adds, and the reason each is a column rather than a
-- hardcoded lookup in Python:
--
--   * PRODUCTS gains the attributes that turn a counted disposal into a
--     costed, weighed, named one. UNIT_WEIGHT_GRAMS in particular is a
--     CATALOG REFERENCE MASS, not a measurement: there are no weight sensors
--     on any can (CLAUDE.md records that as a hard hardware constraint), so
--     every mass this system reports is items x reference mass, and the API
--     labels it an estimate wherever it is served. Storing it here, per
--     product, is what keeps that estimate auditable -- a reviewer can see
--     which number produced the total.
--
--   * EVENT_REVIEWS records a human verdict on a classification. Without it
--     there is no ground truth anywhere in this system, and "accuracy" could
--     only ever mean "the model's own confidence", which measures nothing.
--     Coverage is expected to be partial; the API reports the reviewed
--     fraction alongside the accuracy so a rate over nine samples is never
--     mistaken for a rate over nine hundred.
--
-- Conventions follow 001: identity keys, NUMBER(1) booleans, "/" statement
-- delimiter, IDX_<table>_<columns> index names.

-- --------------------------------------------------------------------------
-- PRODUCTS: catalog detail for cost, mass, and variant-level naming.
-- --------------------------------------------------------------------------
-- BRAND / VARIANT_LABEL exist so "plastic water bottle" can resolve to the
-- specific thing bought -- a 500 mL Dasani rather than a 1 L Smartwater --
-- which is what makes a purchasing recommendation actionable.
--
-- DETECTED_AS is the vision label this product presents as. It is the honest
-- join key between what the camera can say and what the catalog knows:
-- several products share one label precisely because the label alone cannot
-- tell them apart, and analytics.py reports that ambiguity rather than
-- picking a variant arbitrarily.
ALTER TABLE products ADD (
    brand              VARCHAR2(120),
    variant_label      VARCHAR2(160),
    detected_as        VARCHAR2(120),
    material_subtype   VARCHAR2(80),
    unit_weight_grams  NUMBER(8, 2),
    disposal_category  VARCHAR2(20),
    recyclable         NUMBER(1),
    reusable           NUMBER(1),
    case_pack_qty      NUMBER(6),
    case_cost          NUMBER(10, 2),
    active             NUMBER(1) DEFAULT 1
)
/

CREATE INDEX idx_products_detected_as ON products (detected_as)
/

CREATE INDEX idx_products_sku ON products (sku)
/

-- --------------------------------------------------------------------------
-- EVENT_REVIEWS: human ground truth for one classification.
-- --------------------------------------------------------------------------
-- One row per review, not one per event: a contested call can be reviewed
-- twice, and overwriting the first verdict would hide the disagreement. The
-- analytics layer takes the latest review per event.
--
-- CORRECTED_CATEGORY / CORRECTED_OBJECT are NULL when VERDICT is 'correct' --
-- there is nothing to correct -- and carry the true value otherwise, which is
-- what makes a confusion matrix possible rather than just an error count.
CREATE TABLE event_reviews (
    review_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id          NUMBER NOT NULL REFERENCES waste_events (event_id),
    verdict           VARCHAR2(20) NOT NULL,
    corrected_category VARCHAR2(40),
    corrected_object  VARCHAR2(160),
    reviewer          VARCHAR2(120),
    reviewed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    notes             VARCHAR2(600)
)
/

CREATE INDEX idx_event_reviews_event ON event_reviews (event_id, reviewed_at DESC)
/

CREATE INDEX idx_event_reviews_time ON event_reviews (reviewed_at DESC)
/

-- WASTE_EVENTS: the time index every analytics query filters on. Without it
-- each window scan is a full table scan, and the analytics page issues
-- several per page load.
CREATE INDEX idx_waste_events_created_at ON waste_events (created_at DESC)
/

CREATE INDEX idx_waste_events_product ON waste_events (product_id)
/

-- WASTE_EVENTS.MATCH_METHOD: how this event's PRODUCT_ID was arrived at.
-- The pipeline has two matchers of very different reliability -- token
-- overlap on the vision label (db.match_product) and Cohere image-embedding
-- similarity against a reference photo (db.match_product_by_image) -- and
-- seeded demo rows are a third case entirely. Without this column the
-- analytics page can report a cost total but not how much of it rests on a
-- fuzzy string match, which is the first thing anyone should ask of it.
ALTER TABLE waste_events ADD (match_method VARCHAR2(20))
/
