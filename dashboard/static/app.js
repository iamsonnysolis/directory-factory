/* Dashboard client-side JS — vanilla, no frameworks */
/* Handles: modal, tab switching, polling, toasts, API calls */

(function() {
  'use strict';

  // ─── Toast system ───────────────────────────────────────────────────────
  const toastContainer = document.getElementById('toast-container');

  window.showToast = function(message, type, detail) {
    type = type || 'success';
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    const icon = type === 'success' ? '✓' : (type === 'error' ? '✗' : '!');
    let html = '<strong>' + icon + '</strong><span>' + message + '</span>';
    if (detail) {
      const detailEl = document.createElement('div');
      detailEl.className = 'toast-detail';
      detailEl.textContent = detail;
      html += detailEl.outerHTML;
    }
    toast.innerHTML = html;
    toastContainer.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 6000);
  };

  // ─── New Directory Modal ────────────────────────────────────────────────
  const modal = document.getElementById('new-directory-modal');
  const openBtns = document.querySelectorAll('#open-new-directory, #open-new-directory-2');
  const closeModalBtn = document.getElementById('close-modal');
  const cancelModalBtn = document.getElementById('cancel-modal');

  function toggleNewDirectoryModal(show) {
    if (!modal) return;
    modal.classList.toggle('active', show);
  }

  openBtns.forEach(function(btn) { if (btn) btn.addEventListener('click', function() { toggleNewDirectoryModal(true); }); });
  if (closeModalBtn) closeModalBtn.addEventListener('click', function() { toggleNewDirectoryModal(false); });
  if (cancelModalBtn) cancelModalBtn.addEventListener('click', function() { toggleNewDirectoryModal(false); });

  // Close modal on Escape / click outside
  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) toggleNewDirectoryModal(false);
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') toggleNewDirectoryModal(false);
    });
  }

  // Auto-generate slug from name
  const nameInput = document.getElementById('dir-name');
  const slugInput = document.getElementById('dir-slug');
  if (nameInput && slugInput) {
    nameInput.addEventListener('input', function() {
      if (!slugInput._manualEdit) {
        slugInput.value = this.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      }
    });
    slugInput.addEventListener('input', function() {
      slugInput._manualEdit = true;
    });
  }

  // Tag input for search terms
  const tagInput = document.getElementById('search-terms-input');
  const tagContainer = document.getElementById('search-terms-tags');
  if (tagInput && tagContainer) {
    tagInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && this.value.trim()) {
        e.preventDefault();
        const tag = this.value.trim();
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = tag;
        span.onclick = function() { span.remove(); updateHiddenInput(); };
        tagContainer.appendChild(span);
        this.value = '';
        updateHiddenInput();
      }
    });
  }

  function updateHiddenInput() {
    const hidden = document.getElementById('search_terms');
    if (!hidden) return;
    const tags = Array.from(tagContainer ? tagContainer.querySelectorAll('.tag') : [])
      .map(function(el) { return el.textContent; });
    hidden.value = JSON.stringify(tags);
  }

  // ─── Create Directory form submit ───────────────────────────────────────
  const createForm = document.getElementById('create-directory-form');
  if (createForm) {
    createForm.addEventListener('submit', async function(e) {
      e.preventDefault();
      updateHiddenInput();

      // Collect metro checkboxes
      const metroChecks = document.querySelectorAll('input[name="target_metros"]:checked');
      const metros = Array.from(metroChecks).map(function(c) { return c.value; });

      const formData = new FormData(this);
      const payload = {
        name: formData.get('name'),
        slug: formData.get('slug'),
        niche_label: formData.get('niche_label'),
        field_tier: formData.get('field_tier'),
        search_step_km: parseInt(formData.get('search_step_km') || '10'),
        search_terms: formData.get('search_terms'),
        target_metros: JSON.stringify(metros),
        domain: formData.get('domain'),
      };

      try {
        const resp = await fetch('/api/directories', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (resp.ok && data.success) {
          showToast('Created "' + payload.name + '"', 'success');
          toggleNewDirectoryModal(false);
          window.location.href = '/directories/' + data.directory_id;
        } else {
          var errDetail;
          if (data.detail) {
            // Pydantic validation error
            if (Array.isArray(data.detail)) {
              errDetail = data.detail.map(function(d) {
                return d.loc.join('.') + ': ' + d.msg;
              }).join('\n');
            } else {
              errDetail = data.detail;
            }
          } else {
            errDetail = data.message || 'Unknown error';
          }
          showToast('Failed to create "' + payload.name + '"', 'error', errDetail);
        }
      } catch(err) {
        showToast('Network error', 'error');
      }
    });
  }

  // ─── Tab switching ──────────────────────────────────────────────────────
  const tabButtons = document.querySelectorAll('.tab');
  tabButtons.forEach(function(btn) {
    btn.addEventListener('click', function() {
      const thisBtn = btn;
      const tabName = thisBtn.dataset.tab;
      tabButtons.forEach(function(b) { b.classList.toggle('active', b === thisBtn); });
      document.querySelectorAll('.tab-panel').forEach(function(panel) {
        panel.classList.toggle('active', panel.id === 'tab-' + tabName);
      });
    });
  });

  // ─── Run pipeline stage ─────────────────────────────────────────────────
  // Called from the Directory Detail tabs — triggers a script via the runner
  window.runPipelineStage = async function(scriptName, directoryId, params) {
    const btn = event ? event.target : null;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Running…';
    }

    try {
      const resp = await fetch('/api/directories/' + directoryId + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_name: scriptName, params: params || {} }),
      });
      const data = await resp.json();

      if (data.status === 'success') {
        showToast(data.summary || (scriptName + ' completed'), 'success');
        // Reload the page to pick up new run data
        setTimeout(function() { window.location.reload(); }, 1000);
      } else {
        showToast(scriptName + ' failed', 'error', (data.error || 'Unknown error').substring(0, 500));
      }
    } catch(err) {
      showToast('Network error', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || 'Run';
      }
    }
  };

  // ─── Polling for running stages ─────────────────────────────────────────
  let pollInterval = null;

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  function startPolling(directoryId) {
    stopPolling();
    pollInterval = setInterval(async function() {
      try {
        const resp = await fetch('/api/directories/' + directoryId);
        const data = await resp.json();
        document.dispatchEvent(new CustomEvent('pipeline-update', { detail: data }));
      } catch(e) {
        // Silently fail — polling will retry
      }
    }, 3000);
  }

  window.startPolling = startPolling;
  window.stopPolling = stopPolling;

  // Start polling on Directory Detail page
  const dirDetailDirId = typeof DIRECTORY_ID !== 'undefined' ? DIRECTORY_ID : null;
  if (dirDetailDirId) {
    startPolling(dirDetailDirId);
  }

  // ─── Expandable log viewer ──────────────────────────────────────────────
  document.addEventListener('click', function(e) {
    const btn = e.target.closest('[data-action="toggle-log"]');
    if (btn) {
      const logEl = btn.parentElement.querySelector('.log-view');
      if (logEl) {
        const isCollapsed = logEl.style.display === 'none';
        logEl.style.display = isCollapsed ? 'block' : 'none';
        btn.textContent = isCollapsed ? '▴ Hide log' : '▾ View full log';
      }
    }
  });

  // ─── View run log ───────────────────────────────────────────────────────
  window.viewRunLog = async function(runId) {
    try {
      const resp = await fetch('/api/runs/' + runId);
      const data = await resp.json();
      const logContent = data.stdout || '';
      alert('Run #' + runId + '\n\n' + logContent.substring(0, 2000) + '...');
    } catch(e) {
      showToast('Failed to load run log', 'error');
    }
  };

  // ─── Delete confirmation ─────────────────────────────────────────────────
  const deleteModal = document.getElementById('delete-confirm-modal');
  const deleteBtn = document.getElementById('delete-directory');
  const cancelDeleteBtn = document.getElementById('cancel-delete');
  const confirmDeleteBtn = document.getElementById('confirm-delete');

  if (deleteBtn && deleteModal) {
    deleteBtn.addEventListener('click', function() {
      deleteModal.classList.add('active');
    });
  }
  if (cancelDeleteBtn && deleteModal) {
    cancelDeleteBtn.addEventListener('click', function() {
      deleteModal.classList.remove('active');
    });
  }
  if (confirmDeleteBtn && deleteModal) {
    confirmDeleteBtn.addEventListener('click', async function() {
      const dirId = deleteBtn ? deleteBtn.dataset.id : null;
      if (!dirId) return;
      try {
        const resp = await fetch('/api/directories/' + dirId, { method: 'DELETE' });
        const data = await resp.json();
        if (data.success) {
          showToast('Directory deleted', 'success');
          window.location.href = '/';
        }
      } catch(e) {
        showToast('Delete failed: ' + e.message, 'error');
      }
      deleteModal.classList.remove('active');
    });
  }

  // ─── Settings test credentials ──────────────────────────────────────────
  document.addEventListener('click', function(e) {
    const btn = e.target.closest('[data-action="test-credential"]');
    if (btn) {
      const key = btn.dataset.key;
      btn.disabled = true;
      btn.textContent = 'Testing…';
      fetch('/api/settings/test/' + key, { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          btn.disabled = false;
          btn.textContent = 'Test';
          if (data.valid) {
            showToast(key + ': ✓ Valid', 'success');
          } else {
            showToast(key + ': ✗ ' + data.message, 'error');
          }
        })
        .catch(function() {
          btn.disabled = false;
          btn.textContent = 'Test';
          showToast(key + ': Network error', 'error');
        });
    }
  });

  // ─── Settings save ──────────────────────────────────────────────────────
  const saveSettingsBtn = document.getElementById('save-settings');
  if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async function() {
      const formData = new FormData(document.getElementById('settings-form'));
      const settings = {};
      for (const [key, value] of formData.entries()) {
        settings[key] = value;
      }
      try {
        const resp = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(settings),
        });
        const data = await resp.json();
        const statusEl = document.getElementById('save-status');
        if (statusEl) statusEl.textContent = data.success ? 'Saved' : ('Error: ' + (data.message || 'Unknown'));
      } catch(e) {
        showToast('Save failed', 'error');
      }
    });
  }

  // ─── Config form save ───────────────────────────────────────────────────
  const configForm = document.getElementById('config-form');
  if (configForm) {
    configForm.addEventListener('submit', async function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      const config = {};
      for (const [key, value] of formData.entries()) {
        config[key] = value;
      }
      try {
        const resp = await fetch('/api/directories/' + DIRECTORY_ID + '/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        });
        const data = await resp.json();
        if (data.success) {
          showToast('Config saved', 'success');
        } else {
          showToast('Save failed', 'error');
        }
      } catch(e) {
        showToast('Network error', 'error');
      }
    });

    // Live preview for config form
    const colorInputs = configForm.querySelectorAll('input[type="text"]');
    colorInputs.forEach(function(input) {
      input.addEventListener('input', function() {
        const name = input.name;
        const value = input.value;
        const previewName = document.getElementById('preview-' + name);
        if (previewName) previewName.textContent = value || '—';

        if (name === 'theme_primary_color') {
          document.documentElement.style.setProperty('--color-primary', value);
        }
        if (name === 'theme_secondary_color') {
          document.documentElement.style.setProperty('--color-secondary', value);
        }
      });
    });
  }

  // ─── Load places on Collect tab ─────────────────────────────────────────
  function loadPlaces() {
    const searchInput = document.getElementById('places-search');
    const completenessInput = document.getElementById('min-completeness');
    const completenessVal = document.getElementById('completeness-val');
    const tbody = document.getElementById('places-table-body');

    if (!tbody) return;

    async function fetchPlaces() {
      const search = searchInput ? searchInput.value : '';
      const minComp = completenessInput ? completenessInput.value : 0;
      const resp = await fetch('/api/directories/' + DIRECTORY_ID + '/places?search=' + encodeURIComponent(search) + '&min_completeness=' + minComp + '&limit=100');
      const data = await resp.json();
      tbody.innerHTML = data.places.map(function(p) {
        return '<tr><td>' + p.display_name + '</td><td>' + (p.formatted_address || '') + '</td><td>' + (p.data_completeness_score || 0) + '%</td><td>' + (p.search_term || '') + '</td></tr>';
      }).join('');
    }

    if (searchInput) searchInput.addEventListener('input', function() { setTimeout(fetchPlaces, 300); });
    if (completenessInput) completenessInput.addEventListener('input', function() {
      if (completenessVal) completenessVal.textContent = completenessInput.value + '+';
      setTimeout(fetchPlaces, 300);
    });

    fetchPlaces();
  }

  loadPlaces();

})();
