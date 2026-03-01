## Forem ELT

### Project Goal

This project builds an **end-to-end Lakehouse pipeline (ELT)** to analyze technical articles published on `dev.to` platform, focusing on questions like:

- Which articles are more popular (beginner, tutorials, discussions)?
- What keywords and tags trend over time?
- Which metrics impact engagement (reading time, sentiment, etc.)?

### Architecture

**Source → Storage → Processing → Analytics**

![Architecture Diagram](assets/pipeline.webp)

Orchestration is handled by Azure Data Factory:

![ADF Orchestration](assets/azure-data-factory.png)

### Pipeline Description:

1. **Extract**

- Articles are fetched via Python scripts running in an **Azure Function App**.
- Initial historical backfill is loaded once; subsequent loads capture only new articles.

2. **Load**

- Raw JSON is stored directly in ***Azure Blob Storage***.
- Processed data is stored in **Delta Lake** tables in Databricks, organized into Bronze, Silver, and Gold layers following the Medallion Architecture pattern.

3. **Transform**

Data transformations are implemented in **Databricks** using **PySpark**. Transformations are modularized into notebooks for each layer (Bronze, Silver, Gold) to maintain separation of concerns and facilitate maintenance.

4. **Orchestration (Azure Data Factory)**

- Triggers the Azure Function App for incremental article ingestion.
- Orchestrates Databricks notebooks for Silver and Gold transformations.
- Ensures pipeline runs in a scheduled, automated, and auditable way.

5. **Analytics (Power BI)**

Gold tables are used by Power BI dashboards for interactive exploration.


### Data Layers

**Data Source:** raw JSON data is fetched using **Forem REST API** `https://dev.to/api/articles/latest` and stored in **Azure Blob Storage**. Raw data is never modified or deleted to preserve the original state for traceability and reprocessing if needed.

🥉 **Bronze**

Raw JSON is ingested as-is into Delta Lake without any transformations. This layer serves as the **immutable source of truth**, allowing for reprocessing and schema evolution as needed.

***Engineering Decisions:***

- Add metadata columns (ingestion timestamp, source) for traceability
- No transformations or cleaning at this stage to maintain data integrity
- Stored as Delta format (efficient querying, schema evolution, reduced storage costs)
- Supports append-based incremental loads


🥈 **Silver**

Transformed and cleaned data optimized for analysis:

- Deduplicated by id
- Filtered empty articles (reading time > 0)
- Flattened nested structures (e.g., tags, user info)
- Added derived columns for analytical purposes (year, month)
- Selected relevant columns for downstream analysis

***Engineering Decisions:***

- One row per article (normalized structure)
- Exploded tag table created separately for tag-level analytics
- Avoid mixing aggregation logic in Silver


🥇 **Gold**

Analytical tables optimized for BI:

- Timeline trends (articles count, engagement metrics by month/year)
- Tag popularity (top tags by article count)
- Title keyword trends (top keywords in titles)

***Engineering Decisions:***

- Only business-ready aggregates stored here
- Designed for Power BI performance
- Keep grain explicit and documented
- Explode tags in Gold for easier analysis


### Key Engineering Decisions

- **Medallion Architecture**: Clear separation of raw, cleaned, and business-ready data layers for maintainability and scalability.
- **ELT Pattern**: Extract → Load → Transform, with raw data preserved for reproducibility and traceability.
- **Incremental Loads**: Pipeline designed for efficiency; only new articles are processed daily.
- Processed batches information is stored as metadata in the pipeline (`metadata` table) to ensure idempotency and prevent duplicates.
