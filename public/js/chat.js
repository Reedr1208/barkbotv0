// ─── Chat Functionality ─────────────────────────────────────────────────────
// Message sending, typing indicators, suggestions, and chat input handling

function updateSuggestions(botReplyText) {
  const quickPromptsContainer = document.getElementById('quickPromptsContainer');
  if (!quickPromptsContainer) return;

  const genderEl = document.getElementById('dogGender');
  const dogGender = genderEl ? genderEl.textContent : 'male';
  const pron = (dogGender && dogGender.toLowerCase().includes('female')) ? 'her' : 'him';
  const possessive = pron === 'her' ? 'her' : 'his';

  // Candidate questions mapping
  const candidates = [
    {
      text: `What is your rescue story?`,
      keywords: ['story', 'backstory', 'arrive', 'shelter', 'before', 'past', 'background', 'rescue', 'history'],
      hasAnswer: () => currentDogData && (currentDogData.backstory_summary || currentDogData.bio)
    },
    {
      text: `Are you good with other dogs or cats?`,
      keywords: ['dog', 'cat', 'fren', 'animal', 'pet', 'pack', 'other', 'friend', 'doggy'],
      hasAnswer: () => currentDogData && currentDogData.other_animals_notes
    },
    {
      text: `Are you good with kids or strangers?`,
      keywords: ['kid', 'child', 'family', 'people', 'hooman', 'stranger', 'guest', 'person', 'new', 'introduce'],
      hasAnswer: () => currentDogData && currentDogData.people_notes
    },
    {
      text: `How do you do on walks and leash?`,
      keywords: ['walk', 'leash', 'hike', 'run', 'outside', 'yard', 'fence', 'activity', 'collar', 'pull'],
      hasAnswer: () => currentDogData && currentDogData.containment_notes
    },
    {
      text: `Do you have any medical needs or health concerns?`,
      keywords: ['health', 'medical', 'pill', 'vet', 'treat', 'hurt', 'med', 'injury', 'sick'],
      hasAnswer: () => currentDogData && currentDogData.medical_notes
    },
    {
      text: `What does your ideal home look like?`,
      keywords: ['home', 'house', 'apartment', 'yard', 'live', 'owner', 'family', 'ideal', 'space'],
      hasAnswer: () => currentDogData && (
        (currentDogData.ideal_home && currentDogData.ideal_home.length > 0) || 
        currentDogData.containment_notes
      )
    },
    {
      text: `What are your biggest strengths or best qualities?`,
      keywords: ['good', 'best', 'strength', 'love', 'happy', 'cuddle', 'sweet', 'positives', 'special'],
      hasAnswer: () => currentDogData && currentDogData.strengths && currentDogData.strengths.length > 0
    },
    {
      text: `What quirks or challenges are you working on?`,
      keywords: ['quirk', 'challenge', 'bad', 'difficult', 'scared', 'fear', 'issue', 'work', 'trouble', 'nervous'],
      hasAnswer: () => currentDogData && (
        (currentDogData.challenges && currentDogData.challenges.length > 0) ||
        (currentDogData.risk_flags && currentDogData.risk_flags.length > 0)
      )
    },
    {
      text: `What should my human know?`,
      keywords: ['know', 'human', 'owner', 'adopter', 'tell', 'important', 'advice'],
      hasAnswer: () => true
    },
    {
      text: `What does your perfect day look like?`,
      keywords: ['day', 'perfect', 'routine', 'spend', 'sleep', 'morning', 'night'],
      hasAnswer: () => true
    },
    {
      text: `What are some of your favorite things?`,
      keywords: ['favorite', 'thing', 'toy', 'game', 'play', 'treat', 'food', 'bone', 'snack'],
      hasAnswer: () => true
    }
  ];

  // Filter candidates down to those that have actual answers for this dog
  const answeredCandidates = candidates.filter(c => c.hasAnswer());

  // Get user messages already sent to filter out
  const sentMessages = conversationHistory
    .filter(msg => msg.role === 'user')
    .map(msg => msg.content.toLowerCase().trim());

  let finalPrompts = [];

  if (!botReplyText) {
    // 1. Initial State: show 4 diverse prompts that have answers
    // Prioritize specific questions (where hasAnswer checks a field) over general ones
    const specific = answeredCandidates.filter(c => c.text !== `What should my human know?` && c.text !== `What does your perfect day look like?` && c.text !== `What are some of your favorite things?`);
    const general = answeredCandidates.filter(c => c.text === `What should my human know?` || c.text === `What does your perfect day look like?` || c.text === `What are some of your favorite things?`);
    
    const sortedCandidates = [...specific, ...general];
    
    for (const cand of sortedCandidates) {
      const cleanCand = cand.text.toLowerCase().trim();
      if (!sentMessages.includes(cleanCand)) {
        finalPrompts.push(cand.text);
      }
      if (finalPrompts.length >= 3) break;
    }
  } else {
    // 2. Contextual State: show top 3 prompts based on matching keywords in the conversation context
    const lastUserMsg = conversationHistory.length > 0 ? conversationHistory[conversationHistory.length - 1].content : '';
    const contextText = (botReplyText + ' ' + lastUserMsg).toLowerCase();

    // Find matches
    const matched = answeredCandidates.filter(c => c.keywords.some(kw => contextText.includes(kw)));
    
    // Add matched items first, making sure they haven't been sent yet
    for (const cand of matched) {
      const cleanCand = cand.text.toLowerCase().trim();
      if (!sentMessages.includes(cleanCand) && !finalPrompts.includes(cand.text)) {
        finalPrompts.push(cand.text);
      }
    }

    // If we have fewer than 3 matched items, fill with remaining answered candidates
    if (finalPrompts.length < 3) {
      const specific = answeredCandidates.filter(c => c.text !== `What should my human know?` && c.text !== `What does your perfect day look like?` && c.text !== `What are some of your favorite things?`);
      const general = answeredCandidates.filter(c => c.text === `What should my human know?` || c.text === `What does your perfect day look like?` || c.text === `What are some of your favorite things?`);
      const sortedCandidates = [...specific, ...general];

      for (const cand of sortedCandidates) {
        const cleanCand = cand.text.toLowerCase().trim();
        if (!sentMessages.includes(cleanCand) && !finalPrompts.includes(cand.text)) {
          finalPrompts.push(cand.text);
        }
        if (finalPrompts.length >= 3) break;
      }
    }
    
    // Limit to exactly 3 suggestions for conversational turns
    finalPrompts = finalPrompts.slice(0, 3);
  }

  // Limit initial state to 3 as well just to be safe
  finalPrompts = finalPrompts.slice(0, 3);

  // Render the suggestions
  quickPromptsContainer.innerHTML = '';
  finalPrompts.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'prompt-shortcut-btn';
    btn.setAttribute('type', 'button');
    btn.setAttribute('data-prompt', p);
    btn.textContent = p;
    
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
        trackEvent('suggestion_clicked', { dog_name: currentDogName, prompt_text: promptText });
        sendMessage(promptText);
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

async function sendMessage(customText = null) {
  if (chatInput.disabled) return; // double-submit safeguard

  const text = (typeof customText === 'string' ? customText : chatInput.value).trim();
  if (!text || !currentAnimalId) return;

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
        dog_image_url: currentImageUrl
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
