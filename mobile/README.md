# ChattyHound — Mobile (Expo)

A native iOS + Android app built with **Expo (React Native + TypeScript)** and
**Expo Router**. It is a faithful rebuild of the chattyhound.com web UI and talks
to the **same Vercel API** (`/api/*`) and Supabase backend — no backend changes
required.

The app lives in this `mobile/` subfolder so the existing web app and Python API
at the repo root are untouched.

---

## 1. Prerequisites

- **Node.js 18+** and npm
- A phone with **Expo Go** (for quick local testing) or an emulator/simulator
- For store builds: an **[Expo account](https://expo.dev)** and the **EAS CLI**
  (`npm install -g eas-cli`)
- Apple Developer Program membership (App Store) and Google Play Developer
  account (Play Store)

---

## 2. Install & align dependencies

```bash
cd mobile
npm install

# Align every package to the exact versions your installed Expo SDK expects.
# (Dependencies here are pinned to Expo SDK 51; this command will reconcile them.)
npx expo install --fix
```

> **Recommended before shipping to the stores:** upgrade to the latest Expo SDK so
> the app targets the current Android API level / iOS SDK that Apple & Google
> require. Run:
>
> ```bash
> npx expo install expo@latest --fix
> ```
>
> then re-test. (This project was authored offline against SDK 51; the upgrade is
> a one-command step.)

---

## 3. Run locally

```bash
npx expo start
```

- Press `i` (iOS simulator), `a` (Android emulator), or scan the QR code with
  **Expo Go**.
- The app points at `https://chattyhound.com` by default. To target a different
  backend (e.g. a local dev server), edit `expo.extra.apiBaseUrl` in `app.json`.

---

## 4. Project structure

```
mobile/
├─ app/                       # Expo Router routes (file-based navigation)
│  ├─ _layout.tsx             # Root stack: fonts, providers, splash
│  ├─ index.tsx               # Entry gate → welcome or tabs
│  ├─ welcome.tsx             # Landing / onboarding
│  ├─ login.tsx               # Email sign-in (modal)
│  ├─ (tabs)/                 # Bottom tab bar
│  │  ├─ discover.tsx         # Browse one dog at a time + shuffle
│  │  ├─ my-dogs.tsx          # Saved dogs + recent chats
│  │  └─ profile.tsx          # Match preferences + account + about
│  ├─ chat/[id].tsx           # AI chat with a dog
│  └─ dogs/[...slug].tsx      # Deep-link target for /dogs/:id (shared links)
├─ src/
│  ├─ api.ts                  # Typed client for the Vercel API
│  ├─ auth.tsx                # Email + preferences + favorites (AsyncStorage)
│  ├─ theme.ts                # Design tokens ported from the site CSS
│  ├─ toast.tsx               # Toast notifications
│  ├─ utils.ts                # Image resolution, match logic, share copy
│  └─ components/             # DogProfileView, ChatBubble, HeartButton, …
├─ assets/                    # Icons, splash, featured images
├─ app.json                   # Expo config (icons, scheme, deep links, extra)
└─ eas.json                   # EAS Build / Submit profiles
```

### How it maps to the backend

| Screen | Endpoint(s) |
| --- | --- |
| Discover / Dog detail | `GET /api/random_dog` |
| Chat | `POST /api/chat`, `GET /api/chat_history?email=&animal_id=` |
| My Dogs | `GET /api/favorites?email=`, `GET /api/chat_history?email=`, `POST /api/favorites` |
| Profile / Preferences | `GET /api/locations`, `POST /api/save_preferences`, `POST /api/login` |

No API keys live in the app — chat/OpenAI and Supabase service keys remain
server-side on Vercel. The client only ever sends the user's email (used as the
identifier, exactly like the website).

---

## 5. Deep links / shared dog links

Shared web links look like `https://chattyhound.com/dogs/<animal_id>` (and
`…/dogs/<location>/<animal_id>`). The app maps these to `app/dogs/[...slug].tsx`.

To make those **https** links open the app (Universal Links / App Links), host
two small verification files on the chattyhound.com domain:

1. **iOS** — `https://chattyhound.com/.well-known/apple-app-site-association`
   (no file extension, served as `application/json`). See
   `deep-linking/apple-app-site-association.json` — replace `TEAMID` with your
   Apple Team ID.

2. **Android** — `https://chattyhound.com/.well-known/assetlinks.json`. See
   `deep-linking/assetlinks.json` — replace the SHA-256 fingerprint with the one
   from your Play app signing key (`eas credentials` shows it, or Play Console →
   Setup → App signing).

The custom scheme `chattyhound://dogs/<id>` works without any hosting.

> If you serve these from the Vercel project, add routes/rewrites so
> `/.well-known/apple-app-site-association` and `/.well-known/assetlinks.json`
> return the JSON files.

---

## 6. Build & submit to the stores (EAS)

```bash
npm install -g eas-cli
eas login
eas init            # creates the project & writes extra.eas.projectId in app.json
```

Update before your first build:

- `app.json` → `ios.bundleIdentifier` and `android.package`
  (currently `com.chattyhound.app` — change if that ID is taken).
- `app.json` → `version`; EAS auto-increments native build numbers in the
  `production` profile.

### Android (Google Play)

```bash
eas build -p android --profile production      # produces an .aab
eas submit -p android --latest                 # uploads to Play Console
```

### iOS (App Store)

```bash
eas build -p ios --profile production
eas submit -p ios --latest
```

EAS will provision signing credentials interactively the first time.

### Internal test builds

```bash
eas build -p android --profile preview          # installable .apk
eas build -p ios --profile preview              # ad-hoc / TestFlight
```

---

## 7. Before you submit — checklist

- [ ] `npx expo install expo@latest --fix` and re-test (current target SDKs).
- [ ] Replace placeholder **bundle identifier / package name** if needed.
- [ ] Set the real support address in `src/components/DogProfileView.tsx`
      (`SUPPORT_EMAIL`) for the "Report an issue" link.
- [ ] Host the two **deep-linking** files (section 5).
- [ ] Add store **screenshots** and a **privacy policy URL** (required by both
      stores).
- [ ] **App Store account-deletion (Guideline 5.1.1):** because signing in with
      an email auto-creates a profile server-side, Apple requires an in-app way to
      delete that data. Add a "Delete my data" action (a new `DELETE`-style API
      endpoint, e.g. clearing `user_preferences`/`saved_dogs`/chats for the email)
      and surface it on the Profile screen before review.
- [ ] Confirm the **data-safety / privacy nutrition** forms: the app collects an
      email (optional, for saving preferences) and chat content; no ads, no
      tracking SDKs are bundled in this client.
- [ ] Test on a physical iOS and Android device (image loading on weak networks,
      keyboard not covering the chat input, share sheet, heart persistence, deep
      link from a shared text).

---

## 8. Notes & known follow-ups

- **Why native (not a WebView):** Apple frequently rejects repackaged-website
  apps (Guideline 4.2). This is a real React Native UI, which is the reliable path
  through review and gives a better UX.
- **Guest vs signed-in:** guests can browse, chat, and save favorites locally.
  Signing in (email only, no password — matches the web) syncs preferences,
  favorites, and chat history across devices via the existing API.
- **Offline-ish favorites:** saved dogs are cached in `AsyncStorage` so the
  My Dogs tab works for guests and offline, then merge with the server on sign-in.
```
