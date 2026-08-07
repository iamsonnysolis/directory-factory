/* Dashboard client-side JS — vanilla, no frameworks */
/* Handles: modal, tab switching, polling, toasts, API calls */

(function() {
  'use strict';

  // ─── Toast system ───────────────────────────────────────────────────────
  const toastContainer = document.getElementById('toast-container');

  window.showToast = function(message, type = 'success') {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<strong>${type === 'success' ? '✓' : '✗'}</strong><span>${message}</span>`;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  };

  // ─── New Directory Modal ────────────────────────────────────────────────
  const modal = document.getElementById('new-directory-modal');
  const openBtn = document.getElementById('open-new-directory');
  const closeBtn = document.getElementById('close-modal');
  const cancelBtn = document.getElementById('cancel-modal');

  function toggleModal(show) {
    if (!modal) return;
    modal.classList.toggle('active', show);
  }

  if (openBtn) openBtn.addEventListener('click', () => toggleModal(true));
  if (closeBtn) closeBtn.addEventListener('click', () => toggleModal(false));
  if (cancelBtn) cancelBtn.addEventListener('click', () => toggleModal(false));

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
        span.ontouchend = () => span.remove();
        span.onclick = () => span.remove();
        tagContainer.appendChild(span);
        this.value = '';
        updateHidden('search_terms');
      }
    });
  }

  function updateHidden(hiddenId) {
    const hidden = document.getElementById(hiddenId);
    if (!hidden) return;
    const tags = Array.from(tagContainer ? tagContainer.querySelectorAll('.tag') : [])
      .map(el => el.textContent);
    hidden.value = JSON.stringify(tags);
  }

  // ─── Create Directory form submit ───────────────────────────────────────
  const createForm = document.getElementById('create-directory-form');
  if (createForm) {
    createForm.addEventListener('submit', async function(e) {
      e.preventDefault();
      updateHidden('search_terms');
      const formData = new FormData(this);
      const params = new URLSearchParams();
      for (const [key, value] of formData.entries()) {
        params.append(key, value);
      }
      try {
        const resp = await fetch('/api/projects', { method: 'POST', body: params });
        const data = await resp.json();
        if (data.success) {
          window.showToast(`Created "${formData.get('name')}"`, 'success');
          toggleModal(false);
          window.location.href = `/directories/${data.project_id}`;
        } else {
          window.showToast(data.message || 'Creation failed', 'error');
        }
      } catch(err) {
        window.showToast('Network error', 'error');
      }
    });
  }

  // ─── Tab switching ──────────────────────────────────────────────────────
  const tabButtons = document.querySelectorAll('.tab');
  tabButtons.forEach(btn => {
    btn.addEventListener('click', function() {
      const tabName = this.dataset.tab;
      // Update active tab button
      tabButtons.forEach(b => b.classList.toggle('active', b === this));
      // Show active panel
      document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === `tab-${tabName}`);
      });
    });
  });

  // ─── Run script trigger ─────────────────────────────────────────────────
  window.runScript = async function(scriptName, projectId, params = {}) {
    const btn = event ? event.target : null;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Running…';
    }
    try {
      const resp = await fetch(`/api/run?script_name=${encodeURIComponent(scriptName)}&project_id=${projectId}&params=${encodeURIComponent(JSON.stringify(params))}`, {method: 'POST'});
      const data = await resp.json();
      if (data.status === 'success') {
        window.showToast(`${scriptName}: ${data.summary || 'Done'}`, 'success');
      } else {
        window.showToast(`${scriptName}: ${data.error || 'Failed'}`, 'error');
      }
      return data;
    } catch (err) {
      window.showToast('Network error', 'error');
      return null;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || 'Run';
      }
    }
  };

  // ─── Polling for running stages ─────────────────────────────────────────
  function startPolling(projectId) {
    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/projects/${projectId}/status`);
        const data = await resp.json();
        // Update pills/status — caller can hook into this
        document.dispatchEvent(new CustomEvent('pipeline-update', { detail: data }));
      } catch (e) {
        // Silently fail — polling will retry
      }
    }, 3000);
    return interval;
  }

  window.startPolling = startPolling;

  // ─── Expandable log viewer ─────────────────────────────────────────────
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

  // ─── Settings test buttons ──────────────────────────────────────────────
  document.addEventListener('click', function(e) {
    const btn = e.target.closest('[data-action="test-credential"]');
    if (btn) {
      const key = btn.dataset.key;
      btn.disabled = true;
      btn.textContent = 'Testing…';
      fetch('/api/settings/test', {
        method: 'POST',
        body: new URLSearchParams({ key: key }),
      }).then(r => r.json()).then(data => {
        btn.disabled = false;
        btn.textContent = 'Test';
        if (data.valid) {
          window.showToast(`${key}: ✓ Valid`, 'success');
        } else {
          window.showToast(`${key}: ✗ ${data.message}`, 'error');
        }
      }).catch(() => {
        btn.disabled = false;
        btn.textContent = 'Test';
        window.showToast(`${key}: Network error`, 'error');
      });
    }
  });

})();
