# Security and Privacy Notes

EPUB Chapters Studio is a local desktop tool served on loopback. It has no user accounts, public users, payments, cloud database, analytics, or stored personal data.

Security controls in this build:

- The local launcher binds only to `127.0.0.1` or `localhost`.
- Ports `3000` and `3001` are refused by the launcher.
- `.env`, secret-looking files, generated API data, and model caches are ignored by Git.
- Server inputs are validated with Pydantic models and bounded file upload sizes.
- EPUB uploads are limited to EPUB MIME types and a `.epub` extension.
- Render jobs log structured event names and non-sensitive context only.
- The app never stores card data, bank data, account credentials, or payment tokens.

Operational notes:

- Keep EPUB inputs and rendered audiobooks on trusted local storage.
- Keep model cache directories local and out of version control.
- Do not expose the local server through a public tunnel or bind it to a public interface.
- Review any third-party model license terms before using generated audio commercially.
