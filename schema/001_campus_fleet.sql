-- Campus fleet schema: the physical smart-can inventory behind the campus map.
--
-- This is the first DDL this repository tracks. Before it, db.py's docstring
-- recorded the schema as "already fixed in OCI", which made the three existing
-- tables (WASTE_EVENTS / PRODUCTS / RECOMMENDATIONS) unreviewable. New tables
-- are tracked here instead, applied by schema/apply.py.
--
-- Conventions mirrored from the existing tables rather than reinvented:
--   * surrogate keys are GENERATED ALWAYS AS IDENTITY, so db.py's
--     "RETURNING <pk> INTO" inserts keep working the same way;
--   * boolean-ish columns are NUMBER(1) compared as "= 1", matching
--     WASTE_EVENTS.HAZARD_FLAG, not a native 23ai BOOLEAN;
--   * timestamps are TIMESTAMP defaulting to CURRENT_TIMESTAMP;
--   * indexes are named IDX_<table>_<columns>.
--
-- Statements are separated by a line containing only "/" because apply.py
-- splits on that delimiter; keep one statement per block.

-- CAN_MODELS: the hardware SKU, shared by every physical can of that version.
-- CAPACITY_ITEMS is the item-unit capacity derived fill is measured against:
-- there are no weight sensors (see CLAUDE.md), so fullness is counted in items,
-- never weighed.
CREATE TABLE can_models (
    model_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_code       VARCHAR2(40) NOT NULL UNIQUE,
    display_name     VARCHAR2(120) NOT NULL,
    capacity_liters  NUMBER(6, 1),
    capacity_items   NUMBER(6) NOT NULL,
    height_cm        NUMBER(5, 1),
    stream_count     NUMBER(2),
    has_camera       NUMBER(1) DEFAULT 1,
    has_actuator     NUMBER(1) DEFAULT 1,
    firmware_version VARCHAR2(40),
    released_on      DATE
)
/

-- BUILDINGS: the campus structure a can sits in. Its lat/long is the building
-- centroid, used as a map fallback and to group cans by area.
CREATE TABLE buildings (
    building_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_code VARCHAR2(40) NOT NULL UNIQUE,
    name          VARCHAR2(160) NOT NULL,
    campus_area   VARCHAR2(80),
    latitude      NUMBER(9, 6),
    longitude     NUMBER(9, 6)
)
/

-- CANS: one physical (or, for now, mostly theoretical) smart can.
-- IS_SIMULATED is the honesty flag that keeps a real reporting unit
-- distinguishable from the mock fleet; it is surfaced in the UI, not just
-- stored, per CLAUDE.md's "distinguish observed data from AI estimates".
CREATE TABLE cans (
    can_id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    can_code         VARCHAR2(40) NOT NULL UNIQUE,
    model_id         NUMBER NOT NULL REFERENCES can_models (model_id),
    building_id      NUMBER NOT NULL REFERENCES buildings (building_id),
    floor            VARCHAR2(20),
    placement_note   VARCHAR2(200),
    latitude         NUMBER(9, 6),
    longitude        NUMBER(9, 6),
    installed_on     DATE,
    lifecycle_status VARCHAR2(20) DEFAULT 'active' NOT NULL,
    is_simulated     NUMBER(1) DEFAULT 1 NOT NULL
)
/

-- CAN_READINGS: append-only telemetry. Never updated in place -- the latest
-- row per can is the current state, and the tail is the history the detail
-- panel charts. FILL_SOURCE records whether FILL_PERCENT was derived from
-- counted disposal events ('observed') or seeded for a mock can ('simulated').
CREATE TABLE can_readings (
    reading_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    can_id          NUMBER NOT NULL REFERENCES cans (can_id),
    reported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    fill_percent    NUMBER(5, 1),
    fill_source     VARCHAR2(20),
    camera_ok       NUMBER(1) DEFAULT 1,
    actuator_ok     NUMBER(1) DEFAULT 1,
    connectivity_ok NUMBER(1) DEFAULT 1,
    battery_percent NUMBER(5, 1),
    fault_code      VARCHAR2(40),
    fault_detail    VARCHAR2(400)
)
/

CREATE INDEX idx_can_readings_can_time ON can_readings (can_id, reported_at DESC)
/

-- SERVICE_EVENTS: what a technician did to a can. An 'emptied' row is the
-- reset point derived fill counts forward from.
CREATE TABLE service_events (
    service_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    can_id       NUMBER NOT NULL REFERENCES cans (can_id),
    service_type VARCHAR2(40) NOT NULL,
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    performed_by VARCHAR2(120),
    notes        VARCHAR2(600)
)
/

CREATE INDEX idx_service_events_can_time ON service_events (can_id, performed_at DESC)
/

-- WASTE_EVENTS.BIN_ID: the real foreign key that makes "click a can to see
-- what it contains" a sound query rather than a string match. Nullable on
-- purpose -- the live sorting pipeline still inserts events without a can,
-- and LOCATION is deliberately left in place as the raw reported value.
ALTER TABLE waste_events ADD (bin_id NUMBER REFERENCES cans (can_id))
/

CREATE INDEX idx_waste_events_bin_id ON waste_events (bin_id)
/
