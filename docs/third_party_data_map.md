# ChattyHound — Third-Party Data Map

| Data Category | Purpose | Destination | Retention | Deletion Path |
|---|---|---|---|---|
| Chat messages (user + AI responses) | AI-powered dog chat | **OpenAI** (API) | Per OpenAI data retention policy (typically 30 days for API, no training) | Automatic per OpenAI policy |
| Chat messages, preferences, favorites, session ID | Core product features | **Supabase** (PostgreSQL) | Until user deletes or 90-day guest inactivity expiry | User: "Delete my data" in-app; Admin: DB deletion |
| Contact form email + message | User support correspondence | **Resend** (email API) | Per Resend's retention policy | Contact Resend support |
| Page views, button clicks, non-content events | Product analytics | **Google Analytics** | Per GA4 data retention settings (default 14 months) | GA4 admin: Data Deletion Requests |
| Application code, runtime environment | Hosting/serving | **Railway** | N/A (operational) | N/A |
| Dog images, profile photos | Image storage/delivery | **Supabase Storage** | While dog is active, cleaned up on deactivation | Automated via scraper pipeline |
| Font files (Inter) | Typography | **Google Fonts** (CDN) | N/A (static asset, no user data sent) | N/A |
| JavaScript libraries (marked, DOMPurify) | Markdown rendering, XSS sanitization | **jsDelivr CDN** | N/A (static asset, no user data sent) | N/A |

## Notes

- **No data is sent to**: FullStory (removed), ip-api.com (removed), Meta/Facebook, advertising networks
- **IP addresses**: Not stored in our database. Used ephemerally for rate limiting only.
- **Chat content**: NOT sent to Google Analytics. Only non-content metadata (event names, dog IDs, turn counts).
- **Google Fonts**: Browser makes requests to fonts.googleapis.com and fonts.gstatic.com. Google may log standard HTTP access info. Consider self-hosting to eliminate this.
- **OpenAI**: Chat messages are sent to OpenAI's API for response generation. OpenAI's API data usage policy (as of 2024) states API inputs/outputs are not used for training.
