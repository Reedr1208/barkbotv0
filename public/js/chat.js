// ─── Chat Functionality ─────────────────────────────────────────────────────
// Message sending, typing indicators, suggestions, and chat input handling

// ─── Suggestion System ──────────────────────────────────────────────────────

/**
 * Fetch the Informative/Whimsical prompt pools from the API (cached).
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
  const profilePrompts = (dogData && dogData.sugg_specific) ? [...dogData.sugg_specific] : [];

  suggestionState = {
    pools: {
      informative: [...cache.informative],
      whimsical: [...cache.whimsical],
      profile: profilePrompts,
    },
    usedPrompts: new Set(),
    current: {
      informative: { text: null, turnsShown: 0 },
      whimsical:   { text: null, turnsShown: 0 },
      profile:     { text: null, turnsShown: 0 },
    },
  };
  activeSuggestions = [];
}

/**
 * Pick a random unused prompt from a category pool.
 * Returns null if the pool is exhausted.
 */
function pickFromPool(category) {
  const pool = suggestionState.pools[category];
  const available = pool.filter(p => !suggestionState.usedPrompts.has(p));
  if (available.length === 0) return null;
  const idx = Math.floor(Math.random() * available.length);
  return available[idx];
}

/**
 * Core suggestion logic. Called on dog load (no args) and after each bot reply.
 * Shows one suggestion per category (Informative, Whimsical, Profile-Specific).
 * Rotates suggestions after 2 chat turns. Used suggestions are never reshown.
 */
function updateSuggestions(botReplyText) {
  const quickPromptsContainer = document.getElementById('quickPromptsContainer');
  if (!quickPromptsContainer) return;

  const categories = ['informative', 'whimsical', 'profile'];

  // Check if ALL prompts across ALL categories have been used
  const totalAvailable = categories.reduce((sum, cat) => {
    return sum + suggestionState.pools[cat].filter(p => !suggestionState.usedPrompts.has(p)).length;
  }, 0);

  if (totalAvailable === 0) {
    // All prompts exhausted — show nothing
    quickPromptsContainer.innerHTML = '';
    activeSuggestions = [];
    return;
  }

  // For each category, decide whether to keep the current prompt or rotate
  for (const cat of categories) {
    const cur = suggestionState.current[cat];

    const needsNew = (
      cur.text === null ||                           // No prompt yet
      suggestionState.usedPrompts.has(cur.text) ||   // Was used (clicked)
      cur.turnsShown >= 2                            // Shown for 2 turns
    );

    if (needsNew) {
      const newPick = pickFromPool(cat);
      suggestionState.current[cat] = { text: newPick, turnsShown: 0 };
    }

    // If we have a bot reply, increment turnsShown for non-null prompts
    if (botReplyText && suggestionState.current[cat].text) {
      suggestionState.current[cat].turnsShown++;
    }
  }

  // Collect one prompt from each category that has one
  let finalPrompts = [];
  const categoriesWithPrompts = [];
  const categoriesExhausted = [];

  for (const cat of categories) {
    const text = suggestionState.current[cat].text;
    if (text && !suggestionState.usedPrompts.has(text)) {
      finalPrompts.push({ text, category: cat });
      categoriesWithPrompts.push(cat);
    } else {
      categoriesExhausted.push(cat);
    }
  }

  // If any category is exhausted, fill from remaining categories (overflow)
  if (categoriesExhausted.length > 0 && finalPrompts.length < 3) {
    const usedTexts = new Set(finalPrompts.map(p => p.text));
    for (const cat of categoriesWithPrompts) {
      if (finalPrompts.length >= 3) break;
      const pool = suggestionState.pools[cat];
      const available = pool.filter(p =>
        !suggestionState.usedPrompts.has(p) && !usedTexts.has(p)
      );
      for (const p of available) {
        if (finalPrompts.length >= 3) break;
        finalPrompts.push({ text: p, category: cat });
        usedTexts.add(p);
      }
    }
  }

  // Limit to 3
  finalPrompts = finalPrompts.slice(0, 3);
  activeSuggestions = finalPrompts.map(p => p.text);

  // Render the suggestion buttons
  quickPromptsContainer.innerHTML = '';
  finalPrompts.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'prompt-shortcut-btn';
    btn.setAttribute('type', 'button');
    btn.setAttribute('data-prompt', p.text);
    btn.textContent = p.text;

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

  showTypingIndicator();

  const historyToSend = conversationHistory.slice(0, -1);

  try {
    const currentImageUrl = document.getElementById('dogImage')?.src || '';
    
    let guestSessionId = localStorage.getItem('chattyhound_guest_id');
    if (!guestSessionId) {
      guestSessionId = 'guest_' + Math.random().toString(36).substr(2, 9) + '@guest.chattyhound.com';
      localStorage.setItem('chattyhound_guest_id', guestSessionId);
    }

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        animal_id: currentAnimalId,
        message: text,
        conversation_history: historyToSend,
        email: userEmail || guestSessionId,
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
      updateSuggestions(data.reply);
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
