import sqlite3
import http.server
import socketserver
import json
import webbrowser
import os
import zlib
import zipfile
import re
import hashlib
import mimetypes
from urllib.parse import urlparse, parse_qs
import logging
import signal
import sys
import socket
import pathlib
import gzip
import tempfile
import shutil
import queue
import xml.etree.ElementTree as ET
import threading
import time
import base64
import io
from collections import defaultdict
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional, Tuple, Iterator

def dynamic_chunker(file_obj, min_size=4096, max_size=1048576, sentinel=b'\x42\xFE'):
    """
    Zero-Dependency Content-Defined Chunking (CDC) using Sentinel Search.
    
    The Math:
    - Sentinel b'\\x42\\xFE' has a probability of 1/65536 in random data.
    - Expected Average Chunk Size: ~64KB.
    - Min Size: 4KB (Clamps tiny fragments).
    - Max Size: 1MB (Clamps massive blocks).
    
    Why this is better than a library:
    - Pure Python 'rolling hash' loops run at ~2MB/s.
    - This runs at disk-speed (~400MB/s+) because it leverages
      the C-optimized 'bytes.find()' method.
    """
    
    # 1. Buffer Management
    # We read in large blocks to minimize I/O calls
    buffer_size = 4 * 1024 * 1024  # 4MB Read Buffer
    buffer = b''
    
    while True:
        # Refill buffer if it's running low
        if len(buffer) < max_size:
            new_data = file_obj.read(buffer_size)
            if not new_data:
                break # End of File
            buffer += new_data
            
        # 2. The "Pointer" Logic
        # We want to cut at the Sentinel, but only AFTER min_size
        
        # Search for sentinel starting from min_size
        # This is the C-Speed optimization.
        cut_offset = buffer.find(sentinel, min_size)
        
        if cut_offset == -1:
            # Sentinel not found.
            # Check if we possess enough data to force a max_size cut
            if len(buffer) >= max_size:
                # Force cut at max_size
                yield buffer[:max_size]
                buffer = buffer[max_size:]
            else:
                # We are at the end of the stream and it's smaller than max_size
                # We need more data to decide, but if EOF is hit (loop break),
                # we yield the rest at the end.
                if not new_data: # Confirm EOF
                    yield buffer
                    buffer = b''
                    break
                continue # Go back and read more data
        
        else:
            # Sentinel FOUND.
            # The cut point is the end of the sentinel
            real_cut = cut_offset + len(sentinel)
            
            # Yield the dynamic chunk
            yield buffer[:real_cut]
            
            # Slice the buffer (Zero-copy view would be better, 
            # but slices are fast enough in modern Python)
            buffer = buffer[real_cut:]

    # Yield any remaining residue
    if buffer:
        yield buffer

class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    pass

# region Frontend Assets

# Revamped HTML template with improved accessibility and layout
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>CompactVault - Efficient Asset Manager</title>
<style>{css}</style>
</head>
<body>
<div id="root">
  <header class="topbar">
    <div class="brand">CompactVault</div>
    <div class="actions">
      <button id="vacuum-btn" class="small">Vacuum</button>
      <button id="theme-toggle" class="small" aria-label="Toggle theme">🌓</button>
    </div>
  </header>

  <main class="main-grid">
    <aside class="col projects" role="region" aria-label="Projects">
      <div class="col-head">
        <span>Projects</span>
        <button id="add-project" class="small" aria-label="Add project">+</button>
      </div>
      <ul id="projects-list" class="list sortable" role="list"></ul>
    </aside>

    <aside class="col collections" role="region" aria-label="Collections">
      <div class="col-head">
        <span>Collections</span>
        <button id="add-collection" class="small" disabled aria-label="Add collection">+</button>
      </div>
      <ul id="collections-list" class="list sortable" role="list"></ul>
    </aside>

    <section class="col assets" role="region" aria-label="Assets">
      <div class="col-head">
        <span>Assets</span>
        <span id="asset-count"></span>
      </div>
      <div id="assets-controls" class="controls">
        <button id="upload-files" class="small" aria-label="Upload files">Upload</button>
        <input id="search-assets" placeholder="Search assets..." class="small">
        <select id="filter-by-type" class="small" aria-label="Filter by type">
          <option value="">All Types</option>
        </select>
        <select id="sort-assets" class="small" aria-label="Sort by">
          <option value="filename_asc">Name (A-Z)</option>
          <option value="filename_desc">Name (Z-A)</option>
          <option value="size_desc">Size (Largest)</option>
          <option value="size_asc">Size (Smallest)</option>
        </select>
      </div>
      <ul id="assets-list" class="list sortable" role="list"></ul>
      <div id="assets-pagination" class="pagination-controls"></div>
    </section>

    <section class="col preview" role="region" aria-label="Preview">
      <div class="col-head">
        <span>Preview</span>
      </div>
      <div id="preview-area" class="preview-area">
        <div id="preview-empty">Select an asset to preview</div>
      </div>
    </section>
  </main>

  <div id="toast" class="toast hidden" role="alert"></div>
  <input id="file-input" type="file" multiple style="display:none" accept=".png,.jpg,.jpeg,.gif,.svg,.webp,.mp3,.wav,.ogg,.m4a,.flac,.mp4,.mov,.webm,.mkv,.avi,.flv,.gltf,.glb,.epub,.pdf,.zip,.rar,.7z" />
  <div id="progress-container" class="progress-container hidden">
    <p>Uploading...</p>
    <div class="progress-bar">
      <div id="progress-bar-inner" class="progress-bar-inner"></div>
    </div>
  </div>
</div>

<script>{js}</script>
</body>
</html>
'''

# Revamped CSS with better theming, responsiveness, and optimizations
CSS_STYLES = '''
:root {
  --font: system-ui, -apple-system, sans-serif;
  --radius: 6px;
  --gap: 12px;

  --bg-dark: #1a1a1a;
  --bg-med: #2a2a2a;
  --bg-light: #3a3a3a;
  --fg-dark: #999;
  --fg-med: #ccc;
  --fg-light: #fff;

  --accent: #0095ff;
  --danger: #ff4d4d;
  --success: #52c41a;

  --border-color: #444;
  --border: 1px solid var(--border-color);
  --shadow: 0 2px 8px rgba(0,0,0,0.3);
}
body {
  font-family: var(--font);
  margin: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-dark);
  color: var(--fg-med);
  font-size: 14px;
}
.topbar {
  height: 50px;
  display: flex;
  align-items: center;
  padding: 0 var(--gap);
  gap: var(--gap);
  background: var(--bg-med);
  border-bottom: var(--border);
}
.brand {
  font-weight: 600;
  font-size: 18px;
  color: var(--accent);
}
input, select {
  padding: 8px 10px;
  border-radius: var(--radius);
  background: var(--bg-dark);
  border: 1px solid var(--border-color);
  color: inherit;
  transition: background 0.2s, border-color 0.2s;
}
input:focus, select:focus {
  background: #000;
  border-color: var(--accent);
  outline: none;
}
input.small, select.small {
  width: auto;
  flex: 1;
}
.main-grid {
  display: grid;
  grid-template-columns: 240px 240px 1fr 1.5fr;
  gap: var(--gap);
  padding: var(--gap);
  flex: 1;
  overflow: hidden;
}
@media (max-width: 1200px) {
  .main-grid {
    grid-template-columns: 1fr 1fr;
  }
  .projects, .collections {
    grid-column: 1 / 3;
  }
  .assets {
    grid-column: 1 / 2;
  }
  .preview {
    grid-column: 2 / 3;
  }
}
@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
  .projects, .collections, .assets, .preview {
    grid-column: 1 / 2;
  }
}
.col {
  background: var(--bg-med);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--gap);
  height: 40px;
  font-weight: 600;
  font-size: 15px;
  border-bottom: var(--border);
  color: var(--fg-light);
}
.small {
  padding: 4px 8px;
  border-radius: var(--radius);
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--fg-med);
  cursor: pointer;
  transition: all 0.2s;
}
.small:hover {
  background: var(--bg-light);
  color: var(--fg-light);
  border-color: #555;
}
.small:active {
  transform: scale(0.95);
}
.danger {
  color: var(--danger);
  border-color: var(--danger);
}
.list {
  overflow: auto;
  flex: 1;
  list-style: none;
  padding: 8px;
  margin: 0;
  height: 100%;
}
.item {
  min-height: 50px;
  height: auto;
  padding: 8px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.item:hover {
  background: var(--bg-light);
}
.item.selected {
  background: var(--accent);
  color: #fff;
  font-weight: 500;
}
.item.has-children > button {
  margin-right: 6px;
  padding: 0 6px;
  background: none;
  border: none;
  color: var(--fg-dark);
  transition: transform 0.2s;
}
.item.expanded > button {
  transform: rotate(90deg);
}
.item > ul {
  display: none;
  list-style: none;
  padding-left: 20px;
  margin-top: 8px;
}
.item.expanded > ul {
  display: block;
}
.controls {
  display: flex;
  gap: 8px;
  padding: 0 var(--gap) 8px;
  border-bottom: var(--border);
}
.preview-area {
  overflow: auto;
  flex: 1;
  padding: var(--gap);
  background: var(--bg-dark);
  border-radius: var(--radius);
}
.preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--fg-dark);
  font-style: italic;
}
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gap);
  padding-bottom: var(--gap);
  border-bottom: var(--border);
}
.preview-header strong {
  color: var(--fg-light);
  font-size: 16px;
}
.preview-surface {
  background: var(--bg-med);
  border-radius: var(--radius);
  padding: var(--gap);
  overflow: auto;
}
.btn {
  padding: 8px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--border-color);
  background: var(--bg-light);
  color: var(--fg-light);
  cursor: pointer;
  transition: all 0.2s;
}
.btn:hover {
  background: #444;
  border-color: #666;
}
.btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.btn.primary:hover {
  background: #007acc;
  border-color: #007acc;
}
.btn.danger {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
}
.btn.danger:hover {
  background: #cc0000;
  border-color: #cc0000;
}
.toast {
  position: fixed;
  right: 20px;
  bottom: 20px;
  padding: 12px 18px;
  border-radius: var(--radius);
  background: var(--bg-light);
  color: var(--fg-light);
  box-shadow: var(--shadow);
  transition: opacity 0.3s, transform 0.3s;
  transform: translateY(20px);
  opacity: 0;
}
.toast:not(.hidden) {
  transform: translateY(0);
  opacity: 1;
}
.toast.hidden {
  display: block; /* Keep it in layout for transition */
}
pre.code {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: var(--radius);
  overflow: auto;
  font-family: 'Fira Code', monospace;
}
pre.code .keyword { color: #ff79c6; }
pre.code .string { color: #50fa7b; }
pre.code .number { color: #bd93f9; }
pre.code .comment { color: #abb2bf; }
.hidden {
  display: none;
}
.progress-container {
  position: fixed;
  bottom: 20px;
  left: 20px;
  width: 320px;
  background: var(--bg-light);
  color: var(--fg-light);
  border-radius: var(--radius);
  padding: 12px 16px;
  box-shadow: var(--shadow);
  transition: opacity 0.3s, transform 0.3s;
  z-index: 1001;
  transform: translateY(20px);
  opacity: 0;
}
.progress-container:not(.hidden) {
  transform: translateY(0);
  opacity: 1;
}
.progress-bar {
  width: 100%;
  background: var(--bg-dark);
  border-radius: var(--radius);
  height: 8px;
  margin-top: 8px;
  overflow: hidden;
}
body.light {
  --bg-dark: #f0f2f5;
  --bg-med: #ffffff;
  --bg-light: #f0f2f5;
  --fg-dark: #666;
  --fg-med: #333;
  --fg-light: #000;
  --border-color: #e0e0e0;
}

.progress-bar-inner {
  width: 0%;
  height: 100%;
  background: var(--accent);
  border-radius: var(--radius);
  transition: width 0.2s ease-in-out;
}
.item-main {
  display: flex;
  flex-direction: column;
  justify-content: center;
  flex-grow: 1;
  word-break: break-word;
  min-width: 0;
}
.item-name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-details {
  font-size: 12px;
  opacity: 0.7;
}
.item-size {
  font-size: 12px;
  opacity: 0.7;
  margin-left: 12px;
  flex-shrink: 0;
}
.pagination-controls {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px;
  border-top: var(--border);
}
.pagination-controls button {
  margin: 0 4px;
  padding: 4px 8px;
  border-radius: var(--radius);
  background: var(--bg-light);
  border: 1px solid var(--border-color);
  color: var(--fg-med);
  cursor: pointer;
}
.pagination-controls button:hover {
  background: #444;
}
.pagination-controls button.current {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.pagination-controls button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
'''

# Revamped JavaScript with better structure, error handling, and features
JAVASCRIPT_CODE = r'''
document.addEventListener('DOMContentLoaded', () => {

  const Progress = {
    show(msg) {
      const container = el('progress-container');
      if (container) {
        container.querySelector('p').textContent = msg;
        container.classList.remove('hidden');
      }
    },
    update(val) {
      const bar = el('progress-bar-inner');
      if (bar) {
        bar.style.width = `${val}%`;
      }
    },
    hide() {
      const container = el('progress-container');
      if (container) {
        container.classList.add('hidden');
      }
    }
  };

  // API helper with error handling
  const api = async (path, opts = {}) => {
    try {
      const r = await fetch("/api" + path, opts);
      if (!r.ok) {
        const err = await r.json().catch(() => ({message: r.statusText}));
        throw new Error(err.message);
      }
      const ct = r.headers.get("Content-Type") || "";
      if (ct.includes("application/json")) return r.json();
      if (ct.includes("application/zip")) return r.blob();
      return r.blob ? r.blob() : r.text();
    } catch (e) {
      throw e;
    }
  };

  // State
  let state = {
    projects: [],
    collections: [],
    collectionsTree: [],
    assets: [],
    limit: 50,
    total: 0,
    page: 1,
    searchQuery: '',
    filterByType: '',
    sortBy: 'filename',
    sortOrder: 'asc',
    selection: {project: null, collection: null, assets: new Set(), last: null},
    projectName: '',
    collectionName: ''
  };

  // DOM shortcut
  const el = id => document.getElementById(id);

  // Toast
  const toast = (txt, type = 'info') => {
    const t = el("toast");
    t.textContent = txt;
    t.className = `toast ${type}`;
    t.classList.remove("hidden");
    setTimeout(() => t.classList.add("hidden"), 3000);
  };

  function downloadAsset(url, filename) {
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  // Load projects
  async function loadProjects() {
    try {
      state.projects = await api("/projects");
      const root = el("projects-list");
      root.innerHTML = "";
      state.projects.forEach(p => {
        const li = document.createElement("li");
        li.className = "item";
        li.role = "listitem";
        li.dataset.id = p.id;

        const nameSpan = document.createElement('span');
        nameSpan.textContent = `${p.name} (${p.type})`;
        li.appendChild(nameSpan);

        const downloadBtn = document.createElement("button");
        downloadBtn.className = "small";
        downloadBtn.textContent = "Download";
        downloadBtn.onclick = (ev) => {
            ev.stopPropagation();
            downloadAsset(`/api/projects/${p.id}/download`, `${p.name}.zip`);
        };
        li.appendChild(downloadBtn);

        li.onclick = () => selectProject(p.id, li, p.name);
        root.appendChild(li);
      });
      if (state.projects.length > 0) {
        const firstProjectLi = root.querySelector('.item');
        if (firstProjectLi) {
            selectProject(state.projects[0].id, firstProjectLi, state.projects[0].name);
        }
      }
    } catch (e) {
      toast(`Error loading projects: ${e.message}`, 'error');
    }
  }

  // Select project
  async function selectProject(id, elItem, name) {
    state.selection.project = id;
    state.projectName = name;
    document.querySelectorAll("#projects-list .item").forEach(i => i.classList.remove("selected"));
    elItem.classList.add("selected");
    el("add-collection").disabled = false;
    clearAssets();
    await loadCollections(id);
  }

  // Build collection tree
  function buildCollectionTree(cs, parent_id = null) {
    return cs.filter(c => c.parent_id === parent_id).map(c => ({
      ...c,
      children: buildCollectionTree(cs, c.id)
    }));
  }

  // Render collection
  function renderCollection(item, ul) {
    const li = document.createElement("li");
    li.className = "item";
    li.role = "listitem";
    li.dataset.id = item.id;

    const nameSpan = document.createElement('span');
    nameSpan.textContent = `${item.name} (${item.type})`;
    li.appendChild(nameSpan);

    const downloadBtn = document.createElement("button");
    downloadBtn.className = "small";
    downloadBtn.textContent = "Download";
    downloadBtn.onclick = (ev) => {
        ev.stopPropagation();
        downloadAsset(`/api/collections/${item.id}/download`, `${item.name}.zip`);
    };
    li.appendChild(downloadBtn);

    li.onclick = (ev) => {
      ev.stopPropagation();
      selectCollection(item.id, li, item.name);
    };
    if (item.children.length) {
      li.classList.add("has-children");
      const toggle = document.createElement("button");
      toggle.className = "small";
      toggle.textContent = "▶";
      toggle.onclick = (ev) => {
        ev.stopPropagation();
        li.classList.toggle("expanded");
        toggle.textContent = li.classList.contains("expanded") ? "▼" : "▶";
      };
      li.prepend(toggle);
      const subUl = document.createElement("ul");
      subUl.role = "list";
      item.children.forEach(child => renderCollection(child, subUl));
      li.appendChild(subUl);
    }
    ul.appendChild(li);
  }

  // Load collections
  async function loadCollections(project_id) {
    const root = el("collections-list");
    root.innerHTML = "";
    try {
      const cs = await api(`/projects/${project_id}/collections`);
      state.collections = cs;
      state.collectionsTree = buildCollectionTree(cs);
      state.collectionsTree.forEach(item => renderCollection(item, root));
      if (state.collections.length > 0) {
        const firstCollectionLi = root.querySelector('.item');
        if (firstCollectionLi) {
            const firstCollectionId = firstCollectionLi.dataset.id;
            const firstCollection = state.collections.find(c => c.id == firstCollectionId);
            if(firstCollection) {
                selectCollection(firstCollection.id, firstCollectionLi, firstCollection.name);
            }
        }
      }
    } catch (e) {
      toast(`Error loading collections: ${e.message}`, 'error');
    }
  }

  // Select collection
  async function selectCollection(id, elItem, name) {
    state.selection.collection = id;
    state.collectionName = name;
    document.querySelectorAll("#collections-list .item").forEach(i => i.classList.remove("selected"));
    elItem.classList.add("selected");
    await loadAssets(id, 1);
  }

  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  function renderAssets() {
    const container = el("assets-list");
    container.innerHTML = state.assets.map(a => {
      const isSelected = state.selection.assets.has(a.id.toString());
      return `
      <li class="item ${isSelected ? 'selected' : ''}" role="listitem" data-id="${a.id}">
        <div class="item-main">
          <div class="item-name">${a.filename}</div>
          <div class="item-details">${a.type}/${a.format}</div>
        </div>
        <div class="item-size">${(a.size_original / 1024).toFixed(1)} KB</div>
      </li>
    `}).join('');
    el("asset-count").textContent = `(${state.assets.length} of ${state.total})`;
  }

  function renderPagination() {
    const container = el("assets-pagination");
    const totalPages = Math.ceil(state.total / state.limit);
    if (totalPages <= 1) {
      container.innerHTML = '';
      return;
    }

    let html = '';
    for (let i = 1; i <= totalPages; i++) {
      html += `<button class="${i === state.page ? 'current' : ''}" onclick="changePage(${i})">${i}</button>`;
    }
    container.innerHTML = html;
  }

  window.changePage = (page) => {
    if (page !== state.page) {
      loadAssets(state.selection.collection, page);
    }
  }

  function applyFiltersAndSorting() {
    const filter = el("filter-by-type").value;
    const sort = el("sort-assets").value.split('_');
    state.filterByType = filter;
    state.sortBy = sort[0];
    state.sortOrder = sort[1];
    loadAssets(state.selection.collection, 1);
  }

  async function loadAssets(collection_id, page = 1) {
    try {
      state.page = page;
      const offset = (page - 1) * state.limit;
      let path = `/collections/${collection_id}/assets?offset=${offset}&limit=${state.limit}`;
      if (state.searchQuery) {
        path += `&query=${encodeURIComponent(state.searchQuery)}`;
      }
      if (state.filterByType) {
        path += `&filter_by_type=${state.filterByType}`;
      }
      path += `&sort_by=${state.sortBy}&sort_order=${state.sortOrder}`;

      const res = await api(path);
      state.assets = res.assets;
      state.total = res.total;

      const filterDropdown = el("filter-by-type");
      if (filterDropdown.options.length <= 1) { // Populate only once
        const allFormats = [...new Set(res.all_formats || [])].sort();
        allFormats.forEach(f => {
          const opt = document.createElement("option");
          opt.value = opt.textContent = f;
          filterDropdown.appendChild(opt);
        });
      }

      renderAssets();
      renderPagination();
      return res;
    } catch (e) {
      toast(`Error loading assets: ${e.message}`, 'error');
      throw e;
    }
  }

  // Clear assets
  function clearAssets() {
    state.assets = [];
    state.selection.collection = null;
    el("assets-list").innerHTML = "";
    el("assets-pagination").innerHTML = "";
    clearPreview();
    el("asset-count").textContent = "";
  }

  // Asset click handler
  function onAssetClick(asset, domNode, ev) {
    const id = asset.id.toString();
    const ctrl = ev.ctrlKey || ev.metaKey;
    const shift = ev.shiftKey;

    if (!ctrl && !shift) {
      state.selection.assets.clear();
      state.selection.assets.add(id);
      state.selection.last = id;
    } else if (ctrl) {
      if (state.selection.assets.has(id)) {
        state.selection.assets.delete(id);
      } else {
        state.selection.assets.add(id);
      }
      state.selection.last = id;
    } else if (shift && state.selection.last) {
      const ids = state.assets.map(a => a.id.toString());
      const start = ids.indexOf(state.selection.last);
      const end = ids.indexOf(id);
      if (start !== -1 && end !== -1) {
        const [s, e] = start < end ? [start, end] : [end, start];
        for (let i = s; i <= e; i++) state.selection.assets.add(ids[i]);
      }
    }

    // Visually update selection
    const items = [...el("assets-list").querySelectorAll(".item")];
    items.forEach(it => it.classList.toggle("selected", state.selection.assets.has(it.dataset.id)));

    if (state.selection.assets.size === 1) {
      const singleId = [...state.selection.assets][0];
      loadPreview(singleId);
    } else if (state.selection.assets.size > 1) {
      showBulkActions();
    } else {
      clearPreview();
    }
  }

  function showBulkActions() {
    const area = el("preview-area");
    area.innerHTML = '';
    const header = document.createElement("div");
    header.className = "preview-header";
    header.innerHTML = `<strong>Selected ${state.selection.assets.size} assets</strong>`;
    const btns = document.createElement("div");
    const down = document.createElement("button");
    down.className = "btn";
    down.textContent = "Download selected";
    down.onclick = () => downloadBulk([...state.selection.assets]);
    btns.appendChild(down);
    header.appendChild(btns);
    area.appendChild(header);
  }

  async function downloadBulk(ids) {
    try {
      const blob = await api(`/collections/${state.selection.collection}/assets/download`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids})
      });
      const url = URL.createObjectURL(blob);
      downloadAsset(url, "selected_assets.zip");
      URL.revokeObjectURL(url);
      toast("Download started", 'success');
    } catch (e) {
      toast(`Download failed: ${e.message}`, 'error');
    }
  }

  // Clear preview
  function clearPreview() {
    el("preview-area").innerHTML = '<div class="preview-empty">Select asset</div>';
  }

  // Load preview
  async function loadPreview(asset_id) {
    try {
      const res = await api(`/assets/${asset_id}/preview`);
      const area = el("preview-area");
      area.innerHTML = "";
      const header = document.createElement("div");
      header.className = "preview-header";
      header.innerHTML = `<strong>${res.filename}</strong> <small>${res.type}/${res.format} - ${(res.size_original / 1024).toFixed(1)} KB</small>`;
      const btns = document.createElement("div");
      const down = document.createElement("button");
      down.className = "btn";
      down.textContent = "Download";
      down.onclick = () => downloadAsset(`/api/assets/${asset_id}`, res.filename);
      btns.appendChild(down);

      const dragLink = document.createElement("a");
      dragLink.className = "btn";
      dragLink.href = `/api/assets/${asset_id}`;
      if (res.type === "video" || res.type === "audio") {
        dragLink.textContent = "Drag to Player";
      } else if (res.type === "image") {
        dragLink.textContent = "View Image";
      } else if (res.type === "text") {
        dragLink.textContent = "View Raw";
      } else {
        dragLink.textContent = "Download Link";
      }
      dragLink.draggable = true;
      btns.appendChild(dragLink);
      header.appendChild(btns);
      area.appendChild(header);
      const surface = document.createElement("div");
      surface.className = "preview-surface";
      if (res.type === "text") {
        const pre = document.createElement("pre");
        pre.className = "code";
        pre.innerHTML = highlight(res.content || "", res.format);
        surface.appendChild(pre);
      } else if (res.type === "image") {
        const img = document.createElement("img");
        img.style.maxWidth = "100%";
        img.src = `/api/assets/${asset_id}`;
        img.alt = res.filename;
        surface.appendChild(img);
      } else if (res.type === "audio") {
        const a = document.createElement("audio");
        a.controls = true;
        a.src = `/api/assets/${asset_id}`;
        a.title = res.filename;
        surface.appendChild(a);
      } else if (res.type === "video") {
        const v = document.createElement("video");
        v.controls = true;
        v.style.maxWidth = "100%";
        v.src = `/api/assets/${asset_id}`;
        v.title = res.filename;
        surface.appendChild(v);
      } else {
        surface.textContent = "Preview not available. Download to view.";
      }
      area.appendChild(surface);
    } catch (e) {
      toast(`Preview error: ${e.message}`, 'error');
    }
  }

  // Improved syntax highlighting
  function highlight(text, format) {
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    text = text.replace(/\b(if|else|for|while|def|class|function|var|let|const|return|async|await)\b/g, '<span class="keyword">$1</span>');
    text = text.replace(/"(.*?)"/g, '<span class="string">"$1"</span>');
    text = text.replace(/\'(.*?)\'/g, `<span class=\"string\">\'$1\'</span>`);
    text = text.replace(/\b(\d+\.?\d*)\b/g, '<span class="number">$1</span>');
    text = text.replace(/#(.*)$/gm, '<span class="comment">#$1</span>');
    text = text.replace(/\/\/(.*)$/gm, '<span class="comment">//$1</span>');
    text = text.replace(/\/\*(.*?)\*\//gs, '<span class="comment">/*$1*/</span>');
    return text;
  }

  // Upload file in chunks
  async function uploadFileInChunks(file, collection_id, path_prefix = '', on_progress) {
    const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
    const upload_id = 'uid-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    const total_chunks = Math.ceil(file.size / CHUNK_SIZE);

    for (let i = 0; i < total_chunks; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);

      const url = `/api/upload/chunk?upload_id=${upload_id}&chunk_index=${i}`;

      const response = await fetch(url, {
        method: 'POST',
        body: chunk,
        headers: {
          'Content-Type': 'application/octet-stream'
        }
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({message: response.statusText}));
        throw new Error(`Upload failed for chunk ${i} of ${file.name}: ${err.message}`);
      }
      if (on_progress) on_progress(chunk.size);
    }

    // All chunks uploaded, now send complete request
    const r = await fetch('/api/upload/complete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        upload_id: upload_id,
        filename: file.name,
        collection_id: collection_id,
        path_prefix: path_prefix
      })
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({message: r.statusText}));
      throw new Error(`Failed to complete upload for ${file.name}: ${err.message}`);
    }
  }

  async function uploadFiles(items) {
    if (!state.selection.collection) {
      toast("Select a collection first", 'error');
      return;
    }

    const filesToUpload = [];

    async function getFilesFromEntry(entry, path = '') {
      if (!entry) {
        return [];
      }
      if (!entry) {
        return [];
      }
      if (entry.isFile) {
        return new Promise(resolve => {
          entry.file(f => resolve([{ file: f, path: path }]));
        });
      }
      if (entry.isDirectory) {
        const reader = entry.createReader();
        const entries = await new Promise(resolve => reader.readEntries(resolve));
        let files = [];
        for (const subEntry of entries) {
          files.push(...await getFilesFromEntry(subEntry, path + entry.name + '/'));
        }
        return files;
      }
      return [];
    }

    const droppedItems = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.webkitGetAsEntry) {
        droppedItems.push(item.webkitGetAsEntry());
      } else if (item instanceof File) {
        // For files from an input or individual dropped files, use webkitRelativePath if available
        const path = item.webkitRelativePath ? item.webkitRelativePath.substring(0, item.webkitRelativePath.lastIndexOf('/') + 1) : '';
        filesToUpload.push({ file: item, path: path });
      }
    }

    for (const entry of droppedItems) {
      filesToUpload.push(...await getFilesFromEntry(entry));
    }

    if (filesToUpload.length === 0) return;

    try {
      let total_size = filesToUpload.reduce((acc, f) => acc + f.file.size, 0);
      let uploaded_size = 0;

      Progress.show(`Uploading ${filesToUpload.length} files...`);
      Progress.update(0);

      const update_progress = (chunk_size) => {
        uploaded_size += chunk_size;
        Progress.update((uploaded_size / total_size) * 100);
      };

      const concurrency = 8;
      const promises = new Set();
      for (const { file, path } of filesToUpload) {
        const promise = uploadFileInChunks(file, state.selection.collection, path, update_progress);
        promises.add(promise);
        promise.then(() => promises.delete(promise));
        if (promises.size >= concurrency) {
          await Promise.race(promises);
        }
      }
      await Promise.all(promises);

    } catch (e) {
      toast(e.message, 'error');
    } finally {
      Progress.hide();
      toast('Uploads accepted, processing in background...', 'info');

      // Poll for changes
      let attempts = 0;
      const maxAttempts = 60;
      const interval = 2000; // 2 seconds

      const poll = setInterval(async () => {
        attempts++;
        try {
            if (!state.selection.collection) {
                clearInterval(poll);
                return;
            }
            const newAssets = await loadAssets(state.selection.collection);
            if (newAssets.assets.length > state.assets.length || attempts > maxAttempts) {
                clearInterval(poll);
            }
        } catch (e) {
            clearInterval(poll);
        }
      }, interval);
    }
  }

  // Event listeners
  el("file-input").onchange = ev => uploadFiles(Array.from(ev.target.files));

  el("upload-files").onclick = () => {
    if (!state.selection.collection) {
      toast("Select a collection first", 'error');
      return;
    }
    el("file-input").click();
  };

  const assetsCol = document.querySelector('.assets');
  assetsCol.addEventListener('dragover', ev => ev.preventDefault());
  assetsCol.addEventListener('drop', ev => {
    ev.preventDefault();
    uploadFiles(ev.dataTransfer.items);
  });

  el("add-project").onclick = () => createProject();

  el("add-collection").onclick = () => createCollection();

  el("vacuum-btn").onclick = async () => {
    try {
      toast("Vacuuming database...", "info");
      await api("/maintenance/vacuum", { method: "POST" });
      toast("Database vacuumed successfully!", "success");
    } catch (e) {
      toast(`Vacuum failed: ${e.message}`, "error");
    }
  };


  async function createProject() {
    const name = prompt("Project name");
    if (!name) return;
    try {
      const newProject = await api("/projects", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name: name, type: 'project'})
      });
      toast("Project created", 'success');
      loadProjects();
    } catch (e) {
      toast(`Create failed: ${e.message}`, 'error');
    }
  }

  async function createCollection(name, type = 'collection', parent_id = null) {
    if (!state.selection.project) {
        toast("Select a project first", 'error');
        return null;
    }
    const n = name || prompt("Collection name");
    if (!n) return null;
    const t = type || prompt("Type", "collection") || "collection";
    try {
      const newCollection = await api("/collections", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({project_id: state.selection.project, name: n, type: t, parent_id: parent_id})
      });
      toast("Collection created", 'success');
      loadCollections(state.selection.project);
      return newCollection.id;
    } catch (e) {
      toast(`Create failed: ${e.message}`, 'error');
      return null;
    }
  }

  el("add-collection").onclick = () => createCollection();

  el('search-assets').addEventListener('input', debounce(() => {
    state.searchQuery = el('search-assets').value;
    applyFiltersAndSorting();
  }, 300));

  el('filter-by-type').onchange = applyFiltersAndSorting;
  el('sort-assets').onchange = applyFiltersAndSorting;

  // Init
  loadProjects();

  el("assets-list").addEventListener('click', e => {
    const item = e.target.closest('.item');
    if (item) {
        const assetId = item.dataset.id;
        const asset = state.assets.find(a => a.id.toString() === assetId);
        if (asset) {
            onAssetClick(asset, item, e);
        }
    }
  });

  // Theme toggle
  const themeToggle = el('theme-toggle');
  const body = document.body;

  const savedTheme = localStorage.getItem('theme');
  if (savedTheme) {
    body.classList.add(savedTheme);
  }

  themeToggle.addEventListener('click', () => {
    if (body.classList.contains('light')) {
      body.classList.remove('light');
      localStorage.removeItem('theme');
    } else {
      body.classList.add('light');
      localStorage.setItem('theme', 'light');
    }
  });
});
'''

# endregion

UPLOAD_TEMP_DIR = 'upload_temp'
if os.path.exists(UPLOAD_TEMP_DIR):
    shutil.rmtree(UPLOAD_TEMP_DIR)
os.makedirs(UPLOAD_TEMP_DIR, exist_ok=True)

DEFAULT_DB = "default.vault"


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# region CompactVaultManager

def natural_sort_key(s):
    """
    A key for natural sorting. Splits the string into text and number parts.
    e.g. 'file10.txt' -> ['file', 10, '.txt']
    """
    if not isinstance(s, str):
        return [s]
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'([0-9]+)', s)]


class CompactVaultManager:
    def __init__(self, db_path: str = DEFAULT_DB) -> None:
        self.db_path = pathlib.Path(db_path)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA busy_timeout = 5000;")
        self.conn.execute("PRAGMA cache_size = -64000;")
        self.conn.execute("PRAGMA temp_store = MEMORY;")
        self.conn.commit()
        self.create_database_schema()
        self._ensure_schema_extensions()

        # Asset creation queue and worker
        self.asset_creation_queue: queue.Queue[Optional[Tuple[int, List[str], str]]] = queue.Queue()
        num_workers = os.cpu_count() or 4
        self.workers: List[threading.Thread] = []
        for _ in range(num_workers):
            t = threading.Thread(target=self._process_asset_creation_queue, daemon=True)
            t.start()
            self.workers.append(t)

    def create_database_schema(self) -> None:
        queries = [
            'CREATE TABLE IF NOT EXISTS vault_properties (key TEXT PRIMARY KEY, value TEXT);',
            'CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL, description TEXT, order_index INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP );',
            'CREATE TABLE IF NOT EXISTS collections (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), parent_id INTEGER REFERENCES collections(id), name TEXT, type TEXT, order_index INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP );',
            'CREATE TABLE IF NOT EXISTS assets (id INTEGER PRIMARY KEY, collection_id INTEGER REFERENCES collections(id), type TEXT NOT NULL, format TEXT, manifest TEXT, order_index INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP );',
            'CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY, asset_id INTEGER REFERENCES assets(id), key TEXT NOT NULL, value TEXT );',
            'CREATE INDEX IF NOT EXISTS idx_metadata_asset ON metadata(asset_id);',
            'CREATE INDEX IF NOT EXISTS idx_metadata_key ON metadata(key);',
            'CREATE INDEX IF NOT EXISTS idx_metadata_asset_key ON metadata(asset_id, key);',
            'CREATE INDEX IF NOT EXISTS idx_metadata_value ON metadata(value);',
            'CREATE INDEX IF NOT EXISTS idx_collections_project ON collections(project_id);',
            'CREATE INDEX IF NOT EXISTS idx_collections_parent ON collections(parent_id);',
            'CREATE INDEX IF NOT EXISTS idx_assets_collection ON assets(collection_id);',
            'CREATE TABLE IF NOT EXISTS chunks (hash TEXT PRIMARY KEY, data BLOB );'

        ]
        with self.lock:
            for q in queries:
                try:
                    self.conn.execute(q)
                except sqlite3.Error as e:
                    logging.error(f"Schema error: {e}")
            self.conn.commit()

    def _ensure_schema_extensions(self) -> None:
        with self.lock:
            c = self.conn.cursor()
            try:
                c.execute("PRAGMA table_info(assets)")
                cols = [r['name'] for r in c.fetchall()]
                if 'data' in cols: self._migrate_to_chunked_storage(c)
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = set(r[0] for r in c.fetchall())
                if 'chunks' not in tables:
                    c.execute('CREATE TABLE IF NOT EXISTS chunks (hash TEXT PRIMARY KEY, data BLOB );')
                for table, col, typ in [
                    ('projects', 'order_index', 'INTEGER'),
                    ('assets', 'order_index', 'INTEGER'),
                    ('collections', 'parent_id', 'INTEGER REFERENCES collections(id)')
                ]:
                    c.execute(f"PRAGMA table_info({table})")
                    if col not in [r['name'] for r in c.fetchall()]:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                self.conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Extension error: {e}")

    def set_password(self, password: str) -> None:
        """Hashes and stores the vault password."""
        with self.lock:
            salt = os.urandom(16)
            pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            self.conn.execute("INSERT OR REPLACE INTO vault_properties (key, value) VALUES (?, ?)", ('password_salt', salt.hex()))
            self.conn.execute("INSERT OR REPLACE INTO vault_properties (key, value) VALUES (?, ?)", ('password_hash', pw_hash.hex()))
            self.conn.commit()

    def check_password(self, password: str) -> bool:
        """Checks if the provided password is correct."""
        with self.lock:
            try:
                cur = self.conn.cursor()
                cur.execute("SELECT value FROM vault_properties WHERE key = 'password_salt'")
                salt_row = cur.fetchone()
                cur.execute("SELECT value FROM vault_properties WHERE key = 'password_hash'")
                hash_row = cur.fetchone()

                if not salt_row or not hash_row:
                    # If no password is set, allow access (for initial setup)
                    return True

                salt = bytes.fromhex(salt_row[0])
                stored_hash = bytes.fromhex(hash_row[0])
                
                new_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
                
                return new_hash == stored_hash
            except (sqlite3.Error, ValueError) as e:
                logging.error(f"Password check error: {e}")
                return False

    def _migrate_to_chunked_storage(self, cursor: sqlite3.Cursor) -> None:
        with self.lock:
            try:
                c = cursor
                c.execute("CREATE TABLE assets_new (id INTEGER PRIMARY KEY, collection_id INTEGER REFERENCES collections(id), type TEXT NOT NULL, format TEXT, manifest TEXT, order_index INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
                c.execute("CREATE TABLE IF NOT EXISTS chunks (hash TEXT PRIMARY KEY, data BLOB)")

                # Add columns if they don't exist
                c.execute("PRAGMA table_info(assets_new)")
                cols = [r['name'] for r in c.fetchall()]
                if 'order_index' not in cols:
                    c.execute("ALTER TABLE assets_new ADD COLUMN order_index INTEGER")

                for asset in c.execute("SELECT * FROM assets").fetchall():
                    data = zlib.decompress(asset['data']) if asset.get('compression') == 'zlib' else asset['data']
                    
                    manifest: Dict[str, Any] = {'chain': [], 'total_size': 0, 'filename': f"asset_{asset['id']}"}
                    previous_block_hash: Optional[str] = None
                    
                    data_stream = io.BytesIO(data)
                    for chunk_data in dynamic_chunker(data_stream):
                        chunk_size = len(chunk_data)
                        chunk_hash = hashlib.blake2b(chunk_data).hexdigest()
                        compressed = zlib.compress(chunk_data, level=9)
                        
                        c.execute("INSERT OR IGNORE INTO chunks (hash, data) VALUES (?, ?)", (chunk_hash, compressed))
                        
                        block = {
                            'chunk_hash': chunk_hash,
                            'size': chunk_size,
                            'previous_hash': previous_block_hash
                        }
                        block_str = json.dumps(block, sort_keys=True)
                        block_hash = hashlib.blake2b(block_str.encode()).hexdigest()

                        manifest['chain'].append(block)
                        manifest['total_size'] += chunk_size
                        previous_block_hash = block_hash

                    manifest_str = json.dumps(manifest)
                    c.execute("INSERT INTO assets_new (id, collection_id, type, format, manifest, created_at) VALUES (?, ?, ?, ?, ?, ?)", (asset['id'], asset['collection_id'], asset['type'], asset['format'], manifest_str, asset['created_at']))
                
                c.execute("DROP TABLE assets")
                c.execute("ALTER TABLE assets_new RENAME TO assets")
                self.conn.commit()
                logging.info("Database migrated to chunked storage.")
            except sqlite3.Error as e:
                logging.error(f"Migration error: {e}")
                self.conn.rollback()

    def _process_asset_creation_queue(self) -> None:
        while True:
            try:
                task = self.asset_creation_queue.get()
                if task is None:
                    break  # Sentinel value to stop the worker
                collection_id, chunk_paths, filename = task
                self.create_asset_from_chunks(collection_id, chunk_paths, filename)
            except Exception as e:
                logging.error(f"Error in asset creation worker: {e}")

    def create_asset_from_chunks(self, collection_id: int, chunk_paths: List[str], filename: str) -> int:
        full_temp_path = None
        try:
            file_extension = filename.split('.')[-1].lower() if '.' in filename else 'binary'
            asset_type_map = {
                'txt':'text','html':'text','css':'text','js':'text','md':'text','json':'text','csv':'text','xml':'text','py':'text',
                'png':'image','jpg':'image','jpeg':'image','gif':'image','svg':'image','webp':'image',
                'mp3':'audio','wav':'audio','ogg':'audio','m4a':'audio','flac':'audio',
                'mp4':'video','mov':'video','webm':'video', 'mkv':'video', 'avi':'video', 'flv':'video',
                'gltf':'3d','glb':'3d',
                'epub':'binary','pdf':'binary','zip':'binary','rar':'binary','7z':'binary'
            }
            asset_type = asset_type_map.get(file_extension, 'binary')

            manifest: Dict[str, Any] = {'chain': [], 'total_size': 0, 'filename': filename}
            previous_block_hash: Optional[str] = None

            if chunk_paths:
                # 1. Create a single temporary file by concatenating the received chunks
                temp_dir = os.path.dirname(chunk_paths[0])
                with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False) as outfile:
                    full_temp_path = outfile.name
                    for p in chunk_paths: # chunk_paths is already sorted by api_complete_upload
                        with open(p, 'rb') as infile:
                            shutil.copyfileobj(infile, outfile)

                # 2. Run Content-Defined Chunking on the complete file
                with open(full_temp_path, 'rb') as stream:
                    for chunk_data in dynamic_chunker(stream):
                        chunk_size = len(chunk_data)
                        chunk_hash = hashlib.blake2b(chunk_data).hexdigest()
                        compressed = zlib.compress(chunk_data, level=9)

                        with self.lock:
                            self.conn.execute("INSERT OR IGNORE INTO chunks (hash, data) VALUES (?, ?)", (chunk_hash, compressed))
                            self.conn.commit()

                        block = {
                            'chunk_hash': chunk_hash,
                            'size': chunk_size,
                            'previous_hash': previous_block_hash
                        }
                        block_str = json.dumps(block, sort_keys=True)
                        block_hash = hashlib.blake2b(block_str.encode()).hexdigest()

                        manifest['chain'].append(block)
                        manifest['total_size'] += chunk_size
                        previous_block_hash = block_hash
            
            manifest_str = json.dumps(manifest)
            logging.info(f"Created manifest for {filename}")

            with self.lock:
                cur = self.conn.cursor()
                sql = 'INSERT INTO assets (collection_id, type, format, manifest) VALUES (?, ?, ?, ?)'
                params = (collection_id, asset_type, file_extension, manifest_str)
                cur.execute(sql, params)
                asset_id = cur.lastrowid

                self.conn.execute("INSERT INTO metadata (asset_id, key, value) VALUES (?, 'filename', ?)", (asset_id, filename))
                self.conn.commit()
                logging.info(f"Successfully inserted asset {asset_id} for {filename}")

            return asset_id

        except Exception as e:
            logging.error(f"Unexpected error during asset creation: {e}")
            raise
        finally:
            # Clean up all temporary files
            if full_temp_path and os.path.exists(full_temp_path):
                os.remove(full_temp_path)
            
            if chunk_paths:
                # Clean up original chunks and their directory
                for path in chunk_paths:
                    try: 
                        os.remove(path)
                    except OSError: 
                        pass
                try: 
                    os.rmdir(os.path.dirname(chunk_paths[0]))
                except (OSError, IndexError): 
                    pass

    def get_or_create_collection_from_path(self, base_collection_id: int, path_prefix: str) -> int:
        with self.lock:
            if not path_prefix:
                return base_collection_id

            # Get project_id from the base collection
            cur = self.conn.execute("SELECT project_id FROM collections WHERE id = ?", (base_collection_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Collection with ID {base_collection_id} not found.")
            project_id = row[0]

            current_parent_id = base_collection_id
            for part in path_prefix.strip('/').split('/'):
                if not part: continue

                cur = self.conn.execute("SELECT id FROM collections WHERE project_id = ? AND parent_id = ? AND name = ?", (project_id, current_parent_id, part))
                existing = cur.fetchone()
                if existing:
                    current_parent_id = existing[0]
                else:
                    cur.execute("INSERT INTO collections (project_id, name, type, parent_id) VALUES (?, ?, ?, ?)", (project_id, part, 'collection', current_parent_id))
                    current_parent_id = cur.lastrowid

            self.conn.commit()
            return current_parent_id


    def get_assets_for_collection(self, collection_id: int, offset: int = 0, limit: int = 50, tag: Optional[str] = None, query: Optional[str] = None, filter_by_type: Optional[str] = None, sort_by: str = 'filename', sort_order: str = 'asc') -> Dict[str, Any]:
        with self.lock:
            try:
                where_clauses = ['a.collection_id = ?']
                params: List[Any] = [collection_id]

                if query:
                    where_clauses.append("a.id IN (SELECT asset_id FROM metadata WHERE key = 'filename' AND LOWER(value) LIKE LOWER(?))")
                    params.append(f'%{query}%')
                
                if filter_by_type:
                    where_clauses.append('a.format = ?')
                    params.append(filter_by_type)

                if tag:
                    where_clauses.append('a.id IN (SELECT asset_id FROM metadata WHERE key = "tags" AND value LIKE ?)')
                    params.append(f'%{re.escape(tag)}%')

                where_sql = ' AND '.join(where_clauses)

                # Get total count
                count_sql = f"SELECT COUNT(a.id) FROM assets a WHERE {where_sql}"
                total = self.conn.execute(count_sql, params).fetchone()[0]

                # Add sorting
                if sort_by == 'size':
                    order_clause = 'json_extract(a.manifest, \'$.total_size\')'
                else: # Default to filename
                    order_clause = '(SELECT value FROM metadata WHERE asset_id = a.id AND key = "filename")'
                
                sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
                order_by_sql = f'ORDER BY {order_clause} {sort_direction}'

                # Fetch paginated assets
                base_sql = f'SELECT a.id, a.type, a.format, a.manifest, (SELECT value FROM metadata WHERE asset_id = a.id AND key = "filename") as filename FROM assets a WHERE {where_sql} {order_by_sql} LIMIT ? OFFSET ?'
                
                paginated_params = params + [limit, offset]
                cur = self.conn.execute(base_sql, paginated_params)
                
                paginated_assets = []
                for row in cur.fetchall():
                    r = dict(row)
                    manifest = json.loads(r['manifest']) if r['manifest'] else {}
                    if not r['filename']:
                        r['filename'] = manifest.get('filename', 'Untitled')
                    r['size_original'] = manifest.get('total_size', 0)
                    del r['manifest']
                    paginated_assets.append(r)

                # Get all formats for the filter dropdown
                all_formats_sql = 'SELECT DISTINCT format FROM assets WHERE collection_id = ?'
                all_formats_cur = self.conn.execute(all_formats_sql, [collection_id])
                all_formats = [row[0] for row in all_formats_cur.fetchall() if row[0]]

                return {'assets': paginated_assets, 'total': total, 'all_formats': all_formats}

            except (sqlite3.Error, json.JSONDecodeError) as e:
                logging.error(f"Get assets error: {e}")
                return {'assets': [], 'total': 0, 'all_formats': []}

    def get_asset_metadata(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Gets asset metadata without loading data."""
        with self.lock:
            row = self.conn.execute("SELECT manifest FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row or not row['manifest']: return None
            manifest = json.loads(row['manifest'])
            filename = manifest.get('filename', f'asset_{asset_id}')
            mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            size = manifest.get('total_size', 0)
            return {'filename': filename, 'mime': mime, 'size': size, 'manifest_str': row['manifest']}

    def get_manifest(self, asset_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.conn.execute("SELECT manifest FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row or not row['manifest']:
                return None
            return json.loads(row['manifest'])

    def stream_asset_range(self, asset_id: int, start_byte: int, end_byte: int) -> Iterator[bytes]:
        manifest = self.get_manifest(asset_id)
        if not manifest:
            return

        total_size = manifest['total_size']
        if end_byte is None or end_byte >= total_size:
            end_byte = total_size - 1

        current_pos = 0

        for block in manifest['chain']:
            chunk_hash = block['chunk_hash']
            chunk_size = block['size']

            chunk_start = current_pos
            chunk_end = current_pos + chunk_size - 1

            if chunk_end >= start_byte:
                with self.lock:
                    chunk_row = self.conn.execute("SELECT data FROM chunks WHERE hash=?", (chunk_hash,)).fetchone()

                if chunk_row and chunk_row['data']:
                    try:
                        data = zlib.decompress(chunk_row['data'])

                        slice_start = max(0, start_byte - chunk_start)
                        slice_end = min(chunk_size, end_byte - chunk_start + 1)

                        if slice_start < slice_end:
                            yield data[slice_start:slice_end]
                    except zlib.error:
                        logging.error(f"Failed to decompress chunk {chunk_hash} for asset {asset_id}")
                        continue

            current_pos += chunk_size
            if current_pos > end_byte:
                break

    def stream_asset_data(self, asset_id: int) -> Iterator[bytes]:
        """Yields asset data chunk by chunk for streaming."""
        manifest = self.get_manifest(asset_id)
        if not manifest:
            return

        for block in manifest['chain']:
            chunk_hash = block['chunk_hash']
            with self.lock:
                chunk_row = self.conn.execute("SELECT data FROM chunks WHERE hash=?", (chunk_hash,)).fetchone()

            if chunk_row and chunk_row['data']:
                try:
                    yield zlib.decompress(chunk_row['data'])
                except zlib.error:
                    logging.error(f"Failed to decompress chunk {chunk_hash} for asset {asset_id}")
                    continue

    def get_asset_ids_with_paths_for_collection(self, collection_id: int, base_path: str = "") -> List[Tuple[int, str]]:
        """Recursively gets asset IDs and their zip paths for a collection."""
        with self.lock:
            results: List[Tuple[int, str]] = []
            coll = self.get_collection(collection_id)
            if not coll: return []

            current_path = base_path + coll['name'] + '/'

            assets = self.get_assets_for_collection(collection_id, 0, 999999)['assets']
            for a in assets:
                if a.get('filename'):
                    results.append((a['id'], current_path + a['filename']))

            subs = self.conn.execute("SELECT id FROM collections WHERE parent_id=?", (collection_id,)).fetchall()
            for sub in subs:
                results.extend(self.get_asset_ids_with_paths_for_collection(sub['id'], current_path))
            return results

    def get_asset_ids_with_paths_for_project(self, project_id: int) -> List[Tuple[int, str]]:
        """Gets all asset IDs and their zip paths for a project."""
        with self.lock:
            results: List[Tuple[int, str]] = []
            proj = self.get_project(project_id)
            if not proj: return []
            base_path = proj['name'] + '/'
            tops = self.conn.execute("SELECT id FROM collections WHERE project_id=? AND parent_id IS NULL", (project_id,)).fetchall()
            for top in tops:
                results.extend(self.get_asset_ids_with_paths_for_collection(top['id'], base_path))
            return results

    def write_asset_to_zip(self, asset_id: int, zf: zipfile.ZipFile, path_in_zip: str) -> None:
        """Streams an asset's data directly into a ZipFile object."""
        info = zipfile.ZipInfo(path_in_zip, time.localtime())
        info.compress_type = zipfile.ZIP_STORED
        with zf.open(info, 'w') as asset_file:
            for chunk in self.stream_asset_data(asset_id):
                asset_file.write(chunk)

    def create_project(self, name: str, type: str, description: str) -> int:
        with self.lock:
            try:
                cur = self.conn.cursor()
                cur.execute('INSERT INTO projects (name, type, description) VALUES (?, ?, ?)', (name, type, description))
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Create project error: {e}")
                raise

    def get_all_projects(self) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM projects ORDER BY order_index ASC, name")
                return [dict(row) for row in cur.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Get all projects error: {e}")
                return []

    def create_collection(self, project_id: int, name: str, type: str, parent_id: Optional[int]) -> int:
        with self.lock:
            try:
                cur = self.conn.cursor()
                cur.execute('INSERT INTO collections (project_id, name, type, parent_id) VALUES (?, ?, ?, ?)', (project_id, name, type, parent_id))
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Create collection error: {e}")
                raise

    def get_collections_for_project(self, project_id: int) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM collections WHERE project_id = ? ORDER BY order_index ASC, name", (project_id,))
                return [dict(row) for row in cur.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Get collections for project error: {e}")
                return []

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Get project error: {e}")
                return None

    def get_collection(self, collection_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Get collection error: {e}")
                return None

    def get_asset_preview(self, asset_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            try:
                row = self.conn.execute('SELECT a.id, a.type, a.format, a.manifest, (SELECT value FROM metadata m WHERE m.asset_id=a.id AND m.key="filename" LIMIT 1) as filename FROM assets a WHERE a.id = ?', (asset_id,)).fetchone()
                if not row: return None
                manifest = json.loads(row['manifest'])
                filename = manifest.get('filename', f'asset_{asset_id}')
                size = manifest.get('total_size', 0)

                if row['type'] == 'text':
                    data = bytearray()
                    for block in manifest['chain']:
                        chunk_hash = block['chunk_hash']
                        chunk_row = self.conn.execute("SELECT data FROM chunks WHERE hash=?", (chunk_hash,)).fetchone()
                        if chunk_row: data.extend(zlib.decompress(chunk_row['data']))
                    text = data.decode('utf-8', errors='ignore')
                    if row['format'] == 'json':
                        try: text = json.dumps(json.loads(text), indent=2)
                        except: pass
                    elif row['format'] == 'xml':
                        try:
                            tree = ET.fromstring(text)
                            ET.indent(tree, space='  ')
                            text = ET.tostring(tree, encoding='unicode', method='xml')
                        except: pass
                    return {'id':asset_id, 'type':'text', 'format':row['format'], 'filename':filename, 'size_original':size, 'content':text}
                else:
                    return {'id':asset_id, 'type':row['type'], 'format':row['format'], 'filename':filename, 'size_original':size}
            except sqlite3.Error as e:
                logging.error(f"Preview error: {e}")
                return None
            except Exception as e:
                logging.error(f"Unexpected preview error: {e}")
                return None

    def vacuum(self) -> None:
        """Optimizes the database file."""
        with self.lock:
            self.conn.execute("VACUUM;")
            self.conn.commit()

# endregion

HTML_SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Select a Vault</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <h1>Select or Create a Vault</h1>
        <div id="file-list">
            {file_links}
        </div>
        <div id="unlock-section" class="hidden">
            <h2 id="unlock-title">Unlock Vault</h2>
            <input type="password" id="unlock-password" placeholder="Enter vault password">
            <button onclick="unlockVault()">Unlock</button>
        </div>
        <div class="new-vault">
            <h2>Create New Vault</h2>
            <input type="text" id="new-vault-name" placeholder="Vault name (default: default.vault)">
            <input type="password" id="new-vault-password" placeholder="Enter password">
            <input type="password" id="new-vault-password-confirm" placeholder="Confirm password">
            <button onclick="createVault()">Create New Vault</button>
        </div>
    </div>
    <script>
        let selectedDb = null;

        function selectDb(db_name) {
            selectedDb = db_name;
            document.getElementById('unlock-section').classList.remove('hidden');
            document.getElementById('unlock-title').textContent = `Unlock ${db_name}`;
        }

        function unlockVault() {
            const password = document.getElementById('unlock-password').value;
            if (selectedDb && password) {
                fetch('/api/unlock_vault', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ db: selectedDb, password: password })
                }).then(res => {
                    if (res.ok) {
                        location.reload();
                    } else {
                        alert('Invalid password');
                    }
                });
            }
        }

        function createVault() {
            let name = document.getElementById('new-vault-name').value;
            const password = document.getElementById('new-vault-password').value;
            const passwordConfirm = document.getElementById('new-vault-password-confirm').value;

            if (password !== passwordConfirm) {
                alert('Passwords do not match!');
                return;
            }

            if (!name) {
                name = 'default';
            }

            if (name && password) {
                fetch('/api/create_vault', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ db: name + '.vault', password: password })
                }).then(res => {
                    if (res.ok) {
                        location.reload();
                    } else {
                        alert('Failed to create vault');
                    }
                });
            }
        }
    </script>
</body>
</html>
"""

CSS_SELECTOR_STYLES = """
body { font-family: sans-serif; background-color: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.container { background: #1e1e1e; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); text-align: center; }
h1 { color: #1fb6ff; }
#file-list a { display: block; padding: 0.5rem 1rem; margin: 0.5rem 0; background: #333; color: #e0e0e0; text-decoration: none; border-radius: 4px; transition: background-color 0.2s; }
#file-list a:hover { background-color: #1fb6ff; color: #121212; }
.new-vault, #unlock-section { margin-top: 1.5rem; }
#new-vault-name, #new-vault-password, #new-vault-password-confirm, #unlock-password { padding: 0.5rem; border-radius: 4px; border: 1px solid #333; background: #222; color: #e0e0e0; margin-bottom: 0.5rem; width: calc(100% - 1rem); }
button { padding: 0.5rem 1rem; border: none; border-radius: 4px; background-color: #1fb6ff; color: #121212; cursor: pointer; transition: background-color 0.2s; }
button:hover { background-color: #1ca0d3; }
.hidden { display: none; }
"""



class RequestHandler(http.server.BaseHTTPRequestHandler):
    routes: Dict[str, List[Tuple[str, str]]] = {
        'GET': [
            (r'^/favicon.ico$', 'handle_favicon'),
            (r'^/api/projects$', 'api_get_all_projects'),
            (r'^/api/projects/(\d+)$', 'api_get_project'),
            (r'^/api/projects/(\d+)/collections$', 'api_get_project_collections'),
            (r'^/api/collections/(\d+)/assets$', 'api_get_collection_assets'),
            (r'^/api/collections/(\d+)$', 'api_get_collection'),
            (r'^/api/assets/(\d+)/preview$', 'handle_asset_preview'),
            (r'^/api/assets/(\d+)$', 'handle_asset_download'),
            (r'^/api/projects/(\d+)/download$', 'api_download_project'),
            (r'^/api/collections/(\d+)/download$', 'api_download_collection'),
        ],
        'POST': [
            (r'^/api/create_vault$', 'api_create_vault'),
            (r'^/api/unlock_vault$', 'api_unlock_vault'),
            (r'^/api/projects$', 'api_create_project'),
            (r'^/api/collections$', 'api_create_collection'),
            (r'^/api/upload/chunk$', 'api_upload_chunk'),
            (r'^/api/upload/complete$', 'api_complete_upload'),
            (r'^/api/maintenance/vacuum$', 'api_vacuum'),
            (r'^/api/collections/(\d+)/assets/download$', 'handle_bulk_download'),
        ],
    }

    def __init__(self, request: bytes, client_address: Tuple[str, int], server: http.server.HTTPServer) -> None:
        super().__init__(request, client_address, server)

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.end_headers()

    def handle_one_request(self) -> None:
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.send_error(414)
                return
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                return

            # New authentication flow
            if self.command != 'OPTIONS':
                # Allow access to the main page and unlock/create vault endpoints
                if self.path not in ('/', '/api/unlock_vault', '/api/create_vault'):
                    if not self.server.app_state.get("manager"):
                        self.send_error(401, "Unauthorized: No vault unlocked")
                        return

            mname = 'do_' + self.command
            if hasattr(self, mname):
                getattr(self, mname)()
            self.wfile.flush()
        except socket.timeout as e:
            self.log_error("Request timed out: %r", e)

    def _send_json(self, obj: Any, code: int = 200) -> None:
        data = json.dumps(obj, default=str).encode('utf-8')
        headers = {'Content-Type':'application/json'}
        self._send_compressed(data, code, headers)

    def _send_raw(self, data: bytes, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        headers = headers or {}
        self._send_compressed(data, status, headers)

    def _send_compressed(self, data: bytes, code: int, headers: Dict[str, str]) -> None:
        accept = self.headers.get('Accept-Encoding', '').lower()
        if 'gzip' in accept and len(data) > 200:
            data = gzip.compress(data, compresslevel=6)
            headers['Content-Encoding'] = 'gzip'
            headers['Vary'] = 'Accept-Encoding'
        headers['Content-Length'] = str(len(data))
        # Add CORS headers to allow API calls
        headers['Access-Control-Allow-Origin'] = '*'
        headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        headers['Access-Control-Allow-Headers'] = 'Content-Type,Range,Authorization'
        self.send_response(code)
        for k,v in headers.items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header('Access-control-allow-methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type,Range,Authorization')
        self.end_headers()

    def require_manager(self) -> bool:
        if not self.server.app_state.get("manager"):
            self._send_json({"message": "No database selected"}, 400)
            return False
        return True

    def route_request(self, method: str) -> None:
        for pattern, handler_name in self.routes.get(method, []):
            m = re.match(pattern, self.path.split('?')[0])
            if m:
                handler = getattr(self, handler_name)
                handler(*m.groups())
                return
        self.send_error(404)

    def do_GET(self) -> None:
        if self.path == '/':
            if not self.server.app_state["manager"]:
                self.show_db_selector()
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.server.app_state["rendered_html"])
        else:
            self.route_request('GET')

    def do_POST(self) -> None:
        self.route_request('POST')

    def handle_favicon(self) -> None:
        self.send_response(204)
        self.end_headers()

    def show_db_selector(self) -> None:
        files = [f for f in os.listdir('.') if f.endswith('.vault')]
        file_links = ' '.join(f'<a href="#" onclick="selectDb(\'{f}\')">{f}</a>' for f in files)
        html = HTML_SELECTOR_TEMPLATE.replace('{css}', CSS_SELECTOR_STYLES).replace('{file_links}', file_links)
        self._send_raw(html.encode('utf-8'), headers={'Content-Type': 'text/html'})

    def api_get_all_projects(self) -> None:
        if not self.require_manager(): return
        self._send_json(self.server.app_state["manager"].get_all_projects())

    def api_get_project(self, project_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            project_id = int(project_id_str)
            project = self.server.app_state["manager"].get_project(project_id)
            if project:
                self._send_json(project)
            else:
                self._send_json({'message': 'Project not found'}, 404)
        except ValueError:
            self._send_json({'message': 'Invalid project ID'}, 400)

    def api_create_project(self) -> None:
        if not self.require_manager(): return
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            name = body.get('name')
            type = body.get('type', 'project')
            description = body.get('description', '')
            if not name:
                self._send_json({'message': 'Name is required'}, 400)
                return
            pid = self.server.app_state["manager"].create_project(name, type, description)
            self._send_json({'id': pid, 'name': name, 'type': type, 'description': description}, 201)
        except Exception as e:
            self._send_json({'message': f'Create failed: {e}'}, 500)

    def api_get_project_collections(self, project_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            project_id = int(project_id_str)
            self._send_json(self.server.app_state["manager"].get_collections_for_project(project_id))
        except ValueError:
            self._send_json({'message': 'Invalid project ID'}, 400)

    def api_get_collection(self, collection_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            collection_id = int(collection_id_str)
            collection = self.server.app_state["manager"].get_collection(collection_id)
            if collection:
                self._send_json(collection)
            else:
                self._send_json({'message': 'Collection not found'}, 404)
        except ValueError:
            self._send_json({'message': 'Invalid collection ID'}, 400)

    def api_create_collection(self) -> None:
        if not self.require_manager(): return
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            project_id = body.get('project_id')
            name = body.get('name')
            type = body.get('type', 'collection')
            parent_id = body.get('parent_id')
            if not (project_id and name):
                self._send_json({'message': 'Project ID and name required'}, 400)
                return
            cid = self.server.app_state["manager"].create_collection(project_id, name, type, parent_id)
            self._send_json({'id': cid, 'name': name, 'type': type, 'parent_id': parent_id}, 201)
        except Exception as e:
            self._send_json({'message': f'Create failed: {e}'}, 500)

    def api_get_collection_assets(self, collection_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            collection_id = int(collection_id_str)
            qs = parse_qs(urlparse(self.path).query)
            offset = int(qs.get('offset', [0])[0])
            limit = int(qs.get('limit', [50])[0])
            tag = qs.get('tag', [None])[0]
            query = qs.get('query', [None])[0]
            filter_by_type = qs.get('filter_by_type', [None])[0]
            sort_by = qs.get('sort_by', ['filename'])[0]
            sort_order = qs.get('sort_order', ['asc'])[0]
            self._send_json(self.server.app_state["manager"].get_assets_for_collection(collection_id, offset, limit, tag, query, filter_by_type, sort_by, sort_order))
        except ValueError:
            self._send_json({'message': 'Invalid collection ID'}, 400)

    def handle_asset_preview(self, asset_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            asset_id = int(asset_id_str)
            preview_data = self.server.app_state["manager"].get_asset_preview(asset_id)
            if preview_data:
                self._send_json(preview_data)
            else:
                self._send_json({'message': 'Asset not found'}, 404)
        except ValueError:
            self._send_json({'message': 'Invalid asset ID'}, 400)

    def handle_asset_download(self, asset_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            asset_id = int(asset_id_str)

            meta = self.server.app_state["manager"].get_asset_metadata(asset_id)
            if not meta:
                self.send_error(404)
                return

            total_size = meta['size']
            range_header = self.headers.get('Range')

            if range_header:
                range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
                if not range_match:
                    self.send_error(416, "Invalid Range header")
                    return

                start_byte = int(range_match.group(1))
                end_byte_str = range_match.group(2)
                end_byte = int(end_byte_str) if end_byte_str else total_size - 1

                if start_byte >= total_size or end_byte >= total_size or start_byte > end_byte:
                    self.send_error(416, "Range not satisfiable")
                    return

                self.send_response(206)
                self.send_header('Content-Type', meta['mime'])
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Range', f'bytes {start_byte}-{end_byte}/{total_size}')

                content_length = end_byte - start_byte + 1
                self.send_header('Content-Length', str(content_length))
                self.end_headers()

                for data_chunk in self.server.app_state["manager"].stream_asset_range(asset_id, start_byte, end_byte):
                    self.wfile.write(data_chunk)
            else:
                self.send_response(200)
                self.send_header('Content-Type', meta['mime'])
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(total_size))
                self.end_headers()

                for data_chunk in self.server.app_state["manager"].stream_asset_data(asset_id):
                    self.wfile.write(data_chunk)

        except ValueError:
            self.send_error(400)
        except Exception as e:
            logging.error(f"Download error: {e}")
            self.send_error(500)

    def handle_bulk_download(self, collection_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            ids = body.get('ids', [])
            if not ids:
                self.send_error(400)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', 'attachment; filename="selected_assets.zip"')
            self.end_headers()
            with zipfile.ZipFile(self.wfile, 'w', compression=zipfile.ZIP_STORED) as zf:
                for aid in ids:
                    meta = self.server.app_state["manager"].get_asset_metadata(aid)
                    if meta:
                        path_in_zip = meta['filename']
                        self.server.app_state["manager"].write_asset_to_zip(aid, zf, path_in_zip)
        except Exception as e:
            logging.error(f"Bulk download error: {e}")
            self.send_error(500)

    def api_unlock_vault(self) -> None:
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            db_name = body.get('db')
            password = body.get('password')

            if not db_name or not password or not db_name.endswith('.vault'):
                self._send_json({'message': 'Invalid request'}, 400)
                return

            manager = CompactVaultManager(db_name)
            if manager.check_password(password):
                self.server.app_state["db_path"] = db_name
                self.server.app_state["manager"] = manager
                self.server.app_state["rendered_html"] = HTML_TEMPLATE.replace('{css}', CSS_STYLES).replace('{js}', JAVASCRIPT_CODE).encode('utf-8')
                self._send_json({'message': f'Unlocked {db_name}'})
            else:
                self._send_json({'message': 'Invalid password'}, 401)

        except Exception as e:
            self._send_json({'message': f'Vault unlock failed: {e}'}, 500)

    def api_create_vault(self) -> None:
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            db_name = body.get('db')
            password = body.get('password')

            if not db_name or not password or not db_name.endswith('.vault'):
                self._send_json({'message': 'Invalid request'}, 400)
                return

            if os.path.exists(db_name):
                self._send_json({'message': 'Vault already exists'}, 400)
                return

            manager = CompactVaultManager(db_name)
            manager.set_password(password)
            self._send_json({'message': f'Created and unlocked {db_name}'}, 201)

            # Automatically unlock the new vault
            self.server.app_state["db_path"] = db_name
            self.server.app_state["manager"] = manager
            self.server.app_state["rendered_html"] = HTML_TEMPLATE.replace('{css}', CSS_STYLES).replace('{js}', JAVASCRIPT_CODE).encode('utf-8')

        except Exception as e:
            self._send_json({'message': f'Vault creation failed: {e}'}, 500)

    def api_vacuum(self) -> None:
        if not self.require_manager(): return
        self.server.app_state["manager"].vacuum()
        self._send_json({'message': 'VACUUM complete'})

    def api_upload_chunk(self) -> None:
        try:
            qs = parse_qs(urlparse(self.path).query)
            upload_id = qs.get('upload_id', [None])[0]
            chunk_index = int(qs.get('chunk_index', [-1])[0])
            logging.info(f"Received chunk {chunk_index} for upload {upload_id}")
            if not upload_id or chunk_index < 0:
                self._send_json({'message': 'Missing upload_id or chunk_index'}, 400)
                return

            upload_dir = os.path.join(UPLOAD_TEMP_DIR, upload_id)
            os.makedirs(upload_dir, exist_ok=True)
            chunk_path = os.path.join(upload_dir, str(chunk_index))

            length = int(self.headers.get('content-length'))
            with open(chunk_path, 'wb') as f:
                remaining = length
                while remaining > 0:
                    buf = self.rfile.read(min(remaining, 4096))
                    if not buf:
                        raise EOFError("Unexpected end of stream")
                    f.write(buf)
                    remaining -= len(buf)

            self._send_json({'message': 'Chunk received'})
        except Exception as e:
            logging.error(f"Chunk upload failed: {e}")
            self._send_json({'message': f'Chunk upload failed: {e}'}, 500)

    def api_complete_upload(self) -> None:
        if not self.require_manager(): return
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            upload_id = body.get('upload_id')
            filename = body.get('filename')
            collection_id = int(body.get('collection_id'))
            path_prefix = body.get('path_prefix', '')
            logging.info(f"Completing upload for {filename} (upload_id: {upload_id}) in collection {collection_id}")

            if not all([upload_id, filename, collection_id is not None]):
                self._send_json({'message': 'Missing required fields'}, 400)
                return

            upload_dir = os.path.join(UPLOAD_TEMP_DIR, upload_id)
            if not os.path.isdir(upload_dir):
                self._send_json({'message': 'Invalid upload_id'}, 400)
                return

            chunk_files = sorted(os.listdir(upload_dir), key=int)
            chunk_paths = [os.path.join(upload_dir, cf) for cf in chunk_files]

            final_collection_id = self.server.app_state["manager"].get_or_create_collection_from_path(collection_id, path_prefix)

            # Add task to the queue
            task = (final_collection_id, chunk_paths, filename)
            self.server.app_state["manager"].asset_creation_queue.put(task)

            self._send_json({'message': 'Upload accepted, processing in background'})
        except Exception as e:
            self._send_json({'message': f'Upload completion failed: {e}'}, 500)

    def api_download_project(self, project_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            project_id = int(project_id_str)
            proj = self.server.app_state["manager"].get_project(project_id)
            if not proj:
                self.send_error(404)
                return

            zip_filename = f"{proj['name']}.zip"

            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{zip_filename}"')
            self.end_headers()

            with zipfile.ZipFile(self.wfile, 'w', compression=zipfile.ZIP_STORED) as zf:
                asset_paths = self.server.app_state["manager"].get_asset_ids_with_paths_for_project(project_id)
                for aid, path_in_zip in asset_paths:
                    self.server.app_state["manager"].write_asset_to_zip(aid, zf, path_in_zip)
        except ValueError:
            self.send_error(400)
        except Exception as e:
            logging.error(f"Project download error: {e}")
            self.send_error(500)

    def api_download_collection(self, collection_id_str: str) -> None:
        if not self.require_manager(): return
        try:
            collection_id = int(collection_id_str)
            coll = self.server.app_state["manager"].get_collection(collection_id)
            if not coll:
                self.send_error(404)
                return

            zip_filename = f"{coll['name']}.zip"

            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{zip_filename}"')
            self.end_headers()

            with zipfile.ZipFile(self.wfile, 'w', compression=zipfile.ZIP_STORED) as zf:
                asset_paths = self.server.app_state["manager"].get_asset_ids_with_paths_for_collection(collection_id)
                for aid, path_in_zip in asset_paths:
                    self.server.app_state["manager"].write_asset_to_zip(aid, zf, path_in_zip)
        except ValueError:
            self.send_error(400)
        except Exception as e:
            logging.error(f"Collection download error: {e}")
            self.send_error(500)

def run(server_class: type = ThreadedHTTPServer, handler_class: type = RequestHandler, port: int = 8000) -> None:
    # Server state
    db_path: Optional[str] = None
    manager: Optional[CompactVaultManager] = None
    rendered_html: Optional[bytes] = None

    server_class.app_state = {
        "db_path": db_path,
        "manager": manager,
        "rendered_html": rendered_html,
        "password": None  # No global password
    }

    # Find a free port
    while True:
        try:
            server_address = ('', port)
            server = server_class(server_address, handler_class)
            break
        except OSError as e:
            if e.errno == 98:  # Address already in use
                port += 1
            else:
                raise

    # Graceful shutdown
    def signal_handler(sig: int, frame: Any) -> None:
        logging.info('Shutting down server...')
        try:
            if server.app_state.get("manager"):
                manager = server.app_state["manager"]
                logging.info("Running database checkpoint...")
                manager.conn.execute("PRAGMA wal_checkpoint(FULL);")
                manager.conn.close()
                logging.info("Database connection closed.")
        except Exception as e:
            logging.error(f"Error during DB shutdown: {e}")
        finally:
            logging.info("Stopping HTTP server.")
            server.server_close()
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.info(f'Starting httpd on port {port}...')
    webbrowser.open_new_tab(f'http://localhost:{port}')
    server.serve_forever()

if __name__ == '__main__':
    run()
