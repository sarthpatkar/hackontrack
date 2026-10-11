# ForwardCheck: WhatsApp prototype

One static file (`index.html`), no build step, no backend, no API keys.
All replies and evidence are simulated samples that mirror the real reply format in `forwardcheck/app/reply.py`.

## Deploy (pick one)

- **Netlify (fastest):** open https://app.netlify.com/drop and drag this `prototype` folder in.
- **Vercel:** `cd prototype && npx vercel --prod`
- **GitHub Pages:** push the repo, then Settings > Pages > deploy from branch, folder `/prototype` (or copy `index.html` to `/docs`).

## What to show

1. Open a chat (Sharma Parivar, Aai, College Gang...). Hover a message and use the chevron (or right-click, or long-press on a phone), choose Forward or Select, pick ForwardCheck, press send. This is the same flow as WhatsApp.
2. The bot chat opens with your forwarded message and replies with verdicts. Business info (right pane) shows the live steps.
3. Open `index.html#backend` (the `</>` icon in the rail, the chat menu, or Business info) and press the single button to replay what the server does for the message you last forwarded.
4. Reply HINDI / MARATHI in the bot chat to switch language.

## Live mode
Deploy `forwardcheck/` (see its README, "Deploy the API"), then in the prototype open Business info > Live backend, paste the URL and press Connect, or open the page with `?api=https://your-service.onrender.com`.
