My top pre-MVP recommendations

1. Do one final “state rendering” check

This is still the biggest thing I’d verify before launch. The indexable page output still includes multiple states at once: Loading..., unavailable dog, no matches, placeholder quick facts, chat, share, and dog CTAs.

Even if the visual UI looks clean, make sure these are not being read by screen readers, indexed by search engines, or flashed during hydration. For MVP, the app should feel stable even on slow mobile internet.

2. Add “last updated” / freshness language for each dog

Because shelter data changes quickly, I’d add a small line on dog detail pages:

Shelter listing last checked: Today
Availability may change — confirm with the shelter.

This makes ChattyHound feel more trustworthy and protects against the “I fell in love with a dog who is no longer available” problem.

3. Add a tiny feedback/report button

Before MVP, add a lightweight feedback mechanism:

Something wrong? Report an issue

This could capture broken dog pages, bad AI responses, unavailable dogs, incorrect info, missing images, or shelter link problems. For an MVP, this is extremely valuable because users will find edge cases faster than you will.

4. Make the AI chat boundaries visible inside chat

The trust disclaimer exists on the page, which is good. But I’d also put a short version inside or near the chat module:

I can help you understand this dog’s profile, but please confirm adoption, medical, and behavior details with the shelter.

That way, users see the reminder at the exact moment they are interacting with AI.

5. Strengthen the “My Dogs” page as a retention hook

The site now has My Dogs, with Saved Dogs and Recent Chats. Before MVP, make sure this page feels like a real reason to come back:

Saved dogs ordered by most recently saved
Recent chats ordered by last activity
Clear “Continue chat” CTA
Clear empty states
Dog unavailable state preserved instead of disappearing silently

This is probably your strongest retention feature.

6. Add basic funnel analytics

Before MVP, track the core adoption-discovery funnel:

Visited site
Clicked Start Sniffing
Viewed dog
Clicked heart
Clicked chat
Sent first chat message
Clicked share
Clicked shelter page
Returned to My Dogs
Continued prior chat

You do not need complicated analytics yet. You just need to know where users drop off.

7. Make sharing feel emotionally polished

Since sharing is now part of the product, make the share copy feel human:

Meet Coffee Bean on ChattyHound 🐶
I found this adoptable dog and thought of you.

Also test previews in iMessage, WhatsApp, Gmail, and LinkedIn. The shared dog page should have a good image, title, and description.

8. Final mobile QA checklist

Before MVP, test these on real phones:

Dog image loading on weak connection
Bottom nav not blocking content
Chat input not hidden by keyboard
Share sheet opens properly
Heart state persists after refresh
My Dogs loads after sign-in
Shelter link opens correctly
Back button behavior feels natural
Deep link to /dogs/:id works from a shared text

9. Accessibility pass

Use WCAG 2.2 AA as the practical target. W3C describes WCAG as the shared standard for making web content accessible, with testable success criteria under perceivable, operable, understandable, and robust principles.

For your MVP, I’d especially check: keyboard navigation, visible focus states, readable contrast, accessible names for heart/share buttons, and whether hidden inactive states are announced by screen readers.

My recommendation before MVP

Do not add more product surface area yet. The MVP is already feature-rich enough.

I’d prioritize:

State/rendering cleanup
Dog data freshness messaging
My Dogs polish
Chat trust copy
Analytics
Real mobile QA
Feedback/report issue button

That combination will make the MVP feel safer, more credible, and easier to improve after launch.