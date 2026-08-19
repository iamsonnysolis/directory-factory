/* Dashboard client-side JS — vanilla, no frameworks */
/* Handles: modal, tab switching, polling, toasts, API calls */

(function() {
  'use strict';

  // ─── Toast system ───────────────────────────────────────────────────────
  const toastContainer = document.getElementById('toast-container');

  window.showToast = function(message, type, detail) {
    type = type || 'success';
    if (!toastContainer) return;
    // Remove any existing progress/info toast to avoid stacking
    if (type === 'info' || type === 'collection-progress') {
      const existing = toastContainer.querySelector('.toast-collection-progress');
      if (existing) existing.remove();
    }
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type + (type === 'info' || type === 'collection-progress' ? ' toast-collection-progress' : '');
    const icon = type === 'success' ? '✓' : (type === 'error' ? '✗' : type === 'info' ? 'ⓘ' : '!');
    let html = '<strong>' + icon + '</strong><span>' + message + '</span>';
    if (detail) {
      const detailEl = document.createElement('div');
      detailEl.className = 'toast-detail';
      detailEl.textContent = detail;
      html += detailEl.outerHTML;
    }
    toast.innerHTML = html;
    toastContainer.appendChild(toast);
    // Info/progress toasts stay longer; error/success fade after 6s
    const duration = (type === 'info' || type === 'collection-progress') ? 30000 : 6000;
    toast._autoRemove = setTimeout(function() { toast.remove(); }, duration);
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

  // Tag input for search terms — mobile-friendly
  const tagInput = document.getElementById('search-terms-input');
  const tagContainer = document.getElementById('search-terms-tags');

  function addTag() {
    if (!tagInput || !tagContainer) return;
    const tag = tagInput.value.trim();
    if (!tag) return;
    const span = document.createElement('span');
    span.className = 'tag';
    span.textContent = tag;
    span.onclick = function() { span.remove(); updateHiddenInput(); updateAddSearchTermState(); };
    tagContainer.appendChild(span);
    tagInput.value = '';
    updateHiddenInput();
    updateAddSearchTermState();
  }

  function updateAddSearchTermState() {
    // Update the Add button state based on input
    const addBtn = document.getElementById('add-search-term');
    const errorEl = document.getElementById('search-terms-error');
    const tags = tagContainer ? tagContainer.querySelectorAll('.tag') : [];
    if (addBtn) {
      addBtn.style.opacity = tagInput.value.trim() ? '1' : '0.5';
    }
    // Clear error if tags exist
    if (tags.length > 0 && errorEl) {
      errorEl.style.display = 'none';
    }
  }

  if (tagInput && tagContainer) {
    tagInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && this.value.trim()) {
        e.preventDefault();
        addTag();
      }
    });
    // Add button — works on mobile regardless of virtual keyboard behavior
    const addBtn = document.getElementById('add-search-term');
    if (addBtn) {
      addBtn.addEventListener('click', addTag);
    }
    // Update button state on input
    tagInput.addEventListener('input', updateAddSearchTermState);
  }

  function updateHiddenInput() {
    const hidden = document.getElementById('search_terms');
    if (!hidden) return;
    const tags = Array.from(tagContainer ? tagContainer.querySelectorAll('.tag') : [])
      .map(function(el) { return el.textContent; });
    // Store tags as a simple comma-separated value (backend expects array from JSON body)
    hidden.value = tags.join(',');
  }

  // ─── Create Directory form submit ───────────────────────────────────────
  const createForm = document.getElementById('create-directory-form');
  if (createForm) {
    createForm.addEventListener('submit', async function(e) {
      e.preventDefault();
      updateHiddenInput();

      // Validate: at least one search term required
      const tags = tagContainer ? tagContainer.querySelectorAll('.tag') : [];
      const errorEl = document.getElementById('search-terms-error');
      if (tags.length === 0) {
        if (errorEl) errorEl.style.display = 'block';
        tagInput.focus();
        return;
      }
      if (errorEl) errorEl.style.display = 'none';

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
        search_terms: Array.from(tagContainer ? tagContainer.querySelectorAll('.tag') : [])
          .map(function(el) { return el.textContent; }),
        target_metros: metros,
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
  // The API now runs scripts as background tasks, so we get an immediate
  // "started" response and poll for completion via the directory API
  window.runPipelineStage = async function(scriptName, directoryId, params) {
    const btn = event ? event.target : null;
    if (btn) {
      btn.disabled = true;
      btn.dataset.originalText = btn.textContent;
      btn.textContent = 'Starting…';
    }

    try {
      const resp = await fetch('/api/directories/' + directoryId + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_name: scriptName, params: params || {} }),
      });
      const data = await resp.json();

      if (data.status === 'started' || data.status === 'success') {
        // Start collection progress polling if this is a collection run
        if (scriptName === 'collection.collect') {
          startCollectionProgressPolling(directoryId);
        }
        showToast(scriptName + ' started', 'success', 'Running in background — progress updates below');
      } else {
        showToast(scriptName + ' failed', 'error', (data.error || data.detail || 'Unknown error').substring(0, 500));
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
  let collectionPollInterval = null;
  let lastProgressPct = -1;
  let progressToastTimeout = null;

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

  // ─── Collection progress polling ──────────────────────────────────────────
  // Polls /api/directories/{id}/collection-progress when collection is running.
  // Shows a persistent toast with live progress (jobs done, places found).
  function startCollectionProgressPolling(directoryId) {
    if (collectionPollInterval) {
      clearInterval(collectionPollInterval);
    }
    let progressToast = null;

    function clearProgressToast() {
      if (progressToastTimeout) {
        clearTimeout(progressToastTimeout);
        progressToastTimeout = null;
      }
      // Don't remove — keep it until collection is done
    }

    collectionPollInterval = setInterval(async function() {
      try {
        const resp = await fetch('/api/directories/' + directoryId + '/collection-progress');
        const data = await resp.json();

        // Only update toast while collection is running
        if (data.project_status === 'running' || data.project_status === 'complete') {
          const pct = data.total_jobs > 0 ? Math.round((data.complete / data.total_jobs) * 100) : 0;

          // Show toast only when progress changes (avoid spam)
          if (pct !== lastProgressPct) {
            lastProgressPct = pct;
            const msg = 'Collection: ' + data.complete + '/' + data.total_jobs + ' jobs done (' + pct + '%)';
            const detail = data.complete + ' jobs • ' + data.failed + ' failed • ' + data.places_collected + ' places found • ' + data.running + ' in progress';

            // Show a persistent info toast
            showToast(msg, 'info', detail);
          }

          // If collection is complete, stop polling
          if (data.project_status === 'complete' && data.pending === 0 && data.running === 0) {
            clearInterval(collectionPollInterval);
            collectionPollInterval = null;
            showToast('Collection complete!', 'success', data.places_collected + ' places collected from ' + data.complete + ' jobs');
          }
        }
      } catch(e) {
        // Silently fail — polling will retry
      }
    }, 2000);
  }

  window.startPolling = startPolling;
  window.stopPolling = stopPolling;
  window.startCollectionProgressPolling = startCollectionProgressPolling;

  // Start polling on Directory Detail page
  const dirDetailDirId = typeof DIRECTORY_ID !== 'undefined' ? DIRECTORY_ID : null;
  if (dirDetailDirId) {
    startPolling(dirDetailDirId);

    // If collection is already running, start progress polling so the user
    // sees live updates even if they navigated to the page after collection started
    setTimeout(function() {
      fetch('/api/directories/' + dirDetailDirId + '/collection-progress')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.project_status === 'running' && data.total_jobs > 0) {
            startCollectionProgressPolling(dirDetailDirId);
          }
        })
        .catch(function() { /* ignore — polling will retry */ });
    }, 500);
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
  // The ONE AND ONLY confirm dialog in the entire UI (per spec)
  const deleteModal = document.getElementById('delete-confirm-modal');
  const deleteBtn = document.getElementById('delete-directory');
  const cancelDeleteBtn = document.getElementById('cancel-delete');
  const confirmDeleteBtn = document.getElementById('confirm-delete');

  if (deleteBtn && deleteModal) {
    deleteBtn.addEventListener('click', function() {
      var dirName = deleteBtn.dataset.name || 'this directory';
      var nameEl = document.getElementById('delete-dir-name');
      if (nameEl) nameEl.textContent = dirName;
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

  // ─── Data tab loaders ───────────────────────────────────────────────────
  // Each tab has a search input, filter controls, table body, and pagination bar.
  // Loaders are auto-triggered when the tab is clicked (lazy load).

  var loadedTabs = {};

  function loadDataTable(tabName, options) {
    var tbody = document.getElementById(tabName + '-table-body');
    if (!tbody) return;
    var searchInput = document.getElementById(tabName + '-search');
    var offset = 0;
    var limit = 100;
    // Map tab names to API endpoints
    var endpointMap = {
      collected: 'places',
      cleaned: 'cleaned',
      enriched: 'enriched'
    };
    var apiPath = endpointMap[tabName] || tabName;

    async function fetchPage() {
      var search = searchInput ? searchInput.value : '';
      var params = { search: search, limit: limit, offset: offset };
      if (options && options.minCompleteness) {
        params.min_completeness = document.getElementById(tabName + '-completeness').value;
      }
      if (options && options.minQuality) {
        params.min_quality = document.getElementById(tabName + '-quality').value;
      }

      var qs = Object.keys(params).map(function(k) {
        return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
      }).join('&');

      try {
        console.log('fetchPage: fetching ' + apiPath + ' for ' + tabName);
        var resp = await fetch('/api/directories/' + DIRECTORY_ID + '/' + apiPath + '?' + qs);
        var data = await resp.json();
        // Handle both 'places' and 'records' response formats
        var recs = data.records || data.places || [];
        tbody.innerHTML = renderTableRows(tabName, recs);
        renderPagination(tabName, data.total || recs.length, data.limit, data.offset);
      } catch(e) {
        tbody.innerHTML = '<tr><td colspan="10" class="loading-row">Error loading data</td></tr>';
      }
    }

    function renderTableRows(tabName, records) {
      if (tabName === 'collected') {
        return records.map(function(r) {
          return '<tr><td>' + (r.display_name || '') + '</td><td>' + (r.formatted_address || '') + '</td><td>' + (r.search_term || '') + '</td><td>' + (r.data_completeness_score || 0) + '%</td><td>' + (r.created_at || '') + '</td></tr>';
        }).join('') || '<tr><td colspan="5" class="loading-row">No collected places found</td></tr>';
      }
      if (tabName === 'cleaned') {
        return records.map(function(r) {
          return '<tr><td>' + (r.name || '') + '</td><td>' + (r.address || '') + '</td><td>' + (r.suburb_name || '') + '</td><td>' + (r.state_code || '') + '</td><td>' + (r.data_completeness_score || 0) + '%</td><td>' + (r.phone || '') + '</td><td>' + (r.website || '') + '</td><td>' + (r.rating || '') + '</td></tr>';
        }).join('') || '<tr><td colspan="8" class="loading-row">No cleaned data yet — run the Clean stage</td></tr>';
      }
      if (tabName === 'enriched') {
        return records.map(function(r) {
          return '<tr><td>' + (r.name || '') + '</td><td>' + (r.address || '') + '</td><td>' + (r.suburb_name || '') + '</td><td>' + (r.quality_score || 0) + '</td><td>' + (r.phone || '') + '</td><td>' + (r.website || '') + '</td><td>' + (r.rating || '') + '</td><td>' + (r.ai_generated ? '✓' : '—') + '</td></tr>';
        }).join('') || '<tr><td colspan="8" class="loading-row">No enriched data yet — run the Enrich stage</td></tr>';
      }
      return '';
    }

    function renderPagination(tabName, total, lim, off) {
      var bar = document.getElementById(tabName + '-pagination');
      if (!bar) return;
      var start = off + 1;
      var end = Math.min(off + lim, total);
      var prevDisabled = off === 0;
      var nextDisabled = off + lim >= total;
      var prevBtn = prevDisabled ? '<span class="page-btn disabled">←</span>' : '<button class="page-btn" onclick="loadDataTableNav(\'' + tabName + '\', -1)">←</button>';
      var nextBtn = nextDisabled ? '<span class="page-btn disabled">→</span>' : '<button class="page-btn" onclick="loadDataTableNav(\'' + tabName + '\', 1)">→</button>';
      bar.innerHTML = '<span class="page-info">' + (total > 0 ? start + '–' + end + ' of ' + total : 'No results') + '</span>' + prevBtn + nextBtn;
    }

    // Expose navigation for pagination buttons
    window.loadDataTableNav = function(tab, direction) {
      var newOffset = offset + (direction * limit);
      if (newOffset < 0 || newOffset >= loadedTabs[tab].total) return;
      offset = newOffset;
      loadedTabs[tab].offset = offset;
      fetchPage();
    };

    // Expose for refresh buttons
    window.loadDataTableRefresh = function(tab) {
      offset = 0;
      loadedTabs[tab].offset = offset;
      fetchPage();
    };

    if (searchInput) {
      searchInput.addEventListener('input', function() { setTimeout(function() { offset = 0; loadedTabs[tabName].offset = 0; fetchPage(); }, 300); });
    }
    if (options && options.minCompleteness) {
      var compInput = document.getElementById(tabName + '-completeness');
      var compVal = document.getElementById(tabName + '-completeness-val');
      if (compInput && compVal) {
        compInput.addEventListener('input', function() {
          compVal.textContent = this.value + '%';
          setTimeout(function() { offset = 0; loadedTabs[tabName].offset = 0; fetchPage(); }, 300);
        });
      }
    }
    if (options && options.minQuality) {
      var qInput = document.getElementById(tabName + '-quality');
      var qVal = document.getElementById(tabName + '-quality-val');
      if (qInput && qVal) {
        qInput.addEventListener('input', function() {
          qVal.textContent = this.value + '+';
          setTimeout(function() { offset = 0; loadedTabs[tabName].offset = 0; fetchPage(); }, 300);
        });
      }
    }

    loadedTabs[tabName] = { offset: offset, total: 0 };
    console.log('loadDataTable: ' + tabName + ' starting fetchPage');
    fetchPage();
  }

  // Lazy-load data when a tab is clicked
  document.addEventListener('click', function(e) {
    var tab = e.target.closest('.tab');
    if (!tab) return;
    var tabName = tab.dataset.tab;
    if (tabName === 'collected' && !loadedTabs.collected) {
      loadDataTable('collected', { minCompleteness: false });
    }
    if (tabName === 'cleaned' && !loadedTabs.cleaned) {
      loadDataTable('cleaned', { minCompleteness: true });
    }
    if (tabName === 'enriched' && !loadedTabs.enriched) {
      loadDataTable('enriched', { minQuality: true });
    }
  });

  // Refresh buttons for data tabs
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-action]');
    if (!btn) return;
    var action = btn.getAttribute('data-action');
    if (action === 'refresh-collected') { window.loadDataTableRefresh('collected'); }
    if (action === 'refresh-cleaned') { window.loadDataTableRefresh('cleaned'); }
    if (action === 'refresh-enriched') { window.loadDataTableRefresh('enriched'); }
  });

  // Auto-load all data tabs on page load so users see data immediately
  // without having to click each tab first
  if (typeof DIRECTORY_ID !== 'undefined') {
    if (document.getElementById('collected-table-body')) {
      loadDataTable('collected', { minCompleteness: false });
    }
    if (document.getElementById('cleaned-table-body')) {
      loadDataTable('cleaned', { minCompleteness: true });
    }
    if (document.getElementById('enriched-table-body')) {
      loadDataTable('enriched', { minQuality: true });
    }
  }

  // ─── Load places on Collect tab (legacy) ─────────────────────────────────

  // ─── Overview: Card action button (always navigates to detail page) ─────────
  // Per spec: button label is always "View Project", consistent color, no stage logic
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.card-action-btn');
    if (!btn) return;
    var dirId = btn.dataset.dirId;
    if (dirId) {
      window.location.href = '/directories/' + dirId;
    }
  });

  // ─── Overview: Search/Filter/Sort ────────────────────────────────────────
  // ─── Filter/Sort logic removed — search, filter, and sort dropdowns were removed from the UI ───

  // ─── Top bar hamburger toggle (mobile) ─────────────────────────────────────
  var hamburger = document.getElementById('hamburger');
  var topBarNav = document.getElementById('top-bar-nav');
  var navOverlay = document.getElementById('nav-overlay');
  if (hamburger && topBarNav && navOverlay) {
    function toggleNav() {
      var open = topBarNav.classList.contains('open');
      if (open) {
        topBarNav.classList.remove('open');
        hamburger.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
        navOverlay.classList.remove('active');
      } else {
        topBarNav.classList.add('open');
        hamburger.classList.add('open');
        hamburger.setAttribute('aria-expanded', 'true');
        navOverlay.classList.add('active');
      }
    }
    hamburger.addEventListener('click', toggleNav);
    navOverlay.addEventListener('click', toggleNav);
    // Close menu when a nav link is clicked
    topBarNav.addEventListener('click', function(e) {
      if (e.target.tagName === 'A') {
        toggleNav();
      }
    });
  }

})();
