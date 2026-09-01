# LocalAI Agent — Expo (iOS / Android)

Same online accounts as the web app: **email**, **Google**, and **Apple**. The mobile client posts ID tokens to:

- `POST /api/v1/auth/oauth/google`
- `POST /api/v1/auth/oauth/apple`

## Setup

```bash
cd mobile
cp .env.example .env
npx expo install
```

Set `EXPO_PUBLIC_API_URL` to your public API (not localhost on a physical device).

## Google / Apple

1. Create OAuth clients in Google Cloud (Web + iOS + Android). Put the **web** client id in backend `GOOGLE_OAUTH_CLIENT_ID` so token audience checks pass.
2. Enable Sign in with Apple on the App Store identifier `com.localai.agent`. Set backend `APPLE_OAUTH_CLIENT_ID` to that Services ID / bundle id.
3. Replace placeholders in `app.json` (`REPLACE_GOOGLE_IOS_CLIENT`, EAS `projectId`).

## Publish

```bash
npx eas login
npx eas build:configure
npx eas build --platform ios --profile production
npx eas build --platform android --profile production
npx eas submit --platform ios --profile production
npx eas submit --platform android --profile production
```

App Store / Play require production HTTPS API, privacy policy, and real OAuth client IDs.
