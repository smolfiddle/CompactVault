# CompactVault

**Your personal, permanent, write-once asset archive.**

![CompactVault Screenshot](https://i.imgur.com/tOeRCV6.png)

CompactVault is a local-first asset manager designed for long-term, reliable storage. It operates on a **WORM (Write Once, Read Many)** principle, ensuring that once an asset is added to the vault, it remains unchanged. This makes it the perfect solution for developers, artists, and archivists who need to build a permanent and secure library of their digital assets.

---

## Design Philosophy: The WORM Model

CompactVault is intentionally designed as a permanent archive, not a file editor.

-   **Write Once:** When you add an asset, it is committed to the vault. The system is not designed for in-place editing or deletion of assets through the UI.
-   **Read Many:** Once stored, assets can be searched, viewed, and exported countless times, with the confidence that they have not been altered.

This approach guarantees the integrity of your collection, preventing accidental modification or data loss. Think of it like archiving a photo negative or burning a master to a CD-R—the goal is preservation, not modification.

## Key Features

-   **Permanent WORM Storage:** Store assets with confidence, knowing they won't be accidentally altered.
-   **Hierarchical Organization:** Structure your archive with Projects and nested Collections.
-   **Broad Asset Support:** Handles images, video, audio, code, documents, and more.
-   **Instant Previews:** Quickly view assets directly in the browser without downloading them.
-   **Efficient Search:** Find any asset quickly with full-text search.
-   **Local-First Security:** Your data is stored on your local machine and never leaves your control. A password can be set for an extra layer of security.
-   **Bulk Export:** Easily download entire collections or projects as a `.zip` file at any time.

## Getting Started

1.  **Run the Server:**
    ```bash
    python3 server.py
    ```
    The application will attempt to open automatically in your web browser at `http://localhost:8000`.

2.  **Select or Create a Vault:**
    - If no `.vault` files are found, a new one named `default.vault` will be created.
    - If existing `.vault` files are present, you will be prompted to choose one.

3.  **Set a Password (Recommended):**
    For security, run the server with the `COMPACTVAULT_PASSWORD` environment variable.
    ```bash
    COMPACTVAULT_PASSWORD="your-secret-password" python3 server.py
    ```
    If no password is set, it defaults to `password`.

## How to Use

-   **Create a Project:** Start by creating a top-level project for your archive.
-   **Build Collections:** Organize your project with nested collections.
-   **Add Assets:** Drag and drop files and folders into the "Assets" panel to permanently add them to the vault.
-   **Browse and Preview:** Select any asset to view its content.
-   **Export:** Use the "Download" buttons to export a copy of any asset, collection, or project.
