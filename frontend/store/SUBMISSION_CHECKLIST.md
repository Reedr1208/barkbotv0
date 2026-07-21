# ChattyHound — App Store & Play Store Submission Checklist

A do-this-in-order guide for shipping the app. Run all commands from `mobile/`.

---

## 0. Accounts (one-time)

- [ ] **Apple Developer Program** — enrolled ($99/yr) → https://developer.apple.com
- [ ] **Google Play Console** — account created ($25 one-time) → https://play.google.com/console
- [ ] **Expo account** — free → https://expo.dev

---

## 1. Confirm app config (already set — just verify)

In `app.json` (`expo` key):

| Field | Current value | Action |
| --- | --- | --- |
| `name` | ChattyHound | ok |
| `version` | 1.0.0 | bump for each public release |
| `ios.bundleIdentifier` | `com.chattyhound.app` | must be unique on the App Store — change if taken |
| `android.package` | `com.chattyhound.app` | must be unique on Play — change if taken |
| `ios.infoPlist.ITSAppUsesNonExemptEncryption` | false | ok (no custom encryption) |
| permissions | none requested | ok — app needs no camera/location/etc. |

- Build numbers (`ios.buildNumber` / `android.versionCode`) are **auto-managed** by EAS
  (`eas.json` → `appVersionSource: "remote"`, `production.autoIncrement: true`), so you
  don't set them by hand.
- `extra.eas.projectId` is a placeholder — `eas init` (next step) fills it in.

---

## 2. EAS setup (one-time)

```bash
npm install -g eas-cli
eas login
eas init        # links the project; writes the real projectId into app.json
```

- [ ] Commit the updated `app.json` (it now has your real `projectId`).

---

## 3. Pre-flight sanity check

```bash
npx expo-doctor        # flags config/dependency issues
npx tsc --noEmit       # typecheck (optional but recommended)
```

Fix anything flagged before building.

---

## 4. Build the production binaries (cloud)

```bash
eas build -p ios --profile production       # .ipa for the App Store
eas build -p android --profile production    # .aab for Google Play
```

- First iOS build: EAS offers to **generate signing credentials** automatically —
  say yes (it creates and stores your distribution cert + provisioning profile).
- First Android build: EAS generates an **upload keystore** — say yes and let EAS
  keep it. (Losing it later complicates updates.)
- Want to test on a device first? Use `--profile preview` instead (installable
  `.apk` for Android; ad-hoc/TestFlight for iOS).

---

## 5. Create the store entries

**App Store Connect** (https://appstoreconnect.apple.com)
- [ ] Create a new app; pick the bundle ID `com.chattyhound.app`.
- [ ] Fill in name, subtitle, description, keywords → see `store-listing.md`.
- [ ] Upload screenshots (6.7"/6.9" iPhone required).
- [ ] Set Privacy Policy URL + complete the **App Privacy** questionnaire
      (see `store-listing.md` → Data safety summary for what to declare).
- [ ] Add the **App Review notes** (demo email + deletion path) from `store-listing.md`.

**Google Play Console** (https://play.google.com/console)
- [ ] Create the app; set name, short + full description.
- [ ] Upload screenshots + a 1024×500 feature graphic.
- [ ] Complete **Data safety** form + content rating questionnaire.
- [ ] Add Privacy Policy URL.

---

## 6. Submit

```bash
eas submit -p ios --latest        # uploads the build to App Store Connect / TestFlight
eas submit -p android --latest    # uploads the .aab to Play Console
```

- iOS: EAS will ask for App Store Connect access (sign in or an API key).
- Android: the first upload often must be done **manually in Play Console** for a
  brand-new app; after that, `eas submit` works via a Google service-account key.
- [ ] In each console, submit the build for **review** and roll out (TestFlight /
      Play internal testing first is recommended before production release).

---

## 7. Must-clear-before-review items

- [x] **Native app (not a webview)** — passes Apple Guideline 4.2.
- [ ] **Account deletion (Apple 5.1.1)** — implemented in-app (Profile → "Delete my
      account & data") calling `POST /api/delete_account`.
      ⚠️ **Deploy the backend endpoint only after a security review** — it deletes
      production data and currently trusts a plaintext email (same model as the rest
      of the API). Ideally gate it behind email verification before going live.
- [ ] **Privacy Policy hosted** at a public URL and linked in both stores
      (`store/privacy-policy.md` → fill placeholders, host as e.g. /privacy).
- [ ] **Support email/URL** live, and `SUPPORT_EMAIL` set in
      `src/components/DogProfileView.tsx` (used by "Report an issue").
- [ ] **Screenshots** captured for both platforms.

## 8. Optional / post-launch

- [ ] Host universal-link files (`deep-linking/apple-app-site-association.json`,
      `deep-linking/assetlinks.json`) on chattyhound.com so shared `/dogs/:id`
      links open the app. Replace `TEAMID` and the Android SHA-256 fingerprint
      (`eas credentials` shows the fingerprint).
- [ ] Set up `expo-updates` + `runtimeVersion` if you want over-the-air JS updates.
```
