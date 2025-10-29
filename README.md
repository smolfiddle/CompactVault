# CompactVault

**Your personal, permanent, write-once asset archive.**

![CompactVault Screenshot](https://i.imgur.com/tOeRCV6.png)

CompactVault is a local-first asset manager designed for long-term, reliable storage. It operates on a **WORM (Write Once, Read Many)** principle, ensuring that once an asset is added to the vault, it remains unchanged. This makes it the perfect solution for developers, artists, and archivists who need to build a permanent and secure library of their digital assets.

---

## Design Philosophy: The WORM Model

CompactVault is intentionally designed as a permanent archive, not a file editor.

- **Write Once:** When you add an asset, it is committed to the vault. The system is not designed for in-place editing or deletion of assets through the UI.
- **Read Many:** Once stored, assets can be searched, viewed, and exported countless times, with the confidence that they have not been altered.

This approach guarantees the integrity of your collection, preventing accidental modification or data loss. Think of it like archiving a photo negative or burning a master to a CD-R—the goal is preservation, not modification.

## Key Features

- **Permanent WORM Storage:** Store assets with confidence, knowing they won't be accidentally altered.
- **Hierarchical Organization:** Structure your archive with Projects and nested Collections.
- **Broad Asset Support:** Handles images, video, audio, code, documents, and more.
- **Instant Previews:** Quickly view assets directly in the browser without downloading them.
- **Server-Side Search, Filter, and Sort:** Find any asset quickly with case-insensitive search, and filter and sort by various criteria, all handled efficiently on the server.
- **Pagination:** The asset list is now paginated for easier navigation of large collections.
- **Draggable Asset Links:** A context-aware link in the asset preview allows you to drag and drop assets into external applications like `mpv`.
- **Local-First Security:** Your data is stored on your local machine in a password-protected `.vault` file, ensuring it never leaves your control.
- **Manual Maintenance:** Includes a `VACUUM` option to optimize the database file size on demand.
- **Bulk Export:** Easily download entire collections or projects as a `.zip` file at any time.

## Getting Started

1.  **Run the Server:**

    ```bash
    python3 server.py
    ```

    The application will attempt to open automatically in your web browser at `http://localhost:8000`.

2.  **Select or Create a Vault:**
    - If no `.vault` files are found, you will be prompted to create one with a password.
    - If existing `.vault` files are present, you can select one and unlock it with its password.

## How to Use

- **Create a Project:** Start by creating a top-level project for your archive.
- **Build Collections:** Organize your project with nested collections.
- **Add Assets:** Drag and drop files and folders into the "Assets" panel to permanently add them to the vault.
- **Browse and Preview:** Select any asset to view its content.
- **Filter and Sort:** Use the dropdown menus to filter assets by type and sort them by name or size.
- **Navigate Pages:** Use the pagination controls at the bottom of the asset list to navigate through large collections.
- **Open in External App:** In the asset preview, drag the context-aware link (e.g., "Drag to Player") to an external application like `mpv` to open the asset directly.
- **Vacuum:** Click the "Vacuum" button in the top bar to optimize the database file size.
- **Export:** Use the "Download" buttons to export a copy of any asset, collection, or project.
