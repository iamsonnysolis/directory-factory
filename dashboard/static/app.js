/* Dashboard client-side JS — vanilla, no frameworks */
/* Shared/global functionality: toasts, modals, overview page, settings page */

(function() {
  'use strict';

  // ─── Toast system ───────────────────────────────────────────────────────
  const toastContainer = document.getElementById('toast-container');

  window.showToast = function(message, type, detail) {
    type = type || 'success';
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
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
    // Info/error/success toasts fade after 6s
    const duration = 6000;
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
    const addBtn = document.getElementById('add-search-term');
    const errorEl = document.getElementById('search-terms-error');
    const tags = tagContainer ? tagContainer.querySelectorAll('.tag') : [];
    if (addBtn) {
      addBtn.style.opacity = tagInput.value.trim() ? '1' : '0.5';
    }
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
    const addBtn = document.getElementById('add-search-term');
    if (addBtn) {
      addBtn.addEventListener('click', addTag);
    }
    tagInput.addEventListener('input', updateAddSearchTermState);
  }

  function updateHiddenInput() {
    const hidden = document.getElementById('search_terms');
    if (!hidden) return;
    const tags = Array.from(tagContainer ? tagContainer.querySelectorAll('.tag') : [])
      .map(function(el) { return el.textContent; });
    hidden.value = tags.join(',');
  }

  // ─── Create Directory form submit ───────────────────────────────────────
  const createForm = document.getElementById('create-directory-form');
  if (createForm) {
    createForm.addEventListener('submit', async function(e) {
      e.preventDefault();
      updateHiddenInput();

      const tags = tagContainer ? tagContainer.querySelectorAll('.tag') : [];
      const errorEl = document.getElementById('search-terms-error');
      if (tags.length === 0) {
        if (errorEl) errorEl.style.display = 'block';
        tagInput.focus();
        return;
      }
      if (errorEl) errorEl.style.display = 'none';

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

  // ─── Tab switching (shared by overview page) ─────────────────────────────
  document.addEventListener('click', function(e) {
    var tab = e.target.closest('.tab');
    if (!tab) return;
    var tabName = tab.dataset.tab;
    // Find sibling tabs within the same tab bar
    var tabBar = tab.closest('.tab-bar');
    if (tabBar) {
      tabBar.querySelectorAll('.tab').forEach(function(t) {
        t.classList.toggle('active', t === tab);
      });
      var panels = tabBar.nextElementSibling;
      if (panels && panels.classList.contains('tab-panels')) {
        panels.querySelectorAll('.tab-panel').forEach(function(panel) {
          panel.classList.toggle('active', panel.id === 'tab-' + tabName);
        });
      }
    }
  });

  // ─── Overview: Card action button ───────────────────────────────────────
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.card-action-btn');
    if (!btn) return;
    var dirId = btn.dataset.dirId;
    if (dirId) {
      window.location.href = '/directories/' + dirId;
    }
  });

  // ─── Settings test credentials ──────────────────────────────────────────
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-action="test-credential"]');
    if (!btn) return;
    var key = btn.dataset.key;
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
  });

  // ─── Settings save ──────────────────────────────────────────────────────
  var saveSettingsBtn = document.getElementById('save-settings');
  if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async function() {
      var formData = new FormData(document.getElementById('settings-form'));
      var settings = {};
      for (var [key, value] of formData.entries()) {
        settings[key] = value;
      }
      try {
        var resp = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(settings),
        });
        var data = await resp.json();
        var statusEl = document.getElementById('save-status');
        if (statusEl) statusEl.textContent = data.success ? 'Saved' : ('Error: ' + (data.message || 'Unknown'));
      } catch(e) {
        showToast('Save failed', 'error');
      }
    });
  }

  // ─── Top bar hamburger toggle (mobile) ──────────────────────────────────
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
    topBarNav.addEventListener('click', function(e) {
      if (e.target.tagName === 'A') {
        toggleNav();
      }
    });
  }

})();
