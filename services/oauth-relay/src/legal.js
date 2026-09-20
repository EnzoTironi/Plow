// Static copy for operator review. No request or OAuth data enters these pages.
export const LEGAL = {
  privacy: {
    label: "Privacy policy",
    title: "Your life.",
    accent: "Your say.",
    text: "What Zoen needs to help, where it goes, and how you stay in control.",
    article: `<p class="review-note">Draft for review · September 19, 2026</p>
      <h2>Who runs Zoen</h2>
      <p>Zoen is an AI assistant operated by Enzo Tironi. This policy covers the Zoen iMessage agent and its account-connection service. For privacy questions and requests, contact <a href="mailto:enzo@zoen.space">enzo@zoen.space</a>.</p>
      <h2>What you share</h2>
      <p>Zoen processes the messages, attachments, instructions, and preferences you share, along with your messaging identity and the information needed to deliver replies. Conversation history, task records, and saved memories help it continue your work.</p>
      <p>Connecting an account is optional. You choose the account and permissions on the provider's authorization screen. Zoen stores authorization credentials and the connected account's identity so it can carry out your requests without asking you to sign in every time.</p>
      <h2>Your Google connection</h2>
      <p>Zoen requests access for the features you choose. Depending on your consent, this can include your email address; Gmail messages for search and summaries; sending email you request; calendar events and calendar lists for scheduling; Drive files for finding and using documents; Contacts for looking up people; and Docs or Sheets for reading, creating, or editing documents and spreadsheets.</p>
      <p>Permissions enable a feature; they do not authorize every possible action. Zoen uses connected data to carry out your instructions and any ongoing tasks you have requested. You can decline permissions or stop using a connection.</p>
      <h2>How your data is used and shared</h2>
      <p>Relevant messages and connected-account content are processed by the agent and its AI providers to understand requests, use tools, and produce responses. Hosted Zoen uses Plow for messaging, agent hosting, and model routing, and Cloudflare for the authorization callback service. Plow's model processors may include OpenAI, Anthropic, and OpenRouter. Connected services receive the API requests needed for your task. Processing can take place outside your country.</p>
      <p>The Google authorization service handles login codes and tokens; it does not fetch your mailbox, calendar, or files. Those API calls run from your agent. Information returned by a tool may become part of the conversation, task history, or saved memory.</p>
      <p>Zoen does not sell Google user data, use it for advertising or credit decisions, or use it to train general-purpose AI models. Google data is shared only to provide the features you request, for security, to meet legal obligations, or in a business transfer with your prior consent. Human access is limited to your specific consent, security needs, legal requirements, or data that has been aggregated and anonymized.</p>
      <p>Zoen's use and transfer of information received from Google APIs will adhere to the <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, including its Limited Use requirements.</p>
      <h2>Storage and protection</h2>
      <p>Connections use HTTPS. Google's app secret stays in the authorization service; refresh credentials are encrypted before being stored with your agent. Short-lived access tokens and other connector credentials are kept in restricted files in the agent's persistent storage. This is cloud processing, not processing confined to your phone.</p>
      <p>Authorization attempts expire after five minutes; acknowledgment or cancellation removes the callback delivery data. Conversation history, memories, task records, and saved credentials persist with the agent until removed or the instance's storage is deleted. Revoking a connection does not erase earlier conversations. Infrastructure providers may retain backups or security records under their own retention policies.</p>
      <p>Installation and token-usage totals may be reported to the AI Worth Using Agent Index. The usage reporter does not upload conversation bodies or Google account contents.</p>
      <h2>Your choices</h2>
      <p>You can revoke Zoen's Google access in <a href="https://myaccount.google.com/connections">your Google Account connections</a>. To request access to, correction, export, or deletion of data held by Zoen, email <a href="mailto:enzo@zoen.space">enzo@zoen.space</a>. We may need to verify that the request comes from the account owner. Deleting Zoen's stored data does not delete your originals in Google or another connected service.</p>
      <p>Self-hosted installations can use different infrastructure or AI providers. Their operator controls that configuration and storage; contact that operator about their processing.</p>
      <h2>Updates and contact</h2>
      <p>Material changes will be communicated before they take effect. New uses of Google data require the appropriate notice and consent. Contact <a href="mailto:enzo@zoen.space">enzo@zoen.space</a> with questions.</p>`,
  },
  terms: {
    label: "Terms of service",
    title: "A little help.",
    accent: "A few ground rules.",
    text: "The terms for using the Zoen iMessage beta and connecting your accounts.",
    article: `<p class="review-note">Draft for review · September 19, 2026</p>
      <h2>The service</h2>
      <p>Zoen is an AI assistant operated by Enzo Tironi. By using this service, you agree to these terms. For questions or support, contact <a href="mailto:enzo@zoen.space">enzo@zoen.space</a>.</p>
      <h2>Your instructions and accounts</h2>
      <p>Only connect accounts and share data you are authorized to use. Keep control of your messaging account and review the account and permissions shown during authorization. You can stop using Zoen or revoke a connection at any time.</p>
      <p>Zoen carries out the tasks you request. A connected account does not by itself instruct Zoen to send messages, spend money, delete files, or make other changes. Give clear instructions and review consequential actions and results.</p>
      <h2>A beta that uses AI</h2>
      <p>Features and availability may change. AI responses can be wrong, and tasks or messages can fail or arrive late. Check important information and results. Zoen is not an emergency service or a substitute for qualified professional advice.</p>
      <p>Google and other providers control their own access rules. During the beta, Google may show an unverified-app notice, limit connections, or require renewed consent. Connecting is your choice.</p>
      <h2>Respect people and services</h2>
      <p>Do not use Zoen for unlawful activity, harassment, spam, unauthorized access, or interference with other people's accounts. Third-party services have their own terms, limits, and charges. Zoen does not remove those obligations.</p>
      <h2>Your data and choices</h2>
      <p>You retain your rights in the data you provide. Zoen processes it to deliver your requested assistance as described in the <a href="/privacy">privacy policy</a>. Contact us to request deletion of stored data or help ending your use of the service.</p>
      <p>Access may be suspended for abuse, security, legal, or operational reasons. Nothing here limits rights or protections you have under applicable law. Material changes to these terms will be communicated before they take effect.</p>`,
  },
};
