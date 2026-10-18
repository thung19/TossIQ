-- Initiatives and projects: the goals an organization sets against its own
-- waste data, and the work it does to hit them.
--
-- The design decision that matters here is that an initiative stores a
-- MEASUREMENT RECIPE, not a number somebody types in each month. METRIC
-- says which quantity to measure and the SCOPE_* columns say over what
-- slice, so progress is recomputed from logged disposals every time the
-- page loads. A target tracked by hand drifts from reality the first week
-- somebody is busy, and a dashboard that reports a stale number is worse
-- than one that reports none.
--
-- The scope columns deliberately mirror the analytics filter set
-- (db._analytics_filters). An initiative is "reduce X in scope Y", and Y is
-- exactly the narrowing the analytics page already supports -- so the same
-- query serves both, and a goal can never be defined over a slice the rest
-- of the product cannot show you.

CREATE TABLE initiatives (
    initiative_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                VARCHAR2(200) NOT NULL,
    description         VARCHAR2(1000),
    owner               VARCHAR2(120),

    -- What to measure. One of the keys in initiatives.METRICS; validated
    -- there rather than by a check constraint, so adding a metric is a
    -- code change and not a migration.
    metric              VARCHAR2(40) NOT NULL,
    -- 'reduce' (lower is better) or 'increase' (higher is better). Stored
    -- rather than inferred from the metric: "landfill items" is a reduce
    -- goal and "diversion rate" an increase one, and some metrics could
    -- honestly be either.
    direction           VARCHAR2(10) DEFAULT 'reduce' NOT NULL,

    -- The slice this goal is about. All NULL means campus-wide.
    scope_building_id   NUMBER REFERENCES buildings (building_id),
    scope_category      VARCHAR2(40),
    scope_material      VARCHAR2(80),
    scope_object        VARCHAR2(160),
    scope_supplier      VARCHAR2(255),

    -- Where we started. Captured when the initiative is created so progress
    -- is measured from a real observation rather than from zero, and frozen
    -- afterwards -- a baseline that moves is not a baseline.
    baseline_value      NUMBER(14, 3),
    baseline_window_days NUMBER(5) DEFAULT 30 NOT NULL,
    baseline_captured_at TIMESTAMP,

    target_value        NUMBER(14, 3) NOT NULL,
    target_date         DATE,

    status              VARCHAR2(20) DEFAULT 'active' NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
/

CREATE INDEX idx_initiatives_status ON initiatives (status, target_date)
/

-- PROJECTS: the specific actions that move an initiative.
--
-- SOURCE_RECOMMENDATION_KEY ties this back to the recommendations page.
-- Those cards already say what to do and what it is worth; a project
-- created from one carries its key so the two stay connected and the same
-- recommendation is not raised twice as separate work.
CREATE TABLE projects (
    project_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    initiative_id       NUMBER REFERENCES initiatives (initiative_id),
    name                VARCHAR2(200) NOT NULL,
    description         VARCHAR2(1000),
    owner               VARCHAR2(120),
    status              VARCHAR2(20) DEFAULT 'proposed' NOT NULL,

    -- What this action is expected to contribute, in the units of its
    -- initiative's metric. An estimate the person creating it supplies, not
    -- a measurement: the measured part is the initiative's own progress,
    -- and keeping the two apart is what stops a pile of optimistic
    -- estimates reading as achievement.
    expected_impact     NUMBER(14, 3),
    expected_impact_note VARCHAR2(400),

    source_recommendation_key VARCHAR2(200),

    due_date            DATE,
    started_at          TIMESTAMP,
    completed_at        TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
/

CREATE INDEX idx_projects_initiative ON projects (initiative_id, status)
/

CREATE INDEX idx_projects_recommendation ON projects (source_recommendation_key)
/
