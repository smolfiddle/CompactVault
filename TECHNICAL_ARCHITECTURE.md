# Technical Architecture

This document outlines the core technical decisions and architecture of the CompactVault system.

## Hashing Algorithm

The system utilizes the **BLAKE2b** hashing algorithm for all data chunk and manifest integrity checks.

BLAKE2b was chosen over the previous SHA256 implementation for its significant performance advantages (it is generally faster than SHA256 on modern 64-bit platforms) while providing an equivalent, high level of security.

This change was implemented as a **breaking change**. Any database created with a previous version of the software is incompatible and must be recreated.

## Password Hashing

Each `.vault` file is protected by a password. The password is not stored directly. Instead, it is hashed using **PBKDF2-HMAC-SHA256** with a unique salt for each vault. The salt is stored in the `vault_properties` table along with the hash. This makes the password storage secure against rainbow table and pre-computation attacks.

## Database Schema & Performance

The database schema is designed for efficient storage and retrieval of chunked assets. To enhance performance, the following optimizations have been made:

*   **`vault_properties` Table:** A dedicated table for storing vault-specific metadata, such as the password hash and salt.
*   **Write-Ahead Logging (WAL):** The database operates in WAL mode to improve concurrency and write performance. A graceful shutdown mechanism (`signal_handler` for Ctrl+C) is implemented to run a database checkpoint, which commits all changes from the `.wal` log file into the main database and ensures the temporary files are cleanly removed.
*   **Server-Side Sorting:** All asset sorting is handled by the database, with support for sorting by filename and size. This is much more efficient than the previous client-side sorting implementation.
*   **Manual `VACUUM`:** The application provides a UI button to trigger the `VACUUM` command. This allows the user to manually reclaim unused space and optimize the database file.

The `CompactVaultManager` provides methods for adding and reading data, but **intentionally lacks methods for editing or deleting assets**. The API exposed by the `RequestHandler` reflects this; there are no `PUT`, `PATCH`, or `DELETE` endpoints for assets. This architectural constraint is the primary mechanism for ensuring the permanence of the archive.

### Chunk-Based Storage & Data Integrity

To guarantee integrity and save space, all assets are chunked and hashed:

1.  When a file is uploaded, it is broken into chunks.
2.  A `blake2b` hash of each chunk's data is calculated.
3.  The chunk is compressed and stored in the `chunks` table, indexed by its hash.

This system provides two key benefits for a permanent archive:
-   **Data Deduplication:** If multiple files contain the same chunk, it is only stored once.
-   **Verifiability:** The asset's `manifest` (a list of chunk hashes) acts as a checksum for the entire file. This allows for future integrity checks to verify that the asset data has not degraded or been tampered with at the storage level.

## 4. Frontend Architecture

The frontend is a dependency-free, single-page application (SPA) written in vanilla JavaScript (ES6+). The HTML, CSS, and JavaScript are embedded as strings within `server.py`.

-   **Pagination:** The asset list is now paginated, with the server sending one page of assets at a time. This ensures the UI remains fast and responsive even with thousands of assets, without the complexity of virtual scrolling.
-   **Backend-Driven Logic:** The frontend is designed to be a "dumb" client. It is primarily responsible for rendering the data provided by the backend. All crucial logic, such as filtering and sorting, is handled entirely by the backend to ensure consistency and performance.

## 5. Key Data Flows

### Asset Ingestion (Write Once)

1.  A file is dropped onto the UI.
2.  The frontend JavaScript reads the file and sends it in small chunks to the `/api/upload/chunk` endpoint.
3.  Once all chunks are sent, the frontend calls `/api/upload/complete`.
4.  The backend places a task in a queue to process the asset in a background thread.
5.  The `CompactVaultManager` worker processes the chunks, creates a `manifest` (the ordered list of hashes), and inserts the final, immutable asset record into the database.

### Asset Retrieval (Read Many)

1.  The user navigates to a collection, or applies a filter or sort option.
2.  The frontend requests a page of assets from `/api/collections/{id}/assets`, including any filter, sort, and pagination parameters.
3.  The backend queries the database for the requested page of assets, applying the specified filters and sorting criteria at the database level.
4.  For previews or downloads, the backend reads the asset's manifest and streams the constituent data chunks from the database in the correct order.