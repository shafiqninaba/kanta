-- Extensions
-- Note that you have to allow the extension on the Azure portal first:
-- https://learn.microsoft.com/en-us/azure/PostgreSQL/extensions/how-to-allow-extensions?tabs=allow-extensions-portal
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector for embeddings

-- Drop tables if they exist (only for testing)
DROP TABLE IF EXISTS faces;
DROP TABLE IF EXISTS images;

/*--------------------------------------------------------------------
  Images
    • id is a SERIAL primary key (auto-incrementing integer)
    • uuid is a 32-char hex string (uuid.uuid4().hex) – no default.
      We choose both id and uuid for convenience:
        – id is fast for joins and indexing
        – uuid is a unique identifier for the image, useful for external references
    • file_extension is filled automatically by a trigger.
--------------------------------------------------------------------*/
CREATE TABLE images (
    id             SERIAL PRIMARY KEY,
    uuid           VARCHAR(32) UNIQUE NOT NULL,
    azure_blob_url TEXT      NOT NULL,
    file_extension TEXT      NOT NULL,           -- e.g. 'jpg'
    faces          INTEGER   NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    last_modified  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Trigger to derive the file extension
CREATE OR REPLACE FUNCTION trg_set_file_ext()
  RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.file_extension :=
        LOWER( split_part( split_part( NEW.azure_blob_url, '?', 1 ), '.', -1 ) );
    RETURN NEW;
END;
$$;

CREATE TRIGGER set_file_ext
  BEFORE INSERT OR UPDATE OF azure_blob_url
  ON images
  FOR EACH ROW
  EXECUTE FUNCTION trg_set_file_ext();

/*--------------------------------------------------------------------
  Faces
    • Keep fast FK on image_id          (INTEGER → images.id)
    • Also store image_uuid as plain text for quick look-ups by UUID.
--------------------------------------------------------------------*/
CREATE TABLE faces (
    id          SERIAL PRIMARY KEY,
    image_id    INTEGER  NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    image_uuid  VARCHAR(32) NOT NULL,
    bbox        JSONB    NOT NULL,       -- {"x":10,"y":20,"width":30,"height":40}
    embedding   vector(128) NOT NULL,    -- 128-D face embedding
    cluster_id  INTEGER  NOT NULL DEFAULT -1  -- -1 = unclustered
);

/* ----- OPTIONAL consistency check (uncomment if you want a second FK)
ALTER TABLE faces
  ADD CONSTRAINT fk_faces_image_uuid
    FOREIGN KEY (image_uuid) REFERENCES images(uuid) ON DELETE CASCADE;
*/

-- Sample data
INSERT INTO images (uuid, azure_blob_url, faces) VALUES
  ('123e4567e89b12d3a456426655440000', 'https://example.com/blob1.jpg', 1),
  ('123e4567e89b12d3a456426655440001', 'https://example.com/blob2.png', 2),
  ('123e4567e89b12d3a456426655440002', 'https://example.com/blob3.jpeg?sig=xyz', 3);

WITH ref AS (
  SELECT id, uuid FROM images
)
INSERT INTO faces (image_id, image_uuid, bbox, embedding) VALUES
(
  (SELECT id FROM ref WHERE uuid = '123e4567e89b12d3a456426655440000'),
  '123e4567e89b12d3a456426655440000',
  '{"x":10,"y":20,"width":30,"height":40}',
  ARRAY[
    0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
  ]::vector
),
(
  (SELECT id FROM ref WHERE uuid = '123e4567e89b12d3a456426655440001'),
  '123e4567e89b12d3a456426655440001',
  '{"x":15,"y":25,"width":35,"height":45}',
  ARRAY[
    0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.2,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
  ]::vector
);
