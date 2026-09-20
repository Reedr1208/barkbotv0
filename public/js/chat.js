// ─── Chat Functionality ─────────────────────────────────────────────────────
// Message sending, typing indicators, suggestions, and chat input handling

// ─── Suggestion System ──────────────────────────────────────────────────────

/**
 * Fetch the Informative/Whimsical prompt pools from the API (cached).
 * API returns: { informative: [{text, weight}, ...], whimsical: [{text, weight}, ...] }
 */
async function fetchSuggestedPromptsIfNeeded() {
  if (suggestedPromptsCache) return suggestedPromptsCache;
  try {
    const res = await fetch('/api/suggested_prompts');
    if (res.ok) {
      suggestedPromptsCache = await res.json();
    } else {
      suggestedPromptsCache = { informative: [], whimsical: [] };
    }
  } catch (e) {
    console.warn('Failed to fetch suggested prompts:', e);
    suggestedPromptsCache = { informative: [], whimsical: [] };
  }
  return suggestedPromptsCache;
}

/**
 * Reset suggestion state for a new dog. Call this after dog data loads.
 */
function initSuggestionsForDog(dogData) {
  const cache = suggestedPromptsCache || { informative: [], whimsical: [] };

  // Normalize: handle both old format (plain strings) and new format ({text, weight})
  function normalizePool(items) {
    return (items || []).map(item => {
      if (typeof item === 'string') return { text: item, weight: 1.0 };
      if (item && typeof item === 'object' && typeof item.text === 'string') return item;
      // Unknown format — skip
      return null;
    }).filter(Boolean);
  }

  // Profile-specific prompts come as plain strings — give them weight=1.0
  const profilePrompts = (dogData && dogData.sugg_specific)
    ? dogData.sugg_specific.map(t => ({ text: String(t), weight: 1.0 }))
    : [];

  suggestionState = {
    pools: {
      informative: normalizePool(cache.informative),
      whimsical: normalizePool(cache.whimsical),
      profile: profilePrompts,
    },
    usedPrompts: new Set(),
  };
  activeSuggestions = [];
}

/**
 * Weighted random pick from a pool, excluding used prompts.
 * Returns the {text, weight} object or null if pool exhausted.
 */
function pickWeightedFromPool(category) {
  const pool = suggestionState.pools[category];
  const available = pool.filter(p => !suggestionState.usedPrompts.has(p.text));
  if (available.length === 0) return null;
  if (available.length === 1) return available[0];

  // Weighted random selection
  const totalWeight = available.reduce((sum, p) => sum + p.weight, 0);
  let r = Math.random() * totalWeight;
  for (const p of available) {
    r -= p.weight;
    if (r <= 0) return p;
  }
  return available[available.length - 1]; // fallback
}

/**
 * Core suggestion logic. Called on dog load and after EVERY chat turn.
 * Picks a fresh weighted-random prompt from each category every time.
 * Used (clicked) prompts are excluded. When a category is exhausted,
 * remaining slots fill from other categories.
 */
function updateSuggestions() {
  const quickPromptsContainer = document.getElementById('quickPromptsContainer');
  if (!quickPromptsContainer) return;

  const categories = ['informative', 'whimsical', 'profile'];

  // Check total availability
  const totalAvailable = categories.reduce((sum, cat) => {
    return sum + suggestionState.pools[cat].filter(p => !suggestionState.usedPrompts.has(p.text)).length;
  }, 0);

  if (totalAvailable === 0) {
    quickPromptsContainer.innerHTML = '';
    activeSuggestions = [];
    return;
  }

  // Pick one weighted-random prompt from each category
  let finalPrompts = [];
  const categoriesWithRoom = [];
  const usedTexts = new Set();

  for (const cat of categories) {
    const pick = pickWeightedFromPool(cat);
    if (pick && !usedTexts.has(pick.text)) {
      finalPrompts.push({ text: pick.text, category: cat });
      usedTexts.add(pick.text);
      categoriesWithRoom.push(cat);
    }
  }

  // If any category is exhausted and we have fewer than 3, fill from remaining
  if (finalPrompts.length < 3) {
    for (const cat of categoriesWithRoom) {
      if (finalPrompts.length >= 3) break;
      const pool = suggestionState.pools[cat];
      const available = pool.filter(p =>
        !suggestionState.usedPrompts.has(p.text) && !usedTexts.has(p.text)
      );
      // Pick additional via weighted random
      for (let i = 0; i < available.length && finalPrompts.length < 3; i++) {
        const totalW = available.reduce((s, p) => s + (usedTexts.has(p.text) ? 0 : p.weight), 0);
        if (totalW <= 0) break;
        let r = Math.random() * totalW;
        let picked = null;
        for (const p of available) {
          if (usedTexts.has(p.text)) continue;
          r -= p.weight;
          if (r <= 0) { picked = p; break; }
        }
        if (!picked) break;
        finalPrompts.push({ text: picked.text, category: cat });
        usedTexts.add(picked.text);
      }
    }
  }

  finalPrompts = finalPrompts.slice(0, 3);
  activeSuggestions = finalPrompts.map(p => p.text);

  // Render the suggestion buttons
  quickPromptsContainer.innerHTML = '';
  finalPrompts.forEach(p => {
    const promptText = (typeof p.text === 'object') ? (p.text.text || String(p.text)) : String(p.text);
    const btn = document.createElement('button');
    btn.className = 'prompt-shortcut-btn';
    btn.setAttribute('type', 'button');
    btn.setAttribute('data-prompt', promptText);
    btn.textContent = promptText;

    const handleImmediateSend = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (btn.disabled) return;
      const promptText = btn.getAttribute('data-prompt');
      if (promptText && chatInput && !chatInput.disabled) {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.background = 'var(--accent)';
        btn.style.color = 'var(--accent-text)';

        // Mark this prompt as used so it won't reappear
        suggestionState.usedPrompts.add(promptText);

        trackEvent('suggestion_clicked', { dog_name: currentDogName, prompt_text: promptText });
        sendMessage(promptText, promptText);
      }
    };
    btn.addEventListener('click', handleImmediateSend);

    quickPromptsContainer.appendChild(btn);
  });
}

// scrollToBottom is defined in ui.js

function appendMessage(role, content, avatarLetter = '🐾', shouldScroll = true) {
  const msgRow = document.createElement('div');
  msgRow.className = `msg-row ${role === 'bot' ? 'bot' : 'user'}`;

  if (role === 'bot') {
    const av = document.createElement('div');
    av.className = 'avatar';
    av.textContent = avatarLetter;
    msgRow.appendChild(av);

    const bubble = document.createElement('div');
    bubble.className = 'bubble bot';
    bubble.innerHTML = marked.parse(content);
    msgRow.appendChild(bubble);
  } else {
    const bubble = document.createElement('div');
    bubble.className = 'bubble user';
    bubble.textContent = content;
    msgRow.appendChild(bubble);
  }

  chatHistory.appendChild(msgRow);

  // Smoothly scroll the main layout down as chat history grows
  if (shouldScroll) {
    scrollToBottom();
  }

  // Add to internal history state
  conversationHistory.push({ role: role === 'bot' ? 'assistant' : 'user', content });
}

function showTypingIndicator() {
  const container = document.createElement('div');
  container.className = 'msg-row typing-row';
  container.id = 'typingIndicator';

  const av = document.createElement('div');
  av.className = 'avatar';
  av.textContent = currentDogName.charAt(0).toUpperCase();
  container.appendChild(av);

  const bubble = document.createElement('div');
  bubble.className = 'typing-bubble';
  bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  container.appendChild(bubble);

  chatHistory.appendChild(container);
  scrollToBottom();
}

function removeTypingIndicator() {
  const indicator = document.getElementById('typingIndicator');
  if (indicator) {
    indicator.remove();
  }
}

async function sendMessage(customText = null, chosenPrompt = null) {
  if (chatInput.disabled) return; // double-submit safeguard

  const text = (typeof customText === 'string' ? customText : chatInput.value).trim();
  if (!text || !currentAnimalId) return;

  // Capture the suggestions that were visible when this message is sent
  const currentSuggPrompts = [...activeSuggestions];

  const isFirstMessage = (conversationHistory.length === 0);
  appendMessage('user', text);
  trackEvent('chat_message_sent', { dog_name: currentDogName, message_text: text });
  if (isFirstMessage) {
    trackEvent('first_chat_message_sent', { dog_name: currentDogName });
  }
  chatInput.value = '';
  chatInput.blur();
  document.body.classList.remove('keyboard-active');
  chatInput.disabled = true;
  sendBtn.disabled = true;

  // Rotate suggestions immediately on every user turn
  updateSuggestions();

  showTypingIndicator();

  const historyToSend = conversationHistory.slice(0, -1);

  try {
    const currentImageUrl = document.getElementById('dogImage')?.src || '';

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        animal_id: currentAnimalId,
        message: text,
        conversation_history: historyToSend,
        email: userEmail,
        dog_name: currentDogName,
        dog_image_url: currentImageUrl,
        sugg_prompts: currentSuggPrompts.length > 0 ? currentSuggPrompts : null,
        chosen_prompt: chosenPrompt || null
      })
    });

    removeTypingIndicator();

    if (!response.ok) throw new Error('Chat failed');

    const data = await response.json();
    const firstLetter = currentDogName.charAt(0).toUpperCase();
    if (data.reply) {
      appendMessage('bot', data.reply, firstLetter);
      updateSuggestions();
    } else {
      appendMessage('bot', '[Error: No reply received]', firstLetter);
    }
  } catch (err) {
    removeTypingIndicator();
    console.error(err);
    appendMessage('bot', '[Sorry, I had trouble responding to that.]', '!');
  } finally {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    if (window.innerWidth >= 800) {
      chatInput.focus();
    }
  }
}

nextBtn.addEventListener('click', () => {
  trackEvent('dog_shuffled');
  fetchRandomDog();
});
const prevBtn = document.getElementById('prevBtn');
if (prevBtn) {
  prevBtn.addEventListener('click', () => {
    trackEvent('dog_back');
    goToPreviousDog();
  });
}
sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});
// Force viewport scroll reset to fix iOS keyboard layout displacement bug
chatInput.addEventListener('blur', () => {
  document.body.classList.remove('keyboard-active');
  setTimeout(() => {
    window.scrollTo(0, 0);
  }, 150);
});
chatInput.addEventListener('focus', () => {
  if (!localStorage.getItem('has_interacted_with_chat')) {
    localStorage.setItem('has_interacted_with_chat', 'true');
    chatInput.classList.remove('attention-pulse');
    const chatInputWrapper = document.getElementById('chatInputWrapper');
    if (chatInputWrapper) chatInputWrapper.classList.remove('attention-wrapper');
  }
  enterChatMode();
  document.body.classList.add('keyboard-active');
  setTimeout(() => {
    window.scrollTo(0, 0);
    scrollToBottom();
  }, 150);
});

// Dismiss keyboard on outside tap
document.addEventListener('touchstart', (e) => {
  if (document.body.classList.contains('keyboard-active') && e.target !== chatInput && e.target.closest('.footer-input-bar') === null && e.target.closest('#quickPromptsContainer') === null) {
    chatInput.blur();
  }
});

// Robust keyboard detection via VisualViewport API
if (window.visualViewport) {
  let maxVpHeight = window.visualViewport.height;
  window.visualViewport.addEventListener('resize', () => {
    if (window.visualViewport.height > maxVpHeight) {
      maxVpHeight = window.visualViewport.height;
    }
    // If viewport height is close to max (keyboard closed) but input still thinks it's active
    if (window.visualViewport.height > maxVpHeight - 100 && document.body.classList.contains('keyboard-active')) {
      document.body.classList.remove('keyboard-active');
      chatInput.blur();
      setTimeout(() => {
        window.scrollTo(0, 0);
        scrollToBottom();
      }, 100);
    }
  });
}
