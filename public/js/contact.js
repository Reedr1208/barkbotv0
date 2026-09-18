// ─── Contact Form ─────────────────────────────────────────────────────
// Handles the Contact Us modal: open/close, form submission, validation

function openContactModal(preSelectedSubject) {
  const modal = document.getElementById('contactModal');
  if (!modal) return;
  modal.classList.add('active');
  modal.setAttribute('aria-hidden', 'false');
  // Reset form state
  const form = document.getElementById('contactForm');
  if (form) form.reset();
  const status = document.getElementById('contactStatus');
  if (status) { status.textContent = ''; status.className = 'contact-status'; }
  const charCount = document.getElementById('contactCharCount');
  if (charCount) charCount.textContent = '';
  // Show form, hide success
  const formBody = document.getElementById('contactFormBody');
  const successMsg = document.getElementById('contactSuccessMsg');
  if (formBody) formBody.style.display = '';
  if (successMsg) successMsg.style.display = 'none';
  // Enable submit
  const btn = document.getElementById('contactSubmitBtn');
  if (btn) { btn.disabled = false; btn.textContent = 'Send Message 📬'; }
  // Pre-select subject if provided
  if (preSelectedSubject) {
    const subjectEl = document.getElementById('contactSubject');
    if (subjectEl) subjectEl.value = preSelectedSubject;
  }
}

function closeContactModal() {
  const modal = document.getElementById('contactModal');
  if (!modal) return;
  modal.classList.remove('active');
  modal.setAttribute('aria-hidden', 'true');
}

async function submitContactForm(e) {
  e.preventDefault();

  const subjectEl = document.getElementById('contactSubject');
  const emailEl = document.getElementById('contactEmail');
  const messageEl = document.getElementById('contactMessage');
  const statusEl = document.getElementById('contactStatus');
  const submitBtn = document.getElementById('contactSubmitBtn');

  const subject = subjectEl?.value || '';
  const email = (emailEl?.value || '').trim();
  const message = (messageEl?.value || '').trim();

  // Client-side checks
  if (!subject) {
    showContactError(statusEl, 'Please select a subject.');
    return;
  }
  if (!message) {
    showContactError(statusEl, 'Please enter a message.');
    return;
  }
  if (message.length > 5000) {
    showContactError(statusEl, 'Message is too long (max 5,000 characters).');
    return;
  }

  // Anonymous confirmation
  if (!email) {
    const confirmed = confirm(
      "You haven't entered an email address.\n\n" +
      "Without one, we won't be able to reply to your message. " +
      "Would you like to send it anonymously?"
    );
    if (!confirmed) return;
  }

  // Submit
  submitBtn.disabled = true;
  submitBtn.textContent = 'Sending...';
  statusEl.textContent = '';
  statusEl.className = 'contact-status';

  try {
    const res = await fetch('/api/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject, email, message }),
    });

    const data = await res.json();

    if (res.ok && data.ok) {
      // Show success state
      const formBody = document.getElementById('contactFormBody');
      const successMsg = document.getElementById('contactSuccessMsg');
      if (formBody) formBody.style.display = 'none';
      if (successMsg) successMsg.style.display = '';
      if (typeof trackEvent === 'function') {
        trackEvent('contact_form_sent', { subject });
      }
    } else {
      showContactError(statusEl, data.error || 'Something went wrong. Please try again.');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send Message 📬';
    }
  } catch (err) {
    showContactError(statusEl, 'Network error. Please check your connection and try again.');
    submitBtn.disabled = false;
    submitBtn.textContent = 'Send Message 📬';
  }
}

function showContactError(el, msg) {
  if (!el) return;
  el.textContent = msg;
  el.className = 'contact-status contact-status-error';
}

function updateContactCharCount() {
  const messageEl = document.getElementById('contactMessage');
  const countEl = document.getElementById('contactCharCount');
  if (!messageEl || !countEl) return;
  const len = messageEl.value.length;
  countEl.textContent = len > 0 ? `${len.toLocaleString()} / 5,000` : '';
  countEl.style.color = len > 4500 ? 'var(--accent)' : 'var(--text-muted)';
}

// Wire up events after DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const contactBtn = document.getElementById('contactBtn');
  if (contactBtn) contactBtn.addEventListener('click', openContactModal);

  const contactCloseBtn = document.getElementById('contactCloseBtn');
  if (contactCloseBtn) contactCloseBtn.addEventListener('click', closeContactModal);

  // Report an issue button — opens contact form with subject pre-selected
  const reportIssueBtn = document.getElementById('reportIssueBtn');
  if (reportIssueBtn) {
    reportIssueBtn.addEventListener('click', () => {
      trackEvent('issue_reported', { dog_name: currentDogName, animal_id: currentAnimalId });
      openContactModal('Report a Problem');
    });
  }

  const contactModal = document.getElementById('contactModal');
  if (contactModal) {
    contactModal.addEventListener('click', (e) => {
      if (e.target === contactModal) closeContactModal();
    });
  }

  const contactForm = document.getElementById('contactForm');
  if (contactForm) contactForm.addEventListener('submit', submitContactForm);

  const contactMessage = document.getElementById('contactMessage');
  if (contactMessage) contactMessage.addEventListener('input', updateContactCharCount);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && contactModal?.classList.contains('active')) closeContactModal();
  });
});
