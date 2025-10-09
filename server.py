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
from collections import defaultdict
from socketserver import ThreadingMixIn

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
      </div>
      <ul id="assets-list" class="list sortable" role="list"></ul>
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
  <input id="file-input" type="file" multiple style="display:none" />
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
}
.item-name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
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
    filteredAssets: [],
    loadingMore: false,
    offset: 0,
    limit: 50,
    total: 0,
    searchQuery: '',
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
    state.offset = 0;
    await loadAssets(id);
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

  function applyAssetFilter() {
    const filter = el("filter-by-type").value;
    state.filteredAssets = filter ? state.assets.filter(a => a.format === filter) : state.assets;
    el("asset-count").textContent = `(${state.filteredAssets.length} of ${state.total})`;
    renderVisibleAssets();
  }

  // Load assets
  async function loadAssets(collection_id, append = false) {
    try {
      let path = `/collections/${collection_id}/assets?offset=${state.offset}&limit=${state.limit}`;
      if (state.searchQuery) {
        path += `&query=${encodeURIComponent(state.searchQuery)}`;
      }
      const res = await api(path);
      state.assets = append ? state.assets.concat(res.assets) : res.assets;
      state.total = res.total;

      if (!append) {
        const filterDropdown = el("filter-by-type");
        const currentFilter = filterDropdown.value;
        filterDropdown.innerHTML = "<option value=''>All Types</option>";
        const allFormats = [...new Set(state.assets.map(a => a.format))].sort();
        allFormats.forEach(f => {
          const opt = document.createElement("option");
          opt.value = opt.textContent = f;
          filterDropdown.appendChild(opt);
        });
        filterDropdown.value = currentFilter;
      }

      applyAssetFilter();
      return res;
    } catch (e) {
      toast(`Error loading assets: ${e.message}`, 'error');
      throw e;
    }
  }

  const renderVisibleAssets = () => {
    const container = el("assets-list");
    const itemHeight = 50;
    const filtered = state.filteredAssets || [];

    const scrollTop = container.scrollTop;
    const visibleHeight = container.clientHeight;
    const startIndex = Math.floor(scrollTop / itemHeight);
    const endIndex = Math.min(startIndex + Math.ceil(visibleHeight / itemHeight) + 5, filtered.length);

    const visibleAssets = filtered.slice(startIndex, endIndex);

    const itemsHtml = visibleAssets.map(a => {
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

    container.innerHTML = `
      <div style="height: ${startIndex * itemHeight}px;"></div>
      ${itemsHtml}
      <div style="height: ${(filtered.length - endIndex) * itemHeight}px;"></div>
    `;
  };

  const debouncedRender = debounce(renderVisibleAssets, 16);

  el("assets-list").addEventListener("scroll", () => {
    const container = el("assets-list");
    if (container.scrollTop + container.clientHeight >= container.scrollHeight - 200 && state.assets.length < state.total) {
      if (!state.loadingMore) {
        state.loadingMore = true;
        state.offset += state.limit;
        loadAssets(state.selection.collection, true).finally(() => {
          state.loadingMore = false;
        });
      }
    }
    debouncedRender();
  });

  // Clear assets
  function clearAssets() {
    state.assets = [];
    state.filteredAssets = [];
    state.selection.collection = null;
    el("assets-list").innerHTML = "";
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
      const ids = state.filteredAssets.map(a => a.id.toString());
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
        filesToUpload.push({ file: item, path: '' });
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
  el("file-input").onchange = ev => uploadFiles(ev.target.files);

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

  const searchInput = el('search-assets');
  let searchTimeout;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.searchQuery = searchInput.value;
      state.offset = 0;
      loadAssets(state.selection.collection);
    }, 300);
  });

  // Init
  loadProjects();

  el("assets-list").addEventListener('click', e => {
    const item = e.target.closest('.item');
    if (item) {
        const assetId = item.dataset.id;
        const asset = state.filteredAssets.find(a => a.id.toString() === assetId);
        if (asset) {
            onAssetClick(asset, item, e);
        }
    }
  });

  el("filter-by-type").onchange = () => {
      applyAssetFilter();
  };

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
HARDCODED_PASSWORD = os.getenv("COMPACTVAULT_PASSWORD", "password")  # Use environment variable for security

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
    def __init__(self, db_path=DEFAULT_DB):
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
        self.asset_creation_queue = queue.Queue()
        num_workers = os.cpu_count() or 4
        self.workers = []
        for _ in range(num_workers):
            t = threading.Thread(target=self._process_asset_creation_queue, daemon=True)
            t.start()
            self.workers.append(t)

    def create_database_schema(self):
        queries = [
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

    def _ensure_schema_extensions(self):
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

    def _migrate_to_chunked_storage(self, cursor):
        with self.lock:
            try:
                CHUNK_SIZE = 256 * 1024
                c = cursor
                c.execute("CREATE TABLE assets_new (id INTEGER PRIMARY KEY, collection_id INTEGER REFERENCES collections(id), type TEXT NOT NULL, format TEXT, manifest TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
                c.execute("CREATE TABLE chunks (hash TEXT PRIMARY KEY, data BLOB)")
                for asset in c.execute("SELECT * FROM assets").fetchall():
                    asset_id = asset['id']
                    if 'data' in asset and asset['data']:
                        manifest = {'chunks': [], 'size': asset.get('size_original', len(asset['data']))}
                        data = zlib.decompress(asset['data']) if asset.get('compression') == 'zlib' else asset['data']
                        for i in range(0, len(data), CHUNK_SIZE):
                            chunk_data = data[i:i + CHUNK_SIZE]
                            h = hashlib.sha256(chunk_data).hexdigest()
                            compressed = zlib.compress(chunk_data, level=9)
                            manifest['chunks'].append(h)
                            c.execute("INSERT OR IGNORE INTO chunks (hash, data) VALUES (?, ?)", (h, compressed))
                        manifest_str = json.dumps(manifest)
                    else: manifest_str = None
                    c.execute("INSERT INTO assets_new (id, collection_id, type, format, manifest, created_at) VALUES (?, ?, ?, ?, ?, ?)", (asset['id'], asset['collection_id'], asset['type'], asset['format'], manifest_str, asset['created_at']))
                c.execute("DROP TABLE assets")
                c.execute("ALTER TABLE assets_new RENAME TO assets")
                self.conn.commit()
                logging.info("Database migrated to chunked storage.")
            except sqlite3.Error as e:
                logging.error(f"Migration error: {e}")

    def _process_asset_creation_queue(self):
        while True:
            try:
                task = self.asset_creation_queue.get()
                if task is None:
                    break  # Sentinel value to stop the worker
                collection_id, chunk_paths, filename = task
                self.create_asset_from_chunks(collection_id, chunk_paths, filename)
            except Exception as e:
                logging.error(f"Error in asset creation worker: {e}")

    def create_asset_from_chunks(self, collection_id, chunk_paths, filename):
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

            manifest = {'chain': [], 'total_size': 0, 'filename': filename}
            previous_block_hash = None

            for chunk_path in chunk_paths:
                try:
                    with open(chunk_path, 'rb') as f:
                        chunk_data = f.read()

                    chunk_size = len(chunk_data)
                    chunk_hash = hashlib.sha256(chunk_data).hexdigest()
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
                    block_hash = hashlib.sha256(block_str.encode()).hexdigest()

                    manifest['chain'].append(block)
                    manifest['total_size'] += chunk_size
                    previous_block_hash = block_hash

                except Exception as e:
                    logging.error(f"Error processing chunk {chunk_path}: {e}")
                    raise

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

            # Clean up
            for path in chunk_paths:
                try: os.remove(path)
                except OSError: pass
            try: os.rmdir(os.path.dirname(chunk_paths[0]))
            except (OSError, IndexError): pass

            return asset_id

        except Exception as e:
            logging.error(f"Unexpected error during asset creation: {e}")
            # Ensure cleanup happens on error too
            for path in chunk_paths:
                try: os.remove(path)
                except OSError: pass
            try: os.rmdir(os.path.dirname(chunk_paths[0]))
            except (OSError, IndexError): pass
            raise

    def get_or_create_collection_from_path(self, base_collection_id, path_prefix):
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

    def get_assets_for_collection(self, collection_id, offset=0, limit=50, tag=None, query=None):
        with self.lock:
            try:
                # 1. Fetch all IDs, manifests, and joined filenames with filtering
                base_sql = 'SELECT a.id, a.manifest, m.value as filename FROM assets a LEFT JOIN metadata m ON a.id = m.asset_id AND m.key = "filename" WHERE a.collection_id = ?'
                params = [collection_id]
                if tag:
                    base_sql += ' AND a.id IN (SELECT asset_id FROM metadata WHERE key = "tags" AND value LIKE ?)'
                    params.append(f'%{re.escape(tag)}%')

                all_assets_cursor = self.conn.execute(base_sql, params)
                
                # Create the list, including the fallback logic for filenames
                all_assets = []
                for r in all_assets_cursor.fetchall():
                    filename = r['filename']
                    if not filename:
                        try:
                            manifest = json.loads(r['manifest']) if r['manifest'] else {}
                            filename = manifest.get('filename', 'Untitled')
                        except (json.JSONDecodeError, AttributeError):
                            filename = 'Untitled'
                    all_assets.append({'id': r['id'], 'filename': filename})

                # Apply search query in Python
                if query:
                    all_assets = [a for a in all_assets if query.lower() in a['filename'].lower()]

                # 2. Sort naturally in Python
                all_assets.sort(key=lambda x: natural_sort_key(x['filename']))

                # 3. Get total count
                total = len(all_assets)

                # 4. Get the slice of IDs for the current page
                paginated_ids = [a['id'] for a in all_assets[offset:offset + limit]]

                # 5. If no IDs for this page, return empty
                if not paginated_ids:
                    return {'assets': [], 'total': total}

                # 6. Fetch full data for these paginated IDs
                id_placeholders = ','.join('?' for _ in paginated_ids)
                sql = f'SELECT a.id, a.type, a.format, a.manifest, m.value as filename FROM assets a LEFT JOIN metadata m ON a.id = m.asset_id AND m.key = "filename" WHERE a.id IN ({id_placeholders})'
                
                cur = self.conn.execute(sql, paginated_ids)
                
                # 7. Create a mapping from id -> details
                asset_details_map = {r['id']: dict(r) for r in cur.fetchall()}

                # 8. Create the final results list in the correct order
                results = []
                for asset_id in paginated_ids:
                    row = asset_details_map.get(asset_id)
                    if not row: continue

                    manifest = json.loads(row['manifest']) if row['manifest'] else {}
                    # Re-apply filename logic for the final output
                    if not row['filename']:
                        row['filename'] = manifest.get('filename', 'Untitled')
                    row['size_original'] = manifest.get('total_size', 0)
                    del row['manifest']
                    results.append(row)

                # 9. Return final data
                return {'assets': results, 'total': total}

            except (sqlite3.Error, json.JSONDecodeError) as e:
                logging.error(f"Get assets error: {e}")
                return {'assets': [], 'total': 0}

    def get_asset_metadata(self, asset_id):
        """Gets asset metadata without loading data."""
        with self.lock:
            row = self.conn.execute("SELECT manifest FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row or not row['manifest']: return None
            manifest = json.loads(row['manifest'])
            filename = manifest.get('filename', f'asset_{asset_id}')
            mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            size = manifest.get('total_size', 0)
            return {'filename': filename, 'mime': mime, 'size': size, 'manifest_str': row['manifest']}

    def get_manifest(self, asset_id):
        with self.lock:
            row = self.conn.execute("SELECT manifest FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row or not row['manifest']:
                return None
            return json.loads(row['manifest'])

    def stream_asset_range(self, asset_id, start_byte, end_byte):
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

    def stream_asset_data(self, asset_id):
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

    def get_asset_ids_with_paths_for_collection(self, collection_id, base_path=""):
        """Recursively gets asset IDs and their zip paths for a collection."""
        with self.lock:
            results = []
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

    def get_asset_ids_with_paths_for_project(self, project_id):
        """Gets all asset IDs and their zip paths for a project."""
        with self.lock:
            results = []
            proj = self.get_project(project_id)
            if not proj: return []
            base_path = proj['name'] + '/'
            tops = self.conn.execute("SELECT id FROM collections WHERE project_id=? AND parent_id IS NULL", (project_id,)).fetchall()
            for top in tops:
                results.extend(self.get_asset_ids_with_paths_for_collection(top['id'], base_path))
            return results

    def write_asset_to_zip(self, asset_id, zf, path_in_zip):
        """Streams an asset's data directly into a ZipFile object."""
        info = zipfile.ZipInfo(path_in_zip, time.localtime())
        info.compress_type = zipfile.ZIP_STORED
        with zf.open(info, 'w') as asset_file:
            for chunk in self.stream_asset_data(asset_id):
                asset_file.write(chunk)

    def create_project(self, name, type, description):
        with self.lock:
            try:
                cur = self.conn.cursor()
                cur.execute('INSERT INTO projects (name, type, description) VALUES (?, ?, ?)', (name, type, description))
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Create project error: {e}")
                raise

    def get_all_projects(self):
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM projects ORDER BY order_index ASC, name")
                return [dict(row) for row in cur.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Get all projects error: {e}")
                return []

    def create_collection(self, project_id, name, type, parent_id):
        with self.lock:
            try:
                cur = self.conn.cursor()
                cur.execute('INSERT INTO collections (project_id, name, type, parent_id) VALUES (?, ?, ?, ?)', (project_id, name, type, parent_id))
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Create collection error: {e}")
                raise

    def get_collections_for_project(self, project_id):
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM collections WHERE project_id = ? ORDER BY order_index ASC, name", (project_id,))
                return [dict(row) for row in cur.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Get collections for project error: {e}")
                return []

    def get_project(self, project_id):
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Get project error: {e}")
                return None

    def get_collection(self, collection_id):
        with self.lock:
            try:
                cur = self.conn.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Get collection error: {e}")
                return None

    def get_asset_preview(self, asset_id):
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
        <h1>Select a Vault</h1>
        <div id="file-list">
            {file_links}
        </div>
        <div class="new-vault">
            <input type="text" id="new-vault-name" placeholder="Enter new vault name">
            <button onclick="createDb()">Create New Vault</button>
        </div>
    </div>
    <script>
        function selectDb(db_name) {
            fetch('/api/select_db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ db: db_name })
            }).then(() => location.reload());
        }
        function createDb() {
            const name = document.getElementById('new-vault-name').value;
            if (name) {
                selectDb(name + '.vault');
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
.new-vault { margin-top: 1.5rem; }
#new-vault-name { padding: 0.5rem; border-radius: 4px; border: 1px solid #333; background: #222; color: #e0e0e0; }
button { padding: 0.5rem 1rem; border: none; border-radius: 4px; background-color: #1fb6ff; color: #121212; cursor: pointer; transition: background-color 0.2s; }
button:hover { background-color: #1ca0d3; }
"""

class RateLimiter:
    def __init__(self, requests_per_minute=60):
        self.requests_per_minute = requests_per_minute
        self.last_request = defaultdict(list)

    def is_allowed(self, ip):
        now = time.time()
        self.last_request[ip] = [t for t in self.last_request[ip] if now - t < 60]
        if len(self.last_request[ip]) >= self.requests_per_minute:
            return False
        self.last_request[ip].append(now)
        return True

class RequestHandler(http.server.BaseHTTPRequestHandler):
    rate_limiter = RateLimiter(requests_per_minute=300)
    routes = {
        'GET': [
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
            (r'^/api/projects$', 'api_create_project'),
            (r'^/api/collections$', 'api_create_collection'),
            (r'^/api/upload/chunk$', 'api_upload_chunk'),
            (r'^/api/upload/complete$', 'api_complete_upload'),
            (r'^/api/maintenance/vacuum$', 'api_vacuum'),
            (r'^/api/select_db$', 'api_select_db'),
            (r'^/api/collections/(\d+)/assets/download$', 'handle_bulk_download'),
        ],
    }

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    def check_auth(self):
        auth = self.headers.get('Authorization')
        if not auth: return False
        scheme, credentials = auth.split(maxsplit=1)
        if scheme.lower() != 'basic': return False
        username, password = base64.b64decode(credentials).decode().split(':', maxsplit=1)
        return password == HARDCODED_PASSWORD

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def handle_one_request(self):
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

            ip = self.client_address[0]
            if not (self.path.startswith('/api/upload/chunk') or self.path.startswith('/api/upload/complete')):
                if not self.rate_limiter.is_allowed(ip):
                    self.requestline = ""
                    self.send_error(429, "Too Many Requests")
                    return
            # Skip auth check when no manager is set (initial DB selection)
            if self.command != 'OPTIONS' and not (not self.server.app_state["manager"] and (self.path == '/' or self.path.startswith('/api/select_db'))):
                if not self.check_auth():
                    self.send_response(401)
                    self.send_header('WWW-Authenticate', 'Basic realm="CompactVault"')
                    self.end_headers()
                    return

            mname = 'do_' + self.command
            if hasattr(self, mname):
                getattr(self, mname)()
            self.wfile.flush()
        except socket.timeout as e:
            self.log_error("Request timed out: %r", e)

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, default=str).encode('utf-8')
        headers = {'Content-Type':'application/json'}
        self._send_compressed(data, code, headers)

    def _send_raw(self, data, status=200, headers=None):
        headers = headers or {}
        self._send_compressed(data, status, headers)

    def _send_compressed(self, data, code, headers):
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

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header('Access-control-allow-methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type,Range,Authorization')
        self.end_headers()

    def require_manager(self):
        if not self.server.app_state.get("manager"):
            self._send_json({"message": "No database selected"}, 400)
            return False
        return True

    def route_request(self, method):
        for pattern, handler_name in self.routes.get(method, []):
            m = re.match(pattern, self.path.split('?')[0])
            if m:
                handler = getattr(self, handler_name)
                handler(*m.groups())
                return
        self.send_error(404)

    def do_GET(self):
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

    def do_POST(self):
        self.route_request('POST')

    def show_db_selector(self):
        files = [f for f in os.listdir('.') if f.endswith('.vault')]
        file_links = ' '.join(f'<a href="#" onclick="selectDb(\'{f}\')">{f}</a>' for f in files)
        html = HTML_SELECTOR_TEMPLATE.replace('{css}', CSS_SELECTOR_STYLES).replace('{file_links}', file_links)
        self._send_raw(html.encode('utf-8'), headers={'Content-Type': 'text/html'})

    def api_get_all_projects(self):
        if not self.require_manager(): return
        self._send_json(self.server.app_state["manager"].get_all_projects())

    def api_get_project(self, project_id_str):
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

    def api_create_project(self):
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

    def api_get_project_collections(self, project_id_str):
        if not self.require_manager(): return
        try:
            project_id = int(project_id_str)
            self._send_json(self.server.app_state["manager"].get_collections_for_project(project_id))
        except ValueError:
            self._send_json({'message': 'Invalid project ID'}, 400)

    def api_get_collection(self, collection_id_str):
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

    def api_create_collection(self):
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

    def api_get_collection_assets(self, collection_id_str):
        if not self.require_manager(): return
        try:
            collection_id = int(collection_id_str)
            qs = parse_qs(urlparse(self.path).query)
            offset = int(qs.get('offset', [0])[0])
            limit = int(qs.get('limit', [50])[0])
            tag = qs.get('tag', [None])[0]
            query = qs.get('query', [None])[0]
            self._send_json(self.server.app_state["manager"].get_assets_for_collection(collection_id, offset, limit, tag, query))
        except ValueError:
            self._send_json({'message': 'Invalid collection ID'}, 400)

    def handle_asset_preview(self, asset_id_str):
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

    def handle_asset_download(self, asset_id_str):
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

    def handle_bulk_download(self, collection_id_str):
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

    def api_vacuum(self):
        if not self.require_manager(): return
        self.server.app_state["manager"].vacuum()
        self._send_json({'message': 'VACUUM complete'})

    def api_select_db(self):
        try:
            length = int(self.headers.get('content-length'))
            body = json.loads(self.rfile.read(length))
            db_name = body.get('db')
            if db_name and db_name.endswith('.vault'):
                self.server.app_state["db_path"] = db_name
                self.server.app_state["manager"] = CompactVaultManager(db_name)
                self.server.app_state["rendered_html"] = HTML_TEMPLATE.replace('{css}', CSS_STYLES).replace('{js}', JAVASCRIPT_CODE).encode('utf-8')
                self._send_json({'message': f'Switched to {db_name}'})
            else:
                self._send_json({'message': 'Invalid DB name'}, 400)
        except Exception as e:
            self._send_json({'message': f'DB switch failed: {e}'}, 500)

    def api_upload_chunk(self):
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

    def api_complete_upload(self):
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

    def api_download_project(self, project_id_str):
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

    def api_download_collection(self, collection_id_str):
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

def run(server_class=ThreadedHTTPServer, handler_class=RequestHandler, port=8000):
    # Server state
    db_path = None
    manager = None
    rendered_html = None

    # Check for existing vaults
    vaults = [f for f in os.listdir('.') if f.endswith('.vault')]
    if not vaults:
        logging.info("No vaults found, creating 'default.vault'")
        db_path = "default.vault"
        manager = CompactVaultManager(db_path)

    if manager:
        rendered_html = HTML_TEMPLATE.replace('{css}', CSS_STYLES).replace('{js}', JAVASCRIPT_CODE).encode('utf-8')

    server_class.app_state = {
        "db_path": db_path,
        "manager": manager,
        "rendered_html": rendered_html
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
    def signal_handler(sig, frame):
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
